import asyncio
import builtins
import contextlib
import io
import os
import sys
import types
from abc import ABCMeta
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol, cast, runtime_checkable

try:
    from py_native_io import _ext  # type: ignore[attr-defined]
except ImportError:
    _ext = None


@runtime_checkable
class AsyncIOStream(Protocol):
    """Protocol defining the unified asynchronous stream interface contract."""

    async def aread(self, size: int = -1) -> bytes: ...

    async def awrite(self, b: bytes) -> int: ...

    async def aclose(self) -> None: ...

    async def aflush(self) -> None: ...

    async def asplice(self, target: Any, size: int = -1) -> int: ...


class AsyncIOBaseMeta(ABCMeta):
    """Metaclass inspecting stream definitions to auto-synthesize missing async wrappers."""

    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> "AsyncIOBaseMeta":
        cls: AsyncIOBaseMeta = super().__new__(mcls, name, bases, namespace)

        if "read" in namespace and "aread" not in namespace:
            sync_read = namespace["read"]

            async def auto_aread(self: Any, size: int = -1) -> bytes:
                return await asyncio.to_thread(sync_read, self, size)

            cls.aread = auto_aread  # type: ignore[attr-defined]

        if "write" in namespace and "awrite" not in namespace:
            sync_write = namespace["write"]

            async def auto_awrite(self: Any, b: bytes) -> int:
                return await asyncio.to_thread(sync_write, self, b)

            cls.awrite = auto_awrite  # type: ignore[attr-defined]

        if "close" in namespace and "aclose" not in namespace:
            sync_close = namespace["close"]

            async def auto_aclose(self: Any) -> None:
                await asyncio.to_thread(sync_close, self)

            cls.aclose = auto_aclose  # type: ignore[attr-defined]

        if "flush" in namespace and "aflush" not in namespace:
            sync_flush = namespace["flush"]

            async def auto_aflush(self: Any) -> None:
                await asyncio.to_thread(sync_flush, self)

            cls.aflush = auto_aflush  # type: ignore[attr-defined]

        return cls


