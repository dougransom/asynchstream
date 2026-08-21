# `py-native-io` Implementation TODO List

This document tracks completed features and planned platform engine implementations across all target operating systems.

---

## 1. Core Architecture & CPython Integration
- [x] Base Async Stream Abstraction (`AsyncIOBase` & `AsyncIOBaseMeta`)
- [x] Runtime Protocol Interface (`AsyncIOStream` `@runtime_checkable`)
- [x] Standard Library Patching (`builtins.open`, `io.open`, `io.FileIO`, `socket.socket.makefile`)
- [x] Dynamic Adapter & In-Place Stream Patching (`patch_stream`, `wrap_stream`, `ensure_async_stream`)
- [x] In-Memory Async Byte Stream (`AsyncBytesIO` & `io.BytesIO` patching)
- [x] CPython Test Suite (`tests/test_cpython_io.py`) in Dual Execution Modes (Native & Fallback)

---

## 2. Platform Async Engine Implementation Roadmap

### 🐧 Linux (`io_uring`)
- [x] Linux Kernel Version Gating (`>= 5.10 LTS` CVE security check)
- [x] Hardware & Security Opcode Probing (`IORING_REGISTER_PROBE`)
- [x] Basic Ring Submission & Completion (`IORING_OP_READ`, `IORING_OP_WRITE`)
- [x] Zero-Copy Kernel Transfer (`asplice` via `IORING_OP_SPLICE`)
- [ ] Registered Fixed Buffer Tables (`IORING_REGISTER_BUFFERS`)
- [ ] Network Ring Accept & Connect (`IORING_OP_ACCEPT`, `IORING_OP_CONNECT`)

### 🪟 Windows (`IoRing` & IOCP)
- [x] Windows `IoRing` FFI bindings via `windows-sys` (`CreateIoRing`, `SubmitIoRing`)
- [x] File I/O Operations (`submit_ioring_read`, `submit_ioring_write`)
- [x] Legacy Windows Fallback (Thread-pool engine when `CreateIoRing` unavailable)
- [ ] Pre-registered Fixed Buffer Tables (`BuildIoRingRegisterBuffers`)

### 🍎 macOS & Apple Platforms (`kqueue`)
- [ ] `kqueue` Event Filter Bindings (`EVFILT_READ`, `EVFILT_WRITE`) for Darwin / macOS
- [ ] Non-blocking socket notification & async I/O dispatch
- [ ] iOS / iPadOS POSIX Async Stream Fallback

### 😈 BSD Family (FreeBSD, NetBSD, OpenBSD, DragonFly BSD)
- [ ] FreeBSD `kqueue` Native Async Event Filter Engine
- [ ] NetBSD / OpenBSD `kqueue` Event Engine & POSIX Fallback
- [ ] DragonFly BSD `kqueue` Stream Engine

### ☀️ Solaris & Illumos (SmartOS, OmniOS)
- [ ] Solaris `event ports` (`port_create`, `port_associate`, `port_get`) Engine
- [ ] Illumos POSIX Thread-pool Engine

### 💼 IBM Enterprise Platforms (AIX & z/OS Mainframe)
- [ ] IBM AIX POSIX Async I/O Engine (`aio_read`, `aio_write`)
- [ ] IBM z/OS (s390x) POSIX Thread-pool Engine

### 📱 Mobile & Embedded Platforms
- [ ] Android (`aarch64`) `io_uring` & POSIX Thread-pool Engine
- [ ] Haiku OS POSIX Async Stream Engine

### 🌐 WebAssembly (WASI / Pyodide)
- [ ] WASI Pure In-Memory Async Buffer Stream Adapter

---

## 3. GitHub Actions & Packaging Matrix
- [x] Automated CI verification (`.github/workflows/ci.yml`)
- [x] Linux `x86_64` & `aarch64` Wheel Build (`manylinux_2_28`)
- [x] macOS `x86_64` & `arm64` Wheel Build
- [x] Windows `x64` Wheel Build
- [x] FreeBSD `x86_64` VM Wheel Build (`vmactions/freebsd-vm`)
- [x] Automated PyPI Release Upload (`release.yml`)
- [ ] OpenBSD & NetBSD VM Build Workflows
