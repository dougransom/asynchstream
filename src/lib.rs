#![allow(non_local_definitions)]

use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Mutex;
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyTuple};
use pyo3_asyncio::tokio::future_into_py;

#[pyclass(subclass)]
pub struct NativeFileIO {
    file: Mutex<Option<File>>,
    path: PathBuf,
}

#[allow(non_local_definitions)]
#[pymethods]
impl NativeFileIO {
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

        let mut options = OpenOptions::new();
        let is_write = mode_str.contains('w');
        if is_write || mode_str.contains('a') {
            let set_write_mode: fn(&mut OpenOptions, bool) -> &mut OpenOptions = if is_write {
                OpenOptions::truncate
            } else {
                OpenOptions::append
            };
            set_write_mode(options.write(true).create(true), true);
            if mode_str.contains('+') {
                options.read(true);
            }
        } else {
            options.read(true);
            if mode_str.contains('+') {
                options.write(true);
            }
        }

        let f = options
            .open(&path)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;
        Ok(NativeFileIO {
            file: Mutex::new(Some(f)),
            path,
        })
    }

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

    fn aread<'p>(&self, py: Python<'p>, size: Option<isize>) -> PyResult<&'p PyAny> {
        let path = self.path.clone();
        let s = size.unwrap_or(-1);
        future_into_py(py, async move {
            let buf = tokio::task::spawn_blocking(move || -> std::io::Result<Vec<u8>> {
                let f = File::open(&path)?;
                let read_size = if s < 0 { 65536 } else { s as usize };
                #[cfg(target_os = "linux")]
                {
                    use std::os::unix::io::AsRawFd;
                    if let Ok(res) = submit_uring_read(f.as_raw_fd(), read_size) {
                        return Ok(res);
                    }
                }
                let mut f = f;
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
            let py_bytes = Python::with_gil(|py| PyBytes::new(py, &buf).to_object(py));
            Ok(py_bytes)
        })
    }

    fn awrite<'p>(&self, py: Python<'p>, b: &PyAny) -> PyResult<&'p PyAny> {
        let bytes: Vec<u8> = if let Ok(v) = b.extract::<Vec<u8>>() {
            v
        } else if let Ok(s) = b.extract::<&str>() {
            s.as_bytes().to_vec()
        } else {
            return Err(PyTypeError::new_err("expected bytes-like object or str"));
        };
        let path = self.path.clone();
        future_into_py(py, async move {
            let len = tokio::task::spawn_blocking(move || -> std::io::Result<usize> {
                let f = OpenOptions::new().create(true).append(true).open(&path)?;
                #[cfg(target_os = "linux")]
                {
                    use std::os::unix::io::AsRawFd;
                    if let Ok(written) = submit_uring_write(f.as_raw_fd(), &bytes) {
                        return Ok(written);
                    }
                }
                let mut f = f;
                f.write_all(&bytes)?;
                Ok(bytes.len())
            })
            .await
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?
            .map_err(|e| PyIOError::new_err(e.to_string()))?;
            Ok(len)
        })
    }

    fn close(&self) -> PyResult<()> {
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        *guard = None;
        Ok(())
    }

    fn aclose<'p>(&self, py: Python<'p>) -> PyResult<&'p PyAny> {
        self.close()?;
        future_into_py(py, async move { Ok(()) })
    }

    #[getter]
    fn closed(&self) -> PyResult<bool> {
        let guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        Ok(guard.is_none())
    }

    fn seek(&self, py: Python, pos: i64, whence: Option<i32>) -> PyResult<u64> {
        use std::io::Seek;
        let mut guard = self
            .file
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Lock error"))?;
        let f = guard
            .as_mut()
            .ok_or_else(|| PyIOError::new_err("I/O operation on closed file."))?;
        let w = match whence.unwrap_or(0) {
            0 => std::io::SeekFrom::Start(pos as u64),
            1 => std::io::SeekFrom::Current(pos),
            2 => std::io::SeekFrom::End(pos),
            _ => return Err(pyo3::exceptions::PyValueError::new_err("invalid whence")),
        };
        py.allow_threads(|| f.seek(w).map_err(|e| PyIOError::new_err(e.to_string())))
    }

    fn tell(&self, py: Python) -> PyResult<u64> {
        self.seek(py, 0, Some(1))
    }

    fn readable(&self) -> bool {
        true
    }

    fn writable(&self) -> bool {
        true
    }

    fn seekable(&self) -> bool {
        true
    }

    fn flush(&self) -> PyResult<()> {
        Ok(())
    }

    fn aflush<'p>(&self, py: Python<'p>) -> PyResult<&'p PyAny> {
        future_into_py(py, async move { Ok(()) })
    }

    fn __enter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __exit__(&self, _exc_type: &PyAny, _exc_val: &PyAny, _exc_tb: &PyAny) -> PyResult<()> {
        self.close()
    }
}

#[pyfunction]
fn is_kernel_ring_supported() -> bool {
    if std::env::var("PY_NATIVE_IO_FORCE_LEGACY").is_ok() {
        return false;
    }
    #[cfg(target_os = "linux")]
    {
        io_uring::IoUring::new(1).is_ok()
    }
    #[cfg(target_os = "windows")]
    {
        true
    }
    #[cfg(target_os = "macos")]
    {
        true
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
    {
        false
    }
}

#[pymodule]
fn _ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_kernel_ring_supported, m)?)?;
    m.add_class::<NativeFileIO>()?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn submit_uring_read(fd: std::os::unix::io::RawFd, size: usize) -> std::io::Result<Vec<u8>> {
    use io_uring::{opcode, types, IoUring};

    let mut ring = IoUring::new(8)?;
    let mut buf = vec![0u8; size];
    let read_e = opcode::Read::new(types::Fd(fd), buf.as_mut_ptr(), size as u32)
        .offset(0)
        .build()
        .user_data(0x01);

    unsafe {
        ring.submission()
            .push(&read_e)
            .map_err(|_| std::io::Error::other("SQ queue full"))?;
    }

    ring.submit_and_wait(1)?;

    let cqe = ring
        .completion()
        .next()
        .ok_or_else(|| std::io::Error::other("No CQE"))?;

    let ret = cqe.result();
    if ret < 0 {
        return Err(std::io::Error::from_raw_os_error(-ret));
    }
    buf.truncate(ret as usize);
    Ok(buf)
}

#[cfg(target_os = "linux")]
fn submit_uring_write(fd: std::os::unix::io::RawFd, bytes: &[u8]) -> std::io::Result<usize> {
    use io_uring::{opcode, types, IoUring};

    let mut ring = IoUring::new(8)?;
    let write_e = opcode::Write::new(types::Fd(fd), bytes.as_ptr(), bytes.len() as u32)
        .offset(u64::MAX)
        .build()
        .user_data(0x02);

    unsafe {
        ring.submission()
            .push(&write_e)
            .map_err(|_| std::io::Error::other("SQ queue full"))?;
    }

    ring.submit_and_wait(1)?;

    let cqe = ring
        .completion()
        .next()
        .ok_or_else(|| std::io::Error::other("No CQE"))?;

    let ret = cqe.result();
    if ret < 0 {
        return Err(std::io::Error::from_raw_os_error(-ret));
    }
    Ok(ret as usize)
}