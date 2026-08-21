"""Example 01: OS Syscall Sync vs CPython Built-in Sync vs Async Pipelined Queue Benchmarking."""

import asyncio
import builtins
import logging
import os
import tempfile
import time
from collections.abc import Callable
from typing import Any

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

import py_native_io  # noqa: E402, F401
from py_native_io import aprint  # noqa: E402

BATCH_SIZE = 100


def run_os_sync_benchmark(sync_filename: str, payload: bytes) -> tuple[float, float, list[bytes]]:
    """Perform synchronous sequential file I/O operations using direct OS C-level syscalls."""
    fd = os.open(sync_filename, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
    try:
        # Warmup write
        os.write(fd, payload)

        # 1. OS Syscall Synchronous Writes
        t0 = time.perf_counter()
        for _ in range(BATCH_SIZE):
            os.write(fd, payload)
        t_sync_write_total = (time.perf_counter() - t0) * 1000

        # 2. OS Syscall Synchronous Reads
        os.lseek(fd, 0, os.SEEK_SET)
        t0 = time.perf_counter()
        sync_reads = [os.read(fd, len(payload)) for _ in range(BATCH_SIZE)]
        t_sync_read_total = (time.perf_counter() - t0) * 1000
    finally:
        os.close(fd)

    return t_sync_write_total, t_sync_read_total, sync_reads


def run_builtin_sync_benchmark(
    builtin_filename: str, payload: bytes
) -> tuple[float, float, list[bytes]]:
    """Perform synchronous sequential file I/O operations using standard CPython built-in open()."""
    orig_open: Callable[..., Any] = getattr(builtins, "_orig_open", builtins.open)
    f = orig_open(builtin_filename, "w+b")
    try:
        # Warmup write
        f.write(payload)
        f.flush()

        # 1. CPython Built-in Synchronous Writes
        t0 = time.perf_counter()
        for _ in range(BATCH_SIZE):
            f.write(payload)
        f.flush()
        t_builtin_write_total = (time.perf_counter() - t0) * 1000

        # 2. CPython Built-in Synchronous Reads
        f.seek(0)
        t0 = time.perf_counter()
        builtin_reads = [f.read(len(payload)) for _ in range(BATCH_SIZE)]
        t_builtin_read_total = (time.perf_counter() - t0) * 1000
    finally:
        f.close()

    return t_builtin_write_total, t_builtin_read_total, builtin_reads


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


async def main() -> None:
    print(
        f"=== Example 01: OS Syscall Sync vs CPython Built-in Sync vs Async Pipelined Benchmark "
        f"({BATCH_SIZE} operations) ==="
    )

    payload = b"Hello, py-native-io high-performance kernel streams!\n" * 10

    with tempfile.NamedTemporaryFile("w+b", delete=False) as os_sync_tmp:
        os_sync_filename = os_sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as builtin_sync_tmp:
        builtin_sync_filename = builtin_sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as async_tmp:
        async_filename = async_tmp.name

    # 1. Run OS Syscall Synchronous Baseline
    t_os_w, t_os_r, os_sync_reads = run_os_sync_benchmark(os_sync_filename, payload)

    # 2. Run CPython Built-in Synchronous Baseline
    t_builtin_w, t_builtin_r, builtin_sync_reads = run_builtin_sync_benchmark(
        builtin_sync_filename, payload
    )

    # 3. Run Asynchronous Pipelined Benchmark
    t_async_w, t_async_r, write_results, async_reads = await run_async_benchmark(
        async_filename, payload
    )

    assert len(os_sync_reads) == len(builtin_sync_reads) == len(async_reads) == BATCH_SIZE
    assert len(write_results) == BATCH_SIZE

    print(f"OS Syscall Sync File:      {os_sync_filename}")
    print(f"CPython Built-in File:     {builtin_sync_filename}")
    print(f"Async Pipelined Ring File:  {async_filename}\n")

    print(
        f"OS Syscall Sync {BATCH_SIZE} Writes Total:       {t_os_w:.3f} ms "
        f"({t_os_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"CPython Built-in Sync {BATCH_SIZE} Writes Total: {t_builtin_w:.3f} ms "
        f"({t_builtin_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Asynchronous Pipelined {BATCH_SIZE} Writes Total: {t_async_w:.3f} ms "
        f"({t_async_w / BATCH_SIZE:.3f} ms/op)"
    )

    print(
        f"\nOS Syscall Sync {BATCH_SIZE} Reads Total:        {t_os_r:.3f} ms "
        f"({t_os_r / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"CPython Built-in Sync {BATCH_SIZE} Reads Total:  {t_builtin_r:.3f} ms "
        f"({t_builtin_r / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Asynchronous Pipelined {BATCH_SIZE} Reads Total:  {t_async_r:.3f} ms "
        f"({t_async_r / BATCH_SIZE:.3f} ms/op)"
    )

    w_speedup_builtin = ((t_builtin_w - t_async_w) / t_builtin_w) * 100
    r_speedup_builtin = ((t_builtin_r - t_async_r) / t_builtin_r) * 100

    # Asynchronously gather the final 3 benchmark result prints using aprint
    await asyncio.gather(
        aprint(f"\nAsync vs Built-in Sync Write Speedup: {w_speedup_builtin:+.1f}%"),
        aprint(f"Async vs Built-in Sync Read Speedup:  {r_speedup_builtin:+.1f}%"),
        aprint("Success: All batch benchmark operations completed successfully!\n"),
    )


if __name__ == "__main__":
    asyncio.run(main())
