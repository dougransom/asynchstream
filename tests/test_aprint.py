"""Unit tests for asynchronous aprint in py_native_io."""

import io
import tempfile

import pytest

from py_native_io import DefaultFileIO, aprint


@pytest.mark.asyncio
async def test_aprint_default_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """Test aprint writing to default stdout."""
    await aprint("Hello", "Async", "World!", sep=" ", end="\n")
    captured = capsys.readouterr()
    assert "Hello Async World!\n" in captured.out


@pytest.mark.asyncio
async def test_aprint_async_file() -> None:
    """Test aprint writing to an async file stream."""
    with tempfile.NamedTemporaryFile("w+b", delete=False) as tmp:
        filename = tmp.name

    f = DefaultFileIO(filename, "w+b")
    await aprint("High-performance", "kernel", "ring", sep=" ", end="\n", file=f, flush=True)
    await f.aclose()

    with open(filename, "rb") as r:
        content = r.read()
    assert content == b"High-performance kernel ring\n"


@pytest.mark.asyncio
async def test_aprint_sync_fallback() -> None:
    """Test aprint writing to a standard synchronous file-like stream (io.StringIO)."""
    buf = io.StringIO()
    await aprint("Sync", "fallback", "test", sep="-", end="!", file=buf)
    assert buf.getvalue() == "Sync-fallback-test!"
