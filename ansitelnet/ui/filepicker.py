"""
Datei-Browser für Upload-Auswahl (curses).
Mehrfachauswahl mit Leertaste, Bestätigung mit F10 oder Enter.
"""
from __future__ import annotations
import curses
import sys
from pathlib import Path

from . import win_box as _win_box


def pick_files(start_dir: str | None = None) -> list[str]:
    """Öffnet den Datei-Browser. Gibt ausgewählte Pfade zurück (oder [])."""
    cwd = Path(start_dir).expanduser().resolve() if start_dir else Path.home()

    def _w(stdscr):
        return _run(stdscr, cwd)

    return curses.wrapper(_w)


# ── Interne Hilfsfunktionen ───────────────────────────────────────────────────

def _list_dir(cwd: Path) -> list[Path]:
    try:
        entries = list(cwd.iterdir())
    except PermissionError:
        return []
    dirs  = sorted([e for e in entries if e.is_dir()],  key=lambda e: e.name.lower())
    files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name.lower())
    result: list[Path] = []
    if cwd.parent != cwd:
        result.append(cwd.parent)
    result.extend(dirs)
    result.extend(files)
    return result


def _fmt_sz(n: int) -> str:
    if n >= 1_048_576:
        return f'{n / 1_048_576:.1f}M'
    if n >= 1_024:
        return f'{n / 1_024:.0f}K'
    return f'{n}B'


def _draw(stdscr, cwd: Path, entries: list[Path],
          selected: set[Path], cursor: int, scroll: int, list_h: int) -> None:
    from . import colors as C
    H, W = stdscr.getmaxyx()
    bh   = H - 2
    bw   = min(76, max(50, W - 2))
    by   = 1
    bx   = max(0, (W - bw) // 2)

    # Hintergrund löschen – muss in den virtuellen Bildschirm übernommen werden,
    # damit doupdate() auch den Bereich außerhalb des Dialogs korrekt zeichnet.
    stdscr.erase()
    stdscr.noutrefresh()

    win = None
    try:
        win = curses.newwin(bh, bw, by, bx)
        win.erase()

        # Rahmen
        win.attron(C.p(C.BORDER))
        _win_box(win, bh, bw)
        win.attroff(C.p(C.BORDER))

        # Titel (nur ASCII + Latin-1 – kein U+2713/↑↓ um curses.error zu vermeiden)
        t = '  Datei fuer Upload auswaehlen  '
        win.attron(C.p(C.TITLE) | curses.A_BOLD)
        win.addstr(0, max(1, (bw - len(t)) // 2), t[: bw - 2])
        win.attroff(C.p(C.TITLE) | curses.A_BOLD)

        # Aktueller Pfad
        path_s = str(cwd) + '/'
        win.attron(C.p(C.INFO))
        win.addstr(1, 2, path_s[: bw - 4])
        win.attroff(C.p(C.INFO))

        # Dateiliste
        name_w = bw - 16
        for slot, abs_i in enumerate(range(scroll, scroll + list_h)):
            row = 3 + slot
            if row >= bh - 4 or abs_i >= len(entries):
                break
            entry  = entries[abs_i]
            is_cur = (abs_i == cursor)
            is_sel = entry in selected
            is_dir = entry.is_dir()

            # Name
            if entry == cwd.parent:
                name = '../'
            elif is_dir:
                name = entry.name + '/'
            else:
                name = entry.name

            # Größe
            if is_dir:
                size_s = ' [DIR]'
            else:
                try:
                    size_s = f'{_fmt_sz(entry.stat().st_size):>6}'
                except OSError:
                    size_s = '     ?'

            marker = '[*] ' if is_sel else '    '
            line   = f'{marker}{name:<{name_w}}{size_s}'

            if is_cur and is_sel:
                attr = C.p(C.SELECT) | curses.A_BOLD
            elif is_cur:
                attr = C.p(C.SELECT)
            elif is_sel:
                attr = C.p(C.INFO) | curses.A_BOLD
            else:
                attr = C.p(C.NORMAL)

            win.attron(attr)
            win.addstr(row, 2, line[: bw - 4])
            win.attroff(attr)

        # Ausgewählte Dateien
        n_sel = len(selected)
        if n_sel:
            s = f'Ausgewaehlt: {n_sel} Datei{"en" if n_sel > 1 else ""}'
            win.attron(C.p(C.INFO) | curses.A_BOLD)
            win.addstr(bh - 4, 2, s[: bw - 4])
            win.attroff(C.p(C.INFO) | curses.A_BOLD)

        # Tastaturhinweise
        hints = '[Up/Dn] Nav  [Spc] Ausw.  [Enter] Oeffnen/OK  [F10] OK  [Esc] Abbruch'
        win.attron(C.p(C.KEY))
        win.addstr(bh - 2, 2, hints[: bw - 4])
        win.attroff(C.p(C.KEY))

    except curses.error:
        pass

    # win.noutrefresh() außerhalb von try – auch bei Teilfehler beim Zeichnen aufrufen
    if win is not None:
        try:
            win.noutrefresh()
        except curses.error:
            pass

    curses.doupdate()


def _run(stdscr, cwd: Path) -> list[str]:
    from . import colors as C
    C.init()
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    curses.flushinp()

    # curses wechselt in den Alternate-Screen-Buffer (smcup), wodurch der BBS-
    # Hintergrund verschwindet und nur Schwarz bleibt.  Wir verlassen diesen
    # Buffer sofort wieder, damit der Dialog – wie in dctelnet – über dem
    # laufenden BBS-Terminal schwebt.  Cursor nach oben-links setzen, damit
    # curses' interne Koordinaten stimmen.
    sys.stdout.buffer.write(b'\033[?1049l\033[H')
    sys.stdout.buffer.flush()

    selected: set[Path] = set()
    cursor = 0
    scroll = 0

    while True:
        entries = _list_dir(cwd)
        H, _    = stdscr.getmaxyx()
        list_h  = max(3, H - 12)

        # Cursor klemmen
        if entries:
            cursor = max(0, min(cursor, len(entries) - 1))
        else:
            cursor = 0
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        _draw(stdscr, cwd, entries, selected, cursor, scroll, list_h)

        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
            if cursor > 0:
                cursor -= 1

        elif key in (curses.KEY_DOWN, ord('j')):
            if entries and cursor < len(entries) - 1:
                cursor += 1

        elif key in (curses.KEY_PPAGE,):   # Page Up
            cursor = max(0, cursor - list_h)

        elif key in (curses.KEY_NPAGE,):   # Page Down
            cursor = min(len(entries) - 1, cursor + list_h) if entries else 0

        elif key in (curses.KEY_ENTER, 10, 13):
            if entries and cursor < len(entries):
                entry = entries[cursor]
                if entry.is_dir():
                    try:
                        cwd    = entry.resolve()
                        cursor = 0
                        scroll = 0
                    except PermissionError:
                        pass
                else:
                    # Enter auf Datei = auswählen + bestätigen
                    selected.add(entry)
                    return [str(f) for f in sorted(selected)]

        elif key == ord(' '):
            if entries and cursor < len(entries):
                entry = entries[cursor]
                if entry.is_file():
                    if entry in selected:
                        selected.discard(entry)
                    else:
                        selected.add(entry)

        elif key == curses.KEY_F10:
            if selected:
                return [str(f) for f in sorted(selected)]

        elif key in (27, ord('q')):   # Esc / q
            return []

    return []
