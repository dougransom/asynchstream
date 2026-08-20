import asyncio
import builtins
import io
import sys
from abc import ABCMeta
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

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

__all__ = [
    "AsyncBufferedRandom",
    "AsyncBufferedReader",
    "AsyncBufferedWriter",
    "AsyncBytesIO",
    "AsyncIOBase",
    "AsyncIOBaseMeta",
    "AsyncIOStream",
    "AsyncSocketIO",
    "AsyncTextIOWrapper",
    "DefaultFileIO",
    "FallbackFileIO",
    "LinuxURingFileIO",
    "MacOSKQueueFileIO",
    "NativeFileIO",
    "WindowsIoRingFileIO",
    "_ext",
    "patch_python_io",
]
