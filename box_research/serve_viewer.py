#!/usr/bin/env python3
"""
箱データベース承認ビューワ起動スクリプト (serve_viewer.py)
ローカルHTTPサーバーを起動し、ブラウザで box_db_viewer.html を表示します。
ブラウザからの直接保存API (/api/save) にも対応しています。
"""

import http.server
import socketserver
import json
import os
import webbrowser
import urllib.parse

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOX_DB_PATH = os.path.join(BASE_DIR, "box_db.json")
VIEWER_HTML_PATH = os.path.join(BASE_DIR, "box_db_viewer.html")

class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(VIEWER_HTML_PATH, "rb") as f:
                self.wfile.write(f.read())
            return
        elif parsed.path == "/api/boxes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            with open(BOX_DB_PATH, "rb") as f:
                self.wfile.write(f.read())
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/save":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            try:
                data = json.loads(post_body.decode("utf-8"))
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
        super().do_POST()

def main():
    os.chdir(BASE_DIR)
    handler = ViewerRequestHandler
    
    # ポートの空きを試す
    port = PORT
    for p in range(PORT, PORT + 10):
        try:
            with socketserver.TCPServer(("", p), handler) as httpd:
                url = f"http://localhost:{p}"
                print("=" * 60)
                print(f"📦 箱データベース承認ビューワを起動しました:")
                print(f"   URL: {url}")
                print(f"   終了するには Ctrl+C を押してください")
                print("=" * 60)
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
