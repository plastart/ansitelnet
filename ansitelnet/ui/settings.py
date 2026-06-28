"""Einstellungs-Dialog (curses)."""
from __future__ import annotations
import curses
from ..config import Settings, load_settings, save_settings
from . import win_box as _win_box

_FIELDS = [
    ('download_dir',        'Download-Ordner:    ', 'text'),
    ('ask_before_download', 'Vor Download fragen:', 'bool'),
    ('upload_dir',          'Upload-Ordner:      ', 'text'),
    ('remember_upload_dir', 'Ordner merken:      ', 'bool'),
    ('session_dir',         'Session-Ordner:     ', 'text'),
]


def open_settings(stdscr) -> None:
    s      = load_settings()
    values = {
        'download_dir':        s.download_dir,
        'ask_before_download': s.ask_before_download,
        'upload_dir':          s.upload_dir,
        'remember_upload_dir': s.remember_upload_dir,
        'session_dir':         s.session_dir,
    }
    _run(stdscr, values)


def _run(stdscr, values: dict) -> None:
    from . import colors as C
    nf    = len(_FIELDS)
    focus = 0

    while True:
        H, W = stdscr.getmaxyx()
        dh   = nf * 2 + 7
        dw   = min(66, W - 4)
        dy   = max(0, (H - dh) // 2)
        dx   = max(0, (W - dw) // 2)
        fw   = max(10, dw - 27)

        try:
            win = curses.newwin(dh, dw, dy, dx)
            win.erase()
            win.attron(C.p(C.BORDER))
            _win_box(win, dh, dw)
            win.attroff(C.p(C.BORDER))

            t = '  Einstellungen  '
            win.attron(C.p(C.TITLE) | curses.A_BOLD)
            win.addstr(0, max(1, (dw - len(t)) // 2), t[:dw - 2])
            win.attroff(C.p(C.TITLE) | curses.A_BOLD)

            for i, (key, label, ftype) in enumerate(_FIELDS):
                row  = 2 + i * 2
                is_f = (i == focus)
                val  = values[key]

                win.addstr(row, 2, label)

                if ftype == 'bool':
                    disp = 'Ja  ' if val else 'Nein'
                    attr = C.p(C.SELECT) | curses.A_BOLD if is_f else C.p(C.INPUT)
                    win.attron(attr)
                    win.addstr(row, 2 + len(label), f'[{disp}]')
                    win.attroff(attr)
                else:
                    disp = val or ''
                    attr = C.p(C.INPUT) | curses.A_BOLD if is_f else C.p(C.INPUT)
                    win.attron(attr)
                    win.addstr(row, 2 + len(label), (disp + ' ').ljust(fw)[:fw])
                    win.attroff(attr)
                    if is_f:
                        cx = 2 + len(label) + min(len(disp), fw - 1)
                        try:
                            win.move(min(row, dh - 2), min(cx, dw - 2))
                        except curses.error:
                            pass

            note = '(Session-Ordner leer = Download-Ordner)'
            win.attron(C.p(C.DIM))
            win.addstr(dh - 4, 2, note[:dw - 4])
            win.attroff(C.p(C.DIM))

            hints = '[Tab]=Weiter  [Leer/Enter]=Toggle  [F10]=Speichern  [Esc]=Abbrechen'
            win.attron(C.p(C.KEY))
            win.addstr(dh - 2, 2, hints[:dw - 4])
            win.attroff(C.p(C.KEY))

            win.noutrefresh()
        except curses.error:
            pass

        _, _, ftype = _FIELDS[focus]
        curses.curs_set(1 if ftype == 'text' else 0)
        curses.doupdate()

        key  = stdscr.getch()
        fkey = _FIELDS[focus][0]
        ftype = _FIELDS[focus][2]

        if key in (9, curses.KEY_DOWN):
            focus = (focus + 1) % nf

        elif key in (curses.KEY_BTAB, curses.KEY_UP):
            focus = (focus - 1) % nf

        elif key == curses.KEY_F10:
            _save(values)
            curses.curs_set(0)
            return

        elif key == 27:
            curses.curs_set(0)
            return

        elif key in (curses.KEY_ENTER, 10, 13):
            if ftype == 'bool':
                values[fkey] = not values[fkey]
            else:
                focus = (focus + 1) % nf

        elif key == ord(' ') and ftype == 'bool':
            values[fkey] = not values[fkey]

        elif ftype == 'text':
            if key in (curses.KEY_BACKSPACE, 127, 8):
                values[fkey] = values[fkey][:-1]
            elif 32 <= key < 127:
                if len(values[fkey]) < fw - 1:
                    values[fkey] += chr(key)


def _save(values: dict) -> None:
    save_settings(Settings(
        download_dir        = values['download_dir'].strip(),
        ask_before_download = bool(values['ask_before_download']),
        upload_dir          = values['upload_dir'].strip(),
        remember_upload_dir = bool(values['remember_upload_dir']),
        session_dir         = values['session_dir'].strip(),
    ))
