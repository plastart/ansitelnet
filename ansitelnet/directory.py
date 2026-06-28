"""
BBS-Verzeichnis: Download und Parsing von telnetbbsguide.com.

URL-Strategie (ohne Abhängigkeit von externen Dateien):
  Daily:   ibbs{MM}{DD}{YY}.zip  (heute + letzte 2 Tage)
  Monthly: ibbs{MM}{YY}.zip      (Fallback)

Außerdem werden daily.url / monthly.url aus ~/.config/ansitelnet/ gelesen,
falls der Nutzer sie dort ablegt – oder aus dem Projektverzeichnis (Entwicklung).
"""
from __future__ import annotations
import datetime
import io
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable

from .config import CONFIG_DIR, Server

_GUIDE_BASE = 'http://www.telnetbbsguide.com/bbslist/'
# Projektverzeichnis (bei Entwicklung: telnetbbsguide.com/ liegt direkt neben ansitelnet/)
_PROJ_GUIDE_DIR = Path(__file__).parent.parent / 'telnetbbsguide.com'


def _compute_urls() -> list[str]:
    """Berechnet mögliche ZIP-URLs aus aktuellem Datum (heute + 2 Vortage + monatlich)."""
    today = datetime.date.today()
    urls: list[str] = []
    for delta in range(3):
        d = today - datetime.timedelta(days=delta)
        yy = d.strftime('%y')
        urls.append(f'{_GUIDE_BASE}ibbs{d.month:02d}{d.day:02d}{yy}.zip')
    # Monatlicher Fallback
    urls.append(f'{_GUIDE_BASE}ibbs{today.month:02d}{today.strftime("%y")}.zip')
    return urls


def _file_urls() -> list[str]:
    """Liest .url-Dateien aus Config-Verzeichnis und Projektordner."""
    urls: list[str] = []
    for base in (CONFIG_DIR, _PROJ_GUIDE_DIR):
        for fname in ('daily.url', 'monthly.url'):
            p = base / fname
            try:
                url = p.read_text(encoding='utf-8').strip()
                if url and url not in urls:
                    urls.append(url)
            except OSError:
                pass
    return urls


def candidate_urls() -> list[str]:
    """Alle zu probierenden URLs, priorisiert: .url-Dateien, dann Datum-Berechnung."""
    seen: set[str] = set()
    result: list[str] = []
    for url in _file_urls() + _compute_urls():
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def fetch(on_status: Callable[[str], None] | None = None) -> list[Server]:
    """Lädt das BBS-Verzeichnis herunter und gibt eine Liste von Server-Einträgen zurück.

    Probiert alle URLs der Reihe nach; beim ersten Erfolg wird das Ergebnis zurückgegeben.
    on_status(msg): optionale Callback-Funktion für Statusmeldungen.
    """
    urls = candidate_urls()
    last_err: Exception | None = None
    for url in urls:
        if on_status:
            on_status(f'Lade {url} …')
        try:
            data = _download(url)
            servers = _parse_zip(data)
            if on_status:
                on_status(f'{len(servers)} Eintr\xe4ge geladen.')
            return servers
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f'Kein Download erfolgreich (letzer Fehler: {last_err})\n'
        f'Probierte URLs:\n' + '\n'.join(f'  {u}' for u in urls)
    )


def _download(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'ansitelnet/1.0 (+http://github.com/plastart/ansitelnet)'},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _parse_zip(data: bytes) -> list[Server]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml_name = next(
            (n for n in zf.namelist() if n.lower().endswith('.xml')),
            None,
        )
        if xml_name is None:
            raise ValueError('Keine XML-Datei im ZIP gefunden')
        xml_data = zf.read(xml_name)
    return _parse_xml(xml_data)


def _parse_xml(xml_data: bytes) -> list[Server]:
    import re as _re
    # Quelldatei enthält manchmal nacktes & in Attributwerten (z.B. "Bits & Bytes BBS").
    # Das ist kein gültiges XML – vor dem Parsen bereinigen.
    xml_data = _re.sub(
        rb'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)',
        b'&amp;',
        xml_data,
    )
    root = ET.fromstring(xml_data)
    servers: list[Server] = []
    for bbs in root.iter('BBS'):
        name = (bbs.get('name') or '').strip()
        ip   = (bbs.get('ip')   or '').strip()
        try:
            port = int(bbs.get('port') or '23')
        except ValueError:
            port = 23
        if name and ip:
            servers.append(Server(name=name, host=ip, port=port))
    return servers
