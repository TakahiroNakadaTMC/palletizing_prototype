"""品番方式専用ビューワの API / HTML 生成テスト。"""

import copy
import json
import os
from pathlib import Path
import re
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
from urllib.error import HTTPError
from urllib.request import urlopen

from visualizer.part_result_support import load_part_results_from_manifest, resolve_latest_completed_catalog_run
from visualizer.serve_3d_viewer import ViewerHandler
from visualizer.visualize import generate_html


EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def make_part_result():
    return {
        "test_name": "fixture_part",
        "schema_version": 2,
        "input_mode": "part_number",
        "catalog_revision": "fixture-rev",
        "coordinate_reference": "combined_footprint_min_xy_top_z",
        "pallet": {
            "length": 1200,
            "width": 1000,
            "height": 130,
            "max_x_span": 1360,
            "max_y_span": 1100,
            "max_height": 1200,
        },
        "input_boxes_count": 3,
        "placed_boxes_count": 2,
        "unplaced_boxes_count": 1,
        "input_box_variants": [
            {"part_number": "PN-001", "box_id": "B-A", "box_name": "B-A", "box_model_id": "M-A", "lid_id": "L-A"},
            {"part_number": "PN-002", "box_id": "B-B", "box_name": "B-B", "box_model_id": "M-B", "lid_id": "L-B"},
        ],
        "part_counts": [
            {
                "part_number": "PN-001",
                "supplier_name": "SUP-A",
                "box_name": "B-A",
                "box_model_id": "M-A",
                "lid_id": "L-A",
                "input_count": 2,
                "placed_count": 1,
                "unplaced_count": 1,
            },
            {
                "part_number": "PN-002",
                "supplier_name": "SUP-B",
                "box_name": "B-B",
                "box_model_id": "M-B",
                "lid_id": "L-B",
                "input_count": 1,
                "placed_count": 1,
                "unplaced_count": 0,
            },
        ],
        "boxes": [
            {
                "order": 1,
                "box_id": "B-A",
                "part_number": "PN-001",
                "supplier_name": "SUP-A",
                "box_name": "B-A",
                "box_model_id": "M-A",
                "lid_id": "L-A",
                "position": {"x": 0, "y": 0, "z": 200},
                "dimensions": {"width": 400, "length": 300, "height": 200},
                "rotation": 0,
                "fitting_depth": 5,
                "supported_by": [],
                "lid_thickness": 0,
                "lid_fit_type": "なし",
                "layer_index": 0,
            },
            {
                "order": 2,
                "box_id": "B-B",
                "part_number": "PN-002",
                "supplier_name": "SUP-B",
                "box_name": "B-B",
                "box_model_id": "M-B",
                "lid_id": "L-B",
                "position": {"x": 400, "y": 0, "z": 210},
                "dimensions": {"width": 350, "length": 280, "height": 210},
                "rotation": 90,
                "fitting_depth": 0,
                "supported_by": [1],
                "lid_thickness": 0,
                "lid_fit_type": "なし",
                "layer_index": 0,
            },
        ],
        "unplaced_boxes": [
            {
                "part_number": "PN-001",
                "box_id": "B-A",
                "supplier_name": "SUP-A",
                "box_name": "B-A",
                "box_model_id": "M-A",
                "lid_id": "L-A",
                "count": 1,
                "reason": "space shortage",
            }
        ],
        "summary": {
            "is_valid": True,
            "volume_efficiency_percent": 66.6,
            "total_layers": 1,
            "warnings": [],
            "violations": [],
            "cargo_height": 210,
            "total_height": 340,
            "overhang_mm": {"left": 0, "right": 0, "front": 0, "back": 0},
        },
    }


def make_manifest(result_name="result_fixture_part.json"):
    return {
        "input_mode": "part_number",
        "source": "catalog_store",
        "catalog_revision": "fixture-rev",
        "started_at": "2026-11-11T18:39:00",
        "completed_at": "2026-11-11T18:39:05",
        "counts": {"cases": 1, "passed": 1, "failed": 0, "errors": 0, "input": 3, "placed": 2, "unplaced": 1},
        "cases": [
            {
                "name": "fixture_part",
                "status": "PASS",
                "input": 3,
                "placed": 2,
                "unplaced": 1,
                "violations": [],
                "result_file": result_name,
                "elapsed_seconds": 0.01,
            }
        ],
    }


class ViewerCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.results = self.directory / "run_20261111_183900"
        self.results.mkdir()
        self.part_result = make_part_result()
        (self.results / "result_fixture_part.json").write_text(json.dumps(self.part_result, ensure_ascii=False), encoding="utf-8")
        (self.results / "run_manifest.json").write_text(json.dumps(make_manifest(), ensure_ascii=False), encoding="utf-8")
        fixtures = {}
        probe = {"result": None}

        class Handler(ViewerHandler):
            def do_GET(handler):
                name = handler.path.split("?", 1)[0]
                if name == "/probe":
                    params = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
                    probe["result"] = params.get("result", [""])[0]
                    body = b"ok"
                    handler.send_response(200)
                    handler.send_header("Content-Type", "text/plain; charset=utf-8")
                    handler.send_header("Content-Length", str(len(body)))
                    handler.end_headers()
                    handler.wfile.write(body)
                    return
                if name in fixtures:
                    body = fixtures[name].encode("utf-8")
                    handler.send_response(200)
                    handler.send_header("Content-Type", "text/html; charset=utf-8")
                    handler.send_header("Content-Length", str(len(body)))
                    handler.end_headers()
                    handler.wfile.write(body)
                else:
                    super().do_GET()

        self.fixtures = fixtures
        self.probe = probe
        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.server.results_dir = str(self.results)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_api_lists_manifest_results_only(self):
        with urlopen(self.url + "/api/results") as response:
            data = json.load(response)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual([row["filename"] for row in data], ["result_fixture_part.json"])
        self.assertEqual(data[0]["input_mode"], "part_number")
        with urlopen(self.url + "/api/result/result_fixture_part.json") as response:
            payload = json.load(response)
        self.assertEqual(payload["schema_version"], 2)

    def test_api_rejects_legacy_or_invalid_manifest_data(self):
        legacy = copy.deepcopy(self.part_result)
        legacy["schema_version"] = 1
        (self.results / "result_fixture_part.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/results")
        self.assertEqual(error.exception.code, 422)
        self.assertIn("schema_version=2", error.exception.read().decode("utf-8"))
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/result/result_fixture_part.json")
        self.assertEqual(error.exception.code, 422)
        self.assertIn("schema_version=2", error.exception.read().decode("utf-8"))
        invalid_ref = copy.deepcopy(self.part_result)
        invalid_ref["coordinate_reference"] = "legacy_min_xyz"
        (self.results / "result_fixture_part.json").write_text(json.dumps(invalid_ref, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/results")
        self.assertEqual(error.exception.code, 422)
        self.assertIn("coordinate_reference", error.exception.read().decode("utf-8"))

    def test_manifest_helpers_pick_latest_valid_run(self):
        root = self.directory / "catalog_results"
        root.mkdir()
        old = root / "20260101_000000"
        old.mkdir()
        (old / "result_fixture_part.json").write_text(json.dumps(self.part_result, ensure_ascii=False), encoding="utf-8")
        (old / "run_manifest.json").write_text(json.dumps(make_manifest(), ensure_ascii=False), encoding="utf-8")
        new = root / "20261111_183954"
        new.mkdir()
        (new / "result_fixture_part.json").write_text(json.dumps(self.part_result, ensure_ascii=False), encoding="utf-8")
        (new / "run_manifest.json").write_text(json.dumps(make_manifest(), ensure_ascii=False), encoding="utf-8")
        self.assertEqual(resolve_latest_completed_catalog_run(root), new)
        entries = load_part_results_from_manifest(new)
        self.assertEqual(entries[0]["filename"], "result_fixture_part.json")
        wip = root / "20261111_190000"
        wip.mkdir()
        self.assertEqual(resolve_latest_completed_catalog_run(root), new)
        (wip / "run_manifest.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError) as error:
            resolve_latest_completed_catalog_run(root)
        self.assertIn("最新完了実行フォルダ", str(error.exception))
        self.assertIn("フォールバックしません", str(error.exception))

    def test_manifest_loader_accepts_fail_row(self):
        fail_result = copy.deepcopy(self.part_result)
        fail_result["test_name"] = "fixture_fail"
        fail_result["input_boxes_count"] = 2
        fail_result["placed_boxes_count"] = 0
        fail_result["unplaced_boxes_count"] = 2
        fail_result["boxes"] = []
        fail_result["part_counts"][0]["input_count"] = 1
        fail_result["part_counts"][0]["placed_count"] = 0
        fail_result["part_counts"][0]["unplaced_count"] = 1
        fail_result["part_counts"][1]["input_count"] = 1
        fail_result["part_counts"][1]["placed_count"] = 0
        fail_result["part_counts"][1]["unplaced_count"] = 1
        fail_result["unplaced_boxes"] = [
            {
                "part_number": "PN-001",
                "box_id": "B-A",
                "supplier_name": "SUP-A",
                "box_name": "B-A",
                "box_model_id": "M-A",
                "lid_id": "L-A",
                "count": 1,
                "reason": "space shortage",
            },
            {
                "part_number": "PN-002",
                "box_id": "B-B",
                "supplier_name": "SUP-B",
                "box_name": "B-B",
                "box_model_id": "M-B",
                "lid_id": "L-B",
                "count": 1,
                "reason": "space shortage",
            },
        ]
        fail_result["summary"]["is_valid"] = False
        fail_result["summary"]["violations"] = ["No boxes placed"]
        fail_result["summary"]["volume_efficiency_percent"] = 0.0
        fail_result["summary"]["cargo_height"] = 0
        fail_result["summary"]["total_height"] = 130
        (self.results / "result_fixture_fail.json").write_text(
            json.dumps(fail_result, ensure_ascii=False), encoding="utf-8"
        )
        manifest = make_manifest()
        manifest["cases"].append(
            {
                "name": "fixture_fail",
                "status": "FAIL",
                "input": 2,
                "placed": 0,
                "unplaced": 2,
                "violations": ["No boxes placed"],
                "result_file": "result_fixture_fail.json",
                "elapsed_seconds": 0.02,
            }
        )
        manifest["counts"] = {"cases": 2, "passed": 1, "failed": 1, "errors": 0, "input": 5, "placed": 2, "unplaced": 3}
        (self.results / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        entries = load_part_results_from_manifest(self.results)
        self.assertEqual([entry["filename"] for entry in entries], ["result_fixture_part.json", "result_fixture_fail.json"])

    def test_manifest_loader_rejects_inconsistencies(self):
        def run_case(mutator, needle):
            with self.subTest(needle=needle):
                manifest = make_manifest()
                result_data = copy.deepcopy(self.part_result)
                files = {"result_fixture_part.json": result_data}
                mutator(manifest, result_data, files)
                for filename, payload in files.items():
                    (self.results / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                (self.results / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(ValueError) as error:
                    load_part_results_from_manifest(self.results)
                self.assertIn(needle, str(error.exception))

        run_case(lambda manifest, _result, _files: manifest.update(source="other"), "source='catalog_store'")
        run_case(lambda manifest, _result, _files: manifest.pop("completed_at"), "completed_at")
        run_case(lambda manifest, _result, _files: manifest.update(completed_at=None), "completed_at")
        run_case(lambda manifest, _result, _files: manifest["counts"].update(input=4), "counts.input")
        run_case(lambda manifest, result_data, _files: result_data.update(test_name="other_name"), "test_name")
        run_case(lambda manifest, result_data, _files: result_data.update(catalog_revision="other_rev"), "catalog_revision")
        run_case(lambda manifest, _result, _files: manifest["cases"][0].update(status="SKIP"), "status が不正")
        run_case(lambda manifest, _result, _files: manifest["counts"].update(input=True), "counts.input")

        def duplicate_name(manifest, _result, _files):
            copied = copy.deepcopy(manifest["cases"][0])
            manifest["cases"].append(copied)
            manifest["counts"].update(cases=2, passed=2, input=6, placed=4, unplaced=2)

        run_case(duplicate_name, "case.name が重複")

        def duplicate_file(manifest, _result, files):
            second = copy.deepcopy(manifest["cases"][0])
            second["name"] = "fixture_second"
            second["result_file"] = "result_fixture_part.json"
            manifest["cases"].append(second)
            manifest["counts"].update(cases=2, passed=2, input=6, placed=4, unplaced=2)
            second_result = copy.deepcopy(files["result_fixture_part.json"])
            second_result["test_name"] = "fixture_second"
            files["result_fixture_second.json"] = second_result

        run_case(duplicate_file, "result_file が case 名と一致しません")

    def test_manifest_loader_reports_error_cases(self):
        manifest = make_manifest()
        manifest["cases"].append({"name": "fixture_error", "status": "ERROR", "error": "runner failed", "elapsed_seconds": 0.03})
        manifest["counts"] = {"cases": 2, "passed": 1, "failed": 0, "errors": 1, "input": 3, "placed": 2, "unplaced": 1}
        (self.results / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        entries = load_part_results_from_manifest(self.results)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1], {
            "filename": None, "data": None, "case": manifest["cases"][1],
        })
        with urlopen(self.url + "/api/results") as response:
            listing = json.load(response)
        self.assertEqual(listing[0]["status"], "PASS")
        self.assertEqual(listing[1], {
            "filename": None, "test_name": "fixture_error", "status": "ERROR",
            "error": "runner failed", "input_mode": "part_number",
        })
        with urlopen(self.url + "/api/result/result_fixture_part.json") as response:
            self.assertEqual(json.load(response)["test_name"], "fixture_part")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/result/result_fixture_error.json")
        self.assertEqual(error.exception.code, 404)

    def test_all_error_run_can_be_listed_and_selected_as_latest(self):
        manifest = make_manifest()
        manifest["cases"] = [dict(name="blocked", status="ERROR", error="missing pallet",
                                  elapsed_seconds=0.01)]
        manifest["counts"] = dict(cases=1, passed=0, failed=0, errors=1,
                                   input=0, placed=0, unplaced=0)
        (self.results / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(resolve_latest_completed_catalog_run(self.directory), self.results)
        with urlopen(self.url + "/api/results") as response:
            listing = json.load(response)
        self.assertEqual([row["status"] for row in listing], ["ERROR"])

    def test_error_rows_do_not_bypass_integrity_checks(self):
        for field, value in (("error", ""), ("error", None), ("result_file", "result_blocked.json"),
                             ("input", 1), ("elapsed_seconds", -1)):
            manifest = make_manifest()
            row = dict(name="blocked", status="ERROR", error="missing pallet", elapsed_seconds=.01)
            row[field] = value
            manifest["cases"].append(row)
            manifest["counts"].update(cases=2, errors=1)
            (self.results / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_part_results_from_manifest(self.results)
        manifest = make_manifest()
        manifest["cases"].append(dict(name="blocked", status="ERROR", error="missing pallet",
                                      elapsed_seconds=.01))
        manifest["counts"].update(cases=2, errors=1)
        (self.results / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.results / "result_fixture_part.json").unlink()
        with self.assertRaisesRegex(ValueError, "結果JSONが見つかりません"):
            load_part_results_from_manifest(self.results)

    @unittest.skipUnless(
        EDGE.exists() and os.environ.get("PALLETIZER_RUN_BROWSER_TESTS") == "1",
        "Set PALLETIZER_RUN_BROWSER_TESTS=1 with Playwright available",
    )
    def test_browser_mixed_and_all_error_runs(self):
        from playwright.sync_api import sync_playwright

        manifest = make_manifest()
        fail = copy.deepcopy(self.part_result)
        fail["test_name"] = "fixture_fail"
        fail["summary"].update(is_valid=False, violations=["fixture constraint violation"])
        (self.results / "result_fixture_fail.json").write_text(json.dumps(fail), encoding="utf-8")
        fail_row = dict(manifest["cases"][0], name="fixture_fail", status="FAIL",
                        violations=["fixture constraint violation"], result_file="result_fixture_fail.json")
        blocked = dict(name="blocked", status="ERROR", error="<img src=x onerror=alert(1)> missing pallet",
                       elapsed_seconds=.01)
        manifest["cases"] = [blocked, manifest["cases"][0], fail_row]
        manifest["counts"] = dict(cases=3, passed=1, failed=1, errors=1,
                                   input=6, placed=4, unplaced=2)
        manifest_path = self.results / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.fixtures["/index.html"] = re.sub(
            r'<script src="https://[^"]+"></script>', "",
            (Path(__file__).resolve().parent / "index.html").read_text(encoding="utf-8"),
        ).replace("</head>", "<script>const lucide={createIcons(){}};</script></head>")
        with sync_playwright() as playwright:
            with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1])) as profile:
                context = playwright.chromium.launch_persistent_context(
                    profile, executable_path=str(EDGE), headless=True,
                    args=["--no-first-run", "--disable-extensions", "--disable-background-networking",
                          "--no-proxy-server", "--disable-features=msEdgeSidebarV2"],
                    viewport={"width": 1400, "height": 1000},
                )
                try:
                    page = context.pages[0]
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(self.url + "/index.html")
                    page.wait_for_function("currentData?.test_name === 'fixture_part'")
                    self.assertIn("PASS 1 / FAIL 1 / ERROR 1", page.locator("#run-summary").inner_text())
                    self.assertEqual(page.locator("#select-test-case").input_value(), "1")
                    page.evaluate("inspectBox(currentData.boxes[0]); togglePlay()")
                    page.select_option("#select-test-case", "0")
                    self.assertTrue(page.locator("#case-error").is_visible())
                    self.assertIn("<img", page.locator("#case-error-message").inner_text())
                    self.assertEqual(page.locator("#case-error-message img").count(), 0)
                    self.assertTrue(page.evaluate("currentData === null && !isPlaying && selectedBoxOrder === null"))
                    self.assertEqual(page.locator("#metric-boxes").inner_text(), "—")
                    self.assertEqual(page.locator("#part-summary").inner_text(), "")
                    self.assertEqual(page.locator("#inspector-content").inner_text(), "")
                    self.assertTrue(page.locator("#step-slider").is_disabled())
                    self.assertTrue(page.locator("#btn-play-toggle").is_disabled())
                    page.select_option("#select-test-case", "2")
                    page.wait_for_function("currentData?.test_name === 'fixture_fail'")
                    self.assertIn("FAIL", page.locator("#badge-valid").inner_text())
                    self.assertIn("fixture constraint violation", page.locator("#constraint-summary").inner_text())
                    self.assertFalse(page.locator("#case-error").is_visible())
                    self.assertFalse(page.locator("#btn-play-toggle").is_disabled())
                    for view in ("top", "front", "side", "iso"):
                        page.locator('[data-view="{}"]'.format(view)).dispatch_event("click")
                        self.assertEqual(page.evaluate("viewMode"), view)
                    page.locator("#step-slider").fill("1")
                    self.assertEqual(page.locator("#step-current").inner_text(), "1")

                    # Hold a successful response until after an ERROR selection.
                    page.evaluate("""() => {
                      const original = window.fetch.bind(window);
                      window.fetch = async (...args) => {
                        const response = await original(...args);
                        if (String(args[0]).includes('/api/result/')) {
                          await new Promise(resolve => { window.releaseResult = resolve; });
                        }
                        return response;
                      };
                    }""")
                    page.select_option("#select-test-case", "1")
                    page.wait_for_function("typeof releaseResult === 'function'")
                    page.select_option("#select-test-case", "0")
                    page.evaluate("releaseResult()")
                    page.wait_for_timeout(200)
                    self.assertTrue(page.evaluate("currentData === null"))
                    self.assertTrue(page.locator("#case-error").is_visible())

                    manifest["cases"] = [blocked]
                    manifest["counts"] = dict(cases=1, passed=0, failed=0, errors=1,
                                               input=0, placed=0, unplaced=0)
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    page.reload()
                    page.wait_for_selector("#case-error", state="visible")
                    self.assertIn("PASS 0 / FAIL 0 / ERROR 1", page.locator("#run-summary").inner_text())
                    self.assertTrue(page.evaluate("currentData === null"))
                    self.assertEqual(errors, [])

                    actual = (Path(__file__).resolve().parents[1] / "tester" / "catalog_results"
                              / "skid_20261112_implementation")
                    if (actual / "run_manifest.json").exists():
                        self.server.results_dir = str(actual)
                        page.reload()
                        page.wait_for_function("currentData !== null")
                        self.assertIn("150件 / PASS 143 / FAIL 2 / ERROR 5",
                                      page.locator("#run-summary").inner_text())
                        self.assertEqual(page.locator("#select-test-case option").count(), 150)
                        page.evaluate("""() => {
                          const select = document.getElementById('select-test-case');
                          select.value = String(resultEntries.findIndex(item => item.status === 'ERROR'));
                          select.dispatchEvent(new Event('change'));
                        }""")
                        self.assertTrue(page.locator("#case-error").is_visible())
                        self.assertIn("26411F", page.locator("#case-error-message").inner_text())
                        self.assertTrue(page.evaluate("currentData === null"))
                        self.assertEqual(errors, [])
                finally:
                    context.close()

    @unittest.skipUnless(
        (
            (Path(__file__).resolve().parent.parent / "tester" / "catalog_results" / "consistency_verified" / "run_manifest.json").exists()
            or (Path(__file__).resolve().parent.parent / "tester" / "catalog_results" / "retirement_verified" / "run_manifest.json").exists()
        ),
        "実データがない環境ではスキップ",
    )
    def test_manifest_loader_supports_actual_150_case_run(self):
        root = Path(__file__).resolve().parent.parent / "tester" / "catalog_results"
        if (root / "consistency_verified" / "run_manifest.json").exists():
            path = root / "consistency_verified"
        else:
            path = root / "retirement_verified"
        entries = load_part_results_from_manifest(path)
        self.assertEqual(len(entries), 150)

    def test_standalone_generation_rejects_legacy_input_and_escapes_text(self):
        special = copy.deepcopy(self.part_result)
        special["test_name"] = "<fixture_part>"
        out = self.directory / "viewer.html"
        generate_html(special, str(out))
        text = out.read_text(encoding="utf-8")
        self.assertIn("\\u003c", text)
        bad = copy.deepcopy(self.part_result)
        bad["input_mode"] = "legacy"
        with self.assertRaises(ValueError):
            generate_html(bad, str(self.directory / "bad.html"))

    @unittest.skipUnless(EDGE.exists(), "Edgeがない環境ではHTTPテストのみ実行")
    def test_browser_part_only_and_error_view(self):
        harness = """<!DOCTYPE html><html><body>
<pre id="result">RUNNING</pre><iframe id="app" src="/index.html" width="1400" height="1000"></iframe>
<script>
const frame = document.getElementById('app'), output = document.getElementById('result');
const sleep = () => new Promise(resolve => setTimeout(resolve, 50));
const until = async (f,m) => { for (let i=0;i<300;i++){ if(f()) return; await sleep(); } throw new Error(m); };
const report = async (result, detail='') => { try { await fetch('/probe?result='+encodeURIComponent(result+detail)); } catch(_) {} };
(async()=>{
  await until(()=>frame.contentDocument?.getElementById('part-summary')?.textContent.includes('共通モデル'),'part load');
  const w = frame.contentWindow, d = frame.contentDocument;
  w.inspectBox(w.eval('currentData.boxes[0]'));
  if (!d.getElementById('part-inspector').textContent.includes('PN-001')) throw new Error('inspector');
  d.getElementById('step-slider').value = '1';
  d.getElementById('step-slider').dispatchEvent(new w.Event('input'));
  if (d.getElementById('step-current').textContent !== '1') throw new Error('timeline');
  await report('PASS');
  output.textContent='PASS';
})().catch(async e=>{ await report('FAIL:'+e.message); output.textContent='FAIL: '+e.stack});
</script></body></html>"""
        self.fixtures["/test.html"] = harness
        self.fixtures["/index.html"] = re.sub(
            r'<script src="https://[^"]+"></script>',
            "",
            (Path(__file__).resolve().parent / "index.html").read_text(encoding="utf-8"),
        ).replace("</head>", "<script>const lucide={createIcons(){}};</script></head>")
        run = subprocess.run(
            [
                str(EDGE),
                "--headless",
                "--disable-gpu",
                "--no-first-run",
                "--disable-extensions",
                "--disable-background-networking",
                "--no-proxy-server",
                "--disable-features=msEdgeSidebarV2",
                "--user-data-dir=" + str(Path(tempfile.gettempdir()) / f"viz_edge_{os.getpid()}_{int(time.time() * 1000)}"),
                "--dump-dom",
                "--virtual-time-budget=30000",
                self.url + "/test.html",
            ],
            capture_output=True,
            timeout=90,
        )
        output = run.stdout.decode("utf-8", errors="replace")
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", errors="replace")[-2000:])
        if self.probe["result"] is None:
            self.skipTest(f"Edge headless did not execute harness in this environment (stdout={output!r})")
        self.assertEqual(self.probe["result"], "PASS", f"probe={self.probe['result']} stdout={output!r}")


if __name__ == "__main__":
    unittest.main()
