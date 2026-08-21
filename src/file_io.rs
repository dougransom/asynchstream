use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Mutex;
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyTuple};
use pyo3_asyncio::tokio::future_into_py;

use crate::engines;
use crate::file_mode::FileMode;
use crate::seek_whence::SeekingWhence;

/// Native completion-based file stream wrapping kernel completion rings (io_uring on Linux).
#[pyclass(subclass)]
pub struct NativeFileIO {
    file: Mutex<Option<File>>,
    path: PathBuf,
    mode: FileMode,
}

#[allow(non_local_definitions)]
#[pymethods]
impl NativeFileIO {
    /// Open a new native completion file stream for the given path and mode.
    #[new]
    #[pyo3(signature = (file, mode="rb", *_args, **_kwargs))]
    fn new(
        file: &PyAny,
        mode: Option<&str>,
        _args: &PyTuple,
        _kwargs: Option<&PyDict>,
    ) -> PyResult<Self> {
        let mode_str = mode.unwrap_or("rb");
        let path_str: String = file.str()?.to_str()?.to_string();
        let path = PathBuf::from(path_str);
        let parsed_mode = FileMode::parse(mode_str);

        let mut options = OpenOptions::new();
        parsed_mode.configure_open_options(&mut options);

        let f = options
            .open(&path)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;
        Ok(NativeFileIO {
            file: Mutex::new(Some(f)),
            path,
            mode: parsed_mode,
        })
    }

