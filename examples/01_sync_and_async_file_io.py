"""Example 01: OS Syscall Sync vs CPython Built-in Sync vs aiofiles vs Async Batch Benchmark."""

import argparse
import asyncio
import builtins
import logging
import os
import tempfile
import time
from collections.abc import Callable
from typing import Any

try:
    import aiofiles
except ImportError:
    aiofiles = None

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")

import py_native_io  # noqa: E402, F401
from py_native_io import aprint  # noqa: E402

BATCH_SIZE = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Example 01: OS Sync vs Built-in Sync vs aiofiles vs Async Batch Benchmark."
    )
    parser.add_argument(
        "--payload-size-kb",
        type=int,
        default=128,
        help="Payload size in KB per operation (default: 128 KB, max: 2048 KB).",
    )
    return parser.parse_args()


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


async def run_aiofiles_benchmark(
    aiofiles_filename: str, payload: bytes
) -> tuple[float, float, list[int], list[bytes]]:
    """Perform asynchronous file I/O operations using third-party aiofiles library."""
    if aiofiles is None:
        return 0.0, 0.0, [], []

    async with aiofiles.open(aiofiles_filename, "w+b") as f_aio:
        # Warmup write
        await f_aio.write(payload)
        await f_aio.flush()

        # 1. aiofiles Asynchronous Writes
        t0 = time.perf_counter()
        write_tasks = [f_aio.write(payload) for _ in range(BATCH_SIZE)]
        write_results = list(await asyncio.gather(*write_tasks))
        await f_aio.flush()
        t_aio_write_total = (time.perf_counter() - t0) * 1000

        # 2. aiofiles Asynchronous Reads
        await f_aio.seek(0)
        t0 = time.perf_counter()
        read_tasks = [f_aio.read(len(payload)) for _ in range(BATCH_SIZE)]
        aio_reads = list(await asyncio.gather(*read_tasks))
        t_aio_read_total = (time.perf_counter() - t0) * 1000

    return t_aio_write_total, t_aio_read_total, write_results, aio_reads


async def run_async_pipelined_benchmark(
    async_filename: str, payload: bytes
) -> tuple[float, float, list[int], list[bytes]]:
    """Perform asynchronous pipelined file I/O operations via awrite/aread + asyncio.gather."""
    f_async = open(async_filename, "w+b")  # noqa: SIM115

    # Warmup run to initialize persistent io_uring ring
    await f_async.awrite(payload)
    await f_async.aflush()

    # 1. Asynchronous Pipelined Writes
    t0 = time.perf_counter()
    write_tasks = [f_async.awrite(payload) for _ in range(BATCH_SIZE)]
    write_results = list(await asyncio.gather(*write_tasks))
    await f_async.aflush()
    t_async_write_total = (time.perf_counter() - t0) * 1000

    # 2. Asynchronous Pipelined Reads
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


async def run_async_batch_api_benchmark(
    batch_filename: str, payload: bytes
) -> tuple[float, float, list[int], list[bytes]]:
    """Perform asynchronous file I/O operations via io_uring batch API."""
    f_async = open(batch_filename, "w+b")  # noqa: SIM115

    # Warmup run to initialize persistent io_uring ring
    await f_async.awrite(payload)
    await f_async.aflush()

    # 1. Asynchronous Single-Syscall Batch Writes
    t0 = time.perf_counter()
    write_results = await f_async.awrite_batch([payload] * BATCH_SIZE)
    await f_async.aflush()
    t_batch_write_total = (time.perf_counter() - t0) * 1000

    # 2. Asynchronous Single-Syscall Batch Reads
    f_async.seek(0)
    t0 = time.perf_counter()
    async_batch_reads = await f_async.aread_batch([len(payload)] * BATCH_SIZE)
    t_batch_read_total = (time.perf_counter() - t0) * 1000

    f_async.close()

    return (
        t_batch_write_total,
        t_batch_read_total,
        write_results,
        async_batch_reads,
    )


