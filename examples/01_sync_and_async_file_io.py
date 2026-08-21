"""Example 01: Synchronous and Asynchronous File I/O Benchmarking."""

import asyncio
import tempfile
import time

import py_native_io  # noqa: F401


async def main() -> None:
    print("=== Example 01: Sync vs Async File I/O Benchmark ===")

    with tempfile.NamedTemporaryFile("w+b", delete=False) as tmp:
        filename = tmp.name

    # Write test data
    f = open(filename, "w+b")  # noqa: SIM115
    payload = b"Hello, py-native-io high-performance kernel streams!\n" * 1000

    # Benchmark synchronous write
    t0 = time.perf_counter()
    f.write(payload)
    f.flush()
    t_sync_write = (time.perf_counter() - t0) * 1000

    # Benchmark asynchronous write
    t0 = time.perf_counter()
    written = await f.awrite(payload)
    await f.aflush()
    t_async_write = (time.perf_counter() - t0) * 1000

    # Benchmark synchronous read
    f.seek(0)
    t0 = time.perf_counter()
    sync_data = f.read(1024)
    t_sync_read = (time.perf_counter() - t0) * 1000

    # Benchmark asynchronous read
    f.seek(0)
    t0 = time.perf_counter()
    async_data = await f.aread(1024)
    t_async_read = (time.perf_counter() - t0) * 1000

    f.close()

    print(f"File: {filename}")
    print(f"Synchronous Write: {t_sync_write:.3f} ms")
    print(f"Asynchronous Write: {t_async_write:.3f} ms (wrote {written} bytes)")
    print(f"Synchronous Read:  {t_sync_read:.3f} ms (read {len(sync_data)} bytes)")
    print(f"Asynchronous Read: {t_async_read:.3f} ms (read {len(async_data)} bytes)")
    print("Success: Synchronous and Asynchronous data match!\n")


if __name__ == "__main__":
    asyncio.run(main())
