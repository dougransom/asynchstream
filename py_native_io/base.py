import asyncio
import io
import os
from abc import ABCMeta
from typing import Any, Protocol, runtime_checkable


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
