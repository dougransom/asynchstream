import io
from typing import Any

from py_native_io.base import AsyncIOBase


class AsyncBufferedReader(io.BufferedReader, AsyncIOBase):
    """Buffered reader supporting AsyncIOBase contract."""

    async def aread(self, size: int = -1) -> bytes:
        """Asynchronously read up to size bytes from underlying raw stream."""
        if hasattr(self.raw, "aread"):
            res: bytes = await self.raw.aread(size)
            return res
        return await super().aread(size)


class AsyncBufferedWriter(io.BufferedWriter, AsyncIOBase):
    """Buffered writer supporting AsyncIOBase contract."""

    async def awrite(self, b: Any) -> int:
        """Asynchronously write bytes to underlying raw stream."""
        if hasattr(self.raw, "awrite"):
            res: int = await self.raw.awrite(b)
            return res
        return await super().awrite(b)


class AsyncBufferedRandom(io.BufferedRandom, AsyncIOBase):
    """Buffered random stream supporting AsyncIOBase contract."""

    async def aread(self, size: int = -1) -> bytes:
        """Asynchronously read up to size bytes from underlying raw stream."""
        if hasattr(self.raw, "aread"):
            res: bytes = await self.raw.aread(size)
            return res
        return await super().aread(size)

    async def awrite(self, b: Any) -> int:
        """Asynchronously write bytes to underlying raw stream."""
        if hasattr(self.raw, "awrite"):
            res: int = await self.raw.awrite(b)
            return res
        return await super().awrite(b)


class AsyncTextIOWrapper(io.TextIOWrapper, AsyncIOBase):  # type: ignore[misc]
    """Text stream supporting AsyncIOBase contract."""

    async def aread(self, size: int = -1) -> str:  # type: ignore[override]
        """Asynchronously read text from underlying stream."""
        if hasattr(self.buffer, "aread"):
            raw_bytes: bytes = await self.buffer.aread(size)
            return raw_bytes.decode(self.encoding or "utf-8", errors=self.errors or "strict")
        res_super = await super().aread(size)
        return res_super.decode("utf-8") if isinstance(res_super, bytes) else str(res_super)

    async def awrite(self, s: Any) -> int:
        """Asynchronously write text to underlying stream."""
        data = (
            s.encode(self.encoding or "utf-8", errors=self.errors or "strict")
            if isinstance(s, str)
            else s
        )
        if hasattr(self.buffer, "awrite"):
            res: int = await self.buffer.awrite(data)
            return res
        return await super().awrite(s)
