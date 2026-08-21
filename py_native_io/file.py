import builtins
import io
import sys
from collections.abc import Callable
from typing import Any

from py_native_io.base import AsyncIOBase

try:
    from py_native_io import _ext  # type: ignore[attr-defined]
except ImportError:
    _ext = None

NativeFileIO: Any
if _ext is not None and hasattr(_ext, "NativeFileIO"):
    NativeFileIO = _ext.NativeFileIO
else:

    class DummyNativeFileIO(AsyncIOBase):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise NotImplementedError("Native C-extension engine not compiled.")

    NativeFileIO = DummyNativeFileIO


class FallbackFileIO(AsyncIOBase):
    """Cross-platform thread-pool file I/O stream."""

    def __init__(
        self,
        file: Any,
        mode: str = "rb",
        closefd: bool = True,
        opener: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        orig_open: Callable[..., Any] = getattr(builtins, "_orig_open", builtins.open)
        if opener is not None:
            self._sync_stream: Any = orig_open(file, mode, closefd=closefd, opener=opener)
        elif isinstance(file, int):
            self._sync_stream = orig_open(file, mode, closefd=closefd)
        elif hasattr(file, "read") or hasattr(file, "write"):
            self._sync_stream = file
        else:
            self._sync_stream = orig_open(file, mode)

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


class LinuxURingFileIO(NativeFileIO):  # type: ignore[misc]
    """Linux io_uring native completion file stream."""


class WindowsIoRingFileIO(NativeFileIO):  # type: ignore[misc]
    """Windows IoRing native completion file stream."""


class MacOSKQueueFileIO(NativeFileIO):  # type: ignore[misc]
    """macOS kqueue native completion file stream."""


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


def create_default_file_io(
    file: Any, mode: str = "rb", closefd: bool = True, opener: Any = None
) -> Any:
    if use_native and (isinstance(file, (str, bytes)) or hasattr(file, "__fspath__")):
        try:
            return DefaultFileIO(file, mode, closefd=closefd, opener=opener)
        except Exception:
            pass
    return FallbackFileIO(file, mode, closefd=closefd, opener=opener)


__all__ = [
    "DefaultFileIO",
    "FallbackFileIO",
    "LinuxURingFileIO",
    "MacOSKQueueFileIO",
    "NativeFileIO",
    "WindowsIoRingFileIO",
    "_ext",
    "create_default_file_io",
    "use_native",
]
