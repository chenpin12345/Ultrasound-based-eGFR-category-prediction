"""Bounded parsed-file cache for display only. Never validates execution inputs."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

@lru_cache(maxsize=32)
def _json(path, size, modified):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def display_json(path):
    path = Path(path)
    stat = path.stat()
    # Callers resolve managed paths first. Return copies: source assembly mutates entries.
    return deepcopy(_json(str(path), stat.st_size, stat.st_mtime_ns))