class AsyncIOBase(io.IOBase, metaclass=AsyncIOBaseMeta):
    """Base class for all py-native-io streams (File, Socket, Memory)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()

    async def aread(self, size: int = -1) -> bytes:
        return await asyncio.to_thread(self.read, size)

    async def awrite(self, b: bytes) -> int:
        return await asyncio.to_thread(self.write, b)

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    async def aflush(self) -> None:
        await asyncio.to_thread(self.flush)

    async def asplice(self, target: Any, size: int = -1) -> int:
        target_fd = (
            target
            if isinstance(target, int)
            else (target.fileno() if hasattr(target, "fileno") else -1)
        )
        ext_asplice = getattr(self, "_ext_asplice", None)
        if callable(ext_asplice) and target_fd != -1:
            res: int = await ext_asplice(target_fd, size)
            return res
        chunk = await self.aread(size if size > 0 else 65536)
        if not chunk:
            return 0
        if hasattr(target, "awrite"):
            res_w: int = await target.awrite(chunk)
            return res_w
        elif hasattr(target, "write"):
            res_sync: int = await asyncio.to_thread(target.write, chunk)
            return res_sync
        elif isinstance(target_fd, int) and target_fd != -1:
            res_fd: int = await asyncio.to_thread(os.write, target_fd, chunk)
            return res_fd
        return 0

    def read(self, size: int = -1) -> bytes:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            msg = "Cannot call sync read() inside an active event loop. Use 'await aread()'."
            raise RuntimeError(msg)
        return asyncio.run(self.aread(size))

    def write(self, b: bytes) -> int:
        return asyncio.run(self.awrite(b))


class FallbackFileIO(AsyncIOBase):
    """Cross-platform thread-pool file I/O stream."""

    def __init__(self, file: Any, mode: str = "rb", *args: Any, **kwargs: Any) -> None:
        super().__init__(file, mode, *args, **kwargs)
        orig_open: Callable[..., Any] = getattr(builtins, "_orig_open", builtins.open)
        self._sync_stream: Any = orig_open(file, mode, *args, **kwargs)

    def read(self, size: int = -1) -> bytes:
        res: bytes = self._sync_stream.read(size)
        return res

    def readinto(self, b: Any) -> int:
        res: int = self._sync_stream.readinto(b)
        return res

    def write(self, b: bytes) -> int:
        res: int = self._sync_stream.write(b)
        return res

    def close(self) -> None:
        self._sync_stream.close()

    def flush(self) -> None:
        self._sync_stream.flush()

    @property
    def closed(self) -> bool:
        res: bool = self._sync_stream.closed
        return res

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        res: int = self._sync_stream.seek(offset, whence)
        return res

    def tell(self) -> int:
        res: int = self._sync_stream.tell()
        return res

    def readable(self) -> bool:
        res: bool = self._sync_stream.readable()
        return res

    def writable(self) -> bool:
        res: bool = self._sync_stream.writable()
        return res

    def seekable(self) -> bool:
        res: bool = self._sync_stream.seekable()
        return res

    def fileno(self) -> int:
        res: int = self._sync_stream.fileno()
        return res

    def isatty(self) -> bool:
        res: bool = self._sync_stream.isatty()
        return res

    def __enter__(self) -> "FallbackFileIO":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncBytesIO(AsyncIOBase):
    """In-memory binary stream adhering to the AsyncIOBase contract."""

    def __init__(self, initial_bytes: bytes = b"") -> None:
        super().__init__()
        self._buffer = io.BytesIO(initial_bytes)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def write(self, b: bytes) -> int:
        return self._buffer.write(b)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._buffer.seek(offset, whence)

    def tell(self) -> int:
        return self._buffer.tell()

    def close(self) -> None:
        self._buffer.close()


class AsyncSocketIO(io.RawIOBase, AsyncIOBase):
    """Socket stream adhering to AsyncIOBase and AsyncIOStream contract."""

    def __init__(self, sock: Any, mode: str = "rb") -> None:
        super().__init__()
        self._sock = sock
        self._mode = mode
        self._is_read = "r" in mode or "+" in mode
        self._is_write = "w" in mode or "a" in mode or "+" in mode

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            bufs = []
            while True:
                chunk: bytes = self._sock.recv(65536)
                if not chunk:
                    break
                bufs.append(chunk)
            return b"".join(bufs)
        res: bytes = self._sock.recv(size)
        return res

    def readinto(self, b: Any) -> int:
        res: int = self._sock.recv_into(b)
        return res

    def write(self, b: Any) -> int:
        res: int = self._sock.send(b)
        return res

    def close(self) -> None:
        self._sock.close()

    @property
    def closed(self) -> bool:
        res: bool = self._sock.fileno() == -1
        return res

    def readable(self) -> bool:
        return self._is_read

    def writable(self) -> bool:
        return self._is_write

    def seekable(self) -> bool:
        return False

    def fileno(self) -> int:
        res: int = self._sock.fileno()
        return res


# Platform-specific subclasses (wrapping Rust NativeFileIO where supported)
if _ext is not None and hasattr(_ext, "NativeFileIO"):
    NativeFileIO: Any = _ext.NativeFileIO
    io.IOBase.register(NativeFileIO)
else:
    NativeFileIO = FallbackFileIO


class LinuxURingFileIO(NativeFileIO):  # type: ignore[misc]
    """Linux io_uring native completion file stream."""


class WindowsIoRingFileIO(NativeFileIO):  # type: ignore[misc]
    """Windows IoRing native completion file stream."""


class MacOSKQueueFileIO(NativeFileIO):  # type: ignore[misc]
    """macOS kqueue native completion file stream."""


# Target class resolution at initialization time: if (x) A = B else A = D
use_native = _ext.is_kernel_ring_supported() if _ext is not None else False

if use_native:
    if sys.platform.startswith("linux"):
        DefaultFileIO: Any = LinuxURingFileIO
    elif sys.platform.startswith("win"):
        DefaultFileIO = WindowsIoRingFileIO
    elif sys.platform.startswith("darwin"):
        DefaultFileIO = MacOSKQueueFileIO
    else:
        DefaultFileIO = NativeFileIO
else:
    DefaultFileIO = FallbackFileIO


class AsyncBufferedReader(io.BufferedReader, AsyncIOBase):
    """Buffered reader supporting AsyncIOBase contract."""


class AsyncBufferedWriter(io.BufferedWriter, AsyncIOBase):
    """Buffered writer supporting AsyncIOBase contract."""


class AsyncBufferedRandom(io.BufferedRandom, AsyncIOBase):
    """Buffered random stream supporting AsyncIOBase contract."""


class AsyncTextIOWrapper(io.TextIOWrapper, AsyncIOBase):  # type: ignore[misc]
    """Text stream supporting AsyncIOBase contract."""


def patched_open(
    file: Any,
    mode: str = "r",
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: Any = None,
) -> Any:
    """Full CPython open() implementation supporting binary, text, and buffered streams."""
    is_binary = "b" in mode
    raw_mode = mode
    if not is_binary and "t" not in mode:
        raw_mode = mode + "b" if "+" not in mode else mode.replace("+", "b+")

    raw = DefaultFileIO(file, raw_mode, closefd=closefd, opener=opener)

    if is_binary:
        if buffering == 0:
            return raw
        elif "w" in mode or "a" in mode or "+" in mode:
            if "r" in mode or "+" in mode:
                return AsyncBufferedRandom(
                    raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
                )
            return AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            return AsyncBufferedReader(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )

    if buffering == 0:
        raise ValueError("can't have unbuffered text I/O")

    buffer_stream: Any
    if "w" in mode or "a" in mode or "+" in mode:
        if "r" in mode or "+" in mode:
            buffer_stream = AsyncBufferedRandom(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            buffer_stream = AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
    else:
        buffer_stream = AsyncBufferedReader(
            raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
        )

    return AsyncTextIOWrapper(
        buffer_stream,
        encoding=encoding,
        errors=errors,
        newline=newline,
    )


def patched_socket_makefile(
    self: Any,
    mode: str = "r",
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> Any:
    """Patched socket.socket.makefile returning AsyncSocketIO-backed stream."""
    is_binary = "b" in mode
    raw_mode = mode
    if not is_binary and "t" not in mode:
        raw_mode = mode + "b" if "+" not in mode else mode.replace("+", "b+")

    raw = AsyncSocketIO(self, raw_mode)

    if is_binary:
        if buffering == 0:
            return raw
        elif "w" in mode or "a" in mode or "+" in mode:
            if "r" in mode or "+" in mode:
                return AsyncBufferedRandom(
                    raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
                )
            return AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            return AsyncBufferedReader(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )

    if buffering == 0:
        raise ValueError("can't have unbuffered text I/O")

    buffer_stream: Any
    if "w" in mode or "a" in mode or "+" in mode:
        if "r" in mode or "+" in mode:
            buffer_stream = AsyncBufferedRandom(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            buffer_stream = AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
    else:
        buffer_stream = AsyncBufferedReader(
            raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
        )

    return AsyncTextIOWrapper(
        buffer_stream,
        encoding=encoding,
        errors=errors,
        newline=newline,
    )


def patch_python_io() -> None:
    if hasattr(builtins, "_orig_open"):
        return

    builtins._orig_open = builtins.open  # type: ignore[attr-defined]
    io._orig_open = io.open  # type: ignore[attr-defined]

    io.FileIO = DefaultFileIO  # type: ignore[misc]
    io.AsyncIOBase = AsyncIOBase  # type: ignore[attr-defined]

    builtins.open = patched_open
    io.open = patched_open

    import socket

    if hasattr(socket.socket, "makefile"):
        socket.socket._orig_makefile = socket.socket.makefile  # type: ignore[attr-defined]
        socket.socket.makefile = patched_socket_makefile  # type: ignore[assignment]


patch_python_io()


class AsyncStreamAdapter(AsyncIOBase):
    """Adapter wrapping any standard or 3rd-party stream into an AsyncIOStream."""

    def __init__(self, stream: Any) -> None:
        super().__init__()
        self._inner_stream = stream

    def read(self, size: int = -1) -> bytes:
        res: bytes = self._inner_stream.read(size)
        return res

    def write(self, b: bytes) -> int:
        res: int = self._inner_stream.write(b)
        return res

    def close(self) -> None:
        self._inner_stream.close()

    def flush(self) -> None:
        if hasattr(self._inner_stream, "flush"):
            self._inner_stream.flush()

    def seek(self, offset: int, whence: int = 0) -> int:
        res: int = self._inner_stream.seek(offset, whence)
        return res

    def tell(self) -> int:
        res: int = self._inner_stream.tell()
        return res

    def readable(self) -> bool:
        return (
            bool(self._inner_stream.readable()) if hasattr(self._inner_stream, "readable") else True
        )

    def writable(self) -> bool:
        return (
            bool(self._inner_stream.writable()) if hasattr(self._inner_stream, "writable") else True
        )

    def seekable(self) -> bool:
        return (
            bool(self._inner_stream.seekable())
            if hasattr(self._inner_stream, "seekable")
            else False
        )

    @property
    def closed(self) -> bool:
        return bool(getattr(self._inner_stream, "closed", False))

    async def aread(self, size: int = -1) -> bytes:
        if hasattr(self._inner_stream, "aread"):
            res_a: bytes = await self._inner_stream.aread(size)
            return res_a
        return await asyncio.to_thread(self._inner_stream.read, size)

    async def awrite(self, b: bytes) -> int:
        if hasattr(self._inner_stream, "awrite"):
            res_w: int = await self._inner_stream.awrite(b)
            return res_w
        return await asyncio.to_thread(self._inner_stream.write, b)

    async def aclose(self) -> None:
        if hasattr(self._inner_stream, "aclose"):
            await self._inner_stream.aclose()
        else:
            await asyncio.to_thread(self._inner_stream.close)

    async def aflush(self) -> None:
        if hasattr(self._inner_stream, "aflush"):
            await self._inner_stream.aflush()
        elif hasattr(self._inner_stream, "flush"):
            await asyncio.to_thread(self._inner_stream.flush)


def wrap_stream(stream: Any) -> AsyncIOStream:
    """Wraps an existing stream object in an AsyncStreamAdapter if not already an AsyncIOStream."""
    if isinstance(stream, AsyncIOStream):
        return stream
    return AsyncStreamAdapter(stream)


def patch_stream(stream: Any) -> AsyncIOStream:
    """In-place monkey patches an existing stream object to conform to AsyncIOStream."""
    if isinstance(stream, AsyncIOStream):
        return stream

    cls = stream.__class__

    if hasattr(stream, "read") and not hasattr(stream, "aread"):

        async def _aread(self: Any, size: int = -1) -> bytes:
            return await asyncio.to_thread(self.read, size)

        with contextlib.suppress(TypeError, AttributeError):
            cls.aread = _aread
        stream.aread = types.MethodType(_aread, stream)

    if hasattr(stream, "write") and not hasattr(stream, "awrite"):

        async def _awrite(self: Any, b: bytes) -> int:
            return await asyncio.to_thread(self.write, b)

        with contextlib.suppress(TypeError, AttributeError):
            cls.awrite = _awrite
        stream.awrite = types.MethodType(_awrite, stream)

    if hasattr(stream, "close") and not hasattr(stream, "aclose"):

        async def _aclose(self: Any) -> None:
            await asyncio.to_thread(self.close)

        with contextlib.suppress(TypeError, AttributeError):
            cls.aclose = _aclose
        stream.aclose = types.MethodType(_aclose, stream)

    if hasattr(stream, "flush") and not hasattr(stream, "aflush"):

        async def _aflush(self: Any) -> None:
            await asyncio.to_thread(self.flush)

        with contextlib.suppress(TypeError, AttributeError):
            cls.aflush = _aflush
        stream.aflush = types.MethodType(_aflush, stream)

    if not hasattr(stream, "asplice"):

        async def _asplice(self: Any, target: Any, size: int = -1) -> int:
            chunk = await self.aread(size if size > 0 else 65536)
            if not chunk:
                return 0
            if hasattr(target, "awrite"):
                res_w: int = await target.awrite(chunk)
                return res_w
            elif hasattr(target, "write"):
                res_sync: int = await asyncio.to_thread(target.write, chunk)
                return res_sync
            return 0

        with contextlib.suppress(TypeError, AttributeError):
            cls.asplice = _asplice
        stream.asplice = types.MethodType(_asplice, stream)

    if not hasattr(cls, "aread"):

        async def _aread_stub(self: Any, size: int = -1) -> bytes:
            raise io.UnsupportedOperation("not readable")

        with contextlib.suppress(TypeError, AttributeError):
            cls.aread = _aread_stub

    if not hasattr(cls, "awrite"):

        async def _awrite_stub(self: Any, b: bytes) -> int:
            raise io.UnsupportedOperation("not writable")

        with contextlib.suppress(TypeError, AttributeError):
            cls.awrite = _awrite_stub

    if not hasattr(cls, "aclose"):

        async def _aclose_stub(self: Any) -> None:
            pass

        with contextlib.suppress(TypeError, AttributeError):
            cls.aclose = _aclose_stub

    if not hasattr(cls, "aflush"):

        async def _aflush_stub(self: Any) -> None:
            pass

        with contextlib.suppress(TypeError, AttributeError):
            cls.aflush = _aflush_stub

    if not hasattr(cls, "asplice"):

        async def _asplice_stub(self: Any, target: Any, size: int = -1) -> int:
            return 0

        with contextlib.suppress(TypeError, AttributeError):
            cls.asplice = _asplice_stub

    return cast(AsyncIOStream, stream)


def ensure_async_stream(stream: Any, in_place: bool = True) -> AsyncIOStream:
    """Ensures a stream conforms to AsyncIOStream by patching in-place or wrapping."""
    if isinstance(stream, AsyncIOStream):
        return stream
    if in_place:
        return patch_stream(stream)
    return wrap_stream(stream)


__all__ = [
    "AsyncBufferedRandom",
    "AsyncBufferedReader",
    "AsyncBufferedWriter",
    "AsyncBytesIO",
    "AsyncIOBase",
    "AsyncIOBaseMeta",
    "AsyncIOStream",
    "AsyncSocketIO",
    "AsyncStreamAdapter",
    "AsyncTextIOWrapper",
    "DefaultFileIO",
    "FallbackFileIO",
    "LinuxURingFileIO",
    "MacOSKQueueFileIO",
    "NativeFileIO",
    "WindowsIoRingFileIO",
    "_ext",
    "ensure_async_stream",
    "patch_python_io",
    "patch_stream",
    "wrap_stream",
]
