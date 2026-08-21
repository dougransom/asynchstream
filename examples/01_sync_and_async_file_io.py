"""Example 01: Synchronous vs Asynchronous Batch Queue File I/O Benchmarking."""

import asyncio
import logging
import tempfile
import time

import py_native_io  # noqa: F401

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

BATCH_SIZE = 100


def run_sync_benchmark(sync_filename: str, payload: bytes) -> tuple[float, float, list[bytes]]:
    """Perform synchronous sequential file I/O operations outside event loop."""
    with open(sync_filename, "w+b") as f_sync:
        # Warmup write
        f_sync.write(payload)
        f_sync.flush()

        # 1. Synchronous Sequential Writes
        t0 = time.perf_counter()
        for _ in range(BATCH_SIZE):
            f_sync.write(payload)
            f_sync.flush()
        t_sync_write_total = (time.perf_counter() - t0) * 1000

        # 2. Synchronous Sequential Reads
        f_sync.seek(0)
        t0 = time.perf_counter()
        sync_reads = [f_sync.read(len(payload)) for _ in range(BATCH_SIZE)]
        t_sync_read_total = (time.perf_counter() - t0) * 1000

    return t_sync_write_total, t_sync_read_total, sync_reads


async def run_async_benchmark(
    async_filename: str, payload: bytes
) -> tuple[float, float, list[int], list[bytes]]:
    """Perform asynchronous pipelined file I/O operations via io_uring submission batching."""
    f_async = open(async_filename, "w+b")  # noqa: SIM115

    # Warmup run to initialize persistent io_uring ring
    await f_async.awrite(payload)
    await f_async.aflush()

    # 1. Asynchronous Pipelined Writes
    # Enqueue ALL BATCH_SIZE write tasks onto kernel submission queue concurrently
    t0 = time.perf_counter()
    write_tasks = [f_async.awrite(payload) for _ in range(BATCH_SIZE)]
    write_results = list(await asyncio.gather(*write_tasks))
    await f_async.aflush()
    t_async_write_total = (time.perf_counter() - t0) * 1000

    # 2. Asynchronous Pipelined Reads
    # Enqueue ALL BATCH_SIZE read tasks onto kernel submission queue concurrently
    f_async.seek(0)
    t0 = time.perf_counter()
    read_tasks = [f_async.aread(len(payload)) for _ in range(BATCH_SIZE)]
    async_reads = list(await asyncio.gather(*read_tasks))
    t_async_read_total = (time.perf_counter() - t0) * 1000

    f_async.close()

    return (
        t_async_write_total,
        t_async_read_total,
        write_results,
        async_reads,
    )


def main() -> None:
    print(
        f"=== Example 01: Sync Sequential vs Async Pipelined Queue Benchmark "
        f"({BATCH_SIZE} operations) ==="
    )

    payload = b"Hello, py-native-io high-performance kernel streams!\n" * 10

    with tempfile.NamedTemporaryFile("w+b", delete=False) as sync_tmp:
        sync_filename = sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as async_tmp:
        async_filename = async_tmp.name

    # Run Synchronous Baseline
    t_sync_w, t_sync_r, sync_reads = run_sync_benchmark(sync_filename, payload)

    # Run Asynchronous Pipelined Benchmark
    t_async_w, t_async_r, write_results, async_reads = asyncio.run(
        run_async_benchmark(async_filename, payload)
    )

    assert len(sync_reads) == len(async_reads) == BATCH_SIZE
    assert len(write_results) == BATCH_SIZE

    print(f"Sync File:  {sync_filename}")
    print(f"Async File: {async_filename}\n")
    print(
        f"Synchronous Sequential {BATCH_SIZE} Writes Total: {t_sync_w:.3f} ms "
        f"({t_sync_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Asynchronous Pipelined {BATCH_SIZE} Writes Total: {t_async_w:.3f} ms "
        f"({t_async_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Synchronous Sequential {BATCH_SIZE} Reads Total:  {t_sync_r:.3f} ms "
        f"({t_sync_r / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Asynchronous Pipelined {BATCH_SIZE} Reads Total:  {t_async_r:.3f} ms "
        f"({t_async_r / BATCH_SIZE:.3f} ms/op)"
    )

    w_speedup = ((t_sync_w - t_async_w) / t_sync_w) * 100
    r_speedup = ((t_sync_r - t_async_r) / t_sync_r) * 100
    print(f"\nAsync Pipelined Ring Write Speedup: {w_speedup:+.1f}%")
    print(f"Async Pipelined Ring Read Speedup:  {r_speedup:+.1f}%")
    print("Success: Synchronous and Asynchronous batch operations completed successfully!\n")


if __name__ == "__main__":
    main()
