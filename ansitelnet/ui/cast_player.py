"""
Interaktiver Cast-Player und -Editor (kein curses, wie proxy.py).

  Spc          Play / Pause
  ← →          ±5 Sekunden
  Pos1 / Home  Zum Anfang
  N            Nächste Pause (Lücke ≥ 1s im Cast)
  [            Alles VOR aktueller Position löschen
  ]            Alles AB aktueller Position löschen
  S            Speichern (überschreibt Original)
  Q / Esc      Beenden
"""
from __future__ import annotations
import json
import os
import re
import select
import signal
import sys
import time

try:
    import termios
    import tty
    _HAVE_TERMIOS = True
except ImportError:
    _HAVE_TERMIOS = False

_BAR_ON       = '\033[1;37;44m'
_BAR_OFF      = '\033[0m'
_ANSI_RE      = re.compile(r'\033(?:\[[0-9;]*[a-zA-Z]|\][^\007]*\007|.)')
# Erkennt unvollständige Escape-Sequenzen am Ende eines Strings:
#   \033              – ESC allein
#   \033[ + params    – CSI ohne abschließenden Buchstaben
#                       params = 0-9 ; ? < > = (deckt auch private Sequenzen wie \033[?25h)
#   \033][^\007]*     – OSC ohne BEL
_INCOMPLETE   = re.compile(r'\033(?:\[[0-9;?<>=]*|\][^\007]*|)$')
# Orphaned CSI-Tail: "[0m" etc. ohne vorangestelltes ESC am Anfang eines Event-Textes
_ORPHAN_CSI   = re.compile(r'^\[[0-9;?<>=]*[a-zA-Z]')
# Screen-Clear-Sequenzen: ED 2J/3J löscht den gesamten Bildschirm inkl. Statuszeilen
_CLRSCR_RE    = re.compile(r'\033\[(?:2|3)J')
PAUSE_THRESH  = 1.0    # Sekunden Lücke gilt als "Pause"
SEEK_STEP     = 5.0    # Sekunden pro ←/→


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub('', s)


def _fmt_t(t: float) -> str:
    m, s = divmod(int(max(0.0, t)), 60)
    return f'{m:02d}:{s:02d}'


def _term_size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size()
        return sz.lines, sz.columns
    except OSError:
        return 24, 80


def load_cast(path: str) -> tuple[dict, list]:
    lines = open(path, encoding='utf-8').readlines()
    header = json.loads(lines[0])
    events = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        if ev[1] == 'o':
            events.append(ev)
    return header, events


def save_cast(path: str, header: dict, events: list) -> None:
    """Speichert Cast; normalisiert Timestamps so dass erstes Event bei 0.0 liegt."""
    offset = events[0][0] if events else 0.0
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(header) + '\n')
        for ev in events:
            f.write(json.dumps([round(ev[0] - offset, 6), ev[1], ev[2]]) + '\n')


def _read_key(fd: int) -> bytes:
    if not select.select([fd], [], [], 0.05)[0]:
        return b''
    return os.read(fd, 32)


# ── Haupt-Player ──────────────────────────────────────────────────────────────

