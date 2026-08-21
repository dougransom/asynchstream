import io
from typing import Any

from py_native_io.base import AsyncIOBase


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
