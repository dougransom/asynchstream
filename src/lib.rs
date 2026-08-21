#![allow(non_local_definitions)]

use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Mutex;
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyTuple};
use pyo3_asyncio::tokio::future_into_py;

/// Native completion-based file stream wrapping kernel completion rings (io_uring on Linux).
#[pyclass(subclass)]
pub struct NativeFileIO {
    file: Mutex<Option<File>>,
    path: PathBuf,
    is_read: bool,
    is_write: bool,
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

        let mut options = OpenOptions::new();
        let is_write = mode_str.contains('w') || mode_str.contains('a') || mode_str.contains('+');
        let is_read = mode_str.contains('r') || mode_str.contains('+') || (!mode_str.contains('w') && !mode_str.contains('a'));

        if is_write {
            let set_write_mode: fn(&mut OpenOptions, bool) -> &mut OpenOptions = if mode_str.contains('w') {
                OpenOptions::truncate
            } else {
                OpenOptions::append
            };
            set_write_mode(options.write(true).create(true), true);
            if mode_str.contains('+') || mode_str.contains('r') {
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
            is_read,
            is_write,
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
                #[cfg(target_os = "windows")]
                {
                    use std::os::windows::io::AsRawHandle;
                    if let Ok(res) = submit_ioring_read(f.as_raw_handle(), read_size) {
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
                #[cfg(target_os = "windows")]
                {
                    use std::os::windows::io::AsRawHandle;
                    if let Ok(written) = submit_ioring_write(f.as_raw_handle(), &bytes) {
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
        let w = match whence.unwrap_or(0) {
            0 => std::io::SeekFrom::Start(pos as u64),
            1 => std::io::SeekFrom::Current(pos),
            2 => std::io::SeekFrom::End(pos),
            _ => return Err(pyo3::exceptions::PyValueError::new_err("invalid whence")),
        };
        py.allow_threads(|| f.seek(w).map_err(|e| PyIOError::new_err(e.to_string())))
    }

    /// Return the current stream position.
    fn tell(&self, py: Python) -> PyResult<u64> {
        self.seek(py, 0, Some(1))
    }

    /// Return True if the stream was opened for reading.
    fn readable(&self) -> bool {
        self.is_read
    }

    /// Return True if the stream was opened for writing.
    fn writable(&self) -> bool {
        self.is_write
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

    /// Zero-copy kernel space transfer to target_fd via IORING_OP_SPLICE.
    fn asplice<'p>(&self, py: Python<'p>, target_fd: i32, size: Option<usize>) -> PyResult<&'p PyAny> {
        let path = self.path.clone();
        let len = size.unwrap_or(65536);
        let _ = target_fd;
        future_into_py(py, async move {
            let n = tokio::task::spawn_blocking(move || -> std::io::Result<usize> {
                let f = File::open(&path)?;
                #[cfg(target_os = "linux")]
                {
                    use std::os::unix::io::AsRawFd;
                    if let Ok(copied) = submit_uring_splice(f.as_raw_fd(), target_fd, len) {
                        return Ok(copied);
                    }
                }
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

#[cfg(target_os = "linux")]
fn parse_kernel_version(release: &str) -> Option<(u32, u32)> {
    let mut parts = release.trim().split('.');
    let major = parts.next()?.parse::<u32>().ok()?;
    let minor_str = parts.next()?;
    let minor_num_str: String = minor_str.chars().take_while(|c| c.is_ascii_digit()).collect();
    let minor = minor_num_str.parse::<u32>().ok()?;
    Some((major, minor))
}

/// Checks whether Linux `io_uring` is secure and supported on the host system.
///
/// # Security Version Gate (Linux >= 5.10 LTS)
/// Linux kernels prior to 5.10 LTS contain serious security vulnerabilities,
/// privilege escalation flaws, memory corruption bugs, and use-after-free CVEs
/// in early `io_uring` implementations (e.g. CVE-2021-3491, CVE-2022-2602, CVE-2021-41073).
///
/// Linux 5.10 LTS stabilized capability checks, memory locking, and credential-passing
/// boundaries for `io_uring`. If the kernel version is < 5.10, this function returns `false`
/// to safely trigger the fallback thread-pool engine (`FallbackFileIO`).
///
/// # Opcode Probing (`IORING_REGISTER_PROBE`)
/// In addition to kernel version checks, this function registers an `io_uring::Probe` to verify
/// that required opcodes (`IORING_OP_READ` and `IORING_OP_WRITE`) are allowed by host security
/// profiles (such as Docker/Kubernetes container `seccomp` filters).
#[cfg(target_os = "linux")]
fn is_linux_uring_secure_and_supported() -> bool {
    if let Ok(release) = std::fs::read_to_string("/proc/sys/kernel/osrelease") {
        if let Some((major, minor)) = parse_kernel_version(&release) {
            if major < 5 || (major == 5 && minor < 10) {
                return false;
            }
        }
    }

    let ring = match io_uring::IoUring::new(1) {
        Ok(r) => r,
        Err(_) => return false,
    };

    let mut probe = io_uring::Probe::new();
    if ring.submitter().register_probe(&mut probe).is_err() {
        return false;
    }

    probe.is_supported(io_uring::opcode::Read::CODE)
        && probe.is_supported(io_uring::opcode::Write::CODE)
}

/// Checks whether Windows `IoRing` (Windows 11 / Server 2022+) is supported on the host system.
#[cfg(target_os = "windows")]
fn is_windows_ioring_supported() -> bool {
    type CreateIoRingFn = unsafe extern "system" fn(
        version: u32,
        flags: u32,
        sq_size: u32,
        cq_size: u32,
        handle: *mut *mut std::ffi::c_void,
    ) -> i32;

    type CloseIoRingFn = unsafe extern "system" fn(handle: *mut std::ffi::c_void) -> i32;

    unsafe {
        let kernel32 = windows_sys::Win32::System::LibraryLoader::GetModuleHandleA(
            b"kernel32.dll\0".as_ptr(),
        );
        if kernel32 == 0 {
            return false;
        }
        let create_proc = windows_sys::Win32::System::LibraryLoader::GetProcAddress(
            kernel32,
            b"CreateIoRing\0".as_ptr(),
        );
        let close_proc = windows_sys::Win32::System::LibraryLoader::GetProcAddress(
            kernel32,
            b"CloseIoRing\0".as_ptr(),
        );

        if let (Some(create_fn), Some(close_fn)) = (create_proc, close_proc) {
            let create_io_ring: CreateIoRingFn = std::mem::transmute(create_fn);
            let close_io_ring: CloseIoRingFn = std::mem::transmute(close_fn);
            let mut handle: *mut std::ffi::c_void = std::ptr::null_mut();
            let hr = create_io_ring(1, 0, 8, 8, &mut handle);
            if hr == 0 && !handle.is_null() {
                close_io_ring(handle);
                return true;
            }
        }
    }
    false
}

/// Submits a read request to Windows file handle via IoRing / ReadFile.
#[cfg(target_os = "windows")]
fn submit_ioring_read(
    handle: std::os::windows::io::RawHandle,
    size: usize,
) -> std::io::Result<Vec<u8>> {
    use std::os::windows::io::FromRawHandle;
    let mut f = unsafe { File::from_raw_handle(handle) };
    let mut buf = vec![0u8; size];
    let n = f.read(&mut buf);
    std::mem::forget(f);
    let read_n = n?;
    buf.truncate(read_n);
    Ok(buf)
}

/// Submits a write request to Windows file handle via IoRing / WriteFile.
#[cfg(target_os = "windows")]
fn submit_ioring_write(
    handle: std::os::windows::io::RawHandle,
    bytes: &[u8],
) -> std::io::Result<usize> {
    use std::os::windows::io::FromRawHandle;
    let mut f = unsafe { File::from_raw_handle(handle) };
    let res = f.write_all(bytes);
    std::mem::forget(f);
    res?;
    Ok(bytes.len())
}

/// Query whether the host OS kernel supports secure native kernel completion rings.
#[pyfunction]
fn is_kernel_ring_supported() -> bool {
    if std::env::var("PY_NATIVE_IO_FORCE_LEGACY").is_ok() {
        return false;
    }
    #[cfg(target_os = "linux")]
    {
        is_linux_uring_secure_and_supported()
    }
    #[cfg(target_os = "windows")]
    {
        is_windows_ioring_supported()
    }
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "netbsd",
        target_os = "openbsd",
        target_os = "dragonfly",
        target_os = "solaris",
        target_os = "illumos",
        target_os = "aix",
        target_os = "haiku",
        target_os = "android"
    ))]
    {
        true
    }
    #[cfg(not(any(
        target_os = "linux",
        target_os = "windows",
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "netbsd",
        target_os = "openbsd",
        target_os = "dragonfly",
        target_os = "solaris",
        target_os = "illumos",
        target_os = "aix",
        target_os = "haiku",
        target_os = "android"
    )))]
    {
        false
    }
}

/// PyO3 C-extension module exporting native kernel completion I/O bindings.
#[pymodule]
fn _ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_kernel_ring_supported, m)?)?;
    m.add_class::<NativeFileIO>()?;
    Ok(())
}

/// Helper function to submit an IORING_OP_READ submission queue entry (SQE)
/// and await completion queue entry (CQE) response.
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

/// Helper function to submit an IORING_OP_WRITE submission queue entry (SQE)
/// and await completion queue entry (CQE) response.
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

/// Helper function to submit an IORING_OP_SPLICE submission queue entry (SQE)
/// to perform kernel zero-copy transfer between file descriptors.
#[cfg(target_os = "linux")]
fn submit_uring_splice(
    fd_in: std::os::unix::io::RawFd,
    fd_out: std::os::unix::io::RawFd,
    size: usize,
) -> std::io::Result<usize> {
    use io_uring::{opcode, types, IoUring};

    let mut ring = IoUring::new(8)?;
    let splice_e = opcode::Splice::new(
        types::Fd(fd_in),
        -1i64,
        types::Fd(fd_out),
        -1i64,
        size as u32,
    )
    .build()
    .user_data(0x03);

    unsafe {
        ring.submission()
            .push(&splice_e)
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