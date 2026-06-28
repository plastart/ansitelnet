"""
ZModem Download/Upload Fortschritts-Dialog (curses).
Parst rz/sz stderr in Echtzeit und zeigt Fortschrittsbalken.
"""
from __future__ import annotations
import curses
import os
import re
import select
import socket
import subprocess
import threading
import time

from ..protocol import IACStripper
from . import win_box as _win_box

RE_RZ_FILE = re.compile(r'^Receiving:\s+(.+?)\s*$')
RE_RZ_PROG = re.compile(r'Bytes received:\s*(\d+)/(\d+)\s+BPS:(\d+)\s+ETA\s+(\S+)')
RE_SZ_FILE = re.compile(r'^Sending:\s+(.+?)\s*$')
RE_SZ_PROG = re.compile(r'Bytes Sent:\s*(\d+)/(\d+)\s+BPS:(\d+)\s+ETA\s+(\S+)')
RE_RETRY   = re.compile(r'Retry \d+:')


def _fmt_size(n: int) -> str:
    if n >= 1_048_576:
        return f'{n / 1_048_576:.1f} MB'
    if n >= 1_024:
        return f'{n / 1_024:.0f} KB'
    return f'{n} B'


def _draw(win: 'curses._CursesWindow', title: str, state: dict, is_dl: bool) -> None:
    from . import colors as C
    try:
        h, w = win.getmaxyx()
        win.erase()

        # Rahmen
        win.attron(C.p(C.BORDER))
        _win_box(win, h, w)
        win.attroff(C.p(C.BORDER))

        # Titelzeile
        t = f'  {title}  '
        win.attron(C.p(C.TITLE) | curses.A_BOLD)
        win.addstr(0, max(1, (w - len(t)) // 2), t[: w - 2])
        win.attroff(C.p(C.TITLE) | curses.A_BOLD)

        y = 2
        fn    = state.get('filename', '…')
        label = 'Datei:   ' if is_dl else 'Sendet:  '
        win.addstr(y, 2, label)
        win.attron(curses.A_BOLD)
        win.addstr(fn[: w - len(label) - 4])
        win.attroff(curses.A_BOLD)
        y += 1

        total = state.get('total', 0)
        if total:
            win.addstr(y, 2, f'Größe:   {_fmt_size(total)}')
        y += 2

        # Fortschrittsbalken
        recv   = state.get('received', 0)
        pct    = (recv / total * 100) if total else 0
        bar_w  = max(0, w - 10)
        filled = int(bar_w * pct / 100)

        win.attron(C.p(C.BAR))
        win.addstr(y, 2, '█' * filled)
        win.attroff(C.p(C.BAR))
        if bar_w - filled > 0:
            win.addstr(y, 2 + filled, '░' * (bar_w - filled))
        win.addstr(y, w - 6, f'{pct:3.0f}%')
        y += 2

        if total:
            win.addstr(y, 2, f'Empfangen:  {_fmt_size(recv)} / {_fmt_size(total)}')
            y += 1
        bps = state.get('bps', 0)
        if bps:
            win.addstr(y, 2, f'Tempo:      {bps:,} CPS')
            y += 1
        eta = state.get('eta', '')
        if eta:
            win.addstr(y, 2, f'ETA:        {eta}')
            y += 1
        errs = state.get('errors', 0)
        if errs:
            win.attron(C.p(C.ERROR))
            win.addstr(y, 2, f'Fehler:     {errs}')
            win.attroff(C.p(C.ERROR))
            y += 1

        hint = '[Ctrl+X] Abbrechen'
        win.attron(C.p(C.KEY))
        win.addstr(h - 2, max(2, (w - len(hint)) // 2), hint[: w - 4])
        win.attroff(C.p(C.KEY))

    except curses.error:
        pass
    win.noutrefresh()


def _transfer(stdscr, sock: socket.socket, cmd: list[str],
              is_dl: bool, re_file, re_prog, leftover: bytes,
              cwd: str | None = None) -> int:
    from . import colors as C
    C.init()
    curses.curs_set(0)
    stdscr.clear()

    H, W  = stdscr.getmaxyx()
    bh    = min(20, H - 2)
    bw    = min(64, max(44, W - 4))
    by    = max(0, (H - bh) // 2)
    bx    = max(0, (W - bw) // 2)
    box   = curses.newwin(bh, bw, by, bx)
    title = 'ZModem Download' if is_dl else 'ZModem Upload'

    state = {
        'filename': '…', 'total': 0, 'received': 0,
        'bps': 0, 'eta': '', 'errors': 0,
    }
    lock = threading.Lock()

    r_err, w_err = os.pipe()
    r_in,  w_in  = os.pipe()

    proc = subprocess.Popen(
        cmd,
        stdin=r_in,
        stdout=sock.fileno(),
        stderr=w_err,
        cwd=cwd,
    )
    os.close(r_in)
    os.close(w_err)

    stop     = threading.Event()
    stripper = IACStripper()

    def bridge() -> None:
        try:
            if leftover:
                clean = stripper.feed(leftover)
                if clean:
                    os.write(w_in, clean)
            while not stop.is_set():
                if not select.select([sock], [], [], 0.05)[0]:
                    continue
                data = sock.recv(4096)
                if not data:
                    break
                clean = stripper.feed(data)
                if clean:
                    os.write(w_in, clean)
        except OSError:
            pass
        finally:
            try:
                os.close(w_in)
            except OSError:
                pass

    def stderr_reader() -> None:
        buf = b''
        try:
            while True:
                chunk = os.read(r_err, 512)
                if not chunk:
                    break
                buf += chunk
                for sep in (b'\r', b'\n'):
                    while sep in buf:
                        line_b, buf = buf.split(sep, 1)
                        line = line_b.decode('latin-1', errors='replace').strip()
                        if not line:
                            continue
                        with lock:
                            m = re_file.match(line)
                            if m:
                                state['filename'] = m.group(1)
                                continue
                            m = re_prog.search(line)
                            if m:
                                state['received'] = int(m.group(1))
                                state['total']    = int(m.group(2))
                                state['bps']      = int(m.group(3))
                                state['eta']      = m.group(4)
                            if RE_RETRY.search(line):
                                state['errors'] += 1
        except OSError:
            pass
        finally:
            try:
                os.close(r_err)
            except OSError:
                pass

    t_br = threading.Thread(target=bridge,        daemon=True)
    t_se = threading.Thread(target=stderr_reader, daemon=True)
    t_br.start()
    t_se.start()

    stdscr.nodelay(True)
    while proc.poll() is None:
        with lock:
            _draw(box, title, state, is_dl)
        curses.doupdate()
        time.sleep(0.1)

    stop.set()
    t_br.join(timeout=1)
    t_se.join(timeout=1)

    with lock:
        _draw(box, title, state, is_dl)
    curses.doupdate()
    time.sleep(0.8)

    return proc.wait()


def show_download(sock: socket.socket, leftover: bytes = b'',
                  cwd: str | None = None) -> int:
    """rz starten und Fortschritts-Dialog zeigen.
    Telnet-Binärmodus wird bereits beim Verbindungsaufbau ausgehandelt."""
    def _w(stdscr):
        return _transfer(
            stdscr, sock,
            cmd=['rz', '--overwrite', '--binary'],
            is_dl=True,
            re_file=RE_RZ_FILE,
            re_prog=RE_RZ_PROG,
            leftover=leftover,
            cwd=cwd,
        )

    return curses.wrapper(_w)


def show_upload(sock: socket.socket, files: list[str], leftover: bytes = b'') -> int:
    """sz starten und Fortschritts-Dialog zeigen."""
    def _w(stdscr):
        return _transfer(
            stdscr, sock,
            cmd=['sz', '--binary'] + files,
            is_dl=False,
            re_file=RE_SZ_FILE,
            re_prog=RE_SZ_PROG,
            leftover=leftover,
        )

    return curses.wrapper(_w)
