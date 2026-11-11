#!/usr/bin/env python3
"""品番カタログ編集サーバー。"""

import http.server
import os
import socketserver
import sys
import urllib.parse
import webbrowser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from box_research.catalog_http import handle_catalog

PORT = 8081
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RETIRED_PATHS = {
    "/box_db_viewer.html", "/lid_db_viewer.html", "/db_viewer.html",
    "/db_viewer.js", "/db_viewer.css", "/box_db_viewer.js", "/box_db_viewer.css",
    "/lid_db_viewer.js", "/lid_db_viewer.css",
}
RETIRED_APIS = {
    "/api/boxes", "/api/lids", "/api/pallets", "/api/lid_references",
    "/api/box_references", "/api/pallet_references", "/api/save",
    "/api/lids/save_all", "/api/pallets/save_all", "/api/databases/save",
}


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
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
        if handle_catalog(self, Path(BASE_DIR).parent, "GET", parsed.path):
            return
        if parsed.path in ("/", "/index.html") or parsed.path in RETIRED_PATHS:
            self._redirect("/catalog_viewer.html")
            return
        if parsed.path in RETIRED_APIS:
            self._json_response(410, {
                "status": "error",
                "message": "旧DB APIは廃止されました。品番カタログAPIを使用してください。",
            })
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if handle_catalog(self, Path(BASE_DIR).parent, "POST", parsed.path):
            return
        if parsed.path in RETIRED_APIS:
            self._json_response(410, {
                "status": "error",
                "message": "旧DB APIへの書き込みは受け付けません。品番カタログAPIを使用してください。",
            })
            return
        self._json_response(404, {"status": "error", "message": "Endpoint not found"})


def main():
    for port in range(PORT, PORT + 10):
        try:
            server = socketserver.TCPServer(("", port), ViewerRequestHandler)
        except OSError:
            continue
        with server:
            url = "http://localhost:{}/catalog_viewer.html".format(port)
            print("品番カタログ編集サーバー: {}".format(url))
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                print("ブラウザでURLを開いてください。")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return
    raise OSError("No available port in {}-{}".format(PORT, PORT + 9))


if __name__ == "__main__":
    main()
