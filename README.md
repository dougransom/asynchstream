
# `py-native-io`

Native-first asynchronous kernel I/O for Python targeting **`io_uring`** (Linux), **`IoRing`** (Windows 11 / Server 2022+), and **`kqueue`** (macOS/BSD), with automatic thread-pool fallbacks on legacy kernels.

---

## **1. Core Concepts & Architecture**

### **Unified Stream Contract (`AsyncIOBase` & `AsyncIOStream`)**
`py-native-io` introduces `AsyncIOBase` (inheriting from `io.IOBase`), which bridges synchronous and asynchronous stream APIs on a single stream object. It also provides the `@runtime_checkable` `AsyncIOStream` protocol for static type checking in `mypy`.

```python
import py_native_io
from py_native_io import AsyncIOStream


async def main():
    # Opens native io_uring / Windows IoRing stream (satisfies AsyncIOStream and io.IOBase)
    f = open("data.bin", "rb")
    assert isinstance(f, AsyncIOStream)

    # Non-blocking kernel ring read
    chunk_a = await f.aread(1024)

    # Synchronous read on the same stream object
    chunk_b = f.read(512)
    f.close()
```

### **Higher-Order Metaclass Mechanics (`AsyncIOBaseMeta`)**
The `AsyncIOBaseMeta` metaclass enforces dynamic method target resolution using the `if (x) A = B else A = D; f(A)` pattern:
* At class-creation time, `AsyncIOBaseMeta` inspects subclass method definitions.
* If a stream class defines synchronous `.read()` but lacks a native `.aread()`, the metaclass automatically attaches a dynamically generated `asyncio.to_thread` wrapper.
* Calling synchronous `.read()` inside an active event loop raises a `RuntimeError` to prevent silent event-loop blocking.

---

## **2. Standard Library Patching (`sitecustomize.py`)**

`py-native-io` patches `builtins.open`, `io.open`, `io.FileIO`, and `socket.socket.makefile` transparently on initialization:

* **Kernel Supported:** Factory calls return native Rust-backed ring streams that run `aread()` and `awrite()` directly on kernel ring buffers.
* **Kernel Unsupported:** Factory calls return `FallbackFileIO` streams that run synchronous I/O via thread pools—ensuring code calling `aread()` never breaks on older OS builds.

---

## **3. Security & Kernel Version Gating (Linux >= 5.10 LTS)**

To protect applications against privilege escalation and kernel memory corruption vulnerabilities, `py-native-io` enforces a strict minimum **Linux Kernel 5.10 LTS** requirement for native `io_uring` execution:

* **Why Linux >= 5.10 LTS?**
  Early `io_uring` implementations in Linux kernels 5.1 through 5.9 contained severe security vulnerabilities and use-after-free flaws (*e.g., CVE-2021-3491, CVE-2022-2602*). Kernel 5.10 LTS stabilized `io_uring` security boundaries, capability checks, and memory pinning.
* **Hardware/Kernel Opcode Probing (`IORING_REGISTER_PROBE`):**
  During engine detection, `py-native-io` registers an `io_uring::Probe` to verify that the host kernel and container environment (such as Docker/Kubernetes `seccomp` filters) actively allow `IORING_OP_READ` and `IORING_OP_WRITE` opcodes.
* **Graceful Thread-Pool Fallback:**
  If the host kernel is `< 5.10` or container security policies restrict `io_uring`, `is_kernel_ring_supported()` returns `False`, transparently falling back to secure thread-pool execution (`FallbackFileIO`).

---

## **4. Developer Toolchain (`uv` + `maturin`)**

Build, lint, type-check, and test the repository using `uv`:

```bash
# 1. Build & install C-extension locally into virtualenv
uv run maturin develop

# 2. Run Ruff linter & Mypy strict type checking
uv run ruff check
uv run mypy py_native_io

# 3. Run unit test suite in Native Mode
uv run pytest

# 4. Run test suite forcing Thread-Pool Fallback Mode
PY_NATIVE_IO_FORCE_LEGACY=1 uv run pytest
```

---

*For detailed platform implementation matrices, CPython test suite integration, and multi-phase roadmaps, see [`PROJECT_GOALS.md`](./PROJECT_GOALS.md).*
 