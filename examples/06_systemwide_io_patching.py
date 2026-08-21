"""Example 06: Systemwide Replacement of open(), io.FileIO, io.BytesIO, io.StringIO in main()."""

import asyncio
import builtins
import io
import logging

import py_native_io

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")


async def main() -> None:
    print("=== Example 06: Systemwide io Module Replacement ===")

    # Verify transparent patching in standard library classes
    print(f"builtins.open is patched: {builtins.open == py_native_io.patched_open}")
    print(f"io.open is patched:       {io.open == py_native_io.patched_open}")
    print(f"io.FileIO is patched:     {io.FileIO == py_native_io.DefaultFileIO}")
    print(f"io.BytesIO is patched:    {io.BytesIO == py_native_io.AsyncBytesIO}")
    print(f"io.StringIO is patched:   {io.StringIO == py_native_io.AsyncStringIO}")

    # Standard open() returns AsyncIOStream compliant objects
    f = open("examples/06_systemwide_io_patching.py")  # noqa: SIM115
    assert isinstance(f, py_native_io.AsyncIOStream)

    # Perform non-blocking async read directly on standard open() handle
    first_line = await f.aread(40)
    print(f"First Line of Script: {first_line!r}")
    f.close()


if __name__ == "__main__":
    asyncio.run(main())
