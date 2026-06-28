"""Gemeinsame curses-Hilfsfunktionen für alle UI-Module."""
import curses


def win_box(win, h: int, w: int) -> None:
    """Zeichnet einen einfachen Rahmen (0,0)–(h-1,w-1) ins curses-Fenster."""
    try:
        win.addstr(0,     0, '┌' + '─' * (w - 2) + '┐')
        win.addstr(h - 1, 0, '└' + '─' * (w - 2) + '┘')
        for i in range(1, h - 1):
            win.addstr(i, 0,     '│')
            win.addstr(i, w - 1, '│')
    except curses.error:
        pass
