use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use pyo3_asyncio::tokio::future_into_py;

#[pyclass(subclass)]
pub struct NativeFileIO {
    handle: usize,
}

#[pymethods]
impl NativeFileIO {
    #[new]
    fn new(path: &str, _mode: &str) -> PyResult<Self> {
        Ok(NativeFileIO { handle: 0 })
    }

    fn aread<'p>(&self, py: Python<'p>, size: usize) -> PyResult<&'p PyAny> {
        future_into_py(py, async move {
            Ok(vec![0u8; size])
        })
    }

    fn read(&self, py: Python, size: usize) -> PyResult<Vec<u8>> {
        py.allow_threads(|| Ok(vec![0u8; size]))
    }
}

#[pyfunction]
fn is_kernel_ring_supported() -> bool {
    if std::env::var("PY_NATIVE_IO_FORCE_LEGACY").is_ok() {
        return false;
    }
    #[cfg(target_os = "linux")] { io_uring::IoUring::new(1).is_ok() }
    #[cfg(target_os = "windows")] { true }
    #[cfg(target_os = "macos")] { true }
    #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))] { false }
}

#[pymodule]
fn _ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_kernel_ring_supported, m)?)?;
    m.add_class::<NativeFileIO>()?;
    Ok(())
}