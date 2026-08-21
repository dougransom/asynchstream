use std::io::SeekFrom;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Strongly typed stream seeking position relative to origin.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeekingWhence {
    Start = 0,
    Current = 1,
    End = 2,
}

impl SeekingWhence {
    /// Convert integer whence indicator and byte offset to std::io::SeekFrom.
    pub fn to_seek_from(whence: i32, pos: i64) -> PyResult<SeekFrom> {
        match whence {
            0 => Ok(SeekFrom::Start(pos as u64)),
            1 => Ok(SeekFrom::Current(pos)),
            2 => Ok(SeekFrom::End(pos)),
            _ => Err(PyValueError::new_err("invalid whence")),
        }
    }
}
