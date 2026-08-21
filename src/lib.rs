#![allow(non_local_definitions)]

pub mod engines;
pub mod file_io;
pub mod file_mode;
pub mod seek_whence;

use pyo3::prelude::*;

/// Query whether the host OS kernel supports secure native kernel completion rings.
#[pyfunction]
fn is_kernel_ring_supported() -> bool {
    engines::is_kernel_ring_supported()
}

/// PyO3 C-extension module exporting native kernel completion I/O bindings.
#[pymodule]
fn _ext(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_kernel_ring_supported, m)?)?;
    m.add_class::<file_io::NativeFileIO>()?;
    Ok(())
}