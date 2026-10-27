#!/usr/bin/env python3
"""Read-only local connection attribution and optional verified IMAP probes."""
import argparse
import datetime
import ipaddress
import json
import pathlib
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the controller's authentication to a redirected host.
        return None


def connections(config, target):
    controller = json.loads(config.read_text()).get('experimental', {}).get('clash_api', {})
    endpoint = controller.get('external_controller', '')
    url = urllib.parse.urlsplit('http://' + endpoint)
    if not url.hostname or not ipaddress.ip_address(url.hostname).is_loopback:
        raise ValueError('Controller must use a numeric loopback address')
    if url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('Unexpected controller address format')
    request = urllib.request.Request('http://' + endpoint + '/connections')
    if controller.get('secret'):
        request.add_header('Authorization', 'Bearer ' + controller['secret'])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=5) as response:
        data = json.load(response)
    matches = []
    for item in data.get('connections', []):
        meta = item.get('metadata', {})
        if meta.get('destinationIP') == target:
            matches.append({
                'id': item.get('id'), 'start': item.get('start'),
                'process': meta.get('processPath'), 'host': meta.get('host'),
                'ip': meta.get('destinationIP'), 'port': meta.get('destinationPort'),
                'chains': item.get('chains'),
                'upload': item.get('upload'), 'download': item.get('download'),
            })
    return matches


def exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError('Unexpected SOCKS EOF')
        data += chunk
    return data


def probe_imap(host, socks_port=None):
    address = ('127.0.0.1', socks_port) if socks_port else (host, 993)
    with socket.create_connection(address, timeout=7) as raw:
        raw.settimeout(7)
        if socks_port:
            raw.sendall(b'\x05\x01\x00')
            if exact(raw, 2) != b'\x05\x00':
                raise ConnectionError('SOCKS no-auth negotiation failed')
            domain = host.encode('idna')
            if not 1 <= len(domain) <= 255:
                raise ValueError('Invalid SOCKS domain length')
            raw.sendall(b'\x05\x01\x00\x03' + bytes([len(domain)]) + domain + (993).to_bytes(2, 'big'))
            reply = exact(raw, 4)
            if reply[:3] != b'\x05\x00\x00':
                raise ConnectionError('SOCKS CONNECT failed')
            if reply[3] == 1:
                length = 4
            elif reply[3] == 4:
                length = 16
            elif reply[3] == 3:
                length = exact(raw, 1)[0]
            else:
                raise ConnectionError('Unexpected SOCKS address type')
            exact(raw, length + 2)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
            with tls.makefile('rb') as stream:
                greeting = stream.readline(8193)
                if len(greeting) > 8192 or not greeting.startswith(b'* OK ') or not greeting.endswith(b'\n'):
                    raise ConnectionError('Unexpected IMAP greeting')
                tls.sendall(b'a1 CAPABILITY\r\n')
                for _ in range(25):
                    line = stream.readline(8193)
                    if not line or len(line) > 8192 or not line.endswith(b'\n'):
                        raise ConnectionError('Invalid IMAP response')
                    if line.startswith(b'a1 '):
                        if not line.startswith(b'a1 OK '):
                            raise ConnectionError('IMAP CAPABILITY rejected')
                        return {'path': 'socks' if socks_port else 'tun-or-system',
                                'tls': tls.version(), 'certificate_verified': True,
                                'greeting_ok': True, 'capability_ok': True}
                raise ConnectionError('Too many IMAP response lines')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=pathlib.Path, default=pathlib.Path.home() / 'Library/Application Support/v2rayN/binConfigs/configPre.json')
    parser.add_argument('--target-ip', required=True, type=ipaddress.ip_address)
    parser.add_argument('--samples', type=int, default=1)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--imap-host')
    parser.add_argument('--socks-port', type=int, default=10808)
    args = parser.parse_args()
    if not 1 <= args.samples <= 20 or not 0 <= args.interval <= 60:
        parser.error('samples must be 1..20 and interval 0..60 seconds')
    if not 1 <= args.socks_port <= 65535:
        parser.error('socks-port must be 1..65535')
    failed = False
    for index in range(args.samples):
        if index:
            time.sleep(args.interval)
        try:
            result = connections(args.config, str(args.target_ip))
            print(json.dumps({'time': datetime.datetime.now().astimezone().isoformat(), 'connections': result}, ensure_ascii=False), flush=True)
        except Exception as error:
            print('Connection query failed: ' + type(error).__name__, file=sys.stderr)
            failed = True
    if args.imap_host:
        for port in (None, args.socks_port):
            try:
                print(json.dumps(probe_imap(args.imap_host, port)), flush=True)
            except Exception as error:
                print(('SOCKS' if port else 'TUN/system') + ' probe failed: ' + type(error).__name__, file=sys.stderr)
                failed = True
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
