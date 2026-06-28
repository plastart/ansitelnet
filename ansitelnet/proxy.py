"""
Transparenter TCP-Proxy mit ZModem-Erkennung und Statuszeile.
"""
from __future__ import annotations
import os
import select
import shutil
import signal
import socket
import sys

try:
    import termios
    import tty
    _HAVE_TERMIOS = True
except ImportError:
    _HAVE_TERMIOS = False

from .protocol import (
    handle_iac, find_trigger, to_utf8, send_naws,
    negotiate_binary,
    ZMODEM_TRIGGERS, MAX_TRIGGER_LEN,
    ZRQINIT, ZRINIT, ZFILE,
)

_BAR_ON  = '\033[1;37;44m'   # Fett weiß auf blau
_BAR_OFF = '\033[0m'

_F12 = b'\033[24~'           # xterm F12-Sequenz (5 Bytes)


def _f12_hold(buf: bytes) -> int:
    """Bytes am Ende von buf zurückhalten, die ein Präfix von _F12 sein könnten."""
    for n in range(min(len(_F12) - 1, len(buf)), 0, -1):
        if _F12[:n] == buf[-n:]:
            return n
    return 0

# Farbpaletten (aus ansi-8farben.png / ansi-16farben.png)
_PALETTE_8 = [
    0x686868, 0xFF0404, 0x04FF04, 0xFFFF04,
    0x0404FF, 0xFF04FF, 0x04FFFF, 0xFFFFFF,
]
_PALETTE_16 = [
    0x040404, 0xAB0404, 0x04AB04, 0xAB6804,
    0x0404AB, 0xAB04AB, 0x04ABAB, 0xBCBCBC,
    0x686868, 0xFF0404, 0x04FF04, 0xFFFF04,
    0x0404FF, 0xFF04FF, 0x04FFFF, 0xFFFFFF,
]


def _apply_palette(stdout_fd: int, color_mode: int) -> None:
    """Terminal-Farbpalette via OSC 4 setzen."""
    palette = _PALETTE_16 if color_mode == 16 else _PALETTE_8
    seq = bytearray()
    for i, rgb in enumerate(palette):
        r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
        seq += f'\033]4;{i};rgb:{r:02x}/{g:02x}/{b:02x}\007'.encode()
    os.write(stdout_fd, bytes(seq))


def _reset_palette(stdout_fd: int) -> None:
    """Terminal-Farbpalette auf Standard zurücksetzen."""
    os.write(stdout_fd, b'\033]104\007')


# ── Anzeigegeometrie ──────────────────────────────────────────────────────────

def _geo(W: int, cap: int) -> tuple[int, int, int]:
    """Berechnet (eff_W, left_bdr, right_bdr) aus Terminalbreite und Cap.

    left_bdr / right_bdr: 1-basierte Spalte der Randlinie (0 = kein Rahmen).
    eff_W: Breite, die dem BBS via NAWS gemeldet wird.
    """
    if cap and W > cap:
        m = (W - cap) // 2
        if m >= 1:
            return cap, m, m + cap + 1
        return cap, 0, 0   # zu schmal für Rahmen, aber NAWS trotzdem begrenzen
    return W, 0, 0


def _border_seq(H: int, left_bdr: int, right_bdr: int) -> bytes:
    """ESC-Sequenz zum Zeichnen der seitlichen Randlinien.

    Schaltet DECOM temporär aus, damit absolute Koordinaten gelten,
    und aktiviert es danach wieder.
    """
    if left_bdr <= 0:
        return b''
    seq = bytearray(b'\033[?6l\033[34m')   # DECOM aus, blau
    for row in range(1, H):
        seq += f'\033[{row};{left_bdr}H│\033[{row};{right_bdr}H│'.encode('utf-8')
    seq += b'\033[0m\033[?6h'              # Farbe zurück, DECOM an
    return bytes(seq)


# ── Terminal-Hilfsfunktionen ──────────────────────────────────────────────────

def _term_size() -> tuple[int, int]:
    try:
        s = os.get_terminal_size()
        return s.lines, s.columns
    except OSError:
        return 24, 80


