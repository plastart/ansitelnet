"""
Telnet-IAC und ZModem-Protokoll-Hilfsfunktionen (kein curses, kein subprocess).
"""
from __future__ import annotations
import select
import socket
import time

# ── Telnet ────────────────────────────────────────────────────────────────────
IAC    = 0xFF
DONT   = 0xFE
DO     = 0xFD
WONT   = 0xFC
WILL   = 0xFB
SB     = 0xFA
SE     = 0xF0
BINARY = 0x00   # RFC 856
NAWS   = 0x1F   # RFC 1073 – Negotiate About Window Size

# ── ZModem ────────────────────────────────────────────────────────────────────
ZMODEM_TRIGGERS = [
    (b'**\x18B', 'hex'),    # ZPAD ZPAD ZDLE ZHEX
    (b'*\x18A',  'bin'),    # ZPAD ZDLE ZBIN
    (b'*\x18C',  'bin32'),  # ZPAD ZDLE ZBIN32
]
MAX_TRIGGER_LEN = max(len(t) for t, _ in ZMODEM_TRIGGERS)

# Frame-Typen (rohe Integer, unabhängig von Encoding)
ZRQINIT = 0   # Sender will senden  → rz starten
ZRINIT  = 1   # Sender will empfang → sz starten
ZFILE   = 4   # Datei-Header (BBS sendet direkt nach Retry)


def to_utf8(data: bytes) -> bytes:
    return data.decode('cp437', errors='replace').encode()


class IACStripper:
    """Entfernt IAC-Sequenzen aus Binärstrom; puffert über Chunk-Grenzen."""

    def __init__(self) -> None:
        self._p = b''

    def feed(self, data: bytes) -> bytes:
        data = self._p + data
        self._p = b''
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != IAC:
                out.append(b)
                i += 1
            elif i + 1 >= len(data):
                self._p = bytes([IAC])
                break
            else:
                nxt = data[i + 1]
                if nxt == IAC:
                    out.append(IAC)
                    i += 2
                elif nxt in (WILL, WONT, DO, DONT):
                    if i + 2 >= len(data):
                        self._p = data[i:]
                        break
                    i += 3
                elif nxt == SB:
                    end = data.find(bytes([IAC, SE]), i + 2)
                    if end < 0:
                        self._p = data[i:]
                        break
                    i = end + 2
                else:
                    i += 2
        return bytes(out)


def send_naws(sock: socket.socket, w: int, h: int) -> None:
    """WILL NAWS + SB NAWS Fenstergröße an Server senden (RFC 1073)."""
    try:
        sock.sendall(bytes([
            IAC, WILL, NAWS,
            IAC, SB, NAWS,
            (w >> 8) & 0xFF, w & 0xFF,
            (h >> 8) & 0xFF, h & 0xFF,
            IAC, SE,
        ]))
    except OSError:
        pass


def handle_iac(data: bytes, sock: socket.socket) -> bytes:
    """Verarbeitet IAC-Sequenzen, lehnt alle Optionen außer NAWS ab."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] != IAC or i + 1 >= len(data):
            out.append(data[i])
            i += 1
            continue
        cmd = data[i + 1]
        if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
            opt = data[i + 2]
            if opt != NAWS:   # NAWS wird per send_naws separat verhandelt
                reply = WONT if cmd in (DO, DONT) else DONT
                try:
                    sock.sendall(bytes([IAC, reply, opt]))
                except OSError:
                    pass
            i += 3
        elif cmd == SB:
            end = data.find(bytes([IAC, SE]), i + 2)
            i = end + 2 if end >= 0 else len(data)
        elif cmd == IAC:
            out.append(IAC)
            i += 2
        else:
            i += 2
    return bytes(out)


def find_trigger(buf: bytes):
    """Frühesten ZModem-Trigger in buf suchen. → (index, enc) oder None."""
    best_i   = len(buf)
    best_enc = None
    for magic, enc in ZMODEM_TRIGGERS:
        idx = buf.find(magic)
        if 0 <= idx < best_i:
            best_i   = idx
            best_enc = enc
    return (best_i, best_enc) if best_enc else None


def negotiate_binary(sock: socket.socket) -> bytes:
    """IAC WILL/DO BINARY senden; IAC-Antworten des Servers konsumieren.
    Gibt Nicht-IAC-Bytes zurück, die während der Verhandlung ankamen."""
    try:
        sock.sendall(bytes([IAC, WILL, BINARY, IAC, DO, BINARY]))
    except OSError:
        return b''

    leftover = bytearray()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        rem = deadline - time.monotonic()
        if not select.select([sock], [], [], max(0.0, rem))[0]:
            break
        try:
            chunk = sock.recv(256)
        except OSError:
            break
        if not chunk:
            break
        i = 0
        while i < len(chunk):
            if chunk[i] == IAC and i + 1 < len(chunk):
                cmd = chunk[i + 1]
                if cmd in (WILL, WONT, DO, DONT) and i + 2 < len(chunk):
                    i += 3
                elif cmd == SB:
                    end = chunk.find(bytes([IAC, SE]), i + 2)
                    i = end + 2 if end >= 0 else len(chunk)
                elif cmd == IAC:
                    leftover.append(IAC)
                    i += 2
                else:
                    i += 2
            else:
                leftover.append(chunk[i])
                i += 1
        if leftover:
            break
    return bytes(leftover)
