#!/usr/bin/env python3
"""
テストパターン承認・編集サーバー (serve_testcase_viewer.py)
テストケースの取得・編集・追加・一括保存を行うローカルHTTPサーバーを提供し、
スクリプト実行時にブラウザを自動起動します。
"""

import os
import sys
import json
import glob
import webbrowser
import socketserver
import re
import math
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if __package__ in (None, ""):
    sys.path.insert(0, PROJECT_ROOT)

from box_research.database_validation import (
    validate_box_lid_databases,
    validate_case_references,
    validate_pallet_database,
)

BOX_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "box_db.json")
LID_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "lid_db.json")
PALLET_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "pallet_db.json")
TEST_CASES_DIR = os.path.join(BASE_DIR, "test_cases")
APPROVAL_STATE_PATH = os.path.join(BASE_DIR, "test_case_approval.json")
DEFAULT_PORT = 8083
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
PALLET_DEFAULTS = {
    "max_x_span": 1360.0,
    "max_y_span": 1100.0,
    "max_height": 1200.0,
}

def parse_positive_finite_number(raw, label):
    if isinstance(raw, bool):
        raise ValueError(f"{label} は真偽値を指定できません")
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        trimmed = raw.strip()
        if trimmed == "":
            raise ValueError(f"{label} は空欄にできません")
        try:
            value = float(trimmed)
        except ValueError as e:
            raise ValueError(f"{label} は数値で指定してください") from e
    else:
        raise ValueError(f"{label} は数値で指定してください")

    if not math.isfinite(value):
        raise ValueError(f"{label} は有限の数値で指定してください")
    if value <= 0:
        raise ValueError(f"{label} は0より大きい値で指定してください")
    return value

def validate_and_normalize_pallet_spec(case_id, pallet_obj):
    if pallet_obj is None:
        pallet_obj = {}
    if not isinstance(pallet_obj, dict):
        raise ValueError(f"テストケース {case_id} の pallet はオブジェクトである必要があります")

    merged = {**PALLET_DEFAULTS, **pallet_obj}
    normalized = {
        "max_x_span": parse_positive_finite_number(merged.get("max_x_span"), f"{case_id}.pallet.max_x_span"),
        "max_y_span": parse_positive_finite_number(merged.get("max_y_span"), f"{case_id}.pallet.max_y_span"),
        "max_height": parse_positive_finite_number(merged.get("max_height"), f"{case_id}.pallet.max_height"),
    }
    if normalized["max_x_span"] < normalized["max_y_span"]:
        raise ValueError(f"{case_id}.pallet: max_x_span は max_y_span 以上で指定してください")
    return normalized

def get_test_case_ids():
    return {
        os.path.splitext(os.path.basename(path))[0]
        for path in glob.glob(os.path.join(TEST_CASES_DIR, "*.json"))
    }

def write_json_atomic(path, data):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)

def load_approval_state():
    case_ids = get_test_case_ids()
    if os.path.exists(APPROVAL_STATE_PATH):
        with open(APPROVAL_STATE_PATH, "r", encoding="utf-8") as f:
            saved_state = json.load(f)
        if not isinstance(saved_state, dict):
            raise ValueError("採否状態ファイルはJSONオブジェクトである必要があります")
        state = {case_id: saved_state.get(case_id) is True for case_id in case_ids}
    else:
        state = {case_id: True for case_id in case_ids}

    if not os.path.exists(APPROVAL_STATE_PATH) or state != saved_state:
        write_json_atomic(APPROVAL_STATE_PATH, state)
    return state

class TestCaseViewerHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        clean_path = urllib.parse.unquote(clean_path)
        if clean_path in ["/", "/index.html"]:
            return os.path.join(BASE_DIR, "testcase_viewer.html")
        return super().translate_path(path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # API: 箱DBの取得
        if parsed.path == "/api/boxes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            if os.path.exists(BOX_DB_PATH):
                with open(BOX_DB_PATH, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"{}")
            return

        # API: 蓋DBの取得
        if parsed.path == "/api/lids":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            if os.path.exists(LID_DB_PATH):
                with open(LID_DB_PATH, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{}')
            return

        if parsed.path == "/api/pallets":
            try:
                with open(PALLET_DB_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except OSError as e:
                self.send_error(500, f"パレットDBを読み込めません: {e}")
            return

        # API: テストケース一覧の取得
        if parsed.path == "/api/testcases":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

            files = glob.glob(os.path.join(TEST_CASES_DIR, "*.json"))
            tcs = {}
            for fpath in sorted(files):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tc_name = os.path.splitext(os.path.basename(fpath))[0]
                    tcs[tc_name] = data
                except Exception as e:
                    pass

            self.wfile.write(json.dumps(tcs, ensure_ascii=False).encode("utf-8"))
            return

        # API: 共有テストケース採否状態
        if parsed.path == "/api/testcase/approval_state":
            try:
                state = load_approval_state()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(state, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"採否状態を読み込めません: {e}")
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/testcase/save_all":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                tcs_data = payload.get("test_cases")
                approval_state = payload.get("approval_state")
                delete_ids = payload.get("delete_ids", [])
                if (not isinstance(tcs_data, dict) or not isinstance(approval_state, dict)
                        or not isinstance(delete_ids, list)):
                    raise ValueError("test_cases、approval_state、delete_ids が必要です")

                case_ids = set(tcs_data)
                if len(delete_ids) != len(set(delete_ids)):
                    raise ValueError("delete_ids に重複があります")
                for case_id in delete_ids:
                    if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
                        raise ValueError(f"不正な削除対象IDです: {case_id}")
                    if case_id in case_ids:
                        raise ValueError(f"保存対象を削除対象にはできません: {case_id}")

                for case_id, tc_obj in tcs_data.items():
                    if not CASE_ID_PATTERN.fullmatch(case_id):
                        raise ValueError(f"不正なテストケースIDです: {case_id}")
                    if not isinstance(tc_obj, dict):
                        raise ValueError(f"テストケース {case_id} の内容が不正です")
                    if type(approval_state.get(case_id)) is not bool:
                        raise ValueError(f"テストケース {case_id} の採否状態が不正です")
                    tc_obj["pallet"] = validate_and_normalize_pallet_spec(case_id, tc_obj.get("pallet"))
                with open(PALLET_DB_PATH, "r", encoding="utf-8") as f:
                    pallet_db = validate_pallet_database(json.load(f))
                with open(BOX_DB_PATH, "r", encoding="utf-8") as f:
                    boxes = json.load(f)
                with open(LID_DB_PATH, "r", encoding="utf-8") as f:
                    lids = json.load(f)
                validate_box_lid_databases(boxes, lids)
                for case_id, tc_obj in tcs_data.items():
                    validate_case_references(case_id, tc_obj, boxes, lids, pallet_db)

                os.makedirs(TEST_CASES_DIR, exist_ok=True)

                saved_count = 0
                for tc_name, tc_obj in tcs_data.items():
                    fpath = os.path.join(TEST_CASES_DIR, f"{tc_name}.json")
                    write_json_atomic(fpath, tc_obj)
                    saved_count += 1

                deleted_count = 0
                for case_id in delete_ids:
                    existing_path = os.path.join(TEST_CASES_DIR, f"{case_id}.json")
                    if os.path.isfile(existing_path):
                        os.remove(existing_path)
                        deleted_count += 1

                shared_state = {case_id: approval_state[case_id] for case_id in case_ids}
                write_json_atomic(APPROVAL_STATE_PATH, shared_state)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                res = {
                    "status": "ok",
                    "saved_count": saved_count,
                    "deleted_count": deleted_count,
                    "approved_count": sum(shared_state.values())
                }
                self.wfile.write(json.dumps(res).encode("utf-8"))
                print(f"保存完了: {saved_count} 件 / 削除: {deleted_count} 件 / 採用: {sum(shared_state.values())} 件")
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                err = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(err).encode("utf-8"))
                return

        self.send_error(404, "Endpoint not found")

def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    for p in range(port, port + 10):
        try:
            with socketserver.TCPServer(("", p), TestCaseViewerHandler) as httpd:
                url = f"http://localhost:{p}"
                print("=" * 65)
                print(f"📋 テストパターン承認ビューワを起動しました:")
                print(f"   URL: {url}")
                print(f"   終了するには Ctrl+C を押してください")
                print("=" * 65)
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                httpd.serve_forever()
                break
        except OSError:
            continue

if __name__ == "__main__":
    main()
