#[cfg(target_os = "linux")]
use std::os::unix::io::RawFd;

/// Strongly typed io_uring opcode user data identifiers.
#[repr(u64)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RingOpcode {
    Read = 0x01,
    Write = 0x02,
    Splice = 0x03,
}

impl RingOpcode {
    pub fn user_data(self) -> u64 {
        self as u64
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
#[cfg(target_os = "linux")]
pub fn is_linux_uring_secure_and_supported() -> bool {
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

/// Helper function to submit an IORING_OP_READ submission queue entry (SQE)
/// and await completion queue entry (CQE) response.
#[cfg(target_os = "linux")]
pub fn submit_uring_read(fd: RawFd, size: usize) -> std::io::Result<Vec<u8>> {
    use io_uring::{opcode, types, IoUring};

    let mut ring = IoUring::new(8)?;
    let mut buf = vec![0u8; size];
    let read_e = opcode::Read::new(types::Fd(fd), buf.as_mut_ptr(), size as u32)
        .offset(0)
        .build()
        .user_data(RingOpcode::Read.user_data());

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
pub fn submit_uring_write(fd: RawFd, bytes: &[u8]) -> std::io::Result<usize> {
    use io_uring::{opcode, types, IoUring};

    let mut ring = IoUring::new(8)?;
    let write_e = opcode::Write::new(types::Fd(fd), bytes.as_ptr(), bytes.len() as u32)
        .offset(u64::MAX)
        .build()
        .user_data(RingOpcode::Write.user_data());

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
pub fn submit_uring_splice(
    fd_in: RawFd,
    fd_out: RawFd,
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
    .user_data(RingOpcode::Splice.user_data());

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
