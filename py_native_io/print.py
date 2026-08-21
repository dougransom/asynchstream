"""Asynchronous print implementation for py-native-io."""

import sys
from typing import Any

from py_native_io.file import DefaultFileIO

_async_stdout: DefaultFileIO | None = None
_async_stderr: DefaultFileIO | None = None


def get_async_stdout() -> DefaultFileIO:
    """Retrieve or lazy-initialize async stdout stream for file descriptor 1."""
    global _async_stdout
    if _async_stdout is None or _async_stdout.closed:
        _async_stdout = DefaultFileIO(1, "w")
    return _async_stdout


def get_async_stderr() -> DefaultFileIO:
    """Retrieve or lazy-initialize async stderr stream for file descriptor 2."""
    global _async_stderr
    if _async_stderr is None or _async_stderr.closed:
        _async_stderr = DefaultFileIO(2, "w")
    return _async_stderr


async def aprint(
    *objects: object,
    sep: str = " ",
    end: str = "\n",
    file: Any = None,
    flush: bool = False,
) -> None:
    """Asynchronously output objects to a stream or stdout using high-performance kernel I/O.

    Args:
        *objects: Objects to print.
        sep: Separator inserted between objects (default: ' ').
        end: End character appended after last object (default: '\\n').
        file: Target output stream. If None, defaults to sys.stdout.
        flush: Whether to forcibly flush the stream immediately (default: False).
    """
    output = sep.join(map(str, objects)) + end
    encoded_bytes = output.encode("utf-8")

    target_file = sys.stdout if file is None else file

    if hasattr(target_file, "awrite"):
        try:
            await target_file.awrite(encoded_bytes)
        except (TypeError, ValueError):
            await target_file.awrite(output)
        if flush and hasattr(target_file, "aflush"):
            await target_file.aflush()
        elif hasattr(target_file, "flush"):
            target_file.flush()
    elif hasattr(target_file, "write"):
        target_file.write(output)
        if hasattr(target_file, "flush"):
            target_file.flush()
