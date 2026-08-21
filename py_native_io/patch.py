import asyncio
import builtins
import contextlib
import io
import logging
import os
import types
from collections.abc import Callable
from typing import Any, cast

from py_native_io.base import AsyncIOBase, AsyncIOStream
from py_native_io.buffered import (
    AsyncBufferedRandom,
    AsyncBufferedReader,
    AsyncBufferedWriter,
    AsyncTextIOWrapper,
)
from py_native_io.file import DefaultFileIO, create_default_file_io
from py_native_io.memory import AsyncBytesIO, AsyncStringIO
from py_native_io.socket import AsyncSocketIO

logger = logging.getLogger("py_native_io")


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
    if opener is not None or not isinstance(file, (str, bytes, os.PathLike, int)):
        orig_open: Callable[..., Any] = getattr(builtins, "_orig_open", builtins.open)
        return orig_open(
            file,
            mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
            closefd=closefd,
            opener=opener,
        )

    is_binary = "b" in mode
    raw_mode = mode
    if not is_binary and "t" not in mode:
        raw_mode = mode + "b" if "+" not in mode else mode.replace("+", "b+")

    raw = create_default_file_io(file, raw_mode, closefd=closefd, opener=opener)

    res_stream: Any
    if is_binary:
        if buffering == 0:
            res_stream = raw
        elif "w" in mode or "a" in mode or "+" in mode:
            if "r" in mode or "+" in mode:
                res_stream = AsyncBufferedRandom(
                    raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
                )
            else:
                res_stream = AsyncBufferedWriter(
                    raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
                )
        else:
            res_stream = AsyncBufferedReader(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
    else:
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

        res_stream = AsyncTextIOWrapper(
            buffer_stream,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    logger.debug(
        "py-native-io: open('%s', mode='%s') -> stream '%s.%s' (raw: '%s.%s')",
        file,
        mode,
        res_stream.__class__.__module__,
        res_stream.__class__.__qualname__,
        raw.__class__.__module__,
        raw.__class__.__qualname__,
    )
    return res_stream


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

    res_stream: Any
    if is_binary:
        if buffering == 0 or "+" in mode:
            res_stream = raw
        elif "w" in mode or "a" in mode:
            res_stream = AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            res_stream = AsyncBufferedReader(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
    else:
        if buffering == 0:
            raise ValueError("can't have unbuffered text I/O")

        buf_stream: Any
        if "w" in mode or "a" in mode:
            buf_stream = AsyncBufferedWriter(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )
        else:
            buf_stream = AsyncBufferedReader(
                raw, buffer_size=buffering if buffering > 0 else io.DEFAULT_BUFFER_SIZE
            )

        res_stream = AsyncTextIOWrapper(
            buf_stream,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    logger.debug(
        "py-native-io: socket.makefile(mode='%s') -> stream '%s.%s'",
        mode,
        res_stream.__class__.__module__,
        res_stream.__class__.__qualname__,
    )
    return res_stream

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
    io.BytesIO = AsyncBytesIO  # type: ignore[misc]
    io.StringIO = AsyncStringIO  # type: ignore[misc]
    io.BufferedReader = AsyncBufferedReader  # type: ignore[assignment,misc]
    io.BufferedWriter = AsyncBufferedWriter  # type: ignore[assignment,misc]
    io.BufferedRandom = AsyncBufferedRandom  # type: ignore[misc]
    io.TextIOWrapper = AsyncTextIOWrapper  # type: ignore[assignment,misc]
    io.AsyncIOBase = AsyncIOBase  # type: ignore[attr-defined]

    builtins.open = patched_open
    io.open = patched_open

    import socket

    if hasattr(socket.socket, "makefile"):
        socket.socket._orig_makefile = socket.socket.makefile  # type: ignore[attr-defined]
        socket.socket.makefile = patched_socket_makefile  # type: ignore[assignment]


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

    async def aread_batch(self, specs: list[Any]) -> list[bytes]:
        if hasattr(self._inner_stream, "aread_batch"):
            res_a: list[bytes] = await self._inner_stream.aread_batch(specs)
            return res_a
        return [await self.aread(sz if isinstance(sz, int) else sz[1]) for sz in specs]

    async def awrite(self, b: bytes) -> int:
        if hasattr(self._inner_stream, "awrite"):
            res_w: int = await self._inner_stream.awrite(b)
            return res_w
        return await asyncio.to_thread(self._inner_stream.write, b)

    async def awrite_batch(self, chunks: list[Any]) -> list[int]:
        if hasattr(self._inner_stream, "awrite_batch"):
            res_w: list[int] = await self._inner_stream.awrite_batch(chunks)
            return res_w
        return [await self.awrite(chunk) for chunk in chunks]

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

    if (hasattr(stream, "aread") or hasattr(stream, "read")) and not hasattr(stream, "aread_batch"):

        async def _aread_batch(self: Any, specs: list[Any]) -> list[bytes]:
            return [await self.aread(sz if isinstance(sz, int) else sz[1]) for sz in specs]

        with contextlib.suppress(TypeError, AttributeError):
            cls.aread_batch = _aread_batch
        stream.aread_batch = types.MethodType(_aread_batch, stream)

    if hasattr(stream, "write") and not hasattr(stream, "awrite"):

        async def _awrite(self: Any, b: bytes) -> int:
            return await asyncio.to_thread(self.write, b)

        with contextlib.suppress(TypeError, AttributeError):
            cls.awrite = _awrite
        stream.awrite = types.MethodType(_awrite, stream)

    if (hasattr(stream, "awrite") or hasattr(stream, "write")) and not hasattr(
        stream, "awrite_batch"
    ):

        async def _awrite_batch(self: Any, chunks: list[Any]) -> list[int]:
            return [await self.awrite(chunk) for chunk in chunks]

        with contextlib.suppress(TypeError, AttributeError):
            cls.awrite_batch = _awrite_batch
        stream.awrite_batch = types.MethodType(_awrite_batch, stream)

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
