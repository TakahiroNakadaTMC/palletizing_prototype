#!/usr/bin/env python3
"""
統合3D荷姿Webビューワサーバー (serve_3d_viewer.py)
tester/results/ 配下にある全パレタイズ結果JSONを自動検出し、
ブラウザを自動起動してケース切り替え・3D表示・アニメーション再生・箱インスペクトを行えるWebアプリを提供します。
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
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tester", "results")
DEFAULT_PORT = 8082

class ViewerHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        clean_path = urllib.parse.unquote(clean_path)
        if clean_path in ["/", "/index.html", "/viewer"]:
            return os.path.join(BASE_DIR, "index.html")
        return super().translate_path(path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # API: 結果ファイル一覧
        if parsed.path == "/api/results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

            files = glob.glob(os.path.join(RESULTS_DIR, "*.json"))
            results_list = []
            for fpath in sorted(files):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results_list.append({
                        "filename": os.path.basename(fpath),
                        "test_name": data.get("test_name", os.path.basename(fpath)),
                        "boxes_count": data.get("placed_boxes_count", len(data.get("boxes", []))),
                        "is_valid": data.get("summary", {}).get("is_valid", False),
                        "vol_eff": data.get("summary", {}).get("volume_efficiency_percent", 0.0)
                    })
                except Exception as e:
                    pass

            self.wfile.write(json.dumps(results_list, ensure_ascii=False).encode("utf-8"))
            return

        # API: 単一結果データの取得
        if parsed.path.startswith("/api/result/"):
            fname = parsed.path.replace("/api/result/", "")
            target_file = os.path.join(RESULTS_DIR, fname)
            if os.path.exists(target_file):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                with open(target_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Result file not found")
            return

        # 通常の静的ファイル配信
        super().do_GET()

def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    for p in range(port, port + 10):
        try:
            with socketserver.TCPServer(("", p), ViewerHandler) as httpd:
                url = f"http://localhost:{p}"
                print("=" * 65)
                print(f"🚀 3Dパレタイズ統合ビューワを起動しました:")
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
