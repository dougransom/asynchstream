"""Example 05: In-Memory Binary and Text Async Streams (AsyncBytesIO & AsyncStringIO)."""

import asyncio
import io
import logging

import py_native_io

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")


async def main() -> None:
    print("=== Example 05: In-Memory Async Streams (AsyncBytesIO & AsyncStringIO) ===")

    # 1. Binary In-Memory Stream
    bytes_stream = io.BytesIO(b"Initial Binary Payload")
    assert isinstance(bytes_stream, py_native_io.AsyncBytesIO)

    initial_bytes = await bytes_stream.aread(14)
    print(f"Async Read Bytes: {initial_bytes!r}")

    bytes_stream.seek(0)
    await bytes_stream.awrite(b"Updated Memory Ring")
    print(f"BytesIO getvalue(): {bytes_stream.getvalue()!r}")
    bytes_stream.close()

    # 2. Text In-Memory Stream
    text_stream = io.StringIO("Header Line\n")
    assert isinstance(text_stream, py_native_io.AsyncStringIO)

    await text_stream.awrite("Line 1: Async Text Write\n")
    await text_stream.awrite("Line 2: Another Async Line\n")

    text_stream.seek(0)
    full_text = await text_stream.aread()
    print("--- StringIO getvalue() ---")
    print(full_text)
    text_stream.close()


if __name__ == "__main__":
    asyncio.run(main())
