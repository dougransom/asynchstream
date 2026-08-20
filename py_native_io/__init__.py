import asyncio
import builtins
import io
import socket
from abc import ABCMeta

try:
    from py_native_io import _ext
except ImportError:
    _ext = None

class AsyncIOBaseMeta(ABCMeta):
    def __new__(mcls, name, bases, namespace):
        cls = super().__new__(mcls, name, bases, namespace)
        if "read" in namespace and "aread" not in namespace:
            sync_read = namespace["read"]
            async def auto_aread(self, size: int = -1) -> bytes:
                return await asyncio.to_thread(sync_read, self, size)
            setattr(cls, "aread", auto_aread)
        return cls

class AsyncIOBase(io.IOBase, metaclass=AsyncIOBaseMeta):
    async def aread(self, size: int = -1) -> bytes:
        return await asyncio.to_thread(self.read, size)

    async def awrite(self, b: bytes) -> int:
        return await asyncio.to_thread(self.write, b)

    def read(self, size: int = -1) -> bytes:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            raise RuntimeError("Cannot call sync read() inside an active event loop. Use 'await aread()'.")
        return asyncio.run(self.aread(size))

    def write(self, b: bytes) -> int:
        return asyncio.run(self.awrite(b))

class FallbackFileIO(AsyncIOBase):
    def __init__(self, file, mode="rb", *args, **kwargs):
        self._sync_stream = builtins._orig_open(file, mode, *args, **kwargs)

    def read(self, size: int = -1) -> bytes:
        return self._sync_stream.read(size)

    def write(self, b: bytes) -> int:
        return self._sync_stream.write(b)

    def close(self) -> None:
        self._sync_stream.close()

def patch_python_io():
    if hasattr(builtins, "_orig_open"):
        return

    builtins._orig_open = builtins.open
    io._orig_open = io.open

    use_native = _ext.is_kernel_ring_supported() if _ext else False

    def patched_open(file, mode="rb", *args, **kwargs):
        target_cls = _ext.NativeFileIO if use_native else FallbackFileIO
        return target_cls(file, mode, *args, **kwargs)

    builtins.open = patched_open
    io.open = patched_open
    io.AsyncIOBase = AsyncIOBase

patch_python_io()