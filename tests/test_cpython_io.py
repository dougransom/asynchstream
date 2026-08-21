import io
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
