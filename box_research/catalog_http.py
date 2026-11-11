"""両ビューアサーバーから利用する、切替準備DB専用のHTTP入口。"""

import json
from pathlib import Path
from typing import Any

from box_research.catalog_store import (
    catalog_pallets, load_catalog, preview_model_rename, rename_model, save_catalog,
)

ASSETS = {
    "/catalog_viewer.html": ("catalog_viewer.html", "text/html"),
    "/catalog_cases.html": ("catalog_viewer.html", "text/html"),
    "/catalog_viewer.js": ("catalog_viewer.js", "text/javascript"),
    "/catalog_viewer.css": ("catalog_viewer.css", "text/css"),
}
ASSET_DIR = Path(__file__).resolve().parent


def _reply(handler: Any, status: int, value: Any) -> None:
    body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_catalog(handler: Any, root: Path, method: str, path: str) -> bool:
    """対象リクエストのみ処理する。旧DBのAPI・保存先とは混在させない。"""
    if method == "GET" and path in ASSETS:
        filename, mime = ASSETS[path]
        body = (ASSET_DIR / filename).read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", mime + "; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if not path.startswith("/api/catalog"):
        return False
    try:
        if method == "GET" and path == "/api/catalog":
            data, revision = load_catalog(root)
            if "cases" not in data:
                raise ValueError("準備用ケースがありません。prepare-casesを実行してください")
            _reply(handler, 200, {
                **{key: data[key] for key in ("parts", "models", "lids", "cases")},
                "revision": revision, "pallets": catalog_pallets(root)["pallets"],
                "assignments": data["migration"]["case_assignments"],
                "model_references": {
                    key: sorted(old for old, current in data["migration"]["legacy_model_mapping"].items()
                                if current == key)
                    for key in data["models"]
                },
                "phase": data["migration"]["phase"],
            })
            return True
        if method != "POST" or path not in (
                "/api/catalog/save", "/api/catalog/rename-preview", "/api/catalog/rename"):
            _reply(handler, 404, {"status": "error", "message": "対応するAPIがありません"})
            return True
        length = int(handler.headers.get("Content-Length", 0))
        if not 0 < length <= 5_000_000:
            raise ValueError("保存データが空、または5MBを超えています")
        def unique_keys(pairs):
            records = {}
            for key, value in pairs:
                if key in records:
                    raise ValueError("リクエスト内のキーが重複しています: " + key)
                records[key] = value
            return records

        payload = json.loads(handler.rfile.read(length).decode("utf-8"),
                             object_pairs_hook=unique_keys)
        if not isinstance(payload, dict):
            raise ValueError("リクエストはオブジェクトが必要です")
        if path == "/api/catalog/save":
            if (not payload or set(payload) - {"revision", "parts", "models", "lids", "cases"}
                    or not isinstance(payload.get("revision"), str)
                    or len(payload) < 2):
                raise ValueError("保存対象と読込み時の版が必要です")
            data, revision = load_catalog(root)
            if payload["revision"] != revision:
                raise ValueError("別の画面で更新されています。再読み込みして再確認してください")
            for key in ("parts", "models", "lids", "cases"):
                if key in payload:
                    data[key] = payload[key]
            save_catalog(root, data, revision)
        elif path == "/api/catalog/rename-preview":
            _reply(handler, 200, preview_model_rename(root, payload["old_name"], payload["new_name"]))
            return True
        else:
            rename_model(root, payload["old_name"], payload["new_name"], payload["confirmation"])
        _reply(handler, 200, {"status": "ok", "message": "切替準備用の保存が完了しました"})
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        handler.log_error("Catalog request rejected: %s", error)
        _reply(handler, 400, {"status": "error", "message": str(error)})
    except OSError as error:
        handler.log_error("Catalog storage failed: %s", error)
        _reply(handler, 500, {"status": "error", "message": str(error)})
    return True
