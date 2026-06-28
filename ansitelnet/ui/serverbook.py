"""
Serverbook Hauptscreen (curses).
Tab 1 "Serverbook":  persönliche gespeicherte Server.
Tab 2 "Verzeichnis": Online-BBS-Liste von telnetbbsguide.com (F5=Aktualisieren).
"""
from __future__ import annotations
import curses
from ..config import Server, load, save, load_directory, save_directory
from . import win_box as _win_box


def run_serverbook() -> Server | None:
    """Serverbook öffnen. Gibt ausgewählten Server zurück oder None."""
    def _w(stdscr):
        return _main(stdscr)
    return curses.wrapper(_w)


def _filter(servers: list[Server], q: str) -> list[Server]:
    if not q:
        return servers
    q = q.lower()
    return [s for s in servers if q in s.name.lower() or q in s.host.lower()]


# ── Hauptloop ─────────────────────────────────────────────────────────────────

def _main(stdscr) -> Server | None:
    from . import colors as C
    C.init()
    curses.curs_set(0)

    servers     = load()
    dir_servers = load_directory()   # gecachtes Verzeichnis
    dir_status  = f'{len(dir_servers)} Eintr\xe4ge' if dir_servers else 'Nicht geladen – [F5]'

    cursor   = 0
    scroll   = 0
    q        = ''          # Filter-/Sucheingabe
    dc_port  = '23'
    focus    = 'list'      # 'list' | 'q'
    view     = 'book'      # 'book' | 'dir'

    while True:
        active   = servers if view == 'book' else dir_servers
        filtered = _filter(active, q)
        H, W     = stdscr.getmaxyx()
        list_h   = max(3, H - 16)

        cursor = max(0, min(cursor, len(filtered) - 1)) if filtered else 0
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        _draw(stdscr, H, W, filtered, cursor, scroll, list_h,
              q, dc_port, focus, view, dir_status)

        curses.curs_set(0 if focus == 'list' else 1)
        key = stdscr.getch()

        # ── Tab wechseln ───────────────────────────────────────────────────
        if key == curses.KEY_F4:
            view   = 'dir' if view == 'book' else 'book'
            cursor = 0
            scroll = 0
            q      = ''
            focus  = 'list'
            continue

        # ── Verzeichnis aktualisieren (F5) ─────────────────────────────────
        if key == curses.KEY_F5:
            _draw_fetch_status(stdscr, H, W, 'Verbinde mit telnetbbsguide.com …')
            status_msg = ''
            try:
                from ..directory import fetch
                new_dir = fetch(on_status=lambda m: _draw_fetch_status(stdscr, H, W, m))
                save_directory(new_dir)
                dir_servers = new_dir
                dir_status  = f'{len(dir_servers)} Eintr\xe4ge – aktuell'
                if view == 'dir':
                    cursor = 0
                    scroll = 0
            except Exception as e:
                dir_status = f'Fehler: {str(e)[:60]}'
            continue

        # ── Serverliste ────────────────────────────────────────────────────
        if focus == 'list':
            if key == curses.KEY_UP:
                if cursor > 0:
                    cursor -= 1

            elif key == curses.KEY_DOWN:
                if filtered and cursor < len(filtered) - 1:
                    cursor += 1

            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - list_h)

            elif key == curses.KEY_NPAGE:
                cursor = min(len(filtered) - 1, cursor + list_h) if filtered else 0

            elif key in (curses.KEY_ENTER, 10, 13):
                if filtered and cursor < len(filtered):
                    return filtered[cursor]

            elif key == curses.KEY_IC:               # Einfg
                if view == 'book':
                    s = _edit_dialog(stdscr, None)
                    if s:
                        servers.append(s)
                        save(servers)
                        cursor = max(0, len(_filter(servers, q)) - 1)
                elif view == 'dir' and filtered and cursor < len(filtered):
                    # Verzeichnis-Eintrag ins Serverbook übernehmen
                    entry = filtered[cursor]
                    if entry not in servers:
                        servers.append(entry)
                        save(servers)

            elif key == curses.KEY_F2 and view == 'book':
                if filtered and cursor < len(filtered):
                    orig = filtered[cursor]
                    s = _edit_dialog(stdscr, orig)
                    if s:
                        idx = servers.index(orig)
                        servers[idx] = s
                        save(servers)

            elif key == curses.KEY_DC and view == 'book':
                if filtered and cursor < len(filtered):
                    orig = filtered[cursor]
                    idx  = servers.index(orig)
                    servers.pop(idx)
                    save(servers)
                    cursor = max(0, min(cursor, len(_filter(servers, q)) - 1))

            elif key == 9:                           # Tab → Sucheingabe
                focus = 'q'

            elif key == 27:
                return None

            elif 32 <= key < 127:
                q      = chr(key)
                cursor = 0
                focus  = 'q'

        # ── Sucheingabe ────────────────────────────────────────────────────
        else:
            if key == 9:
                focus = 'list'

            elif key in (curses.KEY_UP, curses.KEY_DOWN):
                focus = 'list'

            elif key == 27:
                if q:
                    q      = ''
                    cursor = 0
                else:
                    focus = 'list'

            elif key in (curses.KEY_ENTER, 10, 13):
                if filtered and cursor < len(filtered):
                    return filtered[cursor]

            elif key in (curses.KEY_BACKSPACE, 127, 8):
                q = q[:-1]
                cursor = 0

            elif 32 <= key < 127:
                q += chr(key)
                cursor = 0

    return None


