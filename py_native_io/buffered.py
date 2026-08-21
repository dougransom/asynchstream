import io

from py_native_io.base import AsyncIOBase


class AsyncBufferedReader(io.BufferedReader, AsyncIOBase):
    """Buffered reader supporting AsyncIOBase contract."""


class AsyncBufferedWriter(io.BufferedWriter, AsyncIOBase):
    """Buffered writer supporting AsyncIOBase contract."""


class AsyncBufferedRandom(io.BufferedRandom, AsyncIOBase):
    """Buffered random stream supporting AsyncIOBase contract."""


class AsyncTextIOWrapper(io.TextIOWrapper, AsyncIOBase):  # type: ignore[misc]
    """Text stream supporting AsyncIOBase contract."""
