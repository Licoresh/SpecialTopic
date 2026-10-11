import hashlib
from datetime import datetime, timezone
import json

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(value).hexdigest()

def frame_hash(frame):
    return digest(frame.to_csv(index=False).encode("utf-8"))
