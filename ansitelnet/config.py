from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR      = Path.home() / '.config' / 'ansitelnet'
SERVERS_FILE    = CONFIG_DIR / 'servers.json'
DIRECTORY_FILE  = CONFIG_DIR / 'directory.json'


@dataclass
class Server:
    name:  str
    host:  str
    port:  int = 23
    color: int = 16
    mode:  str = 'telnet'   # 'telnet' | 'nc'


def load() -> list[Server]:
    if not SERVERS_FILE.exists():
        return []
    try:
        raw = json.loads(SERVERS_FILE.read_text(encoding='utf-8'))
        return [Server(**s) for s in raw]
    except Exception:
        return []


def save(servers: list[Server]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SERVERS_FILE.write_text(
        json.dumps([asdict(s) for s in servers], indent=2, ensure_ascii=False),
        encoding='utf-8',
    )


def load_directory() -> list[Server]:
    """Gecachtes BBS-Verzeichnis laden (leer wenn noch nie gefetcht)."""
    if not DIRECTORY_FILE.exists():
        return []
    try:
        raw = json.loads(DIRECTORY_FILE.read_text(encoding='utf-8'))
        return [Server(**s) for s in raw]
    except Exception:
        return []


def save_directory(servers: list[Server]) -> None:
    """BBS-Verzeichnis-Cache schreiben."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DIRECTORY_FILE.write_text(
        json.dumps([asdict(s) for s in servers], indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
