#!/usr/bin/env python3
"""品番カタログのケース編集画面を提供するサーバー。"""

import os
import socketserver
import sys
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if __package__ in (None, ""):
    sys.path.insert(0, PROJECT_ROOT)

from box_research.catalog_http import handle_catalog

DEFAULT_PORT = 8083
RETIRED_PATHS = {"/testcase_viewer.html"}
RETIRED_APIS = {
    "/api/boxes", "/api/lids", "/api/pallets", "/api/testcases",
    "/api/testcase/approval_state", "/api/testcase/save_all",
}


class TestCaseViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _json_response(self, status, data):
        import json

        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if handle_catalog(self, Path(PROJECT_ROOT), "GET", parsed.path):
            return
        if parsed.path in ("/", "/index.html") or parsed.path in RETIRED_PATHS:
            self._redirect("/catalog_cases.html")
            return
        if parsed.path in RETIRED_APIS:
            self._json_response(410, {
                "status": "error",
                "message": "旧テストケースAPIは廃止されました。品番カタログAPIを使用してください。",
            })
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if handle_catalog(self, Path(PROJECT_ROOT), "POST", parsed.path):
            return
        if parsed.path in RETIRED_APIS:
            self._json_response(410, {
                "status": "error",
                "message": "旧テストケースAPIへの書き込みは受け付けません。品番カタログAPIを使用してください。",
            })
            return
        self._json_response(404, {"status": "error", "message": "Endpoint not found"})


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    for candidate in range(port, port + 10):
        try:
            server = socketserver.TCPServer(("", candidate), TestCaseViewerHandler)
        except OSError:
            continue
        with server:
            url = "http://localhost:{}/catalog_cases.html".format(candidate)
            print("品番ケース編集サーバー: {}".format(url))
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                print("ブラウザでURLを開いてください。")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return


if __name__ == "__main__":
    main()
