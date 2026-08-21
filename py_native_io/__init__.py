"""py-native-io: Native-first cross-platform asynchronous kernel I/O for Python."""

import logging

from py_native_io.base import AsyncIOBase, AsyncIOBaseMeta, AsyncIOStream
from py_native_io.buffered import (
    AsyncBufferedRandom,
    AsyncBufferedReader,
    AsyncBufferedWriter,
    AsyncTextIOWrapper,
)
from py_native_io.file import (
    DefaultFileIO,
    FallbackFileIO,
    LinuxURingFileIO,
    MacOSKQueueFileIO,
    NativeFileIO,
    WindowsIoRingFileIO,
    _ext,
)
from py_native_io.memory import AsyncBytesIO, AsyncStringIO
from py_native_io.patch import (
    AsyncStreamAdapter,
    ensure_async_stream,
    patch_python_io,
    patch_stream,
    patched_open,
    patched_socket_makefile,
    wrap_stream,
)
from py_native_io.socket import AsyncSocketIO

logger = logging.getLogger("py_native_io")

# Automatically trigger systemwide io class and function patching on package import
patch_python_io()

__all__ = [
    "AsyncBufferedRandom",
    "AsyncBufferedReader",
    "AsyncBufferedWriter",
    "AsyncBytesIO",
    "AsyncIOBase",
    "AsyncIOBaseMeta",
    "AsyncIOStream",
    "AsyncSocketIO",
    "AsyncStringIO",
    "AsyncStreamAdapter",
    "AsyncTextIOWrapper",
    "DefaultFileIO",
    "FallbackFileIO",
    "LinuxURingFileIO",
    "MacOSKQueueFileIO",
    "NativeFileIO",
    "WindowsIoRingFileIO",
    "_ext",
    "ensure_async_stream",
    "logger",
    "patch_python_io",
    "patch_stream",
    "patched_open",
    "patched_socket_makefile",
    "wrap_stream",
]
