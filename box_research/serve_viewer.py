#!/usr/bin/env python3
"""
箱・蓋DBおよびハンド設定ビューワ起動スクリプト (serve_viewer.py)
ローカルHTTPサーバーを起動し、選択したビューアをブラウザで表示します。
ブラウザからの直接保存API (/api/save) にも対応しています。
"""

import http.server
import socketserver
import json
import os
import webbrowser
import urllib.parse
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from algorithm_programmer.hand_profile import build_preview, validate_store
from algorithm_programmer.models import BoxSpec

PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOX_DB_PATH = os.path.join(BASE_DIR, "box_db.json")
LID_DB_PATH = os.path.join(BASE_DIR, "lid_db.json")
TEST_CASES_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "test_programmer", "test_cases"))
BOX_VIEWER_HTML_PATH = os.path.join(BASE_DIR, "box_db_viewer.html")
LID_VIEWER_HTML_PATH = os.path.join(BASE_DIR, "lid_db_viewer.html")
HAND_PROFILES_PATH = os.path.join(BASE_DIR, "..", "algorithm_programmer", "hand_profiles.json")

# グローバル変数：どのビューアを開くか指定
VIEWER_MODE = "box"  # "box", "lid", "hand"


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


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/hand_profiles":
            try:
                with open(HAND_PROFILES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                validate_store(data)
                self._hand_json(200, data)
            except (OSError, ValueError) as error:
                self.log_error("Hand settings read failed: %s", error)
                self._hand_json(500, {"error": str(error)})
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            # ルートアクセス時は、VIEWER_MODE に応じて適切なHTMLを返す
            viewer_file = {
                "box": BOX_VIEWER_HTML_PATH,
                "lid": LID_VIEWER_HTML_PATH,
                "hand": os.path.join(BASE_DIR, "hand_viewer.html"),
            }[VIEWER_MODE]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(viewer_file, "rb") as f:
                self.wfile.write(f.read())
            return
        elif parsed.path == "/box_db_viewer.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(BOX_VIEWER_HTML_PATH, "rb") as f:
                self.wfile.write(f.read())
            return
        elif parsed.path == "/lid_db_viewer.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(LID_VIEWER_HTML_PATH, "rb") as f:
                self.wfile.write(f.read())
            return
        elif parsed.path == "/api/boxes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            with open(BOX_DB_PATH, "rb") as f:
                self.wfile.write(f.read())
            return
        elif parsed.path == "/api/lids":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            if os.path.exists(LID_DB_PATH):
                with open(LID_DB_PATH, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"{}")
            return
        elif parsed.path == "/api/lid_references":
            try:
                with open(LID_DB_PATH, "r", encoding="utf-8") as f:
                    lid_db = json.load(f)
                default_lid_id = next(
                    (lid_id for lid_id, lid in lid_db.items() if lid.get("type") == "NONE"),
                    None
                )
                test_case_references = {}
                for filename in sorted(os.listdir(TEST_CASES_DIR)):
                    if not filename.endswith(".json"):
                        continue
                    with open(os.path.join(TEST_CASES_DIR, filename), "r", encoding="utf-8") as f:
                        test_case = json.load(f)
                    for item in test_case.get("box_list", []):
                        lid_id = item.get("lid_id", default_lid_id)
                        if lid_id:
                            test_case_references.setdefault(lid_id, set()).add(filename)

                response = {
                    lid_id: sorted(filenames)
                    for lid_id, filenames in test_case_references.items()
                }
                body = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/hand_profiles/save", "/api/hand_preview"):
            self._hand_post(parsed.path)
            return
        if parsed.path == "/api/save":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            try:
                data = _length_first_box_fields(json.loads(post_body.decode("utf-8")))
                with open(BOX_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                response = {"status": "ok", "message": f"Successfully updated {len(data)} boxes in box_db.json"}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                response = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            return
        elif parsed.path == "/api/lids/save_all":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            try:
                data = json.loads(post_body.decode("utf-8"))
                with open(LID_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                response = {"status": "ok", "message": f"Successfully updated {len(data)} lids in lid_db.json"}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                response = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            return
        super().do_POST()

    def _hand_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _hand_post(self, path):
        temporary_path = None
        try:
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
                self._hand_json(403, {"error": "別サイトからの操作は許可されていません"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                raise ValueError("リクエストは1MB以下のJSONで指定してください")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/hand_profiles/save":
                validate_store(data)
                with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=os.path.dirname(HAND_PROFILES_PATH),
                        suffix=".tmp", delete=False) as f:
                    temporary_path = f.name
                    json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
                    f.write("\n")
                os.replace(temporary_path, HAND_PROFILES_PATH)
                temporary_path = None
                self._hand_json(200, {"status": "ok"})
                return
            if not isinstance(data, dict):
                raise ValueError("プレビュー条件はオブジェクトで指定してください")
            with open(BOX_DB_PATH, encoding="utf-8") as f:
                boxes = json.load(f)
            box_id = data.get("box_id")
            if not isinstance(box_id, str) or box_id not in boxes:
                raise ValueError("箱を選択してください")
            box = BoxSpec.from_dict(boxes[box_id])
            lid_id = data.get("lid_id", "")
            if not isinstance(lid_id, str):
                raise ValueError("蓋IDは文字列で指定してください")
            if lid_id:
                if lid_id not in boxes[box_id].get("compatible_lids", []):
                    raise ValueError("箱に対応していない蓋です")
                with open(LID_DB_PATH, encoding="utf-8") as f:
                    lids = json.load(f)
                if lid_id not in lids:
                    raise ValueError("蓋がDBに存在しません")
                lid = lids[lid_id]
                box.lid_width = float(lid["width"])
                box.lid_length = float(lid["length"])
                box.lid_thickness = float(lid["thickness"])
                box.lid_fit_type = lid["fit_type"]
            preview = build_preview(data.get("profile"), box, data.get("rotation"),
                                    data.get("corner"))
            self._hand_json(200, preview)
        except (ValueError, TypeError, KeyError) as error:
            self.log_error("Hand settings request rejected: %s", error)
            self._hand_json(400, {"error": str(error)})
        except OSError as error:
            self.log_error("Hand settings IO failed: %s", error)
            self._hand_json(500, {"error": str(error)})
        finally:
            if temporary_path is not None:
                os.unlink(temporary_path)

def main():
    global VIEWER_MODE
    
    # ユーザーに選択を促す
    print("\n" + "=" * 60)
    print("📦 箱・蓋データベース ビューア選択")
    print("=" * 60)
    print("どのビューアを開きますか？")
    print("  [1] 箱DB ビューア（デフォルト）")
    print("  [2] 蓋DB ビューア")
    print("  [3] ハンド設定・形状確認（第1段階）")
    print("=" * 60)
    
    choice = input("選択（1 / 2 / 3）[1]: ").strip() or "1"
    
    if choice == "3":
        VIEWER_MODE = "hand"
        viewer_name = "ハンド設定"
    elif choice == "2":
        VIEWER_MODE = "lid"
        viewer_name = "蓋DB"
    else:
        VIEWER_MODE = "box"
        viewer_name = "箱DB"
    
    os.chdir(BASE_DIR)
    handler = ViewerRequestHandler
    
    # ポートの空きを試す
    port = PORT
    for p in range(PORT, PORT + 10):
        try:
            with socketserver.TCPServer(("", p), handler) as httpd:
                url = f"http://localhost:{p}"
                print("\n" + "=" * 60)
                print(f"✅ {viewer_name} ビューアを起動しました:")
                print(f"   URL: {url}")
                print(f"   終了するには Ctrl+C を押してください")
                print("=" * 60 + "\n")
                try:
                    webbrowser.open(url)
                except Exception as e:
                    print(f"⚠️  ブラウザを自動で開けませんでした")
                    print(f"   手動で上記URLをブラウザで開いてください")
                httpd.serve_forever()
                break
        except OSError:
            continue

if __name__ == "__main__":
    main()
