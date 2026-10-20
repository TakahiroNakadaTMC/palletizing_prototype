import copy
import http.client
import json
import os
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch

from box_research import serve_viewer as viewer


class ViewerServerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.boxes = {
            "BOX": {
                "id": "BOX", "name": "Box", "length": 600, "width": 400,
                "height": 200, "rib_thickness": 22, "compatible_lids": ["LID"],
            }
        }
        self.lids = {
            "NONE": {"id": "NONE", "type": "NONE", "thickness": 0},
            "LID": {"id": "LID", "type": "TP", "thickness": 15},
        }
        self.box_path = self.root / "box_db.json"
        self.lid_path = self.root / "lid_db.json"
        self.box_path.write_text(json.dumps(self.boxes), encoding="utf-8")
        self.lid_path.write_text(json.dumps(self.lids), encoding="utf-8")
        (self.root / "cases").mkdir()
        (self.root / "db_viewer.html").write_text("<title>Integrated viewer</title>", encoding="utf-8")
        for name, value in {
            "BASE_DIR": str(self.root),
            "BOX_DB_PATH": str(self.box_path),
            "LID_DB_PATH": str(self.lid_path),
            "VIEWER_HTML_PATH": str(self.root / "db_viewer.html"),
            "TEST_CASES_DIR": str(self.root / "cases"),
        }.items():
            patcher = patch.object(viewer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = socketserver.TCPServer(("127.0.0.1", 0), viewer.ViewerRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, data=None, raw=None):
        body = raw if raw is not None else (json.dumps(data) if data is not None else None)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_root_and_index_show_same_integrated_viewer(self):
        for path in ("/", "/index.html"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(b"Integrated viewer", body)

    def test_legacy_urls_redirect_to_matching_tabs(self):
        for path, tab in (("/box_db_viewer.html", "boxes"), ("/lid_db_viewer.html", "lids")):
            status, headers, _ = self.request("GET", path)
            self.assertEqual(status, 302)
            self.assertEqual(headers["Location"], "/#" + tab)

    def test_reads_disable_cache_and_report_missing_database(self):
        status, headers, body = self.request("GET", "/api/boxes")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), self.boxes)
        self.lid_path.unlink()
        status, _, body = self.request("GET", "/api/lids")
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body)["status"], "error")

    def test_related_save_replaces_both_and_preserves_dimension_values(self):
        boxes = copy.deepcopy(self.boxes)
        lids = copy.deepcopy(self.lids)
        lids["NEW"] = dict(lids.pop("LID"), id="NEW")
        boxes["BOX"]["compatible_lids"] = ["NEW"]
        status, _, body = self.request("POST", "/api/databases/save", {"boxes": boxes, "lids": lids})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(self.box_path.read_text(encoding="utf-8")), boxes)
        self.assertEqual(json.loads(self.lid_path.read_text(encoding="utf-8")), lids)
        self.assertLess(self.box_path.read_text().index('"length"'), self.box_path.read_text().index('"width"'))
        self.assertFalse(list(self.root.glob(".viewer-*.tmp")))

    def test_legacy_save_endpoints_still_work(self):
        for endpoint, data in (("/api/save", self.boxes), ("/api/lids/save_all", self.lids)):
            status, _, body = self.request("POST", endpoint, data)
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body)["status"], "ok")

    def test_invalid_payloads_do_not_write(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        for payload in (
            {}, [], {"other": {}}, {"boxes": []}, {"boxes": {"BOX": {"id": "different"}}},
            {"lids": {}}, {"boxes": {"BOX": {"id": "BOX", "compatible_lids": ["MISSING"]}}},
        ):
            status, _, body = self.request("POST", "/api/databases/save", payload)
            self.assertEqual(status, 400, body)
            self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)
        status, _, _ = self.request("POST", "/api/databases/save", raw="{")
        self.assertEqual(status, 400)

    def test_deleting_referenced_lid_is_blocked_server_side(self):
        (self.root / "cases" / "used.json").write_text(
            json.dumps({"box_list": [{"box_id": "BOX", "lid_id": "LID"}]}), encoding="utf-8"
        )
        lids = {"NONE": self.lids["NONE"]}
        boxes = copy.deepcopy(self.boxes)
        boxes["BOX"]["compatible_lids"] = []
        status, _, body = self.request("POST", "/api/databases/save", {"boxes": boxes, "lids": lids})
        self.assertEqual(status, 400)
        self.assertIn("Lid LID", json.loads(body)["message"])
        self.assertIn("used.json", json.loads(body)["message"])
        self.assertEqual(json.loads(self.lid_path.read_text()), self.lids)

    def test_lid_only_deletion_cannot_leave_dangling_box_reference(self):
        status, _, body = self.request(
            "POST", "/api/databases/save", {"lids": {"NONE": self.lids["NONE"]}}
        )
        self.assertEqual(status, 400)
        self.assertIn("compatible_lids", json.loads(body)["message"])
        self.assertEqual(json.loads(self.lid_path.read_text()), self.lids)

    def test_box_references_list_sorted_unique_test_case_names(self):
        for filename in ("b.json", "a.json"):
            (self.root / "cases" / filename).write_text(
                json.dumps({"box_list": [{"box_id": "BOX"}, {"box_id": "BOX"}]}), encoding="utf-8"
            )
        status, headers, body = self.request("GET", "/api/box_references")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), {"BOX": ["a.json", "b.json"]})

    def test_referenced_box_removal_and_rename_block_all_save_endpoints(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        for boxes in ({}, {"NEW": dict(self.boxes["BOX"], id="NEW")}):
            for endpoint in ("/api/save", "/api/databases/save"):
                with self.subTest(endpoint=endpoint, boxes=boxes):
                    # Reference is created after the viewer's initial load.
                    (self.root / "cases" / "used.json").write_text(
                        json.dumps({"box_list": [{"box_id": "BOX"}]}), encoding="utf-8"
                    )
                    payload = boxes if endpoint == "/api/save" else {"boxes": boxes, "lids": self.lids}
                    status, _, body = self.request("POST", endpoint, payload)
                    self.assertEqual(status, 400)
                    self.assertIn("BOX", json.loads(body)["message"])
                    self.assertIn("used.json", json.loads(body)["message"])
                    self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)

    def test_unreferenced_box_removal_and_rename_allowed(self):
        for boxes in ({"NEW": dict(self.boxes["BOX"], id="NEW")}, {}):
            status, _, body = self.request("POST", "/api/databases/save", {"boxes": boxes})
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(self.box_path.read_text()), boxes)

    def test_broken_box_references_fail_closed(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        for content in ('{', '{"box_list":[null]}', '{"box_list":[{"box_id":42}]}'):
            (self.root / "cases" / "invalid.json").write_text(content, encoding="utf-8")
            status, _, _ = self.request("GET", "/api/box_references")
            self.assertEqual(status, 500)
            status, _, _ = self.request("POST", "/api/databases/save", {"boxes": {}})
            self.assertEqual(status, 400)
            self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)

    def test_implicit_no_lid_reference_is_retained(self):
        (self.root / "cases" / "default.json").write_text(
            json.dumps({"box_list": [{"box_id": "BOX"}]}), encoding="utf-8"
        )
        status, _, body = self.request("GET", "/api/lid_references")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"NONE": ["default.json"]})
        lids = copy.deepcopy(self.lids)
        lids["NEW-NONE"] = dict(lids.pop("NONE"), id="NEW-NONE")
        status, _, _ = self.request("POST", "/api/databases/save", {"lids": lids})
        self.assertEqual(status, 400)

    def test_reference_read_failure_blocks_save_without_writing(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        (self.root / "cases" / "invalid.json").write_text('{"box_list": [null]}', encoding="utf-8")
        status, _, body = self.request("GET", "/api/lid_references")
        self.assertEqual(status, 500)
        self.assertIn("invalid.json", json.loads(body)["message"])
        status, _, _ = self.request("POST", "/api/databases/save", {"lids": self.lids})
        self.assertEqual(status, 400)
        self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)

    def test_second_replace_failure_restores_first_database(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        replace = os.replace
        call_count = 0

        def fail_second(source, target):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise PermissionError("Simulated second database write failure")
            return replace(source, target)

        with patch.object(viewer.os, "replace", side_effect=fail_second):
            status, _, body = self.request(
                "POST", "/api/databases/save", {"boxes": {}, "lids": self.lids}
            )
        self.assertEqual(status, 500, body)
        self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)
        self.assertFalse(list(self.root.glob(".viewer-*.tmp")))

    def test_serialization_failure_does_not_write(self):
        before = (self.box_path.read_bytes(), self.lid_path.read_bytes())
        lids = copy.deepcopy(self.lids)
        lids["LID"]["thickness"] = float("nan")
        status, _, _ = self.request("POST", "/api/databases/save", {"boxes": {}, "lids": lids})
        self.assertEqual(status, 400)
        self.assertEqual((self.box_path.read_bytes(), self.lid_path.read_bytes()), before)
        self.assertFalse(list(self.root.glob(".viewer-*.tmp")))

    def test_rollback_failure_retains_recovery_files_and_reports_them(self):
        original_box_bytes = self.box_path.read_bytes()
        replace = os.replace
        call_count = 0

        def fail_after_first(source, target):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise PermissionError("Simulated replacement and restoration failure")
            return replace(source, target)

        with patch.object(viewer.os, "replace", side_effect=fail_after_first):
            status, _, body = self.request(
                "POST", "/api/databases/save", {"boxes": {}, "lids": self.lids}
            )
        self.assertEqual(status, 500)
        message = json.loads(body)["message"]
        self.assertIn("rollback failed", message)
        recovery_files = list(self.root.glob(".viewer-*.tmp"))
        self.assertTrue(any(path.read_bytes() == original_box_bytes for path in recovery_files))
        self.assertTrue(all(str(path) in message for path in recovery_files))

    def test_main_starts_without_prompt_or_changing_working_directory(self):
        server = unittest.mock.MagicMock()
        server.__enter__.return_value = server
        server.serve_forever.side_effect = KeyboardInterrupt
        with patch.object(viewer.socketserver, "TCPServer", return_value=server), \
                patch.object(viewer.webbrowser, "open", return_value=True) as browser, \
                patch("builtins.input", side_effect=AssertionError("Must not prompt")), \
                patch("builtins.print"):
            original_directory = os.getcwd()
            viewer.main()
            self.assertEqual(os.getcwd(), original_directory)
            browser.assert_called_once_with("http://localhost:8081")


if __name__ == "__main__":
    unittest.main()
