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
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

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
        if clean_path == "/result_identity.js":
            return os.path.join(BASE_DIR, "result_identity.js")
        return super().translate_path(path)

    def send_json(self, status, data):
        try:
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as error:
            self.log_error("Result serialization error: %s", error)
            status = 500
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # API: 結果ファイル一覧
        if parsed.path == "/api/results":
            directory = getattr(self.server, "results_dir", RESULTS_DIR)
            files = glob.glob(os.path.join(directory, "result_*.json"))
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
                        "vol_eff": data.get("summary", {}).get("volume_efficiency_percent", 0.0),
                        "input_mode": data.get("input_mode", "legacy"),
                    })
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    self.log_error("Result list error: %s: %s", os.path.basename(fpath), error)
                    self.send_json(500, {"error": os.path.basename(fpath) + ": " + str(error)})
                    return

            self.send_json(200, results_list)
            return

        # API: 単一結果データの取得
        if parsed.path.startswith("/api/result/"):
            fname = urllib.parse.unquote(parsed.path[len("/api/result/"):])
            if (not fname.startswith("result_") or not fname.endswith(".json")
                    or Path(fname).name != fname or "/" in fname or "\\" in fname):
                self.send_json(400, {"error": "Invalid result filename"})
                return
            directory = getattr(self.server, "results_dir", RESULTS_DIR)
            target_file = os.path.join(directory, fname)
            if os.path.exists(target_file):
                try:
                    with open(target_file, "r", encoding="utf-8") as source:
                        self.send_json(200, json.load(source))
                except (OSError, ValueError, TypeError) as error:
                    self.log_error("Result read error: %s", error)
                    self.send_json(500, {"error": str(error)})
            else:
                self.send_error(404, "Result file not found")
            return

        # 通常の静的ファイル配信
        super().do_GET()

def main():
    parser = argparse.ArgumentParser(description="荷姿結果の3D表示（旧方式・品番方式対応）")
    parser.add_argument("port", type=int, nargs="?", default=DEFAULT_PORT)
    parser.add_argument("--results-dir", type=Path, default=Path(RESULTS_DIR),
                        help="表示する結果フォルダ。省略時は旧方式の結果")
    args = parser.parse_args()
    if not args.results_dir.is_dir():
        parser.error("結果フォルダがありません。計算後のフォルダを指定してください")
    if not 1 <= args.port <= 65526:
        parser.error("ポートは1〜65526で指定してください")
    port = args.port

    for p in range(port, port + 10):
        try:
            httpd = socketserver.TCPServer(("", p), ViewerHandler)
        except OSError as error:
            print(f"ポート{p}で起動できません: {error}", file=sys.stderr)
            continue
        with httpd:
            httpd.results_dir = str(args.results_dir.resolve())
            url = f"http://localhost:{p}"
            print("=" * 65)
            print(f"🚀 3Dパレタイズ統合ビューワを起動しました:")
            print(f"   URL: {url}")
            print(f"   結果フォルダ: {httpd.results_dir}")
            print(f"   終了するには Ctrl+C を押してください")
            print("=" * 65)
            try:
                webbrowser.open(url)
            except webbrowser.Error as error:
                print(f"ブラウザを自動起動できません: {error}", file=sys.stderr)
            httpd.serve_forever()
            break
    else:
        parser.exit(1, "利用できるポートがありません\n")

if __name__ == "__main__":
    main()
