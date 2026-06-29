"""
Serverbook Hauptscreen (curses).
Tab 1 "Serverbook":  persönliche gespeicherte Server.
Tab 2 "Verzeichnis": Online-BBS-Liste von telnetbbsguide.com (F5=Aktualisieren).

Rechtes Panel: Session-Recordings für den gewählten Server.
  [Tab]   = zwischen Serverliste, Replays und Suchfeld wechseln
  [Enter] auf Replay = Cast abspielen (Player startet, danach Serverbook zurück)
  [←/Esc] im Replay-Panel = zurück zur Serverliste
"""
from __future__ import annotations
import curses
import datetime
import glob
import os
from ..config import Server, load, save, load_directory, save_directory
from . import win_box as _win_box


def run_serverbook() -> Server | None:
    """Serverbook öffnen. Gibt ausgewählten Server zurück oder None."""
    while True:
        result = curses.wrapper(_main)
        if result is None or isinstance(result, Server):
            return result
        # result ist ein Cast-Dateipfad → abspielen, dann Serverbook neu starten
        from .cast_player import play_cast
        play_cast(result)


def _filter(servers: list[Server], q: str) -> list[Server]:
    if not q:
        return servers
    q = q.lower()
    return [s for s in servers if q in s.name.lower() or q in s.host.lower()]


def _find_replays(server: Server) -> list[str]:
    """Cast-Dateien für diesen Server im Session-Verzeichnis (neueste zuerst)."""
    try:
        from ..config import load_settings, effective_session_dir
        sdir   = effective_session_dir(load_settings())
        safe_h = server.host.replace(':', '_')
        files  = glob.glob(str(sdir / f'{safe_h}_{server.port}_*.cast'))
        files.sort(key=os.path.getmtime, reverse=True)
        return files
    except Exception:
        return []


def _cast_label(path: str, host: str, port: int) -> str:
    """Cast-Dateiname → lesbares Datum/Zeit-Label (z.B. '29.06.26 14:30')."""
    fname  = os.path.basename(path)
    prefix = f'{host.replace(":", "_")}_{port}_'
    if fname.startswith(prefix) and fname.endswith('.cast'):
        try:
            dt = datetime.datetime.strptime(fname[len(prefix):-5], '%Y-%m-%d_%H-%M-%S')
            return dt.strftime('%d.%m.%y %H:%M')
        except ValueError:
            pass
    return fname


# ── Hauptloop ─────────────────────────────────────────────────────────────────

