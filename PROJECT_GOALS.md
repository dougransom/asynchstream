# Project Goal: Native-First Python I/O with Legacy Fallback (`py-native-io`)

## 1. High-Level Objective
Build a high-performance Rust C-extension for Python (`pyo3`) that unifies synchronous and asynchronous stream interfaces under a shared `AsyncIOBase` contract. The package defaults to each operating system's state-of-the-art native completion interface. If the host kernel lacks native ring support, it gracefully wraps CPython's standard built-in I/O operations inside thread pools to provide a fully functional, transparent `AsyncIOBase` interface.

---

## 2. Platform-Specific Engine & Fallback Strategy

| Operating System | Primary Native Engine | Fallback Strategy (Unsupported / Legacy) |
| :--- | :--- | :--- |
| **Linux** | Native `io_uring` ring buffer via `io-uring` crate. | Wraps CPython `io` streams using `asyncio.to_thread` to preserve the `AsyncIOBase` contract (`aread()`, `awrite()`). |
| **Windows** | Native Windows `IoRing` engine (Windows 11 / Server 2022+) via `windows-sys`. | Wraps standard CPython file/socket handles via background executor threads on older Windows builds. |
| **macOS / FreeBSD** | Native `kqueue` engine via `kqueue` / `mio` crates. | Delegates directly to wrapped CPython built-in streams for unsupported operations or older OS builds. |

---

## 3. Architecture & Interface Mechanics

* **Higher-Order Metaclass (`AsyncIOBaseMeta`):** 
  Uses the `if (x) A = B else A = D; f(A)` pattern to resolve target functions dynamically instead of repeating conditional logic. Inspects class definitions during creation and decorates synchronous methods with `asyncio.to_thread` fallbacks if native async routines are absent.
* **Stream Protocol (`AsyncIOBase`):**
  Extends `io.IOBase`. Implements native non-blocking `aread()` / `awrite()` and thread-safe synchronous `read()` / `write()` fallbacks. Calling synchronous `.read()` inside a running event loop raises a `RuntimeError` to enforce async safety.
* **Standard Library Patching (`sitecustomize.py`):**
  Hooks `builtins.open`, `io.open`, `io.FileIO`, and `socket.socket.makefile` on application startup to return `AsyncIOBase`-compliant streams without requiring user code modifications.

---

## 4. Multi-Phase Roadmap

### Phase 1: Linux Core Engine (`io_uring`)
* Build Rust SQE/CQE ring handlers for `IORING_OP_READ`, `IORING_OP_WRITE`, `IORING_OP_ACCEPT`, and `IORING_OP_CONNECT`.
* Implement zero-copy kernel passing using `splice()` ring buffers for pipe-to-socket transfers.
* Verify CPython GIL releases (`py.allow_threads`) during synchronous fallback execution.

### Phase 2: Windows Engine (`IoRing`)
* Bind to Windows 11 / Server 2022+ `IoRing` system calls via `windows-sys` (`CreateIoRing`, `BuildIoRingReadFile`, `SubmitIoRing`).
* Implement pre-registered fixed buffer tables (`BuildIoRingRegisterBuffers`) to eliminate memory page pinning overhead.
* Provide runtime fallback to thread-wrapped standard Windows file handles if running on older OS builds (e.g., Windows 10 / Server 2019).

### Phase 3: macOS & FreeBSD Engine (`kqueue` / POSIX AIO)
* Leverage `kqueue` event filters (`EVFILT_READ` / `EVFILT_WRITE`) for non-blocking stream notification.
* Implement thread-pool offloading for synchronous operations that cannot be mapped cleanly to `kqueue`.

---

## 5. Verification, Compliance & Quality Standards

* **CPython Compliance Suite Integration:** Adapt official tests from CPython's `test_io` and `test_socket` to validate both native engine streams and thread-wrapped legacy fallbacks.
* **Dual-Mode Matrix Testing:** Run test suites across all target platforms in two execution modes:
  1. **Native Mode:** Kernel rings enabled (`io_uring`, Windows `IoRing`, `kqueue`).
  2. **Fallback Mode:** Native rings forcibly disabled via `PY_NATIVE_IO_FORCE_LEGACY=1`.
* **Toolchain Standards:**
  * Build Backend: `maturin`
  * Python Formatting & Linting: `ruff`
  * Strict Type Checking: `mypy` (with `py.typed` marker shipped)
  * Testing: `pytest` + `pytest-asyncio`