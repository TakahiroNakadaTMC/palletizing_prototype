#!/usr/bin/env python3
"""
箱・蓋データベース承認ビューワ起動スクリプト (serve_viewer.py)
ローカルHTTPサーバーを起動し、箱DB・蓋DBの統合タブ画面を表示します。
既存URLの転送と、箱・蓋DBの連動保存に対応しています。
"""

import http.server
import socketserver
import json
import os
import math
import tempfile
import webbrowser
import urllib.parse
from typing import Any, Dict, List

PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOX_DB_PATH = os.path.join(BASE_DIR, "box_db.json")
LID_DB_PATH = os.path.join(BASE_DIR, "lid_db.json")
PALLET_DB_PATH = os.path.join(BASE_DIR, "pallet_db.json")
STANDARD_PALLET_ID = "__STANDARD_1200_1000_130__"
STANDARD_PALLET = {
    "id": STANDARD_PALLET_ID,
    "model": "標準パレット（型番未指定）",
    "length": 1200,
    "width": 1000,
    "height": 130,
    "suppliers": [],
    "standard": True,
}
TEST_CASES_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "test_programmer", "test_cases"))
VIEWER_HTML_PATH = os.path.join(BASE_DIR, "db_viewer.html")


def _length_first_box_fields(box_db):
    for box_id, box in box_db.items():
        if not isinstance(box, dict) or "length" not in box or "width" not in box:
            continue

        ordered_box = {}
        for key, value in box.items():
            if key == "width":
                continue
            ordered_box[key] = value
            if key == "length":
                ordered_box["width"] = box["width"]
        box_db[box_id] = ordered_box
    return box_db


def _read_database(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict) or any(not isinstance(item, dict) for item in data.values()):
        raise ValueError("Database must be an object containing records")
    return data


def _read_pallet_database() -> Dict[str, Any]:
    with open(PALLET_DB_PATH, "r", encoding="utf-8") as source:
        data = json.load(source)
    return _validate_pallet_database(data)


def _pallet_references() -> Dict[str, List[str]]:
    references = {}
    for filename in sorted(os.listdir(TEST_CASES_DIR)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(TEST_CASES_DIR, filename), "r", encoding="utf-8") as source:
            test_case = json.load(source)
        if not isinstance(test_case, dict):
            raise ValueError("Invalid test case: {}".format(filename))
        pallet_id = test_case.get("pallet_id")
        if pallet_id:
            if not isinstance(pallet_id, str):
                raise ValueError("Invalid pallet_id in {}".format(filename))
            references.setdefault(pallet_id, []).append(filename)
    return references


