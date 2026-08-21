pub mod linux;
pub mod macos;
pub mod windows;

/// Query whether the host OS kernel supports secure native kernel completion rings.
pub fn is_kernel_ring_supported() -> bool {
    if std::env::var("PY_NATIVE_IO_FORCE_LEGACY").is_ok() {
        return false;
    }
    #[cfg(target_os = "linux")]
    {
        linux::is_linux_uring_secure_and_supported()
    }
    #[cfg(target_os = "windows")]
    {
        windows::is_windows_ioring_supported()
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
