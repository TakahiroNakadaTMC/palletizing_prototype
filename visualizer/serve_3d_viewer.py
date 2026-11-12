#!/usr/bin/env python3
"""品番方式専用の統合3D荷姿ビューワサーバー。"""

import argparse
import json
import os
import socketserver
import sys
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

try:
    from visualizer.part_result_support import (
        load_part_results_from_manifest,
        resolve_latest_completed_catalog_run,
    )
except ModuleNotFoundError:  # script direct execution fallback
    from part_result_support import load_part_results_from_manifest, resolve_latest_completed_catalog_run

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
CATALOG_RESULTS_ROOT = PROJECT_ROOT / "tester" / "catalog_results"
DEFAULT_PORT = 8082


class ViewerHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split("?", 1)[0].split("#", 1)[0]
        clean_path = urllib.parse.unquote(clean_path)
        if clean_path in {"/", "/index.html", "/viewer"}:
            return str(BASE_DIR / "index.html")
        if clean_path == "/result_identity.js":
            return str(BASE_DIR / "result_identity.js")
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

    def _load_entries(self):
        directory = Path(getattr(self.server, "results_dir"))
        return load_part_results_from_manifest(directory)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/results":
            try:
                entries = self._load_entries()
            except ValueError as error:
                self.send_json(422, {"error": str(error)})
                return
            results = []
            for entry in entries:
                row = entry["case"]
                if row["status"] == "ERROR":
                    results.append({
                        "filename": None, "test_name": row["name"],
                        "status": "ERROR", "error": row["error"], "input_mode": "part_number",
                    })
                    continue
                data = entry["data"]
                results.append(
                    {
                        "filename": entry["filename"],
                        "status": row["status"],
                        "test_name": data.get("test_name", entry["filename"]),
                        "boxes_count": data.get("placed_boxes_count", len(data.get("boxes", []))),
                        "is_valid": data.get("summary", {}).get("is_valid", False),
                        "vol_eff": data.get("summary", {}).get("volume_efficiency_percent", 0.0),
                        "input_mode": "part_number",
                    }
                )
            self.send_json(200, results)
            return

        if parsed.path.startswith("/api/result/"):
            fname = urllib.parse.unquote(parsed.path[len("/api/result/") :])
            if (
                not fname.startswith("result_")
                or not fname.endswith(".json")
                or Path(fname).name != fname
                or "/" in fname
                or "\\" in fname
            ):
                self.send_json(400, {"error": "Invalid result filename"})
                return
            try:
                entries = self._load_entries()
            except ValueError as error:
                self.send_json(422, {"error": str(error)})
                return
            index = {entry["filename"]: entry["data"] for entry in entries if entry["data"] is not None}
            if fname not in index:
                self.send_json(404, {"error": f"{fname} は manifest の品番結果に含まれていません"})
                return
            self.send_json(200, index[fname])
            return

        super().do_GET()


def _resolve_results_dir(args) -> Path:
    if args.results_dir is not None:
        selected = args.results_dir.resolve()
    else:
        selected = resolve_latest_completed_catalog_run(CATALOG_RESULTS_ROOT)
    load_part_results_from_manifest(selected)
    return selected


def main():
    parser = argparse.ArgumentParser(description="品番方式結果の3D表示")
    parser.add_argument("port", type=int, nargs="?", default=DEFAULT_PORT)
    parser.add_argument("--results-dir", type=Path, default=None, help="表示する結果フォルダ")
    args = parser.parse_args()
    if not 1 <= args.port <= 65526:
        parser.error("ポートは1〜65526で指定してください")
    try:
        results_dir = _resolve_results_dir(args)
    except ValueError as error:
        parser.exit(
            2,
            "表示可能な品番結果を見つけられません。\n"
            f"{error}\n"
            "対処: --results-dir で run_manifest.json を含む catalog_results 実行フォルダを指定してください。\n",
        )

    for port in range(args.port, args.port + 10):
        try:
            httpd = socketserver.TCPServer(("", port), ViewerHandler)
        except OSError as error:
            print(f"ポート{port}で起動できません: {error}", file=sys.stderr)
            continue
        with httpd:
            httpd.results_dir = str(results_dir)
            url = f"http://localhost:{port}"
            print("=" * 65)
            print("🚀 3Dパレタイズ統合ビューワを起動しました:")
            print(f"   URL: {url}")
            print(f"   結果フォルダ: {httpd.results_dir}")
            print("   終了するには Ctrl+C を押してください")
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
