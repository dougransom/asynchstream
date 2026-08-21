/// macOS / Darwin kqueue completion engine stub.
#[cfg(target_os = "macos")]
pub fn is_macos_kqueue_supported() -> bool {
    true
}
