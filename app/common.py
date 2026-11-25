from __future__ import annotations
import hashlib, json, os, re, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def now(): return datetime.now(timezone.utc).isoformat()
def uid(prefix): return prefix + '_' + uuid.uuid4().hex
def sha(data): return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp-' + uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'); os.replace(tmp, path)
def inside(base, target):
    base = Path(base).resolve(); target = Path(target).resolve()
    if not target.is_relative_to(base): raise ValueError('path escapes allowed root')
    return target
def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'password|authorization|api.?key|secret|credential', k, re.I) else redact(v)) for k,v in value.items()}
    if isinstance(value, list): return [redact(v) for v in value]
    if isinstance(value, str):
        # Never record reasoning; remove bearer/key-like material from diagnostics.
        return re.sub(r'(?i)(Bearer\s+|sk-)[\w.\-]+', '[REDACTED]', value)
    return value