# ── Zeichenfunktionen ─────────────────────────────────────────────────────────

def _draw(stdscr, H: int, W: int, servers: list[Server],
          cursor: int, scroll: int, list_h: int,
          q: str, dc_port: str, focus: str, view: str, dir_status: str) -> None:
    from . import colors as C
    try:
        stdscr.erase()

        # ── Kopfzeile mit Tab-Auswahl ──────────────────────────────────────
        tab_book = ' Serverbook '
        tab_dir  = ' Verzeichnis '
        tab_hint = '[F4]=Wechseln  [F5]=Aktualisieren  [Esc]=Ende '

        stdscr.attron(C.p(C.TITLE) | curses.A_BOLD)
        stdscr.addstr(0, 0, ' ansitelnet '.ljust(W)[: W])
        stdscr.attroff(C.p(C.TITLE) | curses.A_BOLD)

        # Tabs in Zeile 1
        col = 1
        for label, is_active in ((tab_book, view == 'book'), (tab_dir, view == 'dir')):
            attr = (C.p(C.SELECT) | curses.A_BOLD) if is_active else C.p(C.DIM)
            try:
                stdscr.attron(attr)
                stdscr.addstr(1, col, label[: W - col - 1])
                stdscr.attroff(attr)
            except curses.error:
                pass
            col += len(label) + 1

        try:
            stdscr.attron(C.p(C.KEY))
            stdscr.addstr(1, max(col, W - len(tab_hint) - 1), tab_hint[: W - 2])
            stdscr.attroff(C.p(C.KEY))
        except curses.error:
            pass

        # ── Trennlinie ─────────────────────────────────────────────────────
        stdscr.attron(C.p(C.BORDER))
        try:
            stdscr.addstr(2, 0, '─' * (W - 1))
        except curses.error:
            pass
        stdscr.attroff(C.p(C.BORDER))

        # ── Sektion-Header ──────────────────────────────────────────────────
        if view == 'book':
            section = f'Serverbook ({len(servers)} Eintr\xe4ge)'
        else:
            section = f'Verzeichnis – {dir_status}'
        if q:
            section += f'  [Suche: {q}]'

        stdscr.attron(C.p(C.INFO) | curses.A_BOLD)
        try:
            stdscr.addstr(3, 1, section[: W - 2])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.INFO) | curses.A_BOLD)

        # ── Serverliste ─────────────────────────────────────────────────────
        lx = 1
        ly = 4
        lw = W - 2
        lh = list_h + 2

        stdscr.attron(C.p(C.BORDER))
        _box(stdscr, ly, lx, lh, lw)
        stdscr.attroff(C.p(C.BORDER))

        name_w = max(10, lw - 28)
        for slot in range(list_h):
            abs_i = scroll + slot
            row   = ly + 1 + slot
            if row >= ly + lh - 1 or abs_i >= len(servers):
                break
            srv    = servers[abs_i]
            is_cur = (abs_i == cursor)
            conn   = f'{srv.host}:{srv.port}'
            line   = f' {srv.name:<{name_w}} {conn:>{lw - name_w - 5}}'

            if is_cur and focus == 'list':
                stdscr.attron(C.p(C.SELECT) | curses.A_BOLD)
            elif is_cur:
                stdscr.attron(C.p(C.SELECT))
            try:
                stdscr.addstr(row, lx + 1, line[: lw - 2])
            except curses.error:
                pass
            if is_cur:
                stdscr.attroff(C.p(C.SELECT) | curses.A_BOLD)

        if not servers:
            stdscr.attron(C.p(C.DIM))
            if q:
                msg = f'Keine Treffer f\xfcr "{q}"'
            elif view == 'book':
                msg = 'Keine Server – [Ins] f\xfcr neuen Eintrag'
            else:
                msg = 'Verzeichnis leer – [F5] zum Laden'
            try:
                stdscr.addstr(ly + 1, lx + 2, msg[: lw - 4])
            except curses.error:
                pass
            stdscr.attroff(C.p(C.DIM))

        # ── Aktions-Hinweise ────────────────────────────────────────────────
        hint_row = ly + lh
        stdscr.attron(C.p(C.KEY))
        if view == 'book':
            hints = '[Ins]=Neu  [F2]=Edit  [Entf]=L\xf6schen  [Enter]=Verbinden  [Tab]=Suche'
        else:
            hints = '[Ins]=→Serverbook  [Enter]=Verbinden  [Tab]=Suche  [F5]=Aktualisieren'
        try:
            stdscr.addstr(hint_row, 1, hints[: W - 2])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.KEY))

        # ── Trennlinie ─────────────────────────────────────────────────────
        sep_row = hint_row + 1
        stdscr.attron(C.p(C.BORDER))
        try:
            stdscr.addstr(sep_row, 0, '─' * (W - 1))
        except curses.error:
            pass
        stdscr.attroff(C.p(C.BORDER))

        # ── Suchfeld ────────────────────────────────────────────────────────
        sq_row = sep_row + 1
        stdscr.attron(C.p(C.INFO) | curses.A_BOLD)
        try:
            stdscr.addstr(sq_row, 1, 'Suche / Direktverbindung')
        except curses.error:
            pass
        stdscr.attroff(C.p(C.INFO) | curses.A_BOLD)
        sq_row += 1

        host_lbl = 'Host/Filter: '
        try:
            stdscr.addstr(sq_row, 2, host_lbl)
        except curses.error:
            pass
        field_w  = min(40, W - 22)
        q_attr = C.p(C.INPUT) | curses.A_BOLD if focus == 'q' else C.p(C.INPUT)
        stdscr.attron(q_attr)
        try:
            stdscr.addstr(sq_row, 2 + len(host_lbl),
                          (q + ' ').ljust(field_w)[: field_w])
        except curses.error:
            pass
        stdscr.attroff(q_attr)

        if focus == 'q':
            curpos_x = 2 + len(host_lbl) + min(len(q), field_w - 1)
            try:
                stdscr.move(sq_row, min(curpos_x, W - 1))
            except curses.error:
                pass

        sq_row += 1
        stdscr.attron(C.p(C.KEY))
        try:
            stdscr.addstr(sq_row, 2,
                          '[↑↓]=Liste  [Tab]=Weiter  [Enter]=Verbinden  [Esc]=L\xf6schen/Liste'[: W - 4])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.KEY))

        stdscr.noutrefresh()
    except curses.error:
        pass

    curses.doupdate()


