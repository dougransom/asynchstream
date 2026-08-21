#[cfg(target_os = "linux")]
use std::collections::HashMap;
#[cfg(target_os = "linux")]
use std::os::unix::io::RawFd;
#[cfg(target_os = "linux")]
use std::sync::atomic::{AtomicU64, Ordering};
#[cfg(target_os = "linux")]
use std::sync::Mutex;

#[cfg(target_os = "linux")]
use io_uring::IoUring;

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
static NEXT_USER_DATA: AtomicU64 = AtomicU64::new(1);

#[cfg(target_os = "linux")]
struct RingState {
    ring: IoUring,
    completed: HashMap<u64, i32>,
}

#[cfg(target_os = "linux")]
thread_local! {
    static THREAD_RING: Mutex<Option<RingState>> = const { Mutex::new(None) };
}

/// Retrieve configured io_uring submission queue depth size.
///
/// Configurable via the `PY_NATIVE_IO_RING_SIZE` environment variable.
/// Must be a positive power of two (e.g., 256, 1024, 4096). Defaults to 1024.
#[cfg(target_os = "linux")]
fn get_configured_ring_size() -> u32 {
    if let Ok(val) = std::env::var("PY_NATIVE_IO_RING_SIZE") {
        if let Ok(parsed) = val.parse::<u32>() {
            if parsed > 0 && parsed.is_power_of_two() {
                return parsed;
            }
        }
    }
    1024
}

/// Execute a closure with a persistent thread-local `io_uring` instance under a thread-local lock.
#[cfg(target_os = "linux")]
fn with_thread_ring_state<F, R>(f: F) -> std::io::Result<R>
where
    F: FnOnce(&mut IoUring, &mut HashMap<u64, i32>) -> std::io::Result<R>,
{
    THREAD_RING.with(|mutex| {
        let mut option = mutex.lock().map_err(|_| std::io::Error::other("Lock error"))?;
        if option.is_none() {
            let entries = get_configured_ring_size();
            let state = RingState {
                ring: IoUring::new(entries)?,
                completed: HashMap::new(),
            };
            *option = Some(state);
        }
        let state = option.as_mut().unwrap();
        f(&mut state.ring, &mut state.completed)
    })
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

#[cfg(target_os = "linux")]
fn poll_completion_for_id(
    ring: &mut IoUring,
    completed: &mut HashMap<u64, i32>,
    my_id: u64,
) -> std::io::Result<i32> {
    loop {
        if let Some(res) = completed.remove(&my_id) {
            return Ok(res);
        }

        {
            let cq = ring.completion();
            for cqe in cq {
                completed.insert(cqe.user_data(), cqe.result());
            }
        }

        if let Some(res) = completed.remove(&my_id) {
            return Ok(res);
        }

        ring.submit_and_wait(1)?;
    }
}

/// Flush all pending submission queue entries to the Linux kernel ring in a single syscall.
#[cfg(target_os = "linux")]
pub fn flush_thread_ring() -> std::io::Result<usize> {
    with_thread_ring_state(|ring, _completed| {
        let submitted = ring.submit()?;
        Ok(submitted)
    })
}

/// Helper function to submit an IORING_OP_READ submission queue entry (SQE)
/// using the persistent thread-local io_uring ring with deferred batch submission.
#[cfg(target_os = "linux")]
pub fn submit_uring_read(fd: RawFd, offset: u64, size: usize) -> std::io::Result<Vec<u8>> {
    use io_uring::{opcode, types};

    let my_id = NEXT_USER_DATA.fetch_add(1, Ordering::Relaxed);
    let mut buf = vec![0u8; size];

    with_thread_ring_state(|ring, _completed| {
        let read_e = opcode::Read::new(types::Fd(fd), buf.as_mut_ptr(), size as u32)
            .offset(offset)
            .build()
            .user_data(my_id);

        unsafe {
            if ring.submission().push(&read_e).is_err() {
                ring.submit_and_wait(1)?;
                ring.submission()
                    .push(&read_e)
                    .map_err(|_| std::io::Error::other("SQ queue full"))?;
            }
        }

        Ok(())
    })?;

    let ret = with_thread_ring_state(|ring, completed| {
        poll_completion_for_id(ring, completed, my_id)
    })?;

    if ret < 0 {
        return Err(std::io::Error::from_raw_os_error(-ret));
    }
    buf.truncate(ret as usize);
    Ok(buf)
}

/// Helper function to submit an IORING_OP_WRITE submission queue entry (SQE)
/// using the persistent thread-local io_uring ring with deferred batch submission.
#[cfg(target_os = "linux")]
pub fn submit_uring_write(fd: RawFd, bytes: &[u8]) -> std::io::Result<usize> {
    use io_uring::{opcode, types};

    let my_id = NEXT_USER_DATA.fetch_add(1, Ordering::Relaxed);

    with_thread_ring_state(|ring, _completed| {
        let write_e = opcode::Write::new(types::Fd(fd), bytes.as_ptr(), bytes.len() as u32)
            .offset(u64::MAX)
            .build()
            .user_data(my_id);

        unsafe {
            if ring.submission().push(&write_e).is_err() {
                ring.submit_and_wait(1)?;
                ring.submission()
                    .push(&write_e)
                    .map_err(|_| std::io::Error::other("SQ queue full"))?;
            }
        }

        Ok(())
    })?;

    let ret = with_thread_ring_state(|ring, completed| {
        poll_completion_for_id(ring, completed, my_id)
    })?;

    if ret < 0 {
        return Err(std::io::Error::from_raw_os_error(-ret));
    }
    Ok(ret as usize)
}

/// Helper function to submit an IORING_OP_SPLICE submission queue entry (SQE)
/// to perform kernel zero-copy transfer between file descriptors using thread-local ring.
#[cfg(target_os = "linux")]
pub fn submit_uring_splice(
    fd_in: RawFd,
    fd_out: RawFd,
    size: usize,
) -> std::io::Result<usize> {
    use io_uring::{opcode, types};

    let my_id = NEXT_USER_DATA.fetch_add(1, Ordering::Relaxed);

    with_thread_ring_state(|ring, _completed| {
        let splice_e = opcode::Splice::new(
            types::Fd(fd_in),
            -1i64,
            types::Fd(fd_out),
            -1i64,
            size as u32,
        )
        .build()
        .user_data(my_id);

        unsafe {
            if ring.submission().push(&splice_e).is_err() {
                ring.submit_and_wait(1)?;
                ring.submission()
                    .push(&splice_e)
                    .map_err(|_| std::io::Error::other("SQ queue full"))?;
            }
        }

        Ok(())
    })?;

    let ret = with_thread_ring_state(|ring, completed| {
        poll_completion_for_id(ring, completed, my_id)
    })?;

    if ret < 0 {
        return Err(std::io::Error::from_raw_os_error(-ret));
    }
    Ok(ret as usize)
}
