"""Versioned grouping rules, also used by the historical data migration."""

import hashlib
import json
import re
from pathlib import PurePosixPath

FRAME = re.compile(r'^\s*File "(.+)", line \d+, in (.+?)\s*$', re.MULTILINE)


def fingerprint_v1(
    application: str | None,
    exception_type: str,
    traceback: str,
    message: str,
) -> str:
    frames = [
        (PurePosixPath(path.replace("\\", "/")).name, function)
        for path, function in FRAME.findall(traceback)
    ]
    signature = {
        "version": 1,
        "application": application,
        "exception_type": exception_type,
        "frames": frames,
        "fallback_message": None if frames else message,
    }
    encoded = json.dumps(signature, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