def _main(stdscr) -> Server | str | None:
    """Gibt Server, Cast-Dateipfad (str) oder None zurück."""
    from . import colors as C
    C.init()
    curses.curs_set(0)

    servers     = load()
    dir_servers = load_directory()
    dir_status  = f'{len(dir_servers)} Einträge' if dir_servers else 'Nicht geladen – [F5]'

    cursor     = 0
    scroll     = 0
    q          = ''
    panel      = 'list'    # 'list' | 'replays' | 'q'
    view       = 'book'    # 'book' | 'dir'
    rep_cursor = 0
    rep_scroll = 0
    _prev_sel  = object()  # Sentinel – noch kein Server selektiert

    while True:
        active   = servers if view == 'book' else dir_servers
        filtered = _filter(active, q)
        H, W     = stdscr.getmaxyx()
        list_h   = max(3, H - 16)
        show_rep = W >= 70              # Replay-Panel erst ab 70 Spalten

        cursor = max(0, min(cursor, len(filtered) - 1)) if filtered else 0
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        # Replays für aktuell selektierten Server ermitteln
        sel = filtered[cursor] if filtered and cursor < len(filtered) else None
        if sel is not _prev_sel:
            rep_cursor = 0
            rep_scroll = 0
            _prev_sel  = sel
        replays = _find_replays(sel) if sel and show_rep else []

        rep_cursor = max(0, min(rep_cursor, len(replays) - 1)) if replays else 0
        if rep_cursor < rep_scroll:
            rep_scroll = rep_cursor
        elif rep_cursor >= rep_scroll + list_h:
            rep_scroll = rep_cursor - list_h + 1

        if panel == 'replays' and not show_rep:
            panel = 'list'

        _draw(stdscr, H, W, filtered, cursor, scroll, list_h,
              q, panel, view, dir_status,
              replays, rep_cursor, rep_scroll, sel, show_rep)

        curses.curs_set(0 if panel in ('list', 'replays') else 1)
        key = stdscr.getch()

        # ── Einstellungen (F3) ────────────────────────────────────────────
        if key == curses.KEY_F3:
            from .settings import open_settings
            open_settings(stdscr)
            continue

        # ── View wechseln (F4) ─────────────────────────────────────────────
        if key == curses.KEY_F4:
            view = 'dir' if view == 'book' else 'book'
            cursor = 0; scroll = 0; q = ''; panel = 'list'
            continue

        # ── Verzeichnis aktualisieren (F5) ─────────────────────────────────
        if key == curses.KEY_F5:
            _draw_fetch_status(stdscr, H, W, 'Verbinde mit telnetbbsguide.com …')
            try:
                from ..directory import fetch
                new_dir     = fetch(on_status=lambda m: _draw_fetch_status(stdscr, H, W, m))
                save_directory(new_dir)
                dir_servers = new_dir
                dir_status  = f'{len(dir_servers)} Einträge – aktuell'
                if view == 'dir':
                    cursor = 0; scroll = 0
            except Exception as e:
                dir_status = f'Fehler: {str(e)[:60]}'
            continue

        # ── Serverliste ────────────────────────────────────────────────────
        if panel == 'list':
            if key == curses.KEY_UP and cursor > 0:
                cursor -= 1
            elif key == curses.KEY_DOWN and filtered and cursor < len(filtered) - 1:
                cursor += 1
            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - list_h)
            elif key == curses.KEY_NPAGE:
                cursor = min(len(filtered) - 1, cursor + list_h) if filtered else 0
            elif key in (curses.KEY_ENTER, 10, 13):
                if filtered and cursor < len(filtered):
                    return filtered[cursor]
            elif key == curses.KEY_IC:
                if view == 'book':
                    s = _edit_dialog(stdscr, None)
                    if s:
                        servers.append(s); save(servers)
                        cursor = max(0, len(_filter(servers, q)) - 1)
                elif view == 'dir' and filtered and cursor < len(filtered):
                    entry = filtered[cursor]
                    if entry not in servers:
                        servers.append(entry); save(servers)
            elif key == curses.KEY_F2 and view == 'book':
                if filtered and cursor < len(filtered):
                    orig = filtered[cursor]
                    s = _edit_dialog(stdscr, orig)
                    if s:
                        servers[servers.index(orig)] = s; save(servers)
            elif key == curses.KEY_DC and view == 'book':
                if filtered and cursor < len(filtered):
                    servers.pop(servers.index(filtered[cursor])); save(servers)
                    cursor = max(0, min(cursor, len(_filter(servers, q)) - 1))
            elif key == 9:                      # Tab → Replays oder Suche
                panel = 'replays' if show_rep else 'q'
            elif key == 27:
                return None
            elif 32 <= key < 127:
                q = chr(key); cursor = 0; panel = 'q'

        # ── Replay-Panel ───────────────────────────────────────────────────
        elif panel == 'replays':
            if key == curses.KEY_UP and rep_cursor > 0:
                rep_cursor -= 1
            elif key == curses.KEY_DOWN and replays and rep_cursor < len(replays) - 1:
                rep_cursor += 1
            elif key in (curses.KEY_ENTER, 10, 13):
                if replays and rep_cursor < len(replays):
                    return replays[rep_cursor]  # Dateipfad → run_serverbook spielt ab
            elif key == 9:                      # Tab → Suche
                panel = 'q'
            elif key in (27, curses.KEY_LEFT):
                panel = 'list'

        # ── Sucheingabe ────────────────────────────────────────────────────
        else:
            if key == 9:
                panel = 'list'
            elif key in (curses.KEY_UP, curses.KEY_DOWN):
                panel = 'list'
            elif key == 27:
                if q:
                    q = ''; cursor = 0
                else:
                    panel = 'list'
            elif key in (curses.KEY_ENTER, 10, 13):
                if filtered and cursor < len(filtered):
                    return filtered[cursor]
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                q = q[:-1]; cursor = 0
            elif 32 <= key < 127:
                q += chr(key); cursor = 0

    return None


