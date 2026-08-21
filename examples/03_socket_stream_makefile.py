"""Example 03: Asynchronous Socket Stream Creation via socket.makefile()."""

import asyncio
import logging
import socket

import py_native_io  # noqa: F401

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    _ = await reader.read(100)
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nHello Socket!")
    await writer.drain()
    writer.close()


async def main() -> None:
    print("=== Example 03: Async Socket Stream via socket.makefile() ===")

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr, port = server.sockets[0].getsockname()

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect((addr, port))

    # socket.makefile() returns AsyncSocketIO-backed stream
    stream = client_sock.makefile("r+b")
    assert isinstance(stream, py_native_io.AsyncIOStream)

    await stream.awrite(b"GET / HTTP/1.1\r\n\r\n")
    response = await stream.aread(256)
    print("Received Response:")
    print(response.decode("utf-8"))

    stream.close()
    client_sock.close()
    server.close()
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