def _setup_display(H: int, left_bdr: int, right_bdr: int, W: int = 0) -> None:
    """Scrollregion + optionale DECLRMM/DECOM-Zentrierung einrichten."""
    if H < 3:
        return
    # Immer sauber starten: DECOM + DECLRMM deaktivieren
    seq = bytearray(b'\033[?6l\033[?69l')
    if left_bdr > 0:
        con_l = left_bdr + 1
        con_r = right_bdr - 1
        # Randbereiche (außerhalb der Rahmenlinien) mit Leerzeichen füllen
        if W > 0:
            for row in range(1, H):
                if left_bdr > 1:
                    seq += f'\033[{row};1H{" " * (left_bdr - 1)}'.encode()
                if right_bdr < W:
                    seq += f'\033[{row};{right_bdr + 1}H{" " * (W - right_bdr)}'.encode()
        seq += b'\033[?69h'                            # DECLRMM aktivieren
        seq += f'\033[{con_l};{con_r}s'.encode()       # DECSLRM: Inhalts-Margins
    seq += f'\033[1;{H - 1}r'.encode()                 # DECSTBM: vertikale Scrollregion
    seq += _border_seq(H, left_bdr, right_bdr)         # Randlinien (DECOM-sicher)
    if left_bdr > 0:
        seq += b'\033[?6h'                             # DECOM aktivieren
    seq += f'\033[{H - 1};1H'.encode()                 # Cursor ans untere Ende
    sys.stdout.buffer.write(bytes(seq))
    sys.stdout.buffer.flush()


def _restore_display(H: int, left_bdr: int = 0) -> None:
    """Scrollregion zurücksetzen und Statuszeile leeren."""
    seq = bytearray()
    if left_bdr > 0:
        seq += b'\033[?6l\033[?69l'  # DECOM aus, DECLRMM aus
    seq += b'\033[r'                 # DECSTBM reset
    seq += f'\033[{H};1H\033[2K'.encode()
    sys.stdout.buffer.write(bytes(seq))
    sys.stdout.buffer.flush()


def _draw_status(stdout_fd: int,
                 host: str, port: int, color_mode: int, mode: str,
                 H: int, W: int) -> None:
    if H < 3:
        return
    info = f'  ansitelnet │ {host}:{port} │ {color_mode} Farb. │ {mode} │ F12=Men\xfc  '
    bar  = info.ljust(W)[:W]
    # ESC 7 / ESC 8 (DECSC/DECRC) statt \033[s/\033[u –
    # \033[s kollidiert mit DECSLRM wenn DECLRMM aktiv ist.
    # \033[?6l schaltet DECOM aus, damit \033[H;1H absolute gilt.
    os.write(stdout_fd,
             f'\0337\033[?6l\033[{H};1H{_BAR_ON}{bar}{_BAR_OFF}\0338'.encode())


def _show_menu(stdin_fd: int, stdout_fd: int, H: int, W: int) -> str | None:
    """Menü auf der Statuszeile anzeigen. Gibt 'disconnect', 'upload' oder None zurück."""
    if H < 3:
        return None
    txt = '  Men\xfc:  [D]=Trennen  [U]=Upload  [beliebige Taste]=Weiter  '
    bar = txt.ljust(W)[:W]
    os.write(stdout_fd,
             f'\0337\033[?6l\033[{H};1H{_BAR_ON}{bar}{_BAR_OFF}\0338'.encode())
    try:
        if not select.select([stdin_fd], [], [], 10.0)[0]:
            return None
        ch = os.read(stdin_fd, 1)
        if not ch:
            return 'disconnect'
        b = ch[0]
        if b in (ord('d'), ord('D')):
            return 'disconnect'
        if b in (ord('u'), ord('U')):
            return 'upload'
        return None
    except OSError:
        return None


# ── Hauptproxy ────────────────────────────────────────────────────────────────