def _validate_pallet_database(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {"pallets"}:
        raise ValueError("Pallet database must contain a pallets object")
    pallets = data["pallets"]
    if not isinstance(pallets, dict):
        raise ValueError("pallets must be an object")
    if STANDARD_PALLET_ID not in pallets:
        raise ValueError("The fixed standard pallet record is required")
    for pallet_id, pallet in pallets.items():
        if (not isinstance(pallet_id, str) or not pallet_id
                or not isinstance(pallet, dict) or pallet.get("id") != pallet_id):
            raise ValueError("Pallet id must match its key")
        if not isinstance(pallet.get("model"), str) or not pallet["model"].strip():
            raise ValueError("Pallet {} requires a model".format(pallet_id))
        suppliers = pallet.get("suppliers")
        is_standard = pallet_id == STANDARD_PALLET_ID
        if (not isinstance(suppliers, list) or (not suppliers and not is_standard)
                or any(not isinstance(name, str) or not name.strip() for name in suppliers)
                or len(suppliers) != len(set(suppliers))):
            raise ValueError("Pallet {} requires unique supplier names".format(pallet_id))
        if is_standard and pallet != STANDARD_PALLET:
            raise ValueError("The standard pallet record is fixed and cannot be changed")
        if not is_standard and pallet.get("standard"):
            raise ValueError("Only the reserved standard pallet can be marked standard")
        for field in ("length", "width", "height"):
            value = pallet.get(field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError("Pallet {}.{} must be a positive finite number".format(pallet_id, field))
    return data


def _validate_pallet_case_references(test_cases: Dict[str, Any], pallet_db: Dict[str, Any]) -> None:
    pallets = pallet_db["pallets"]
    for case_id, case in test_cases.items():
        if not isinstance(case, dict):
            raise ValueError("Test case {} must be an object".format(case_id))
        pallet_id = case.get("pallet_id")
        supplier_name = case.get("supplier_name")
        if pallet_id is None:
            continue
        if not isinstance(pallet_id, str) or pallet_id not in pallets:
            raise ValueError("Test case {} references an unknown pallet".format(case_id))
        pallet = pallets[pallet_id]
        if pallet_id != STANDARD_PALLET_ID and supplier_name not in pallet["suppliers"]:
            raise ValueError("Test case {} supplier does not use pallet {}".format(case_id, pallet_id))
        spec = case.get("pallet")
        if not isinstance(spec, dict) or any(
            spec.get(field) != pallet[field] for field in ("length", "width", "height")
        ):
            raise ValueError("Test case {} pallet dimensions do not match {}".format(case_id, pallet_id))


def _lid_references(lid_db: Dict[str, Any]) -> Dict[str, List[str]]:
    default_id = next(
        (lid_id for lid_id, lid in lid_db.items() if lid.get("type") == "NONE"), None
    )
    return _test_case_references("lid_id", default_id)


def _test_case_references(field: str, default_id: Any = None) -> Dict[str, List[str]]:
    references = {}
    for filename in sorted(os.listdir(TEST_CASES_DIR)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(TEST_CASES_DIR, filename), "r", encoding="utf-8") as source:
            test_case = json.load(source)
        if not isinstance(test_case, dict) or not isinstance(test_case.get("box_list", []), list):
            raise ValueError("Invalid test case: {}".format(filename))
        for item in test_case.get("box_list", []):
            if not isinstance(item, dict):
                raise ValueError("Invalid box_list in {}".format(filename))
            record_id = item.get(field, default_id)
            if field == "box_id" and (not isinstance(record_id, str) or not record_id):
                raise ValueError("Invalid box_id in {}".format(filename))
            if record_id:
                if not isinstance(record_id, str):
                    raise ValueError("Invalid {} in {}".format(field, filename))
                references.setdefault(record_id, set()).add(filename)
    return {lid_id: sorted(names) for lid_id, names in references.items()}


def _validate_databases(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or not data or set(data) - {"boxes", "lids", "pallets"}:
        raise ValueError("Specify boxes, lids, and/or pallets")
    for name, database in data.items():
        if name == "pallets":
            _validate_pallet_database(database)
            continue
        if not isinstance(database, dict):
            raise ValueError("{} must be an object".format(name))
        for key, item in database.items():
            if not isinstance(item, dict) or item.get("id") != key:
                raise ValueError("{}: record id must match its key ({})".format(name, key))

    old_lids = _read_database(LID_DB_PATH)
    lids = data.get("lids", old_lids)
    boxes = data.get("boxes")
    if boxes is None:
        boxes = _read_database(BOX_DB_PATH)
    if "boxes" in data:
        references = _test_case_references("box_id")
        old_boxes = _read_database(BOX_DB_PATH)
        for box_id in sorted(old_boxes.keys() - boxes.keys()):
            if references.get(box_id):
                raise ValueError("Box {} is referenced by: {}".format(
                    box_id, ", ".join(references[box_id])
                ))
    if not any(lid.get("type") == "NONE" for lid in lids.values()):
        raise ValueError("Keep at least one no-lid (NONE) option")
    if "lids" in data:
        references = _lid_references(old_lids)
        for lid_id in old_lids.keys() - lids.keys():
            if references.get(lid_id):
                raise ValueError("Lid {} is referenced by: {}".format(
                    lid_id, ", ".join(references[lid_id])
                ))
        for lid_id, lid in old_lids.items():
            if (lid.get("type") == "NONE" and lid_id in lids
                    and lids[lid_id].get("type") != "NONE" and references.get(lid_id)):
                raise ValueError("Referenced no-lid option cannot change type: {}".format(lid_id))
    for box_id, box in boxes.items():
        compatible = box.get("compatible_lids", [])
        if not isinstance(compatible, list) or any(
            not isinstance(lid_id, str) or lid_id not in lids for lid_id in compatible
        ):
            raise ValueError("Unknown or invalid compatible_lids for {}".format(box_id))
    if "pallets" in data:
        _validate_pallet_database(data["pallets"])
        references = _pallet_references()
        old_pallets = _read_pallet_database()["pallets"]
        new_pallets = data["pallets"]["pallets"]
        for pallet_id in sorted(old_pallets.keys() - new_pallets.keys()):
            if references.get(pallet_id):
                raise ValueError("Pallet {} is referenced by: {}".format(
                    pallet_id, ", ".join(references[pallet_id])
                ))
        test_cases = {}
        for filename in sorted(os.listdir(TEST_CASES_DIR)):
            if filename.endswith(".json"):
                with open(os.path.join(TEST_CASES_DIR, filename), "r", encoding="utf-8") as source:
                    test_cases[os.path.splitext(filename)[0]] = json.load(source)
        _validate_pallet_case_references(test_cases, data["pallets"])
    return data


def _save_databases(data: Dict[str, Any]) -> None:
    """Stage all files first; restore originals if a replacement fails."""
    _validate_databases(data)
    paths = {"boxes": BOX_DB_PATH, "lids": LID_DB_PATH, "pallets": PALLET_DB_PATH}
    staged = {}
    backups = {}
    replaced = []
    try:
        for name, database in data.items():
            path = paths[name]
            if name == "boxes":
                database = _length_first_box_fields(database)
            body = json.dumps(database, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
            with open(path, "rb") as original:
                original_body = original.read()
            for collection, content in ((staged, body), (backups, original_body)):
                with tempfile.NamedTemporaryFile(
                    dir=os.path.dirname(path), prefix=".viewer-", suffix=".tmp", delete=False
                ) as temporary:
                    collection[name] = temporary.name
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
        try:
            for name, temporary_path in staged.items():
                os.replace(temporary_path, paths[name])
                replaced.append(name)
        except OSError as error:
            rollback_errors = []
            for name in reversed(replaced):
                try:
                    os.replace(backups[name], paths[name])
                except OSError as rollback_error:
                    rollback_errors.append("{}: {}".format(name, rollback_error))
            if rollback_errors:
                # Retain recovery copies when automatic restoration is not possible.
                recovery = {name: path for name, path in backups.items() if os.path.exists(path)}
                backups = {}
                raise OSError("Save failed: {}; rollback failed: {}; recovery files: {}".format(
                    error, "; ".join(rollback_errors),
                    "; ".join("{}: {}".format(name, path) for name, path in recovery.items())
                )) from error
            raise
    finally:
        for temporary_path in list(staged.values()) + list(backups.values()):
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _json_response(self, status: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            with open(VIEWER_HTML_PATH, "rb") as source:
                body = source.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        elif parsed.path in ("/box_db_viewer.html", "/lid_db_viewer.html"):
            tab = "boxes" if parsed.path == "/box_db_viewer.html" else "lids"
            self.send_response(302)
            self.send_header("Location", "/#" + tab)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        elif parsed.path in ("/api/boxes", "/api/lids", "/api/pallets", "/api/lid_references", "/api/box_references", "/api/pallet_references"):
            try:
                if parsed.path == "/api/boxes":
                    data = _read_database(BOX_DB_PATH)
                elif parsed.path == "/api/lids":
                    data = _read_database(LID_DB_PATH)
                elif parsed.path == "/api/pallets":
                    data = _read_pallet_database()
                elif parsed.path == "/api/box_references":
                    data = _test_case_references("box_id")
                elif parsed.path == "/api/pallet_references":
                    data = _pallet_references()
                else:
                    data = _lid_references(_read_database(LID_DB_PATH))
                self._json_response(200, data)
            except (OSError, ValueError, TypeError, AttributeError) as error:
                self.log_error("Database read failed: %s", error)
                self._json_response(500, {"status": "error", "message": str(error)})
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/save", "/api/lids/save_all", "/api/pallets/save_all", "/api/databases/save"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len <= 0:
                    raise ValueError("Request body is required")
                data = json.loads(self.rfile.read(content_len).decode("utf-8"))
                if parsed.path == "/api/save":
                    data = {"boxes": data}
                elif parsed.path == "/api/lids/save_all":
                    data = {"lids": data}
                elif parsed.path == "/api/pallets/save_all":
                    data = {"pallets": data}
                _save_databases(data)
            except (ValueError, UnicodeError, TypeError) as error:
                self.log_error("Invalid database save: %s", error)
                self._json_response(400, {"status": "error", "message": str(error)})
            except OSError as error:
                self.log_error("Database save failed: %s", error)
                self._json_response(500, {"status": "error", "message": str(error)})
            else:
                self._json_response(200, {"status": "ok", "message": "Databases saved"})
            return
        super().do_POST()

def main():
    handler = ViewerRequestHandler
    
    # ポートの空きを試す
    port = PORT
    for p in range(PORT, PORT + 10):
        try:
            httpd = socketserver.TCPServer(("", p), handler)
        except OSError:
            continue
        with httpd:
            url = f"http://localhost:{p}"
            print("\n" + "=" * 60)
            print("✅ 箱・蓋データベース統合ビューアを起動しました:")
            print(f"   URL: {url}")
            print(f"   終了するには Ctrl+C を押してください")
            print("=" * 60 + "\n")
            try:
                opened = webbrowser.open(url)
                if not opened:
                    print("ブラウザを開けませんでした。上記URLを手動で開いてください。")
            except webbrowser.Error:
                print("⚠️  ブラウザを自動で開けませんでした")
                print("   手動で上記URLをブラウザで開いてください")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nビューアを終了しました。")
            return
    raise OSError("No available port in {}-{}".format(port, PORT + 9))

if __name__ == "__main__":
    main()
