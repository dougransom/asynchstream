"""Example 01: Synchronous and Asynchronous File I/O Benchmarking."""

import asyncio
import tempfile
import time

import py_native_io  # noqa: F401

ITERATIONS = 100


async def main() -> None:
    print(f"=== Example 01: Sync vs Async File I/O Benchmark ({ITERATIONS} iterations) ===")

    payload = b"Hello, py-native-io high-performance kernel streams!\n" * 1000

    with tempfile.NamedTemporaryFile("w+b", delete=False) as sync_tmp:
        sync_filename = sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as async_tmp:
        async_filename = async_tmp.name

    f_sync = open(sync_filename, "w+b")  # noqa: SIM115
    f_async = open(async_filename, "w+b")  # noqa: SIM115

    # Warmup run to initialize threads and persistent io_uring ring
    f_sync.write(payload)
    f_sync.flush()
    await f_async.awrite(payload)
    await f_async.aflush()

    # Benchmark synchronous writes
    sync_write_times = []
    for _ in range(ITERATIONS):
        f_sync.seek(0)
        t0 = time.perf_counter()
        f_sync.write(payload)
        f_sync.flush()
        sync_write_times.append((time.perf_counter() - t0) * 1000)

    # Benchmark asynchronous writes
    async_write_times = []
    for _ in range(ITERATIONS):
        f_async.seek(0)
        t0 = time.perf_counter()
        written = await f_async.awrite(payload)
        await f_async.aflush()
        async_write_times.append((time.perf_counter() - t0) * 1000)

    # Benchmark synchronous reads
    sync_read_times = []
    for _ in range(ITERATIONS):
        f_sync.seek(0)
        t0 = time.perf_counter()
        sync_data = f_sync.read(1024)
        sync_read_times.append((time.perf_counter() - t0) * 1000)

    # Benchmark asynchronous reads
    async_read_times = []
    for _ in range(ITERATIONS):
        f_async.seek(0)
        t0 = time.perf_counter()
        async_data = await f_async.aread(1024)
        async_read_times.append((time.perf_counter() - t0) * 1000)

    f_sync.close()
    f_async.close()

    assert sync_data == async_data

    avg_sync_w = sum(sync_write_times) / ITERATIONS
    avg_async_w = sum(async_write_times) / ITERATIONS
    avg_sync_r = sum(sync_read_times) / ITERATIONS
    avg_async_r = sum(async_read_times) / ITERATIONS

    print(f"Sync File:  {sync_filename}")
    print(f"Async File: {async_filename}")
    print(f"Synchronous Write Avg:  {avg_sync_w:.3f} ms/iter (min: {min(sync_write_times):.3f} ms)")
    min_async_w = min(async_write_times)
    print(
        f"Asynchronous Write Avg: {avg_async_w:.3f} ms/iter "
        f"(min: {min_async_w:.3f} ms, wrote {written} bytes)"
    )
    print(f"Synchronous Read Avg:   {avg_sync_r:.3f} ms/iter (min: {min(sync_read_times):.3f} ms)")
    print(
        f"Asynchronous Read Avg:  {avg_async_r:.3f} ms/iter (min: {min(async_read_times):.3f} ms)"
    )
    print("Success: Synchronous and Asynchronous file contents match!\n")


if __name__ == "__main__":
    asyncio.run(main())
