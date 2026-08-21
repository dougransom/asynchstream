#[cfg(target_os = "windows")]
use std::fs::File;
#[cfg(target_os = "windows")]
use std::io::{Read, Write};

/// Checks whether Windows `IoRing` (Windows 11 / Server 2022+) is supported on the host system.
#[cfg(target_os = "windows")]
pub fn is_windows_ioring_supported() -> bool {
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
pub fn submit_ioring_read(
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
pub fn submit_ioring_write(
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
