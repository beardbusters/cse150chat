#!/usr/bin/env python3
import argparse
import socket
import sys
import select

CRLF = "\r\n"

def parse_server(server_str: str):
    if ":" not in server_str:
        raise ValueError("Expected --server in form IP:port")
    host, port_str = server_str.rsplit(":", 1)
    return host, int(port_str)

def send_simple(server_host: str, server_port: int, payload: str) -> None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_host, server_port))
        s.sendall(payload.encode("utf-8"))
        # PROGRESS CHECK 2
        resp = recv_message(s)
        s.close()
        return resp
    except socket.error as e:
        print(f"Socket error: {e}", file=sys.stderr)

def send_register(client_id: str, client_port: int, server_host: str, server_port: int) -> None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_host, server_port))
        local_ip = s.getsockname()[0]

        payload = (
            f"REGISTER{CRLF}"
            f"clientID: {client_id}{CRLF}"
            f"IP: {local_ip}{CRLF}"
            f"Port: {client_port}{CRLF}"
            f"{CRLF}"
        )
        s.sendall(payload.encode("utf-8"))
        # PROGRESS CHECK 2
        resp = recv_message(s)
        s.close()
        return resp
    except socket.error as e:
        print(f"Socket error: {e}", file=sys.stderr)


# PROGRESS CHECK 2 


def recv_message(sock: socket.socket, timeout: float = 2.0, max_bytes: int = 65536) -> str:

    sock.setblocking(False)
    data = b""
    while True:
        rlist, _, _ = select.select([sock], [], [], timeout)
        if not rlist:
            # timeout
            break
        chunk = sock.recv(4096)
        if not chunk:
            # peer closed
            break
        data += chunk
        if len(data) >= max_bytes:
            break
        # stop once we have end-of-headers marker
        if b"\r\n\r\n" in data:
            break
    return data.decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, dest="client_id")
    ap.add_argument("--port", required=True, type=int, dest="client_port")
    ap.add_argument("--server", required=True, dest="server")
    args = ap.parse_args()

    try:
        server_host, server_port = parse_server(args.server)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    for line in sys.stdin:
        cmd = line.strip()

        if cmd == "/id":
            print(args.client_id)

        elif cmd == "/register":
            send_register(args.client_id, args.client_port, server_host, server_port)

        elif cmd == "/bridge":
            payload = (
                f"BRIDGE{CRLF}"
                f"clientID: {args.client_id}{CRLF}"
                f"{CRLF}"
            )
            send_simple(server_host, server_port, payload)

        else:
            # ignore unknown commands
            continue

    return 0

if __name__ == "__main__":
    raise SystemExit(main())


