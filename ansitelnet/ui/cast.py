"""asciinema v2 cast writer — kein externes Binary nötig zum Aufzeichnen."""
from __future__ import annotations
import json
import time


class CastWriter:
    def __init__(self, path: str, width: int, height: int, title: str = '') -> None:
        self._t0 = time.monotonic()
        self._f  = open(path, 'w', encoding='utf-8')
        header: dict = {'version': 2, 'width': width, 'height': height,
                        'timestamp': int(time.time())}
        if title:
            header['title'] = title
        self._f.write(json.dumps(header) + '\n')
        self._f.flush()

    def write(self, data: bytes) -> None:
        t    = round(time.monotonic() - self._t0, 6)
        text = data.decode('utf-8', errors='replace')
        self._f.write(json.dumps([t, 'o', text]) + '\n')
        self._f.flush()

    def close(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass

    @property
    def path(self) -> str:
        return self._f.name
