#!/usr/bin/env python3
#Kent Young and Florian Horn Sanders
#CSE 150
import argparse
import select
import signal
import socket
import sys
from typing import Tuple #used for seperating ip and port

CRLF = "\r\n"
BUFFER_SIZE = 4096

#Seperates the ip from the port in the arugment
def parse_server(server_str: str) -> Tuple[str, int]:
    if ":" not in server_str:
        raise ValueError("Server must be in the form IP:PORT")
    ip, port_str = server_str.rsplit(":", 1)
    return ip, int(port_str)

#Builds register to send to server
def build_register(client_id: str, ip: str, port: int) -> str:
    return (
        "REGISTER" + CRLF
        + f"clientID: {client_id}" + CRLF
        + f"IP: {ip}" + CRLF
        + f"Port: {port}" + CRLF
        + CRLF
    )

#Builds bridge to send to server
def build_bridge(client_id: str) -> str:
    return (
        "BRIDGE" + CRLF
        + f"clientID: {client_id}" + CRLF
        + CRLF
    )

def build_chat(client_id: str, ip: str, port: int) -> str:
    return (
        "CHAT" + CRLF
        + f"clientID: {client_id}" + CRLF
        + f"IP: {ip}" + CRLF
        + f"Port: {port}" + CRLF
        + CRLF
    )

def recv_all(sock: socket.socket) -> str:
    data = b""
    while True:
        try:
            chunk = sock.recv(BUFFER_SIZE)
        except socket.error:
            return ""
        if not chunk:
            break
        data += chunk
        if len(chunk) < BUFFER_SIZE:
            break
    return data.decode("utf-8", errors="replace")

def send_to_server(server_ip: str, server_port: int, msg: str) -> str:
    data = msg.encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((server_ip, server_port))
        s.sendall(data)
        return recv_all(s)

def build_quit() -> str:
    return "QUIT" + CRLF + CRLF

def build_text_message(text: str) -> str:
    return text + CRLF

