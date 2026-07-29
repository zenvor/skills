#!/usr/bin/env python3
import argparse
import secrets
import socket
import struct
import sys
import time

MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a read-only RakNet unconnected ping to a Bedrock server")
    parser.add_argument("host")
    parser.add_argument("port", nargs="?", type=int, default=19132)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    packet = (
        b"\x01"
        + struct.pack(">Q", int(time.time() * 1000))
        + MAGIC
        + struct.pack(">Q", secrets.randbits(64))
    )
    addresses = socket.getaddrinfo(args.host, args.port, type=socket.SOCK_DGRAM)
    last_error = None
    protocol_errors = []

    for family, socktype, protocol, _, destination in addresses:
        sock = socket.socket(family, socktype, protocol)
        sock.settimeout(args.timeout)
        started = time.perf_counter()
        try:
            sock.sendto(packet, destination)
            data, peer = sock.recvfrom(4096)
            elapsed_ms = (time.perf_counter() - started) * 1000
        except OSError as exc:
            last_error = exc
            continue
        finally:
            sock.close()

        if not data or data[0] != 0x1C:
            protocol_errors.append(f"{destination}: unexpected response type {data[:1].hex() or 'empty'}")
            continue
        if len(data) < 35 or data[17:33] != MAGIC:
            protocol_errors.append(f"{destination}: malformed RakNet pong header")
            continue

        declared_length = struct.unpack(">H", data[33:35])[0]
        if len(data) < 35 + declared_length:
            protocol_errors.append(
                f"{destination}: truncated MOTD, declared {declared_length} bytes, received {len(data) - 35}"
            )
            continue
        payload = data[35 : 35 + declared_length].decode("utf-8", "replace")
        fields = payload.split(";")
        labels = [
            "edition",
            "motd",
            "protocol",
            "version",
            "online_players",
            "max_players",
            "server_guid",
            "level_name",
            "game_mode",
            "game_mode_numeric",
            "ipv4_port",
            "ipv6_port",
        ]
        print(f"peer={peer[0]}:{peer[1]}")
        print(f"rtt_ms={elapsed_ms:.1f}")
        for label, value in zip(labels, fields):
            print(f"{label}={value}")
        print(f"raw_motd={payload}")
        return 0

    for error in protocol_errors:
        print(error, file=sys.stderr)
    if protocol_errors:
        return 2
    print(f"no UDP response: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