def _draw_fetch_status(stdscr, H: int, W: int, msg: str) -> None:
    """Einfaches Statusfenster während des Downloads."""
    from . import colors as C
    try:
        dh, dw = 5, min(70, W - 4)
        dy = max(0, (H - dh) // 2)
        dx = max(0, (W - dw) // 2)
        win = curses.newwin(dh, dw, dy, dx)
        win.erase()
        win.attron(C.p(C.BORDER))
        _win_box(win, dh, dw)
        win.attroff(C.p(C.BORDER))
        t = '  Verzeichnis laden  '
        win.attron(C.p(C.TITLE) | curses.A_BOLD)
        win.addstr(0, max(1, (dw - len(t)) // 2), t[: dw - 2])
        win.attroff(C.p(C.TITLE) | curses.A_BOLD)
        win.addstr(2, 2, msg[: dw - 4])
        win.noutrefresh()
    except curses.error:
        pass
    curses.doupdate()


def _box(win, y: int, x: int, h: int, w: int) -> None:
    try:
        win.addstr(y,         x,     '┌' + '─' * (w - 2) + '┐')
        win.addstr(y + h - 1, x,     '└' + '─' * (w - 2) + '┘')
        for i in range(1, h - 1):
            win.addstr(y + i, x,         '│')
            win.addstr(y + i, x + w - 1, '│')
    except curses.error:
        pass


# ── Server bearbeiten / anlegen ───────────────────────────────────────────────

def _edit_dialog(stdscr, srv: Server | None) -> Server | None:
    from . import colors as C

    fields = {
        'name':  srv.name       if srv else '',
        'host':  srv.host       if srv else '',
        'port':  str(srv.port)  if srv else '23',
        'color': str(srv.color) if srv else '16',
        'mode':  srv.mode       if srv else 'telnet',
    }
    order  = ['name', 'host', 'port', 'color', 'mode']
    labels = {
        'name':  'Name:       ',
        'host':  'Host:       ',
        'port':  'Port:       ',
        'color': 'Farben:     ',
        'mode':  'Modus:      ',
    }
    focus = 0

    while True:
        H, W = stdscr.getmaxyx()
        dh, dw = 14, min(60, W - 4)
        dy = max(0, (H - dh) // 2)
        dx = max(0, (W - dw) // 2)

        try:
            win = curses.newwin(dh, dw, dy, dx)
            win.erase()
            win.attron(C.p(C.BORDER))
            _win_box(win, dh, dw)
            win.attroff(C.p(C.BORDER))

            t = '  Server bearbeiten  ' if srv else '  Neuer Server  '
            win.attron(C.p(C.TITLE) | curses.A_BOLD)
            win.addstr(0, max(1, (dw - len(t)) // 2), t[: dw - 2])
            win.attroff(C.p(C.TITLE) | curses.A_BOLD)

            fw = dw - len(labels['name']) - 6
            for i, fname in enumerate(order):
                row  = 2 + i * 2
                lbl  = labels[fname]
                val  = fields[fname]
                is_f = (i == focus)
                attr = C.p(C.INPUT) | curses.A_BOLD if is_f else C.p(C.INPUT)
                win.addstr(row, 2, lbl)
                win.attron(attr)
                win.addstr(row, 2 + len(lbl), (val + ' ').ljust(fw)[: fw])
                win.attroff(attr)

            hints = '[Tab]=Weiter  [Enter]=OK  [Esc]=Abbr.'
            win.attron(C.p(C.KEY))
            win.addstr(dh - 2, 2, hints[: dw - 4])
            win.attroff(C.p(C.KEY))

            fname   = order[focus]
            val     = fields[fname]
            cur_row = 2 + focus * 2
            cur_col = 2 + len(labels[fname]) + min(len(val), fw - 1)
            win.move(min(cur_row, dh - 2), min(cur_col, dw - 2))

            win.noutrefresh()
        except curses.error:
            pass
        curses.curs_set(1)
        curses.doupdate()

        key = stdscr.getch()

        if key in (9, curses.KEY_DOWN):
            focus = (focus + 1) % len(order)

        elif key in (curses.KEY_BTAB, curses.KEY_UP):
            focus = (focus - 1) % len(order)

        elif key in (curses.KEY_ENTER, 10, 13):
            if focus < len(order) - 1:
                focus = (focus + 1) % len(order)
            else:
                try:
                    return Server(
                        name  = fields['name'].strip() or fields['host'].strip(),
                        host  = fields['host'].strip(),
                        port  = int(fields['port']) if fields['port'].isdigit() else 23,
                        color = int(fields['color']) if fields['color'].isdigit() else 16,
                        mode  = fields['mode'].strip() or 'telnet',
                    )
                except ValueError:
                    pass

        elif key == 27:
            curses.curs_set(0)
            return None

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            fields[order[focus]] = fields[order[focus]][:-1]

        elif 32 <= key < 127:
            fname = order[focus]
            ch    = chr(key)
            if fname in ('port', 'color'):
                if ch.isdigit() and len(fields[fname]) < 5:
                    fields[fname] += ch
            else:
                if len(fields[fname]) < fw - 1:
                    fields[fname] += ch

    return None
