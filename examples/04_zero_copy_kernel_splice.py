"""Example 04: Zero-Copy Kernel Transfer via asplice()."""

import asyncio
import logging
import tempfile

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

import py_native_io  # noqa: E402, F401


async def main() -> None:
    print("=== Example 04: Zero-Copy Kernel Transfer via asplice() ===")

    # Source file
    with tempfile.NamedTemporaryFile("w+b", delete=False) as src_tmp:
        src_name = src_tmp.name
        src_tmp.write(b"Zero-Copy Kernel Splice Data Pipeline Payload\n" * 10)

    # Target file
    with tempfile.NamedTemporaryFile("w+b", delete=False) as dst_tmp:
        dst_name = dst_tmp.name

    src_file = open(src_name, "rb")  # noqa: SIM115
    dst_file = open(dst_name, "w+b")  # noqa: SIM115

    # Splice kernel transfer from src_file to dst_file descriptor
    bytes_spliced = await src_file.asplice(dst_file, size=4096)
    print(f"Transferred {bytes_spliced} bytes via kernel splice ring.")

    dst_file.seek(0)
    copied_data = dst_file.read()
    print("Copied Data Preview:")
    print(copied_data[:100].decode("utf-8"))

    src_file.close()
    dst_file.close()


if __name__ == "__main__":
    asyncio.run(main())