# ── Zeichenfunktionen ─────────────────────────────────────────────────────────

def _draw(stdscr, H: int, W: int, servers: list[Server],
          cursor: int, scroll: int, list_h: int,
          q: str, panel: str, view: str, dir_status: str,
          replays: list[str], rep_cursor: int, rep_scroll: int,
          sel_server: Server | None, show_rep: bool) -> None:
    from . import colors as C
    try:
        stdscr.erase()

        # ── Kopfzeile ─────────────────────────────────────────────────────
        stdscr.attron(C.p(C.TITLE) | curses.A_BOLD)
        stdscr.addstr(0, 0, ' ansitelnet '.ljust(W)[:W])
        stdscr.attroff(C.p(C.TITLE) | curses.A_BOLD)

        # Tabs in Zeile 1
        tab_book = ' Serverbook '
        tab_dir  = ' Verzeichnis '
        tab_hint = '[F3]=Einstellungen  [F4]=Wechseln  [F5]=Aktualisieren  [Esc]=Ende '
        col = 1
        for label, is_active in ((tab_book, view == 'book'), (tab_dir, view == 'dir')):
            attr = (C.p(C.SELECT) | curses.A_BOLD) if is_active else C.p(C.DIM)
            try:
                stdscr.attron(attr)
                stdscr.addstr(1, col, label[:W - col - 1])
                stdscr.attroff(attr)
            except curses.error:
                pass
            col += len(label) + 1
        try:
            stdscr.attron(C.p(C.KEY))
            stdscr.addstr(1, max(col, W - len(tab_hint) - 1), tab_hint[:W - 2])
            stdscr.attroff(C.p(C.KEY))
        except curses.error:
            pass

        # Trennlinie
        stdscr.attron(C.p(C.BORDER))
        try:
            stdscr.addstr(2, 0, '─' * (W - 1))
        except curses.error:
            pass
        stdscr.attroff(C.p(C.BORDER))

        # Sektion-Header
        section = (f'Serverbook ({len(servers)} Einträge)'
                   if view == 'book' else f'Verzeichnis – {dir_status}')
        if q:
            section += f'  [Suche: {q}]'
        stdscr.attron(C.p(C.INFO) | curses.A_BOLD)
        try:
            stdscr.addstr(3, 1, section[:W - 2])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.INFO) | curses.A_BOLD)

        # ── Spaltenaufteilung ──────────────────────────────────────────────
        ly = 4
        lh = list_h + 2

        if show_rep:
            split = W * 3 // 5      # Spalte der Trennlinie
            lw    = split - 1       # nutzbare Breite linker Bereich
            rw    = W - split - 2   # nutzbare Breite rechter Bereich
            rx    = split + 1       # linke Spalte rechter Inhalt
        else:
            split = None
            lw    = W - 3

        # Rahmen zeichnen (mit optionaler Trennlinie)
        stdscr.attron(C.p(C.BORDER))
        _main_box(stdscr, ly, W, lh, split)
        stdscr.attroff(C.p(C.BORDER))

        # ── Serverliste (linkes Panel) ─────────────────────────────────────
        name_w  = max(8, lw - 22)
        list_focused = panel == 'list'
        for slot in range(list_h):
            abs_i = scroll + slot
            row   = ly + 1 + slot
            if row >= ly + lh - 1 or abs_i >= len(servers):
                break
            srv    = servers[abs_i]
            is_cur = (abs_i == cursor)
            line   = f' {srv.name:<{name_w}}  {srv.host}:{srv.port}'
            if is_cur and list_focused:
                stdscr.attron(C.p(C.SELECT) | curses.A_BOLD)
            elif is_cur:
                stdscr.attron(C.p(C.SELECT))
            try:
                stdscr.addstr(row, 1, line[:lw])
            except curses.error:
                pass
            if is_cur:
                stdscr.attroff(C.p(C.SELECT) | curses.A_BOLD)

        if not servers:
            stdscr.attron(C.p(C.DIM))
            if q:
                msg = f'Keine Treffer für "{q}"'
            elif view == 'book':
                msg = 'Keine Server – [Ins] für neuen Eintrag'
            else:
                msg = 'Verzeichnis leer – [F5] zum Laden'
            try:
                stdscr.addstr(ly + 1, 2, msg[:lw - 2])
            except curses.error:
                pass
            stdscr.attroff(C.p(C.DIM))

        # ── Replay-Panel (rechtes Panel) ──────────────────────────────────
        if show_rep:
            rep_focused = panel == 'replays'

            # Mini-Header in der ersten Zeile des rechten Panels
            n_str  = f'{len(replays)}' if replays else '–'
            host_s = f' {sel_server.host}' if sel_server else ''
            hdr    = f' ▶ {n_str} Aufnahme(n){host_s}'
            stdscr.attron(C.p(C.INFO) | curses.A_BOLD)
            try:
                stdscr.addstr(ly + 1, rx, hdr[:rw])
            except curses.error:
                pass
            stdscr.attroff(C.p(C.INFO) | curses.A_BOLD)

            # Replay-Einträge (ab Zeile ly+2, Header belegt ly+1)
            rep_h = list_h - 1
            for slot in range(rep_h):
                abs_i = rep_scroll + slot
                row   = ly + 2 + slot
                if row >= ly + lh - 1 or abs_i >= len(replays):
                    break
                label  = _cast_label(replays[abs_i],
                                     sel_server.host if sel_server else '',
                                     sel_server.port if sel_server else 0)
                is_cur = (abs_i == rep_cursor)
                line   = f' {label}'
                if is_cur and rep_focused:
                    stdscr.attron(C.p(C.SELECT) | curses.A_BOLD)
                elif is_cur:
                    stdscr.attron(C.p(C.SELECT))
                try:
                    stdscr.addstr(row, rx, line[:rw])
                except curses.error:
                    pass
                if is_cur:
                    stdscr.attroff(C.p(C.SELECT) | curses.A_BOLD)

            if not replays and sel_server:
                stdscr.attron(C.p(C.DIM))
                try:
                    stdscr.addstr(ly + 2, rx, ' Keine Aufnahmen'[:rw])
                except curses.error:
                    pass
                stdscr.attroff(C.p(C.DIM))

        # ── Aktions-Hinweise ────────────────────────────────────────────────
        hint_row = ly + lh
        stdscr.attron(C.p(C.KEY))
        if panel == 'replays':
            hints = '[↑↓]=Auswahl  [Enter]=Abspielen  [←/Esc]=zurück  [Tab]=Suche'
        elif view == 'book':
            hints = '[Ins]=Neu  [F2]=Edit  [Entf]=Löschen  [Enter]=Verbinden  [Tab]=Replays'
        else:
            hints = '[Ins]=→Serverbook  [Enter]=Verbinden  [Tab]=Replays  [F5]=Aktualisieren'
        try:
            stdscr.addstr(hint_row, 1, hints[:W - 2])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.KEY))

        # Trennlinie
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
        field_w = min(40, W - 22)
        q_attr  = C.p(C.INPUT) | curses.A_BOLD if panel == 'q' else C.p(C.INPUT)
        stdscr.attron(q_attr)
        try:
            stdscr.addstr(sq_row, 2 + len(host_lbl),
                          (q + ' ').ljust(field_w)[:field_w])
        except curses.error:
            pass
        stdscr.attroff(q_attr)

        if panel == 'q':
            curpos_x = 2 + len(host_lbl) + min(len(q), field_w - 1)
            try:
                stdscr.move(sq_row, min(curpos_x, W - 1))
            except curses.error:
                pass

        sq_row += 1
        stdscr.attron(C.p(C.KEY))
        try:
            stdscr.addstr(sq_row, 2,
                          '[↑↓]=Liste  [Tab]=Weiter  [Enter]=Verbinden  [Esc]=Löschen/Liste'[:W - 4])
        except curses.error:
            pass
        stdscr.attroff(C.p(C.KEY))

        stdscr.noutrefresh()
    except curses.error:
        pass

    curses.doupdate()