def run_proxy(host: str, port: int,
              color_mode: int = 16, mode: str = 'telnet',
              cap_width: int = 0) -> None:
    if not _HAVE_TERMIOS:
        sys.exit(
            'Direkte Terminal-Verbindungen werden unter Windows nicht nativ unterstützt.\n'
            'Bitte Windows Subsystem for Linux (WSL) verwenden:\n'
            '  https://learn.microsoft.com/de-de/windows/wsl/install\n'
        )
    zmodem = _check_lrzsz()

    if color_mode == 8:
        os.environ['TERM'] = 'ansi'
    else:
        os.environ['TERM'] = 'xterm-16color'
    os.environ.pop('COLORTERM', None)

    telnet_mode = (mode == 'telnet')

    sys.stderr.write(
        f'Verbinde mit {host}:{port} '
        f'[{color_mode}-Farben, TERM={os.environ["TERM"]}, {mode}'
        + (f', Breite={cap_width}' if cap_width else '')
        + '] ...\n'
    )

    try:
        sock = socket.create_connection((host, port))
    except ConnectionRefusedError:
        sys.exit(f'Verbindung zu {host}:{port} abgelehnt.')
    except OSError as e:
        sys.exit(f'Netzwerkfehler: {e}')

    stdin_fd  = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    saved     = termios.tcgetattr(stdin_fd)
    H, W      = _term_size()

    # Geometrie (aktualisiert bei SIGWINCH)
    eff_W, left_bdr, right_bdr = _geo(W, cap_width)

    # SIGWINCH über Self-Pipe damit select() abbricht
    winch_r, winch_w = os.pipe()

    def _on_winch(signum, frame):
        try:
            os.write(winch_w, b'\x00')
        except OSError:
            pass

    old_sigwinch = signal.signal(signal.SIGWINCH, _on_winch)

    def enter_raw() -> None:
        tty.setraw(stdin_fd)

    def leave_raw() -> None:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved)

    def redraw(new_H: int, new_W: int) -> None:
        nonlocal left_bdr, right_bdr, eff_W
        old_left, old_right = left_bdr, right_bdr
        eff_W, left_bdr, right_bdr = _geo(new_W, cap_width)
        # Alte Rahmenzeichen überschreiben (mit DECOM aus, da _setup_display das gleich macht)
        if old_left > 0:
            seq = bytearray(b'\033[?6l')  # DECOM aus für absolute Koordinaten
            for row in range(1, new_H):
                seq += f'\033[{row};{old_left}H \033[{row};{old_right}H '.encode()
            sys.stdout.buffer.write(bytes(seq))
            sys.stdout.buffer.flush()
        _apply_palette(stdout_fd, color_mode)
        _setup_display(new_H, left_bdr, right_bdr, new_W)
        _draw_status(stdout_fd, host, port, color_mode, mode, new_H, new_W)
        if telnet_mode:
            send_naws(sock, eff_W, max(1, new_H - 1))

    # Verbindung initialisieren
    enter_raw()
    _apply_palette(stdout_fd, color_mode)
    _setup_display(H, left_bdr, right_bdr, W)
    _draw_status(stdout_fd, host, port, color_mode, mode, H, W)
    if telnet_mode:
        send_naws(sock, eff_W, max(1, H - 1))
        # Binärmodus einmalig beim Verbindungsaufbau – nicht mitten im laufenden rz/sz
        buf = negotiate_binary(sock)
    else:
        buf = b''

    # Tastatur-Puffer für mehrbyte F12-Sequenz (Schutz vor split reads)
    _kbd_buf = b''

    def _write_term(data: bytes) -> None:
        """BBS-Daten → Terminal; nach \033[2J die Randlinien neu zeichnen."""
        out = to_utf8(data)
        if left_bdr > 0 and b'\033[2J' in out:
            out += _border_seq(H, left_bdr, right_bdr)
        os.write(stdout_fd, out)

    try:
        while True:
            try:
                readable, _, exc = select.select(
                    [stdin_fd, sock, winch_r], [], [stdin_fd, sock], 0.1
                )
            except (KeyboardInterrupt, InterruptedError):
                break
            if exc:
                break

            # ── Fenstergröße geändert ──────────────────────────────────────
            if winch_r in readable:
                os.read(winch_r, 64)
                H, W = _term_size()
                redraw(H, W)

            # ── Lokale Eingabe → Remote ────────────────────────────────────
            if stdin_fd in readable:
                try:
                    raw = os.read(stdin_fd, 256)
                except OSError:
                    break
                if not raw:
                    break
                _kbd_buf += raw

                # F12 (xterm: \033[24~) → Menü öffnen
                if _F12 in _kbd_buf:
                    pos = _kbd_buf.index(_F12)
                    pre = _kbd_buf[:pos]
                    _kbd_buf = _kbd_buf[pos + len(_F12):]
                    if pre:
                        try:
                            sock.sendall(pre)
                        except OSError:
                            break
                    action = _show_menu(stdin_fd, stdout_fd, H, W)
                    _draw_status(stdout_fd, host, port, color_mode, mode, H, W)
                    if action == 'disconnect':
                        break
                    elif action == 'upload':
                        leave_raw()
                        _restore_display(H, left_bdr)
                        _do_upload(sock)
                        enter_raw()
                        H, W = _term_size()
                        redraw(H, W)
                    if _kbd_buf:
                        try:
                            sock.sendall(_kbd_buf)
                        except OSError:
                            break
                        _kbd_buf = b''
                    continue

                # Kein F12 – alles senden außer echten F12-Präfixen am Ende
                safe = len(_kbd_buf) - _f12_hold(_kbd_buf)
                if safe > 0:
                    try:
                        sock.sendall(_kbd_buf[:safe])
                    except OSError:
                        break
                    _kbd_buf = _kbd_buf[safe:]

            # ── Remote → Terminal ──────────────────────────────────────────
            if sock in readable:
                try:
                    data = sock.recv(4096)
                except OSError:
                    break
                if not data:
                    break

                if telnet_mode:
                    data = handle_iac(data, sock)
                if not data:
                    continue

                if not zmodem:
                    _write_term(data)
                    continue

                buf += data
                hit = find_trigger(buf)

                if hit is not None:
                    idx, enc = hit
                    magic_len = next(len(m) for m, e in ZMODEM_TRIGGERS if e == enc)
                    after     = idx + magic_len

                    # ZHEX kodiert den Frame-Typ als 2 ASCII-Hex-Ziffern; ZBIN als 1 Byte.
                    need = after + (2 if enc == 'hex' else 1)
                    if need > len(buf):
                        buf = buf[idx:]
                        continue

                    if enc == 'hex':
                        ftype = int(chr(buf[after]) + chr(buf[after + 1]), 16)
                    else:
                        ftype = buf[after]

                    if idx > 0:
                        _write_term(buf[:idx])

                    leave_raw()
                    _restore_display(H, left_bdr)

                    if ftype in (ZRQINIT, ZFILE):
                        _do_download(sock, buf[idx:])
                    elif ftype == ZRINIT:
                        _do_upload(sock, buf[idx:])
                    else:
                        sys.stderr.write(
                            f'\r\n\033[33m[ZModem frame type {ftype:#04x}'
                            f' nicht unterst\xfctzt]\033[0m\r\n'
                        )

                    enter_raw()
                    H, W = _term_size()
                    redraw(H, W)
                    buf = b''

                else:
                    safe = max(0, len(buf) - (MAX_TRIGGER_LEN - 1))
                    if safe > 0:
                        _write_term(buf[:safe])
                        buf = buf[safe:]

            # Flush bei Sendepause
            if sock not in readable and buf:
                _write_term(buf)
                buf = b''

    finally:
        leave_raw()
        _restore_display(H, left_bdr)
        _reset_palette(stdout_fd)
        signal.signal(signal.SIGWINCH, old_sigwinch)
        try:
            os.close(winch_r)
            os.close(winch_w)
        except OSError:
            pass
        sock.close()
        if buf:
            try:
                _write_term(buf)
            except OSError:
                pass


