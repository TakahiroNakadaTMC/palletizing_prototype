import http.client
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from box_research.database_validation import STANDARD_PALLET, STANDARD_PALLET_ID
from test_programmer import serve_testcase_viewer as viewer


class TestCaseViewerPalletTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cases = self.root / "cases"
        self.cases.mkdir()
        self.pallet_id = "MODEL_1200x1000x130"
        self.standard_pallet_id = STANDARD_PALLET_ID
        self.pallet_db = self.root / "pallet_db.json"
        self.pallet_db.write_text(json.dumps({
            "pallets": {
                self.standard_pallet_id: STANDARD_PALLET,
                self.pallet_id: {
                    "id": self.pallet_id, "model": "MODEL", "length": 1200,
                    "width": 1000, "height": 130, "suppliers": ["Supplier A"],
                }
            }
        }), encoding="utf-8")
        self.box_db = self.root / "box_db.json"
        self.lid_db = self.root / "lid_db.json"
        self.box_db.write_text(json.dumps({
            "BOX": {"id": "BOX", "compatible_lids": ["LID"]},
        }), encoding="utf-8")
        self.lid_db.write_text(json.dumps({
            "NONE": {"id": "NONE", "type": "NONE"},
            "LID": {"id": "LID", "type": "TP"},
            "OTHER": {"id": "OTHER", "type": "TP"},
        }), encoding="utf-8")
        for name, value in {
            "BASE_DIR": str(self.root),
            "PROJECT_ROOT": str(self.root),
            "PALLET_DB_PATH": str(self.pallet_db),
            "BOX_DB_PATH": str(self.box_db),
            "LID_DB_PATH": str(self.lid_db),
            "TEST_CASES_DIR": str(self.cases),
            "APPROVAL_STATE_PATH": str(self.root / "approval.json"),
        }.items():
            patcher = patch.object(viewer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = socketserver.TCPServer(("127.0.0.1", 0), viewer.TestCaseViewerHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, data=None):
        body = json.dumps(data) if data is not None else None
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        try:
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def make_case(self, supplier="Supplier A", pallet_id=None, length=1200):
        case = {
            "name": "case", "description": "test",
            "pallet": {
                "length": length, "width": 1000, "height": 130,
                "max_x_span": 1360, "max_y_span": 1100, "max_height": 1200,
            },
            "supplier_name": supplier,
            "box_list": [{"box_id": "BOX", "count": 1, "lid_id": "NONE"}],
        }
        if pallet_id:
            case["pallet_id"] = pallet_id
        return {
            "test_cases": {"case": case},
            "approval_state": {"case": False},
            "delete_ids": [],
        }

    def test_pallet_database_endpoint_returns_master(self):
        status, response = self.request("GET", "/api/pallets")
        self.assertEqual(status, 200)
        self.assertIn(self.pallet_id, response["pallets"])

    def test_save_all_accepts_supplier_and_matching_pallet(self):
        payload = self.make_case(pallet_id=self.pallet_id)
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 200, response)
        saved = json.loads((self.cases / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["supplier_name"], "Supplier A")
        self.assertEqual(saved["pallet_id"], self.pallet_id)
        self.assertEqual(set(saved["pallet"]), {"max_x_span", "max_y_span", "max_height"})

    def test_save_all_rejects_supplier_mismatch(self):
        payload = self.make_case(supplier="Other supplier", pallet_id=self.pallet_id)
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 500)
        self.assertEqual(response["status"], "error")
        self.assertFalse((self.cases / "case.json").exists())

    def test_save_all_discards_legacy_duplicate_pallet_dimensions(self):
        payload = self.make_case(pallet_id=self.pallet_id, length=1100)
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 200, response)
        saved = json.loads((self.cases / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pallet_id"], self.pallet_id)
        self.assertEqual(set(saved["pallet"]), {"max_x_span", "max_y_span", "max_height"})

    def test_save_all_accepts_standard_for_any_supplier(self):
        payload = self.make_case(supplier="Unlisted supplier", pallet_id=self.standard_pallet_id)
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 200, response)
        saved = json.loads((self.cases / "case.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pallet_id"], self.standard_pallet_id)
        self.assertEqual(set(saved["pallet"]), {"max_x_span", "max_y_span", "max_height"})

    def test_save_all_rejects_case_without_pallet_selection(self):
        payload = self.make_case(supplier="Supplier A", length=1100)
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 500)
        self.assertEqual(response["status"], "error")
        self.assertIn("パレット型番または標準パレット", response["message"])
        self.assertFalse((self.cases / "case.json").exists())

    def test_save_all_accepts_compatible_lid_and_count_boundaries(self):
        for lid_id, count in (("NONE", 1), ("LID", 500), ("LID", 1.0)):
            with self.subTest(lid_id=lid_id, count=count):
                payload = self.make_case(pallet_id=self.pallet_id)
                payload["test_cases"]["case"]["box_list"][0].update(
                    lid_id=lid_id, count=count
                )
                status, response = self.request("POST", "/api/testcase/save_all", payload)
                self.assertEqual(status, 200, response)
                saved = json.loads((self.cases / "case.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["box_list"], payload["test_cases"]["case"]["box_list"])

    def test_valid_save_keeps_approval_and_deletion_behavior(self):
        (self.cases / "old.json").write_text('{"name": "old"}', encoding="utf-8")
        payload = self.make_case(pallet_id=self.pallet_id)
        payload["approval_state"]["case"] = True
        payload["delete_ids"] = ["old"]
        status, response = self.request("POST", "/api/testcase/save_all", payload)
        self.assertEqual(status, 200, response)
        self.assertTrue((self.cases / "case.json").exists())
        self.assertFalse((self.cases / "old.json").exists())
        self.assertEqual(
            json.loads((self.root / "approval.json").read_text(encoding="utf-8")),
            {"case": True},
        )

    def test_save_all_rejects_invalid_box_rows_before_any_write_or_delete(self):
        original_case = b'{"name": "original"}'
        original_approval = b'{"old": true}'
        (self.cases / "case.json").write_bytes(original_case)
        (self.cases / "old.json").write_bytes(original_case)
        approval_path = self.root / "approval.json"
        approval_path.write_bytes(original_approval)
        invalid_rows = [
            ({"box_id": "UNKNOWN"}, "箱型番"),
            ({"box_id": []}, "箱型番"),
            ({"lid_id": "UNKNOWN"}, "登録済みの蓋"),
            ({"lid_id": []}, "登録済みの蓋"),
            ({"lid_id": "OTHER"}, "対応していません"),
        ] + [
            ({"count": count}, "1〜500")
            for count in (0, 501, -1, 1.5, True, None, "1", float("nan"), float("inf"))
        ]
        for update, expected in invalid_rows:
            with self.subTest(update=update):
                payload = self.make_case(pallet_id=self.pallet_id)
                bad_case = self.make_case(pallet_id=self.pallet_id)["test_cases"]["case"]
                bad_case["box_list"][0].update(update)
                payload["test_cases"]["invalid"] = bad_case
                payload["approval_state"]["invalid"] = False
                payload["delete_ids"] = ["old"]
                status, response = self.request("POST", "/api/testcase/save_all", payload)
                self.assertEqual(status, 500)
                self.assertIn("invalid 箱行1", response["message"])
                self.assertIn(expected, response["message"])
                self.assertEqual((self.cases / "case.json").read_bytes(), original_case)
                self.assertEqual((self.cases / "old.json").read_bytes(), original_case)
                self.assertEqual(approval_path.read_bytes(), original_approval)
                self.assertFalse((self.cases / "invalid.json").exists())

    def test_save_all_rejects_missing_or_malformed_box_list_and_description(self):
        for update in (
            {"box_list": []}, {"box_list": None}, {"box_list": [None]},
            {"box_list": [{}]}, {"description": ""}, {"description": None},
        ):
            with self.subTest(update=update):
                payload = self.make_case(pallet_id=self.pallet_id)
                payload["test_cases"]["case"].update(update)
                status, response = self.request("POST", "/api/testcase/save_all", payload)
                self.assertEqual(status, 500)
                self.assertIn("case", response["message"])
                self.assertFalse((self.cases / "case.json").exists())
                self.assertFalse((self.root / "approval.json").exists())

    def test_save_all_reports_invalid_or_missing_master_without_writes(self):
        original = self.box_db.read_bytes()
        for content in (b"{", b"[]", b'{"BOX": {"id": "OTHER"}}', None):
            with self.subTest(content=content):
                if content is None:
                    self.box_db.unlink()
                else:
                    self.box_db.write_bytes(content)
                status, response = self.request(
                    "POST", "/api/testcase/save_all", self.make_case(pallet_id=self.pallet_id)
                )
                self.assertEqual(status, 500)
                self.assertTrue(response["message"])
                self.assertFalse((self.cases / "case.json").exists())
                self.assertFalse((self.root / "approval.json").exists())
                self.box_db.write_bytes(original)

    def test_existing_cases_can_be_saved_unchanged_in_temporary_directory(self):
        project = Path(__file__).resolve().parents[1]
        for path, name in (
            (self.box_db, "box_db.json"), (self.lid_db, "lid_db.json"),
            (self.pallet_db, "pallet_db.json"),
        ):
            path.write_bytes((project / "box_research" / name).read_bytes())
        cases = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in (project / "test_programmer" / "test_cases").glob("*.json")
        }
        approvals = json.loads(
            (project / "test_programmer" / "test_case_approval.json").read_text(encoding="utf-8")
        )
        status, response = self.request("POST", "/api/testcase/save_all", {
            "test_cases": cases, "approval_state": approvals, "delete_ids": [],
        })
        self.assertEqual(status, 200, response)
        self.assertEqual(len(list(self.cases.glob("*.json"))), len(cases))
        for case_id, case in cases.items():
            saved = json.loads((self.cases / (case_id + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(saved, case)
        self.assertEqual(
            json.loads((self.root / "approval.json").read_text(encoding="utf-8")), approvals
        )


class ViewerStartupTest(unittest.TestCase):
    def test_direct_and_module_startup_serve_page_and_databases(self):
        project = Path(__file__).resolve().parents[1]
        script = project / "test_programmer" / "serve_testcase_viewer.py"
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            # Suppress only browser launch; exercise the real command and HTTP server.
            (temporary / "sitecustomize.py").write_text(
                "import webbrowser\nwebbrowser.open = lambda *args, **kwargs: False\n",
                encoding="utf-8",
            )
            env = dict(os.environ, PYTHONPATH=directory, PYTHONIOENCODING="utf-8")
            commands = (
                ([sys.executable, "-u", str(script)], project),
                ([sys.executable, "-u", str(script)], temporary),
                ([sys.executable, "-u", "-m", "test_programmer.serve_testcase_viewer"], project),
            )
            for command, cwd in commands:
                with self.subTest(command=command, cwd=cwd):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", 0))
                        port = probe.getsockname()[1]
                    with tempfile.TemporaryFile() as output:
                        process = subprocess.Popen(
                            command + [str(port)], cwd=cwd, env=env,
                            stdout=output, stderr=subprocess.STDOUT,
                        )
                        try:
                            deadline = time.monotonic() + 10
                            while time.monotonic() < deadline and process.poll() is None:
                                try:
                                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                                        break
                                except OSError:
                                    time.sleep(0.05)
                            else:
                                output.seek(0)
                                self.fail(output.read().decode("utf-8", errors="replace"))
                            for endpoint in ("/", "/api/boxes", "/api/lids", "/api/pallets"):
                                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                                try:
                                    connection.request("GET", endpoint)
                                    response = connection.getresponse()
                                    body = response.read()
                                    self.assertEqual(response.status, 200, body)
                                    if endpoint == "/":
                                        self.assertIn(b"<html", body.lower())
                                    else:
                                        self.assertIsInstance(json.loads(body), dict)
                                finally:
                                    connection.close()
                        finally:
                            if process.poll() is None:
                                process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)

    def test_db_server_direct_import_from_outside_project(self):
        project = Path(__file__).resolve().parents[1]
        script = project / "box_research" / "serve_viewer.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import runpy, sys; sys.path[0] = sys.argv[1]; "
                 "runpy.run_path(sys.argv[2], run_name='__startup_test__')",
                 str(script.parent), str(script)],
                cwd=directory, env=dict(os.environ, PYTHONPATH=""),
                capture_output=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