def _main_box(stdscr, ly: int, W: int, lh: int, split: int | None) -> None:
    """Hauptbox; bei split≠None mit vertikaler Trennlinie bei Spalte split."""
    try:
        if split is None:
            stdscr.addstr(ly,          0, '┌' + '─' * (W - 2) + '┐')
            stdscr.addstr(ly + lh - 1, 0, '└' + '─' * (W - 2) + '┘')
            for i in range(1, lh - 1):
                stdscr.addstr(ly + i, 0,     '│')
                stdscr.addstr(ly + i, W - 1, '│')
        else:
            lw = split - 1
            rw = W - split - 2
            stdscr.addstr(ly,          0, '┌' + '─' * lw + '┬' + '─' * rw + '┐')
            stdscr.addstr(ly + lh - 1, 0, '└' + '─' * lw + '┴' + '─' * rw + '┘')
            for i in range(1, lh - 1):
                stdscr.addstr(ly + i, 0,       '│')
                stdscr.addstr(ly + i, split,   '│')
                stdscr.addstr(ly + i, W - 1,   '│')
    except curses.error:
        pass


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
        win.addstr(0, max(1, (dw - len(t)) // 2), t[:dw - 2])
        win.attroff(C.p(C.TITLE) | curses.A_BOLD)
        win.addstr(2, 2, msg[:dw - 4])
        win.noutrefresh()
    except curses.error:
        pass
    curses.doupdate()


# ── Server bearbeiten / anlegen ───────────────────────────────────────────────

def _edit_dialog(stdscr, srv: Server | None) -> Server | None:
    from . import colors as C

    fields = {
        'name':         srv.name            if srv else '',
        'host':         srv.host            if srv else '',
        'port':         str(srv.port)       if srv else '23',
        'color':        str(srv.color)      if srv else '16',
        'mode':         srv.mode            if srv else '',
        'download_dir': srv.download_dir    if srv else '',
        'upload_dir':   srv.upload_dir      if srv else '',
    }
    order  = ['name', 'host', 'port', 'color', 'mode', 'download_dir', 'upload_dir']
    labels = {
        'name':         'Name:           ',
        'host':         'Host:           ',
        'port':         'Port:           ',
        'color':        'Farben:         ',
        'mode':         'Modus:          ',
        'download_dir': 'Download-Ordner:',
        'upload_dir':   'Upload-Ordner:  ',
    }
    focus = 0

    while True:
        H, W = stdscr.getmaxyx()
        dh, dw = 20, min(66, W - 4)
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
            win.addstr(0, max(1, (dw - len(t)) // 2), t[:dw - 2])
            win.attroff(C.p(C.TITLE) | curses.A_BOLD)

            fw = dw - len(labels['download_dir']) - 6
            for i, fname in enumerate(order):
                row  = 2 + i * 2
                lbl  = labels[fname]
                val  = fields[fname]
                is_f = (i == focus)
                attr = C.p(C.INPUT) | curses.A_BOLD if is_f else C.p(C.INPUT)
                win.addstr(row, 2, lbl)
                win.attron(attr)
                win.addstr(row, 2 + len(lbl), (val + ' ').ljust(fw)[:fw])
                win.attroff(attr)

            win.attron(C.p(C.DIM))
            win.addstr(dh - 4, 2, '(Ordner leer = globale Einstellung)'[:dw - 4])
            win.attroff(C.p(C.DIM))

            win.attron(C.p(C.KEY))
            win.addstr(dh - 2, 2, '[Tab]=Weiter  [Enter]=OK  [Esc]=Abbr.'[:dw - 4])
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
                        name         = fields['name'].strip() or fields['host'].strip(),
                        host         = fields['host'].strip(),
                        port         = int(fields['port']) if fields['port'].isdigit() else 23,
                        color        = int(fields['color']) if fields['color'].isdigit() else 16,
                        mode         = fields['mode'].strip(),
                        download_dir = fields['download_dir'].strip(),
                        upload_dir   = fields['upload_dir'].strip(),
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
