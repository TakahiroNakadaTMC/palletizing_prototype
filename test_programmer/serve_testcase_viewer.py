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
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
BOX_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "box_db.json")
TEST_CASES_DIR = os.path.join(BASE_DIR, "test_cases")
DEFAULT_PORT = 8083

class TestCaseViewerHandler(SimpleHTTPRequestHandler):
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
                    tc_name = data.get("name", os.path.basename(fpath).replace(".json", ""))
                    tcs[tc_name] = data
                except Exception as e:
                    pass

            self.wfile.write(json.dumps(tcs, ensure_ascii=False).encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/testcase/save_all":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                tcs_data = json.loads(body.decode("utf-8"))
                os.makedirs(TEST_CASES_DIR, exist_ok=True)

                saved_count = 0
                for tc_name, tc_obj in tcs_data.items():
                    fpath = os.path.join(TEST_CASES_DIR, f"{tc_name}.json")
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(tc_obj, f, ensure_ascii=False, indent=2)
                    saved_count += 1

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                res = {"status": "ok", "saved_count": saved_count}
                self.wfile.write(json.dumps(res).encode("utf-8"))
                print(f"✓ {saved_count} 件のテストケースを test_cases/ に保存しました。")
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
