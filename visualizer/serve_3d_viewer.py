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

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tester", "results")
DEFAULT_PORT = 8082
sys.path.insert(0, PROJECT_ROOT)
from algorithm_programmer.hand_collision import check_static_hand, select_static_corners
from algorithm_programmer.hand_profile import validate_store
from algorithm_programmer.hand_sequence import generate_hand_sequence

HAND_PROFILES_PATH = os.path.join(PROJECT_ROOT, "algorithm_programmer", "hand_profiles.json")

class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _profiles(self):
        with open(HAND_PROFILES_PATH, encoding="utf-8") as f:
            profiles = json.load(f)
        validate_store(profiles)
        return profiles

    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        clean_path = urllib.parse.unquote(clean_path)
        if clean_path in ["/", "/index.html", "/viewer"]:
            return os.path.join(BASE_DIR, "index.html")
        return super().translate_path(path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/hand_profiles":
            try:
                self._json(200, self._profiles())
            except (OSError, ValueError) as error:
                self.log_error("Hand settings read failed: %s", error)
                self._json(500, {"error": str(error)})
            return

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

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/hand_check", "/api/hand_select", "/api/hand_sequence"):
            self.send_error(404, "Unknown API")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("確認条件は16KB以下のJSONが必要です")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("確認条件はオブジェクトが必要です")
            filename = request.get("filename")
            if (not isinstance(filename, str) or not filename.endswith(".json")
                    or os.path.basename(filename) != filename
                    or "/" in filename or "\\" in filename):
                raise ValueError("結果一覧にあるJSONファイル名を指定してください")
            profile = next((p for p in self._profiles()["profiles"]
                            if p["id"] == request.get("profile_id")), None)
            if profile is None:
                raise ValueError("設備設定が見つかりません。設定一覧を再読込してください")
            with open(os.path.join(RESULTS_DIR, filename), encoding="utf-8") as f:
                data = json.load(f)
            if path == "/api/hand_sequence":
                result = generate_hand_sequence(data, profile)
            elif path == "/api/hand_select":
                result = select_static_corners(data, profile)
            else:
                result = check_static_hand(data, profile, request.get("order"), request.get("corner"))
            self._json(200, result)
        except FileNotFoundError as error:
            self.log_error("Hand check file missing: %s", error)
            self._json(404, {"error": str(error)})
        except (ValueError, KeyError, TypeError) as error:
            self.log_error("Hand check rejected: %s", error)
            self._json(400, {"error": str(error)})
        except OSError as error:
            self.log_error("Hand check IO failed: %s", error)
            self._json(500, {"error": str(error)})

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
