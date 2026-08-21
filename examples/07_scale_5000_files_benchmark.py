"""Example 07: Scalability & Performance Benchmark across 5,000 Files."""

import asyncio
import logging
import os
import shutil
import tempfile
import time

import py_native_io  # noqa: F401

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

NUM_FILES = 5000
PAYLOAD = b"High-performance py-native-io kernel ring stream payload\n" * 10


def run_sync_benchmark(temp_dir: str) -> tuple[float, float]:
    sync_dir = os.path.join(temp_dir, "sync")
    os.makedirs(sync_dir, exist_ok=True)

    file_paths = [os.path.join(sync_dir, f"file_{i}.bin") for i in range(NUM_FILES)]

    # 1. Sync Write Benchmark
    t0 = time.perf_counter()
    for path in file_paths:
        f = open(path, "w+b")  # noqa: SIM115
        f.write(PAYLOAD)
        f.flush()
        f.close()
    t_sync_write = (time.perf_counter() - t0) * 1000

    # 2. Sync Read Benchmark
    t0 = time.perf_counter()
    for path in file_paths:
        f = open(path, "rb")  # noqa: SIM115
        _data = f.read()
        f.close()
    t_sync_read = (time.perf_counter() - t0) * 1000

    return t_sync_write, t_sync_read


async def write_async_file(path: str) -> None:
    f = open(path, "w+b")  # noqa: SIM115
    await f.awrite(PAYLOAD)
    await f.aflush()
    f.close()


async def read_async_file(path: str) -> bytes:
    f = open(path, "rb")  # noqa: SIM115
    data = await f.aread()
    f.close()
    return data


async def run_async_benchmark(temp_dir: str) -> tuple[float, float]:
    async_dir = os.path.join(temp_dir, "async")
    os.makedirs(async_dir, exist_ok=True)

    file_paths = [os.path.join(async_dir, f"file_{i}.bin") for i in range(NUM_FILES)]

    # 1. Async Concurrent Write Benchmark (batched in chunks of 500)
    t0 = time.perf_counter()
    chunk_size = 500
    for i in range(0, NUM_FILES, chunk_size):
        chunk_paths = file_paths[i : i + chunk_size]
        await asyncio.gather(*(write_async_file(p) for p in chunk_paths))
    t_async_write = (time.perf_counter() - t0) * 1000

    # 2. Async Concurrent Read Benchmark (batched in chunks of 500)
    t0 = time.perf_counter()
    for i in range(0, NUM_FILES, chunk_size):
        chunk_paths = file_paths[i : i + chunk_size]
        _results = await asyncio.gather(*(read_async_file(p) for p in chunk_paths))
    t_async_read = (time.perf_counter() - t0) * 1000

    return t_async_write, t_async_read


async def main() -> None:
    print(f"=== Example 07: 5,000 Files Scalability Benchmark ({NUM_FILES} files) ===")

    base_dir = tempfile.mkdtemp(prefix="pynativeio_bench_")
    try:
        print(f"Temporary Directory: {base_dir}")

        # Run Synchronous Benchmark
        print("Running 5,000 files synchronous benchmark...")
        sync_write_ms, sync_read_ms = run_sync_benchmark(base_dir)

        # Run Asynchronous Benchmark
        print("Running 5,000 files asynchronous concurrent benchmark...")
        async_write_ms, async_read_ms = await run_async_benchmark(base_dir)

        sync_w_pf = sync_write_ms / NUM_FILES
        async_w_pf = async_write_ms / NUM_FILES
        sync_r_pf = sync_read_ms / NUM_FILES
        async_r_pf = async_read_ms / NUM_FILES

        print("\n--- Benchmark Results (5,000 Files) ---")
        print(f"Synchronous 5,000 Writes:  {sync_write_ms:8.2f} ms ({sync_w_pf:.3f} ms/file)")
        print(f"Asynchronous 5,000 Writes: {async_write_ms:8.2f} ms ({async_w_pf:.3f} ms/file)")
        print(f"Synchronous 5,000 Reads:   {sync_read_ms:8.2f} ms ({sync_r_pf:.3f} ms/file)")
        print(f"Asynchronous 5,000 Reads:  {async_read_ms:8.2f} ms ({async_r_pf:.3f} ms/file)")

        write_speedup = ((sync_write_ms - async_write_ms) / sync_write_ms) * 100
        read_speedup = ((sync_read_ms - async_read_ms) / sync_read_ms) * 100
        print(f"Async Write Speedup: {write_speedup:+.1f}%")
        print(f"Async Read Speedup:  {read_speedup:+.1f}%")

    finally:
        print(f"\nCleaning up 5,000 files in {base_dir}...")
        shutil.rmtree(base_dir, ignore_errors=True)
        print("Cleanup completed successfully! All temporary files deleted.")


if __name__ == "__main__":
    asyncio.run(main())