def play_cast(path: str) -> None:
    if not _HAVE_TERMIOS:
        sys.exit('Cast-Player nur unter Linux/macOS verfügbar.')

    header, events = load_cast(path)
    if not events:
        sys.exit('Cast-Datei enthält keine Ausgabe-Events.')

    total_t  = events[-1][0]
    modified = False

    stdin_fd  = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    saved_tc  = termios.tcgetattr(stdin_fd)
    H, W      = _term_size()

    # SIGWINCH via Self-Pipe
    winch_r, winch_w = os.pipe()
    def _on_winch(s, f):
        try:
            os.write(winch_w, b'\x00')
        except OSError:
            pass
    old_winch = signal.signal(signal.SIGWINCH, _on_winch)

    # ── Playback-Zustand ──────────────────────────────────────────────────────
    play_offset = 0.0           # Cast-Zeit an der "Nullpunkt" liegt
    play_mono   = time.monotonic()
    paused      = True
    ev_idx      = 0             # nächstes zu schreibendes Event

    def cast_t() -> float:
        if paused:
            return play_offset
        return play_offset + (time.monotonic() - play_mono)

    def do_pause() -> None:
        nonlocal paused, play_offset
        play_offset = cast_t()
        paused = True

    def do_resume() -> None:
        nonlocal paused, play_mono
        paused = False
        play_mono = time.monotonic()

    # Puffer für unvollständige Escape-Sequenzen die über Event-Grenzen laufen
    _seq_buf = ['']
    # Marker-Event-Index für Bereichsauswahl (None = kein Marker gesetzt)
    _marker  = [None]

    def _write(data: str) -> None:
        os.write(stdout_fd, data.encode('utf-8', errors='replace'))

    def _write_ev(ev) -> None:
        data = _seq_buf[0] + ev[2]
        _seq_buf[0] = ''
        m = _INCOMPLETE.search(data)
        if m:
            _seq_buf[0] = data[m.start():]
            data = data[:m.start()]
        if data:
            _write(data)
            # Nach Screen-Clear (ED 2J) Scroll-Region und Statusbar sofort wieder herstellen.
            # DECSTBM schützt nur vor Scroll, nicht vor Erase-Display.
            if _CLRSCR_RE.search(data):
                _set_scroll_region()
                draw_status()

    def replay_to(t: float) -> None:
        """Bildschirm leeren und alle Events bis t sofort abspielen."""
        nonlocal ev_idx, play_offset, play_mono
        t = max(0.0, min(t, total_t))
        _seq_buf[0] = ''   # Puffer verwerfen vor Neustart
        os.write(stdout_fd, b'\033[2J\033[H')
        ev_idx = 0
        for i, ev in enumerate(events):
            if ev[0] > t:
                ev_idx = i
                break
            _write_ev(ev)
        else:
            ev_idx = len(events)
        _seq_buf[0] = ''   # Rest nach Replay verwerfen (Bildschirm ist konsistent)
        play_offset = t
        play_mono   = time.monotonic()

    def seek_fwd(dt: float) -> None:
        replay_to(min(cast_t() + dt, total_t))

    def seek_bwd(dt: float) -> None:
        replay_to(max(0.0, cast_t() - dt))

    def next_pause() -> None:
        """Springe zum Beginn der nächsten langen Pause."""
        ct = cast_t()
        for i in range(len(events) - 1):
            if events[i][0] <= ct:
                continue
            if events[i + 1][0] - events[i][0] >= PAUSE_THRESH:
                replay_to(events[i + 1][0])
                return

    def cut_before() -> None:
        nonlocal events, modified, ev_idx, play_offset, play_mono, total_t
        t      = cast_t()
        events = [ev for ev in events if ev[0] >= t]
        total_t  = events[-1][0] if events else 0.0
        modified = True
        ev_idx   = 0
        play_offset = events[0][0] if events else 0.0
        play_mono   = time.monotonic()
        os.write(stdout_fd, b'\033[2J\033[H')

    def cut_after() -> None:
        nonlocal events, modified, total_t
        t        = cast_t()
        events   = [ev for ev in events if ev[0] <= t]
        total_t  = events[-1][0] if events else 0.0
        modified = True

    def step_fwd() -> None:
        """Ein Event vorwärts, dann Pause."""
        nonlocal ev_idx, play_offset
        if ev_idx >= len(events):
            return
        do_pause()
        _write_ev(events[ev_idx])
        ev_idx    += 1
        play_offset = events[ev_idx - 1][0]

    def step_bwd() -> None:
        """Ein Event rückwärts (Replay bis vorletztes Event), dann Pause."""
        nonlocal ev_idx, play_offset, play_mono
        do_pause()
        if ev_idx == 0:
            return
        if ev_idx <= 1:
            _seq_buf[0] = ''
            os.write(stdout_fd, b'\033[2J\033[H')
            _set_scroll_region()
            ev_idx      = 0
            play_offset = 0.0
            play_mono   = time.monotonic()
        else:
            replay_to(events[ev_idx - 2][0])

    def toggle_marker() -> None:
        """Marker setzen (erstes M) oder löschen (zweites M), egal wo der Cursor ist."""
        _marker[0] = None if _marker[0] is not None else ev_idx

    def delete_range() -> None:
        """Events zwischen Marker und aktueller Position löschen."""
        nonlocal events, modified, ev_idx, total_t, play_offset, play_mono
        if _marker[0] is None:
            return
        a = min(_marker[0], ev_idx)
        b = max(_marker[0], ev_idx)
        if a == b:
            _marker[0] = None
            return
        events   = events[:a] + events[b:]
        total_t  = events[-1][0] if events else 0.0
        modified = True
        _marker[0] = None
        _seq_buf[0] = ''
        os.write(stdout_fd, b'\033[2J\033[H')
        _set_scroll_region()
        ev_idx      = 0
        play_offset = 0.0
        play_mono   = time.monotonic()
        for i, ev in enumerate(events):
            if i >= a:
                ev_idx = i
                break
            _write_ev(ev)
        else:
            ev_idx = len(events)
        _seq_buf[0] = ''
        play_offset = events[a - 1][0] if a > 0 and events else 0.0
        do_pause()

    # ── Scrollregion ──────────────────────────────────────────────────────────

    def _set_scroll_region() -> None:
        """Reserviert die letzten 2 Zeilen für die Statusbar (kein Scroll dorthin)."""
        rows = max(1, H - 2)
        os.write(stdout_fd, f'\033[1;{rows}r'.encode())

    # ── Statuszeile ───────────────────────────────────────────────────────────

    def draw_status() -> None:
        if _seq_buf[0]:
            return   # Nicht unterbrechen solange Sequenz unvollständig
        ct     = cast_t()
        state  = '‖' if paused else '▶'
        mod_c  = '*' if modified else ' '
        time_s = f'{_fmt_t(ct)}/{_fmt_t(total_t)}'
        ev_s   = f'{min(ev_idx, len(events))}/{len(events)}'

        # bar_w so berechnen dass der suffix danach noch passt
        # Zeilenformat: "  {state}{mod_c} {time_s} {bar} {ev_s}{suffix}"
        # Festes Prefix: 2+1+1+1+len(time_s)+1 = len(time_s)+6
        # Nach Balken:   1+len(ev_s)+len(suffix)
        _edit_suffix = '  M=Marke  D=Schnitt  [=Vor  ]=Nach  S=Sichern  Q=Ende'
        _play_suffix = '  Spc=▶‖  ⇧←→=±1  ←→=±5s  N  M  D  [  ]  S  Q'
        _suffix = _edit_suffix if paused else _play_suffix
        bar_w  = max(0, W - (len(time_s) + 6) - (1 + len(ev_s) + len(_suffix)))
        filled = int(bar_w * min(ct, total_t) / total_t) if total_t > 0 else 0

        # Marker-Position im Balken als ◆
        marker_pos = -1
        if _marker[0] is not None and _marker[0] < len(events) and total_t > 0:
            marker_pos = int(bar_w * events[_marker[0]][0] / total_t)
        bar = ''
        for i in range(bar_w):
            if i == marker_pos:
                bar += '◆'
            elif i < filled:
                bar += '█'
            else:
                bar += '░'

        prog = f'  {state}{mod_c} {time_s} {bar} {ev_s}'

        if paused:
            # Zeile H-1: Navigationstasten
            line1 = ('  ‖  Spc=Weiter  ⇧←=‹1Ev  ⇧→=1Ev›'
                     '  ←=−5s  →=+5s  Pos1=Anfang  End=Ende  N=nächste Pause')
            # Zeile H: Fortschritt + Edit-Tasten
            line2 = f'{prog}{_edit_suffix}'
        else:
            # Zeile H-1: Vorschau des letzten Events (ANSI entfernt)
            # Event-Text kann mit orphaned CSI-Tail beginnen → erst Tail, dann ANSI strippen
            prev_txt = events[max(0, ev_idx - 1)][2] if events else ''
            preview  = _strip_ansi(_ORPHAN_CSI.sub('', prev_txt)).replace('\r', '').replace('\n', ' ').strip()
            marker_s = (f' ◆ M:{_fmt_t(events[_marker[0]][0])}'
                        if _marker[0] is not None and _marker[0] < len(events) else '')
            line1 = f'  ▸ {preview}'
            if marker_s:
                line1 = line1[:W - len(marker_s)].ljust(W - len(marker_s)) + marker_s
            # Zeile H: Fortschritt + kompakte Hinweise
            line2 = f'{prog}{_play_suffix}'

        try:
            os.write(stdout_fd,
                (f'\0337\033[?6l'
                 f'\033[{H - 1};1H{_BAR_ON}{line1.ljust(W)[:W]}{_BAR_OFF}'
                 f'\033[{H};1H{_BAR_ON}{line2.ljust(W)[:W]}{_BAR_OFF}'
                 f'\0338').encode('utf-8', errors='replace'))
        except OSError:
            pass

    # ── Start ─────────────────────────────────────────────────────────────────

    tty.setraw(stdin_fd)
    os.write(stdout_fd, b'\033[2J\033[H')
    _set_scroll_region()
    draw_status()

    last_draw = time.monotonic()
    running   = True

    try:
        while running:
            # Resize
            if select.select([winch_r], [], [], 0)[0]:
                os.read(winch_r, 64)
                H, W = _term_size()
                _set_scroll_region()

            # Events ausgeben
            if not paused:
                ct = cast_t()
                while ev_idx < len(events) and events[ev_idx][0] <= ct:
                    _write_ev(events[ev_idx])
                    ev_idx += 1
                if ev_idx >= len(events):
                    do_pause()

            # Status neu zeichnen (10 Hz)
            now = time.monotonic()
            if now - last_draw >= 0.1:
                draw_status()
                last_draw = now

            # Tastatur
            key = _read_key(stdin_fd)
            if not key:
                continue

            if key == b' ':
                if paused:
                    do_resume()
                else:
                    do_pause()

            elif key in (b'q', b'Q', b'\x1b'):
                running = False

            elif key in (b'n', b'N'):
                do_pause()
                next_pause()

            elif key in (b'm', b'M'):
                toggle_marker()

            elif key in (b'd', b'D'):
                delete_range()

            elif key in (b's', b'S'):
                save_cast(path, header, events)
                modified = False

            elif key == b'[':
                do_pause()
                cut_before()

            elif key == b']':
                do_pause()
                cut_after()

            elif key == b'\033[1;2C':               # Shift+Rechts = Einzelschritt vor
                step_fwd()

            elif key == b'\033[1;2D':               # Shift+Links = Einzelschritt zurück
                step_bwd()

            elif (key.startswith(b'\033[C') or key.startswith(b'\033OC')):
                seek_fwd(SEEK_STEP)

            elif (key.startswith(b'\033[D') or key.startswith(b'\033OD')):
                seek_bwd(SEEK_STEP)

            elif key in (b'\033[H', b'\033[1~'):   # Home / Pos1
                replay_to(0.0)

            elif key in (b'\033[F', b'\033[4~'):   # End
                seek_fwd(total_t)

            draw_status()

    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved_tc)
        signal.signal(signal.SIGWINCH, old_winch)
        try:
            os.close(winch_r)
            os.close(winch_w)
        except OSError:
            pass
        os.write(stdout_fd, b'\033[r\033[2J\033[H\033[?6l')   # Scrollregion zurücksetzen
        if modified:
            sys.stderr.write(
                f'\n\033[33mUngespeicherte Änderungen – zum Speichern:\033[0m\n'
                f'  ansitelnet --play {path}\n'
                f'  dann [S] drücken\n'
            )
