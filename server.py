#!/usr/bin/env python3
# this is the server code file for the chat program 
# w26

import argparse
import os
import select
import signal
import socket
import sys

CRLF = "\r\n"
END1 = b"\r\n\r\n"
END2 = b"\n\n"
DB_FILE = "server_clients.db"


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_clients() -> list[dict]:
    clients = []
    if not os.path.exists(DB_FILE):
        return clients
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # format: clientID<TAB>IP<TAB>Port
                parts = line.split("\t")
                if len(parts) != 3:
                    continue
                cid, ip, port_s = parts
                try:
                    port = int(port_s)
                except ValueError:
                    continue
                clients.append({"clientID": cid, "IP": ip, "Port": port})
    except OSError:
        pass
    return clients


def save_clients(clients: list[dict]) -> None:
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for c in clients:
            f.write(f"{c['clientID']}\t{c['IP']}\t{c['Port']}\n")
    os.replace(tmp, DB_FILE)


def upsert_client(clientID: str, ip: str, port: int) -> None:
    clients = load_clients()
    found = False
    for c in clients:
        if c["clientID"] == clientID:
            c["IP"] = ip
            c["Port"] = port
            found = True
            break
    if not found:
        clients.append({"clientID": clientID, "IP": ip, "Port": port})
    save_clients(clients)


def choose_peer(requester_id: str) -> dict:
    """
    Choose a peer for requester_id.
    Policy here: first client in DB that is not requester.
    If you want 'most recent other client', reverse iteration.
    """
    clients = load_clients()
    for c in clients:
        if c["clientID"] != requester_id:
            return c
    return {"clientID": "", "IP": "", "Port": ""}


def parse_message(raw: bytes) -> tuple[str, dict]:
    """
    Returns (message_type, headers_dict).
    Expects:
      TYPE\r\n
      key: value\r\n
      ...
      \r\n
    Also tolerates \n newlines.
    """
    text = raw.decode("utf-8", errors="replace")
    # normalize newlines to \n for parsing
    text = text.replace("\r\n", "\n")
    parts = text.split("\n\n", 1)
    head = parts[0]
    lines = [ln.strip() for ln in head.split("\n") if ln.strip() != ""]
    if not lines:
        return "", {}

    msg_type = lines[0].strip()
    headers = {}
    for ln in lines[1:]:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        headers[k.strip()] = v.strip()
    return msg_type, headers


def build_regack(clientID: str, ip: str, port: int) -> str:
    # Adjust header names/order if PDF requires exact ordering
    return (
        f"REGACK{CRLF}"
        f"clientID: {clientID}{CRLF}"
        f"IP: {ip}{CRLF}"
        f"Port: {port}{CRLF}"
        f"Status: registered{CRLF}"
        f"{CRLF}"
    )


def build_bridgeack(peer: dict) -> str:
    # peer may contain empty values if no other client exists
    return (
        f"BRIDGEACK{CRLF}"
        f"clientID: {peer.get('clientID','')}{CRLF}"
        f"IP: {peer.get('IP','')}{CRLF}"
        f"Port: {peer.get('Port','')}{CRLF}"
        f"{CRLF}"
    )


def recv_one_request(conn: socket.socket, timeout: float = 2.0, max_bytes: int = 65536) -> bytes:
    """
    Non-persistent protocol: receive one message then return.
    Stops when we see end-of-headers (\r\n\r\n or \n\n), peer closes, timeout, or max_bytes.
    """
    conn.setblocking(False)
    buf = b""
    while True:
        r, _, _ = select.select([conn], [], [], timeout)
        if not r:
            break
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) >= max_bytes:
            break
        if END1 in buf or END2 in buf:
            break
    return buf


def handle_request(conn: socket.socket, addr: tuple) -> None:
    raw = recv_one_request(conn)
    msg_type, headers = parse_message(raw)

    if msg_type not in ("REGISTER", "BRIDGE"):
        eprint("Malformed incoming message")
        try:
            conn.close()
        finally:
            # strict behavior: exit entire server on malformed message
            os._exit(1)

    if msg_type == "REGISTER":
        cid = headers.get("clientID", "")
        ip = headers.get("IP", "")
        port_s = headers.get("Port", "")
        try:
            port = int(port_s)
        except ValueError:
            eprint("Malformed incoming message")
            try:
                conn.close()
            finally:
                os._exit(1)

        upsert_client(cid, ip, port)

        # stdout log line (exact formatting may need to match PDF)
        print(f"REGISTER: {cid} from {ip}:{port} received")

        resp = build_regack(cid, ip, port)
        conn.sendall(resp.encode("utf-8"))
        conn.close()
        return

    # BRIDGE
    cid = headers.get("clientID", "")
    peer = choose_peer(cid)

    # stdout log line (exact formatting may need to match PDF)
    if peer.get("clientID", ""):
        print(
            f"BRIDGE: {cid} from {peer.get('clientID')} "
            f"({peer.get('IP')}:{peer.get('Port')}) received"
        )
    else:
        print(f"BRIDGE: {cid} received (no peer)")

    resp = build_bridgeack(peer)
    conn.sendall(resp.encode("utf-8"))
    conn.close()


def print_info() -> None:
    clients = load_clients()
    for c in clients:
        print(f"{c['clientID']} {c['IP']}:{c['Port']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, type=int)
    args = ap.parse_args()

    # clean shutdown on Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", args.port))
    lsock.listen(50)
    lsock.setblocking(False)

    # pick a “display IP” 
    display_ip = "127.0.0.1"
    print(f"Server listening on {display_ip}:{args.port}")

    while True:
        rlist = [lsock, sys.stdin]
        readable, _, _ = select.select(rlist, [], [], 0.5)

        for r in readable:
            if r is lsock:
                conn, addr = lsock.accept()
                # non-persistent: handle immediately, close per request
                handle_request(conn, addr)

            elif r is sys.stdin:
                line = sys.stdin.readline()
                if not line:
                    continue
                cmd = line.strip()
                if cmd == "/info":
                    print_info()
                # ignore unknown stdin commands

    return 0


if __name__ == "__main__":
    raise SystemExit(main())