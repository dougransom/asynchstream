import builtins
import io
from pathlib import Path

import pytest

import py_native_io  # noqa: F401


def test_builtins_open_is_patched() -> None:
    assert hasattr(builtins, "_orig_open")
    assert io.open is builtins.open
    assert hasattr(io, "AsyncIOBase")


def test_sync_read_write(tmp_path: Path) -> None:
    test_file = tmp_path / "sync.txt"
    with open(test_file, "wb") as f:
        f.write(b"Hello Native IO")
    with open(test_file, "rb") as f:
        assert f.read(15) == b"Hello Native IO"


@pytest.mark.asyncio
async def test_async_aread(tmp_path: Path) -> None:
    test_file = tmp_path / "async.txt"
    test_file.write_bytes(b"Async Test")
    with open(test_file, "rb") as f:
        data = await f.aread(10)
    assert data == b"Async Test"


def test_async_io_stream_protocol(tmp_path: Path) -> None:
    test_file = tmp_path / "protocol.txt"
    with open(test_file, "wb") as f:
        assert isinstance(f, py_native_io.AsyncIOStream)
        assert isinstance(f, io.IOBase)


@pytest.mark.asyncio
async def test_async_bytes_io() -> None:
    mem_stream = py_native_io.AsyncBytesIO(b"Memory Stream Data")
    assert isinstance(mem_stream, py_native_io.AsyncIOStream)
    assert isinstance(mem_stream, io.IOBase)

    data = await mem_stream.aread(6)
    assert data == b"Memory"
    mem_stream.seek(0, io.SEEK_END)
    await mem_stream.awrite(b" Updated")
    mem_stream.seek(0)
    assert mem_stream.read() == b"Memory Stream Data Updated"
    mem_stream.close()


def test_text_mode_open(tmp_path: Path) -> None:
    test_file = tmp_path / "text.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Hello Text World")

    with open(test_file, encoding="utf-8") as f:
        assert isinstance(f, io.TextIOWrapper)
        assert f.read() == "Hello Text World"


def test_buffered_binary_open(tmp_path: Path) -> None:
    test_file = tmp_path / "buffered.bin"
    with open(test_file, "wb", buffering=1024) as f:
        assert isinstance(f, (io.BufferedWriter, io.BufferedRandom))
        f.write(b"Buffered Data")

    with open(test_file, "rb", buffering=1024) as f:
        assert isinstance(f, io.BufferedReader)
        assert f.read() == b"Buffered Data"


def test_io_file_io_patched() -> None:
    assert io.FileIO is py_native_io.DefaultFileIO