def parse_message(raw: str):
    parts = raw.split(CRLF + CRLF, 1) #splits the header from the pody
    header_part = parts[0]
    body = parts[1] if len(parts) > 1 else "" #if parts is 1, then there is no body

    lines = header_part.split(CRLF) #splits up the lines between the CRLF
    first_line = lines[0].strip() if lines else "" #gets the protocol message
    headers = {}

    for line in lines[1:]: #gets the values from each header
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()

    return first_line, headers, body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Client ID")
    parser.add_argument("--port", required=True, type=int, help="Client port number (int)")
    parser.add_argument("--server", required=True, help="Server address in the form IP:PORT")
    args = parser.parse_args()

    client_id = args.id
    client_port = args.port

    try:
        server_ip, server_port = parse_server(args.server)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_ip = '127.0.0.1' #Always on localhost

    peer_id = ""
    peer_ip = ""
    peer_port = 0

    print(f"{client_id} running on {client_ip}:{client_port}")

    in_chat = False
    peer_sock = None

    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind((client_ip, client_port))
    listen_sock.listen(1)

    def clean_exit(signum=None, frame=None):
        nonlocal peer_sock, listen_sock #calls the outside variable instead of local variable
        try:
            if peer_sock is not None:
                peer_sock.close()
        except:
            pass
        try:
            listen_sock.close()
        except:
            pass
        sys.exit()
    signal.signal(signal.SIGINT, clean_exit)

    while True:
        read_list = [sys.stdin, listen_sock] #adds listening to keyboard and new connections
        if peer_sock is not None:
            read_list.append(peer_sock) #adds listening to peer socket
        try:
            readable, _, _ = select.select(read_list, [], []) #pauses until one of the inputs is given
        except KeyboardInterrupt:
            clean_exit()
        except EOFError:
            break
        for ready in readable:
            if ready == sys.stdin: #Keyboard input
                cmd = sys.stdin.readline()
                if not cmd:
                    clean_exit()
                
                cmd = cmd.strip()

                if cmd == "":
                    continue

                if not in_chat:

                    if cmd == "/id":
                        print(client_id)

                    elif cmd == "/register":
                        try:
                            msg = build_register(client_id, client_ip, client_port) #builds message to send
                            response = send_to_server(server_ip, server_port, msg) #sends message and gets the response
                            if response:
                                first_line, headers, body = parse_message(response) #gets us the headers and first line of the REGACK
                        except socket.error:
                            print("Socket Error", file=sys.stderr)

                    elif cmd == "/bridge":
                        try:
                            msg = build_bridge(client_id) #builds message to send to server
                            response = send_to_server(server_ip, server_port, msg) #sends message and gets the response
                            if response:
                                first_line, headers, body = parse_message(response) #gets us the headers and first line of BRIDGEACK
                                if first_line == "BRIDGEACK": #Assigns all of the information even if it is empty or not
                                    peer_id = headers.get("clientID", "")
                                    peer_ip = headers.get("IP", "")
                                    port_str = headers.get("Port", "")
                                    peer_port = int(port_str) if port_str.isdigit() else 0
                                else:
                                    print("Malformed incoming message", file=sys.stderr)
                        except socket.error:
                            print("Socket Error", file=sys.stderr)
                    
                    elif cmd == "/chat": #initializing chat
                        if peer_ip == "" or peer_port == 0:
                            print("No peer info available, run /bridge first", file=sys.stderr)
                            continue
                        try:
                            peer_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            peer_sock.connect((peer_ip, peer_port))
                            chat_msg = build_chat(client_id, client_ip, client_port)
                            peer_sock.sendall(chat_msg.encode("utf-8"))
                            in_chat = True
                        except socket.error:
                            print("Socket Error", file=sys.stderr)
                            if peer_sock is not None:
                                peer_sock.close()
                                peer_sock = None
                    
                    elif cmd == "/quit": #quitting outside of chat
                        clean_exit()
                        
                    else:
                        print("Error: unknown command (use /id, /register, /bridge, /chat)")

                else:
                    if cmd == "/quit": #quiiting inside of chat
                        try:
                            if peer_sock is not None:
                                peer_sock.sendall(build_quit().encode("utf-8"))
                        except socket.error:
                            pass
                        clean_exit()

                    else:
                        try:
                            if peer_sock is not None:
                                peer_sock.sendall(build_text_message(cmd).encode("utf-8"))
                        except socket.error:
                            print("Socket error", file=sys.stderr)
                            clean_exit()

            elif ready == listen_sock: #gets a message during wait stage
                try:
                    conn, addr = listen_sock.accept()
                    raw = recv_all(conn)

                    if not raw:
                        conn.close()
                        continue
                    first_line, headers, body = parse_message(raw)
                    if first_line == "CHAT": #initial chat message
                        peer_id = headers.get("clientID", "")
                        peer_ip = headers.get("IP", "")
                        port_str = headers.get("Port", "")
                        peer_port = int(port_str) if port_str.isdigit() else 0

                        print(f"Incoming chat request from {peer_id}")
                        print(f"{peer_ip}:{peer_port}")
                        if peer_sock is not None:
                            peer_sock.close()

                        peer_sock = conn
                        in_chat = True
                    else:
                        print("Incorrect format for incoming message", file=sys.stderr)
                        conn.close()

                except socket.error:
                    print("Socket Error", file=sys.stderr)
                    

            elif peer_sock is not None and ready == peer_sock:
                try:
                    data = peer_sock.recv(BUFFER_SIZE) #gets the message from other client

                    if not data:
                        peer_sock.close()
                        peer_sock = None
                        in_chat = False
                        continue

                    raw = data.decode("utf-8", errors = "replace")

                    if raw.startswith("QUIT"): #Quit message from other client
                        if peer_sock is not None:
                            peer_sock.close()
                        peer_sock = None
                        clean_exit()
                    else:
                        print(raw.strip()) #Prints message from other client
                
                except socket.error:
                    print("Socket Error", file = sys.stderr)
                    if peer_sock is not None:
                        peer_sock.close()
                    peer_sock = None
                    in_chat = False

if __name__ == "__main__":
    main()