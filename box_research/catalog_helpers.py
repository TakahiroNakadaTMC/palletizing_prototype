"""Shared helpers for the live catalog and archived migration preview."""

import hashlib
import json
from pathlib import Path
from typing import Any

from box_research.database_validation import normalize_id


SUPPLIER_NAMES = {"クゼー": "グゼー", "NITTAN": "ニッタン"}


def file_sha256(path: Path) -> str:
    """Hash file content while treating CRLF and LF as equivalent."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def supplier_name(value: str) -> str:
    normalized = normalize_id(value)
    return SUPPLIER_NAMES.get(normalized, normalized)


def read_json(path: Path) -> Any:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("{}: JSONキーが重複しています: {}".format(path, key))
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)
