import curses

# Farbpaar-IDs
TITLE  = 1   # Weiss auf Blau         (Titelleisten)
BORDER = 2   # Cyan auf Standard       (Rahmen)
NORMAL = 3   # Weiss auf Standard      (Text)
SELECT = 4   # Schwarz auf Cyan        (Auswahl)
INPUT  = 5   # Weiss auf Dunkelblau    (Eingabefelder)
INFO   = 6   # Gelb auf Standard       (Dateiinfo, Meldungen)
BAR    = 7   # Schwarz auf Cyan        (Fortschrittsbalken gefüllt)
KEY    = 8   # Cyan auf Standard       (Tastenkürzel-Hinweise)
ERROR  = 9   # Weiss auf Rot           (Fehler)
DIM    = 10  # Schwarz auf Standard    (abgedunkelter Text)


def init() -> None:
    """Farbpaare initialisieren. Muss nach curses.initscr() aufgerufen werden."""
    curses.start_color()
    curses.use_default_colors()
    bg = -1   # transparenter Hintergrund

    if curses.has_colors():
        curses.init_pair(TITLE,  curses.COLOR_WHITE,  curses.COLOR_BLUE)
        curses.init_pair(BORDER, curses.COLOR_CYAN,   bg)
        curses.init_pair(NORMAL, curses.COLOR_WHITE,  bg)
        curses.init_pair(SELECT, curses.COLOR_BLACK,  curses.COLOR_CYAN)
        curses.init_pair(INPUT,  curses.COLOR_WHITE,  curses.COLOR_BLUE)
        curses.init_pair(INFO,   curses.COLOR_YELLOW, bg)
        curses.init_pair(BAR,    curses.COLOR_BLACK,  curses.COLOR_CYAN)
        curses.init_pair(KEY,    curses.COLOR_CYAN,   bg)
        curses.init_pair(ERROR,  curses.COLOR_WHITE,  curses.COLOR_RED)
        curses.init_pair(DIM,    curses.COLOR_BLACK,  bg)
    else:
        for i in range(1, 11):
            curses.init_pair(i, -1, -1)


def p(n: int) -> int:
    return curses.color_pair(n)
