import asyncio
import builtins
import io
import pytest
import py_native_io
from py_native_io import AsyncIOBase, FallbackFileIO

def test_builtins_open_is_patched():
    assert hasattr(builtins, "_orig_open")
    assert io.open is builtins.open
    assert hasattr(io, "AsyncIOBase")

def test_sync_read_write(tmp_path):
    test_file = tmp_path / "sync.txt"
    with open(test_file, "wb") as f:
        f.write(b"Hello Native IO")
    with open(test_file, "rb") as f:
        assert f.read(15) == b"Hello Native IO"

@pytest.mark.asyncio
async def test_async_aread(tmp_path):
    test_file = tmp_path / "async.txt"
    test_file.write_bytes(b"Async Test")
    f = open(test_file, "rb")
    data = await f.aread(10)
    f.close()
    assert data == b"Async Test"