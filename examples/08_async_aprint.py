"""Example 08: Asynchronous Non-Blocking Printing with aprint."""

import asyncio
import logging
import os
import tempfile

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

import py_native_io  # noqa: E402, F401
from py_native_io import aprint  # noqa: E402


async def main() -> None:
    print("=== Example 08: Asynchronous Printing with aprint ===")

    # 1. Standard async print to stdout
    await aprint("🚀 Welcome to", "py-native-io", "asynchronous print!", sep=" ", flush=True)

    # 2. Asynchronous print directly to an open async file stream
    demo_file = os.path.join(tempfile.gettempdir(), "aprint_demo.txt")
    f = open(demo_file, "w+b")  # noqa: SIM115
    await aprint("Line 1: High-performance kernel stream output", file=f)
    await aprint("Line 2: Zero-copy async formatted text", file=f, flush=True)
    f.close()

    # Verify written file content
    with open(demo_file) as r:
        content = r.read()

    print("\n--- Content written to temp file via aprint ---")
    print(content)
    print("Success: aprint worked seamlessly across stdout and file streams!")


if __name__ == "__main__":
    asyncio.run(main())