def _check_lrzsz() -> bool:
    missing = [c for c in ('rz', 'sz') if shutil.which(c) is None]
    if missing:
        sys.stderr.write(
            f'\033[31mFehler: {", ".join(missing)} nicht gefunden.\033[0m\n'
            '        ZModem-Transfer nicht verf\xfcgbar. Bitte installieren:\n'
            '        sudo apt install lrzsz\n\n'
        )
        return False
    return True


def _do_download(sock: socket.socket, initial: bytes = b'') -> None:
    from .ui.progress import show_download
    ret = show_download(sock, leftover=initial)
    sys.stderr.write(f'\r\n\033[33m[ZModem] rz abgeschlossen (exit {ret})\033[0m\r\n')


def _do_upload(sock: socket.socket, initial: bytes = b'') -> None:
    import threading
    from .ui.filepicker import pick_files
    from .ui.progress   import show_upload

    # Während der Dateiauswahl Socket-Daten puffern (BBS sendet ZRINIT erneut).
    sock_buf: list[bytes] = []
    stop_ev = threading.Event()

    def _drain() -> None:
        import select as _sel
        while not stop_ev.is_set():
            if _sel.select([sock], [], [], 0.1)[0]:
                try:
                    chunk = sock.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                sock_buf.append(chunk)

    drainer = threading.Thread(target=_drain, daemon=True)
    drainer.start()
    files = pick_files()
    stop_ev.set()
    drainer.join(timeout=1.0)
    leftover = initial + b''.join(sock_buf)

    if files:
        ret = show_upload(sock, files, leftover)
        sys.stderr.write(f'\r\n\033[33m[ZModem] sz abgeschlossen (exit {ret})\033[0m\r\n')
    else:
        sys.stderr.write('\r\n[Abgebrochen]\r\n')
