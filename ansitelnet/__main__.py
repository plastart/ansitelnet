"""
ansitelnet — BBS Terminal Connector
Ohne Argumente: Serverbook öffnen.
Mit Argumente:  Direkt verbinden.
"""
from __future__ import annotations
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='ansitelnet',
        description='BBS Terminal Connector mit ZModem-Unterstützung',
        add_help=True,
    )
    parser.add_argument('host', nargs='?', help='BBS-Hostname oder IP')
    parser.add_argument('port', nargs='?', type=int, default=23, help='Port (Standard: 23)')
    parser.add_argument('-8',  dest='color', action='store_const', const=8,  default=16,
                        help='8-Farben ANSI-Modus  (TERM=ansi)')
    parser.add_argument('-16', dest='color', action='store_const', const=16,
                        help='16-Farben ANSI-Modus (Standard, TERM=xterm-16color)')
    parser.add_argument('-n',  dest='mode',  action='store_const', const='nc',
                        default='telnet', help='Netcat-Modus (kein Telnet-Handshake)')
    parser.add_argument('-w', '--width', dest='width', type=int, default=0,
                        metavar='N',
                        help='Anzeigebreite auf N Zeichen begrenzen und zentrieren (z.B. 80)')
    parser.add_argument('-r', '--record', dest='record', action='store_true',
                        default=False,
                        help='Session von Anfang an als asciinema-Cast aufzeichnen')
    args = parser.parse_args()

    if args.host:
        # Direktverbindung ohne UI
        from .proxy import run_proxy
        run_proxy(args.host, args.port, color_mode=args.color, mode=args.mode,
                  cap_width=args.width, record=args.record)
    else:
        # Serverbook-UI
        from .ui.serverbook import run_serverbook
        server = run_serverbook()
        if server:
            from .proxy import run_proxy
            run_proxy(server.host, server.port,
                      color_mode=server.color,
                      mode=server.mode or 'telnet',
                      cap_width=args.width,
                      record=args.record,
                      download_dir=server.download_dir,
                      upload_dir=server.upload_dir)


if __name__ == '__main__':
    main()
