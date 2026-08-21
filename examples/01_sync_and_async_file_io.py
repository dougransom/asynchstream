"""Example 01: Synchronous and Asynchronous File I/O Benchmarking."""

import asyncio
import tempfile
import time

import py_native_io  # noqa: F401


async def main() -> None:
    print("=== Example 01: Sync vs Async File I/O Benchmark ===")

    payload = b"Hello, py-native-io high-performance kernel streams!\n" * 1000

    with tempfile.NamedTemporaryFile("w+b", delete=False) as sync_tmp:
        sync_filename = sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as async_tmp:
        async_filename = async_tmp.name

    f_sync = open(sync_filename, "w+b")  # noqa: SIM115
    f_async = open(async_filename, "w+b")  # noqa: SIM115

    # Benchmark synchronous write
    t0 = time.perf_counter()
    f_sync.write(payload)
    f_sync.flush()
    t_sync_write = (time.perf_counter() - t0) * 1000

    # Benchmark asynchronous write
    t0 = time.perf_counter()
    written = await f_async.awrite(payload)
    await f_async.aflush()
    t_async_write = (time.perf_counter() - t0) * 1000

    # Benchmark synchronous read
    f_sync.seek(0)
    t0 = time.perf_counter()
    sync_data = f_sync.read(1024)
    t_sync_read = (time.perf_counter() - t0) * 1000

    # Benchmark asynchronous read
    f_async.seek(0)
    t0 = time.perf_counter()
    async_data = await f_async.aread(1024)
    t_async_read = (time.perf_counter() - t0) * 1000

    f_sync.close()
    f_async.close()

    assert sync_data == async_data

    print(f"Sync File:  {sync_filename}")
    print(f"Async File: {async_filename}")
    print(f"Synchronous Write: {t_sync_write:.3f} ms")
    print(f"Asynchronous Write: {t_async_write:.3f} ms (wrote {written} bytes)")
    print(f"Synchronous Read:  {t_sync_read:.3f} ms (read {len(sync_data)} bytes)")
    print(f"Asynchronous Read: {t_async_read:.3f} ms (read {len(async_data)} bytes)")
    print("Success: Synchronous and Asynchronous file contents match!\n")


if __name__ == "__main__":
    asyncio.run(main())