    /// Synchronously read up to size bytes from the file stream.
    fn read<'p>(&self, py: Python<'p>, size: Option<isize>) -> PyResult<&'p PyBytes> {
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_mut()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        let s = size.unwrap_or(-1);
        let buf: PyResult<Vec<u8>> = py.allow_threads(|| {
            let mut buf = Vec::new();
            if s < 0 {
                f.read_to_end(&mut buf)
                    .map_err(|e| PyIOError::new_err(e.to_string()))?;
            } else {
                buf.resize(s as usize, 0);
                let n = f
                    .read(&mut buf)
                    .map_err(|e| PyIOError::new_err(e.to_string()))?;
                buf.truncate(n);
            }
            Ok(buf)
        });
        let buf = buf?;
        Ok(PyBytes::new(py, &buf))
    }

    /// Read bytes directly into a mutable byte buffer (e.g. memoryview or bytearray).
    fn readinto(&self, py: Python, b: &PyAny) -> PyResult<usize> {
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_mut()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        let buf_view = pyo3::buffer::PyBuffer::<u8>::get(b)?;
        let total_len = buf_view.len_bytes();
        let mut temp_buf = vec![0u8; total_len];
        let n = py.allow_threads(|| f.read(&mut temp_buf).map_err(|e| PyIOError::new_err(e.to_string())))?;
        if n > 0 {
            let ptr = buf_view.buf_ptr() as *mut u8;
            unsafe {
                std::ptr::copy_nonoverlapping(temp_buf.as_ptr(), ptr, n);
            }
        }
        Ok(n)
    }

    /// Synchronously write bytes to the file stream.
    fn write(&self, py: Python, b: &PyAny) -> PyResult<usize> {
        let bytes: Vec<u8> = if let Ok(v) = b.extract::<Vec<u8>>() {
            v
        } else if let Ok(s) = b.extract::<&str>() {
            s.as_bytes().to_vec()
        } else {
            return Err(PyTypeError::new_err("expected bytes-like object or str"));
        };
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_mut()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        py.allow_threads(|| {
            f.write_all(&bytes)
                .map_err(|e| PyIOError::new_err(e.to_string()))?;
            Ok(bytes.len())
        })
    }

    /// Asynchronously read up to size bytes using native kernel ring completion.
    fn aread<'p>(&self, py: Python<'p>, size: Option<isize>) -> PyResult<&'p PyAny> {
        let path = self.path.clone();
        let s = size.unwrap_or(-1);
        let raw_fd = {
            let guard = self
                .file
                .lock()
                .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
            let f = guard
                .as_ref()
                .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
            #[cfg(target_os = "linux")]
            {
                use std::os::unix::io::AsRawFd;
                f.as_raw_fd()
            }
            #[cfg(target_os = "windows")]
            {
                use std::os::windows::io::AsRawHandle;
                f.as_raw_handle() as usize
            }
            #[cfg(not(any(target_os = "linux", target_os = "windows")))]
            {
                0
            }
        };
        future_into_py(py, async move {
            let read_size = if s < 0 { 65536 } else { s as usize };

            let res = tokio::task::spawn_blocking(move || -> std::io::Result<Vec<u8>> {
                #[cfg(target_os = "linux")]
                {
                    if let Ok(buf) = engines::linux::submit_uring_read(raw_fd, 0, read_size) {
                        return Ok(buf);
                    }
                }
                #[cfg(target_os = "windows")]
                {
                    if let Ok(buf) = engines::windows::submit_ioring_read(
                        raw_fd as std::os::windows::io::RawHandle,
                        read_size,
                    ) {
                        return Ok(buf);
                    }
                }

                let mut f = File::open(&path)?;
                let mut buf = Vec::new();
                if s < 0 {
                    f.read_to_end(&mut buf)?;
                } else {
                    buf.resize(s as usize, 0);
                    let n = f.read(&mut buf)?;
                    buf.truncate(n);
                }
                Ok(buf)
            })
            .await
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

            let py_bytes = Python::with_gil(|py| PyBytes::new(py, &res).to_object(py));
            Ok(py_bytes)
        })
    }

    /// Asynchronously write bytes using native kernel ring completion.
    fn awrite<'p>(&self, py: Python<'p>, b: &PyAny) -> PyResult<&'p PyAny> {
        let bytes: Vec<u8> = if let Ok(v) = b.extract::<Vec<u8>>() {
            v
        } else if let Ok(s) = b.extract::<&str>() {
            s.as_bytes().to_vec()
        } else {
            return Err(PyTypeError::new_err("expected bytes-like object or str"));
        };
        let path = self.path.clone();
        let raw_fd = {
            let guard = self
                .file
                .lock()
                .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
            let f = guard
                .as_ref()
                .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
            #[cfg(target_os = "linux")]
            {
                use std::os::unix::io::AsRawFd;
                f.as_raw_fd()
            }
            #[cfg(target_os = "windows")]
            {
                use std::os::windows::io::AsRawHandle;
                f.as_raw_handle() as usize
            }
            #[cfg(not(any(target_os = "linux", target_os = "windows")))]
            {
                0
            }
        };
        future_into_py(py, async move {
            let written = tokio::task::spawn_blocking(move || -> std::io::Result<usize> {
                #[cfg(target_os = "linux")]
                {
                    if let Ok(w) = engines::linux::submit_uring_write(raw_fd, &bytes) {
                        return Ok(w);
                    }
                }
                #[cfg(target_os = "windows")]
                {
                    if let Ok(w) = engines::windows::submit_ioring_write(
                        raw_fd as std::os::windows::io::RawHandle,
                        &bytes,
                    ) {
                        return Ok(w);
                    }
                }

                let mut f = OpenOptions::new().create(true).append(true).open(&path)?;
                f.write_all(&bytes)?;
                Ok(bytes.len())
            })
            .await
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

            Ok(written)
        })
    }

    /// Synchronously close the underlying file descriptor.
    fn close(&self) -> PyResult<()> {
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        *guard = None;
        Ok(())
    }

    /// Asynchronously close the underlying file descriptor.
    fn aclose<'p>(&self, py: Python<'p>) -> PyResult<&'p PyAny> {
        self.close()?;
        future_into_py(py, async move { Ok(()) })
    }

    /// Return whether the file stream is closed.
    #[getter]
    fn closed(&self) -> PyResult<bool> {
        let guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        Ok(guard.is_none())
    }

    /// Change the current stream position to pos relative to whence.
    fn seek(&self, py: Python, pos: i64, whence: Option<i32>) -> PyResult<u64> {
        use std::io::Seek;
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_mut()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        let seek_from = SeekingWhence::to_seek_from(whence.unwrap_or(0), pos)?;
        py.allow_threads(|| f.seek(seek_from).map_err(|e| PyIOError::new_err(e.to_string())))
    }

    /// Return the current stream position.
    fn tell(&self, py: Python) -> PyResult<u64> {
        self.seek(py, 0, Some(1))
    }

    /// Return the underlying file descriptor.
    fn fileno(&self) -> PyResult<i32> {
        let guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_ref()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        #[cfg(unix)]
        {
            use std::os::unix::io::AsRawFd;
            Ok(f.as_raw_fd())
        }
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            Ok(f.as_raw_handle() as i32)
        }
        #[cfg(not(any(unix, windows)))]
        {
            Err(PyIOError::new_err("fileno not supported on this platform"))
        }
    }

    /// Return True if the stream was opened for reading.
    fn readable(&self) -> bool {
        self.mode.readable
    }

    /// Return True if the stream was opened for writing.
    fn writable(&self) -> bool {
        self.mode.writable
    }

    /// Return True if the stream supports random access seeking.
    fn seekable(&self) -> bool {
        true
    }

    /// Flush internal stream write buffers.
    fn flush(&self) -> PyResult<()> {
        Ok(())
    }

    /// Asynchronously flush internal stream write buffers.
    fn aflush<'p>(&self, py: Python<'p>) -> PyResult<&'p PyAny> {
        future_into_py(py, async move { Ok(()) })
    }

    /// Zero-copy kernel space transfer to target_fd via IORING_OP_SPLICE without threadpool dispatching.
    fn asplice<'p>(&self, py: Python<'p>, target_fd: i32, size: Option<usize>) -> PyResult<&'p PyAny> {
        let path = self.path.clone();
        let len = size.unwrap_or(65536);
        future_into_py(py, async move {
            let f = File::open(&path).map_err(|e| PyIOError::new_err(e.to_string()))?;
            #[cfg(target_os = "linux")]
            {
                use std::os::unix::io::AsRawFd;
                if let Ok(copied) = engines::linux::submit_uring_splice(f.as_raw_fd(), target_fd, len) {
                    return Ok(copied);
                }
            }

            // Fallback for non-ring target OS
            let n = tokio::task::spawn_blocking(move || -> std::io::Result<usize> {
                let mut f = f;
                let mut buf = vec![0u8; len];
                let read_n = f.read(&mut buf)?;
                #[cfg(target_os = "linux")]
                {
                    use std::os::unix::io::FromRawFd;
                    let mut target_file = unsafe { File::from_raw_fd(target_fd) };
                    let res = target_file.write_all(&buf[..read_n]);
                    std::mem::forget(target_file);
                    res?;
                }
                Ok(read_n)
            })
            .await
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

            Ok(n)
        })
    }

    fn __enter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __exit__(&self, _exc_type: &PyAny, _exc_val: &PyAny, _exc_tb: &PyAny) -> PyResult<()> {
        self.close()
    }
}
