import io
import os
from pathlib import Path

import pytest

import py_native_io


def test_fileio_compliance(tmp_path: Path) -> None:
    file_path = tmp_path / "raw.bin"

    # Write raw binary data
    with open(file_path, "wb", buffering=0) as f:
        assert isinstance(f, py_native_io.DefaultFileIO)
        assert f.writable()
        assert not f.readable()
        written = f.write(b"Raw Binary Payload")
        assert written == 18

    # Read raw binary data
    with open(file_path, "rb", buffering=0) as f:
        assert isinstance(f, py_native_io.DefaultFileIO)
        assert f.readable()
        assert not f.writable()
        assert f.seekable()
        assert f.tell() == 0

        # Test readinto
        buf = bytearray(18)
        n = f.readinto(buf)
        assert n == 18
        assert bytes(buf) == b"Raw Binary Payload"

        # Test seek & read
        f.seek(4)
        assert f.tell() == 4
        assert f.read(6) == b"Binary"


def test_buffered_reader_writer_compliance(tmp_path: Path) -> None:
    file_path = tmp_path / "buffered.bin"

    # Write with BufferedWriter
    with open(file_path, "wb", buffering=1024) as f:
        assert isinstance(f, (io.BufferedWriter, py_native_io.AsyncBufferedWriter))
        f.write(b"Buffered Line 1\n")
        f.write(b"Buffered Line 2\n")
        f.flush()

    # Read with BufferedReader
    with open(file_path, "rb", buffering=1024) as f:
        assert isinstance(f, (io.BufferedReader, py_native_io.AsyncBufferedReader))
        line1 = f.readline()
        assert line1 == b"Buffered Line 1\n"
        line2 = f.readline()
        assert line2 == b"Buffered Line 2\n"
        assert f.readline() == b""


def test_text_io_wrapper_compliance(tmp_path: Path) -> None:
    file_path = tmp_path / "text.txt"

    # Write text with custom encoding & newlines
    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        assert isinstance(f, (io.TextIOWrapper, py_native_io.AsyncTextIOWrapper))
        f.write("Line 1: UTF-8 🚀\n")
        f.write("Line 2: Python Native IO\n")

    # Read text with readline and readlines
    with open(file_path, encoding="utf-8") as f:
        assert isinstance(f, (io.TextIOWrapper, py_native_io.AsyncTextIOWrapper))
        line1 = f.readline()
        assert line1 == "Line 1: UTF-8 🚀\n"
        remaining = f.readlines()
        assert remaining == ["Line 2: Python Native IO\n"]


@pytest.mark.asyncio
async def test_async_cpython_streams(tmp_path: Path) -> None:
    file_path = tmp_path / "async_cpython.txt"

    with open(file_path, "wb", buffering=0) as f:
        await f.awrite(b"Async Raw Stream")

    with open(file_path, "rb", buffering=0) as f:
        data = await f.aread(9)
        assert data == b"Async Raw"
        await f.aclose()
        assert f.closed


@pytest.mark.asyncio
async def test_zero_copy_splice(tmp_path: Path) -> None:
    src_file = tmp_path / "splice_src.bin"
    src_file.write_bytes(b"Splice Zero Copy Kernel Payload")

    r_fd, w_fd = os.pipe()
    try:
        with open(src_file, "rb", buffering=0) as src_stream:
            copied = await src_stream.asplice(w_fd, 31)
            assert copied == 31
            pipe_data = os.read(r_fd, 31)
            assert pipe_data == b"Splice Zero Copy Kernel Payload"
    finally:
        os.close(r_fd)
        os.close(w_fd)


class CustomLegacyStream:
    """A third-party legacy sync-only stream class."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.closed_flag = False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            res = self.data[self.pos :]
            self.pos = len(self.data)
            return res
        res = self.data[self.pos : self.pos + size]
        self.pos += size
        return res

    def close(self) -> None:
        self.closed_flag = True

    @property
    def closed(self) -> bool:
        return self.closed_flag


@pytest.mark.asyncio
async def test_wrap_stream() -> None:
    raw = CustomLegacyStream(b"Legacy Payload Data")
    assert not isinstance(raw, py_native_io.AsyncIOStream)

    wrapped = py_native_io.wrap_stream(raw)
    assert isinstance(wrapped, py_native_io.AsyncIOStream)
    res = await wrapped.aread(14)
    assert res == b"Legacy Payload"
    await wrapped.aclose()
    assert wrapped.closed


@pytest.mark.asyncio
async def test_patch_stream() -> None:
    raw = CustomLegacyStream(b"In-place Patched Stream")
    assert not isinstance(raw, py_native_io.AsyncIOStream)

    patched = py_native_io.patch_stream(raw)
    assert isinstance(patched, py_native_io.AsyncIOStream)
    res = await patched.aread(8)
    assert res == b"In-place"
    await patched.aclose()
    assert patched.closed


@pytest.mark.asyncio
async def test_ensure_async_stream() -> None:
    s1 = CustomLegacyStream(b"Facade In-Place Data")
    ensured1 = py_native_io.ensure_async_stream(s1, in_place=True)
    assert isinstance(ensured1, py_native_io.AsyncIOStream)
    assert await ensured1.aread(6) == b"Facade"

    s2 = CustomLegacyStream(b"Facade Wrapped Data")
    ensured2 = py_native_io.ensure_async_stream(s2, in_place=False)
    assert isinstance(ensured2, py_native_io.AsyncIOStream)
    assert await ensured2.aread(6) == b"Facade"


@pytest.mark.asyncio
async def test_async_bytes_io() -> None:
    buf = io.BytesIO(b"In-Memory Async Byte Stream")
    assert isinstance(buf, py_native_io.AsyncBytesIO)
    assert isinstance(buf, py_native_io.AsyncIOStream)

    data = await buf.aread(9)
    assert data == b"In-Memory"

    buf.seek(0)
    written = await buf.awrite(b"Overwritten Payload")
    assert written == 19
    assert buf.getvalue() == b"Overwritten Payloade Stream"


@pytest.mark.asyncio
async def test_async_string_io() -> None:
    buf = io.StringIO("In-Memory Async Text Stream")
    assert isinstance(buf, py_native_io.AsyncStringIO)
    assert isinstance(buf, py_native_io.AsyncIOStream)

    data = await buf.aread(9)
    assert data == "In-Memory"

    buf.seek(0)
    written = await buf.awrite("Overwritten Payload")
    assert written == 19
    assert buf.getvalue() == "Overwritten Payloadt Stream"
