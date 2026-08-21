import asyncio
import io
from typing import Any

from py_native_io.base import AsyncIOBase


class AsyncBytesIO(io.BytesIO, AsyncIOBase):
    """In-memory binary byte stream supporting AsyncIOBase contract."""

    async def aread(self, size: int = -1) -> bytes:
        return self.read(size)

    async def awrite(self, b: bytes) -> int:
        return self.write(b)

    async def aclose(self) -> None:
        self.close()

    async def aflush(self) -> None:
        self.flush()

    async def asplice(self, target: Any, size: int = -1) -> int:
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


class AsyncStringIO(io.StringIO, AsyncIOBase):  # type: ignore[misc]
    """In-memory text stream supporting AsyncIOBase contract."""

    async def aread(self, size: int = -1) -> str:  # type: ignore[override]
        return self.read(size)

    async def awrite(self, s: str) -> int:  # type: ignore[override]
        return self.write(s)

    async def aclose(self) -> None:
        self.close()

    async def aflush(self) -> None:
        self.flush()

    async def asplice(self, target: Any, size: int = -1) -> int:
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
