#!/usr/bin/env python3
"""
箱・蓋データベース承認ビューワ起動スクリプト (serve_viewer.py)
ローカルHTTPサーバーを起動し、ブラウザで box_db_viewer.html または lid_db_viewer.html を表示します。
ブラウザからの直接保存API (/api/save) にも対応しています。
"""

import http.server
import socketserver
import json
import os
import webbrowser
import urllib.parse
import sys

PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOX_DB_PATH = os.path.join(BASE_DIR, "box_db.json")
LID_DB_PATH = os.path.join(BASE_DIR, "lid_db.json")
BOX_VIEWER_HTML_PATH = os.path.join(BASE_DIR, "box_db_viewer.html")
LID_VIEWER_HTML_PATH = os.path.join(BASE_DIR, "lid_db_viewer.html")

# グローバル変数：どのビューアを開くか指定
VIEWER_MODE = "box"  # "box" または "lid"

class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            # ルートアクセス時は、VIEWER_MODE に応じて適切なHTMLを返す
            viewer_file = BOX_VIEWER_HTML_PATH if VIEWER_MODE == "box" else LID_VIEWER_HTML_PATH
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

def main():
    global VIEWER_MODE
    
    # ユーザーに選択を促す
    print("\n" + "=" * 60)
    print("📦 箱・蓋データベース ビューア選択")
    print("=" * 60)
    print("どのビューアを開きますか？")
    print("  [1] 箱DB ビューア（デフォルト）")
    print("  [2] 蓋DB ビューア")
    print("=" * 60)
    
    choice = input("選択（1 or 2）[1]: ").strip() or "1"
    
    if choice == "2":
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
