#!/usr/bin/env python3
import argparse
import socket
import struct

MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")

parser = argparse.ArgumentParser()
parser.add_argument("--port-file", required=True)
parser.add_argument("--mode", choices=["valid", "truncated"], default="valid")
args = parser.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 0))
with open(args.port_file, "w", encoding="ascii") as handle:
    handle.write(str(sock.getsockname()[1]))

request, peer = sock.recvfrom(2048)
motd = b"MCPE;Fixture;999;1.99.0;0;4;12345;Fixture World;Survival;1;19132;19133;0;1;0;"
declared_length = len(motd) + (8 if args.mode == "truncated" else 0)
response = b"\x1c" + request[1:9] + struct.pack(">Q", 12345) + MAGIC + struct.pack(">H", declared_length) + motd
sock.sendto(response, peer)
sock.close()
