"""Example 02: Patching Existing io.FileIO and io.StringIO Streams."""

import asyncio
import io
import tempfile

import py_native_io


async def main() -> None:
    print("=== Example 02: Patching Existing io.FileIO & io.StringIO Streams ===")

    # 1. Patching io.FileIO for successive writes
    with tempfile.NamedTemporaryFile("w+b", delete=False) as tmp:
        filename = tmp.name

    raw_file = io.FileIO(filename, "w+")
    async_file = py_native_io.ensure_async_stream(raw_file)
    assert isinstance(async_file, py_native_io.AsyncIOStream)

    # Successive synchronous and asynchronous writes
    async_file.write(b"Line 1: Synchronous write.\n")
    await async_file.awrite(b"Line 2: Asynchronous write via ring.\n")
    async_file.write(b"Line 3: Successive sync write.\n")
    await async_file.awrite(b"Line 4: Successive async write.\n")

    async_file.seek(0)
    content = await async_file.aread()
    print("--- File Stream Content ---")
    print(content.decode("utf-8"))
    async_file.close()

    # 2. Patching io.StringIO for text stream
    raw_string = io.StringIO("Initial Header\n")
    async_string = py_native_io.patch_stream(raw_string)

    async_string.write("Line A: Text write.\n")
    await async_string.awrite("Line B: Async text write.\n")

    async_string.seek(0)
    string_content = await async_string.aread()
    print("--- StringIO Content ---")
    print(string_content)
    async_string.close()


if __name__ == "__main__":
    asyncio.run(main())