async def main() -> None:
    args = parse_args()
    # Limit/clamp payload size between 1 KB and 2048 KB (2 MB)
    payload_size_kb = max(1, min(args.payload_size_kb, 2048))
    payload_bytes = payload_size_kb * 1024
    base_chunk = b"Hello, py-native-io high-performance kernel streams!\n"
    payload = (base_chunk * (payload_bytes // len(base_chunk) + 1))[:payload_bytes]
    total_vol_mb = (payload_bytes * BATCH_SIZE) / (1024 * 1024)

    print(
        f"=== Example 01: OS Sync vs Built-in Sync vs aiofiles vs Async Batch Benchmark\n"
        f"    ({BATCH_SIZE} ops, {payload_size_kb} KB/op, Total: {total_vol_mb:.2f} MB) ==="
    )

    with tempfile.NamedTemporaryFile("w+b", delete=False) as os_sync_tmp:
        os_sync_filename = os_sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as builtin_sync_tmp:
        builtin_sync_filename = builtin_sync_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as aiofiles_tmp:
        aiofiles_filename = aiofiles_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as async_tmp:
        async_filename = async_tmp.name

    with tempfile.NamedTemporaryFile("w+b", delete=False) as batch_tmp:
        batch_filename = batch_tmp.name

    # 1. Run OS Syscall Synchronous Baseline
    t_os_w, t_os_r, os_sync_reads = run_os_sync_benchmark(os_sync_filename, payload)

    # 2. Run CPython Built-in Synchronous Baseline
    t_builtin_w, t_builtin_r, builtin_sync_reads = run_builtin_sync_benchmark(
        builtin_sync_filename, payload
    )

    # 3. Run aiofiles Asynchronous Benchmark
    t_aio_w, t_aio_r, aio_write_results, aiofiles_reads = await run_aiofiles_benchmark(
        aiofiles_filename, payload
    )

    # 4. Run Asynchronous Pipelined Benchmark (awrite / aread)
    t_async_w, t_async_r, write_results, async_reads = await run_async_pipelined_benchmark(
        async_filename, payload
    )

    # 5. Run Asynchronous Batch API Benchmark (awrite_batch / aread_batch)
    t_batch_w, t_batch_r, batch_write_results, batch_reads = await run_async_batch_api_benchmark(
        batch_filename, payload
    )

    assert (
        len(os_sync_reads)
        == len(builtin_sync_reads)
        == len(async_reads)
        == len(batch_reads)
        == BATCH_SIZE
    )
    if aiofiles is not None:
        assert len(aiofiles_reads) == len(aio_write_results) == BATCH_SIZE
    assert len(write_results) == len(batch_write_results) == BATCH_SIZE

    print(f"OS Syscall Sync File:      {os_sync_filename}")
    print(f"CPython Built-in File:     {builtin_sync_filename}")
    if aiofiles is not None:
        print(f"aiofiles Async File:       {aiofiles_filename}")
    print(f"Async Pipelined File:      {async_filename}")
    print(f"Async Batch Ring File:     {batch_filename}\n")

    print(
        f"OS Syscall Sync {BATCH_SIZE} Writes Total:       {t_os_w:.3f} ms "
        f"({t_os_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"CPython Built-in Sync {BATCH_SIZE} Writes Total: {t_builtin_w:.3f} ms "
        f"({t_builtin_w / BATCH_SIZE:.3f} ms/op)"
    )
    if aiofiles is not None:
        print(
            f"aiofiles Async {BATCH_SIZE} Writes Total:        {t_aio_w:.3f} ms "
            f"({t_aio_w / BATCH_SIZE:.3f} ms/op)"
        )
    print(
        f"Async Pipelined {BATCH_SIZE} Writes Total:       {t_async_w:.3f} ms "
        f"({t_async_w / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Async Single-Syscall Batch Writes Total: {t_batch_w:.3f} ms "
        f"({t_batch_w / BATCH_SIZE:.3f} ms/op)"
    )

    print(
        f"\nOS Syscall Sync {BATCH_SIZE} Reads Total:        {t_os_r:.3f} ms "
        f"({t_os_r / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"CPython Built-in Sync {BATCH_SIZE} Reads Total:  {t_builtin_r:.3f} ms "
        f"({t_builtin_r / BATCH_SIZE:.3f} ms/op)"
    )
    if aiofiles is not None:
        print(
            f"aiofiles Async {BATCH_SIZE} Reads Total:         {t_aio_r:.3f} ms "
            f"({t_aio_r / BATCH_SIZE:.3f} ms/op)"
        )
    print(
        f"Async Pipelined {BATCH_SIZE} Reads Total:        {t_async_r:.3f} ms "
        f"({t_async_r / BATCH_SIZE:.3f} ms/op)"
    )
    print(
        f"Async Single-Syscall Batch Reads Total:  {t_batch_r:.3f} ms "
        f"({t_batch_r / BATCH_SIZE:.3f} ms/op)"
    )

    w_speedup_batch = ((t_builtin_w - t_batch_w) / t_builtin_w) * 100
    r_speedup_batch = ((t_builtin_r - t_batch_r) / t_builtin_r) * 100

    speedup_prints = [
        aprint(f"\nAsync Batch vs Built-in Sync Write Speedup: {w_speedup_batch:+.1f}%"),
        aprint(f"Async Batch vs Built-in Sync Read Speedup:  {r_speedup_batch:+.1f}%"),
    ]
    if aiofiles is not None:
        w_speedup_aio = ((t_aio_w - t_batch_w) / t_aio_w) * 100
        r_speedup_aio = ((t_aio_r - t_batch_r) / t_aio_r) * 100
        speedup_prints.extend(
            [
                aprint(f"Async Batch vs aiofiles Write Speedup:       {w_speedup_aio:+.1f}%"),
                aprint(f"Async Batch vs aiofiles Read Speedup:        {r_speedup_aio:+.1f}%"),
            ]
        )
    speedup_prints.append(
        aprint("Success: All batch benchmark operations completed successfully!\n")
    )

    # Asynchronously gather the final benchmark result prints using aprint
    await asyncio.gather(*speedup_prints)


if __name__ == "__main__":
    asyncio.run(main())
