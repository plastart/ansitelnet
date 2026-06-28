from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR      = Path.home() / '.config' / 'ansitelnet'
SERVERS_FILE    = CONFIG_DIR / 'servers.json'
DIRECTORY_FILE  = CONFIG_DIR / 'directory.json'
SETTINGS_FILE   = CONFIG_DIR / 'settings.json'


@dataclass
class Server:
    name:         str
    host:         str
    port:         int = 23
    color:        int = 16
    mode:         str = ''   # 'telnet' | 'nc' | '' → global default
    download_dir: str = ''   # '' → globale Einstellung
    upload_dir:   str = ''   # '' → globale Einstellung


@dataclass
class Settings:
    download_dir:         str  = ''     # '' → ~/Downloads
    ask_before_download:  bool = False
    upload_dir:           str  = ''     # '' → ~
    remember_upload_dir:  bool = True
    session_dir:          str  = ''     # '' → download_dir


def effective_download_dir(s: Settings) -> Path:
    return Path(s.download_dir).expanduser() if s.download_dir else Path.home() / 'Downloads'


def effective_upload_dir(s: Settings) -> Path:
    return Path(s.upload_dir).expanduser() if s.upload_dir else Path.home()


def effective_session_dir(s: Settings) -> Path:
    return Path(s.session_dir).expanduser() if s.session_dir else effective_download_dir(s)


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        raw    = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        fields = set(Settings.__dataclass_fields__)
        return Settings(**{k: v for k, v in raw.items() if k in fields})
    except Exception:
        return Settings()


def save_settings(s: Settings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(asdict(s), indent=2, ensure_ascii=False),
        encoding='utf-8',
    )


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
