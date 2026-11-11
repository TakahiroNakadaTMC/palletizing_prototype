import copy
import http.client
import json
import socketserver
import threading
import unittest
from unittest.mock import patch

from box_research.catalog_store import prepare_cases
from box_research.catalog_store_test import CatalogFixture
from box_research import serve_viewer
from test_programmer import serve_testcase_viewer


class CatalogHttpTest(CatalogFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        prepare_cases(self.root)
        for name, value in {
            "BASE_DIR": str(self.db),
            "BOX_DB_PATH": str(self.db / "box_db.json"),
            "LID_DB_PATH": str(self.db / "lid_db.json"),
            "PALLET_DB_PATH": str(self.db / "pallet_db.json"),
            "TEST_CASES_DIR": str(self.root / "test_programmer" / "test_cases"),
        }.items():
            patcher = patch.object(serve_viewer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(serve_testcase_viewer, "PROJECT_ROOT", str(self.root))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.servers = []
        for handler in (serve_viewer.ViewerRequestHandler, serve_testcase_viewer.TestCaseViewerHandler):
            server = socketserver.TCPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.servers.append((server, thread))
        self.addCleanup(self.stop_servers)

    def stop_servers(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def request(self, method, path, payload=None, server_index=0):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.servers[server_index][0].server_address[1], timeout=10)
        try:
            connection.request(method, path, None if payload is None else json.dumps(payload),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            body = response.read()
            if response.getheader("Content-Type", "").startswith("application/json"):
                body = json.loads(body)
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    def read_catalog(self):
        status, _, result = self.request("GET", "/api/catalog")
        self.assertEqual(status, 200)
        return result

    def test_assets_and_catalog_available_on_both_servers(self):
        for index in (0, 1):
            for path, text in (
                ("/catalog_viewer.html", b'lang="ja"'),
                ("/catalog_cases.html", b'id="line-list"'),
                ("/catalog_viewer.js", b'/api/catalog'),
                ("/catalog_viewer.css", b'dialog'),
            ):
                status, headers, body = self.request("GET", path, server_index=index)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertIn(text, body)
            status, _, data = self.request("GET", "/api/catalog", server_index=index)
            self.assertEqual(status, 200)
            self.assertEqual(data["cases"]["test_cases"]["case"]["box_list"],
                             [{"part_number": "00001", "count": 10}])

    def test_case_save_preserves_legacy_and_reports_stale_revisions(self):
        data = self.read_catalog()
        before = {path: path.read_bytes() for path in
                  (self.root / "test_programmer").rglob("*.json")}
        data["cases"]["test_cases"]["case"]["box_list"][0]["count"] = 7
        payload = {"revision": data["revision"], "cases": data["cases"]}
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 200)
        saved = self.read_catalog()
        self.assertEqual(saved["cases"]["test_cases"]["case"]["box_list"][0]["count"], 7)
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 400)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_invalid_saves_are_rejected_without_writing(self):
        data = self.read_catalog()
        before = self.snapshot()
        for key, update in (
            ("parts", lambda records: records["00001"].update(lid_id="UNKNOWN")),
            ("cases", lambda bundle: bundle["test_cases"]["case"]["box_list"][0].update(lid_id="無蓋")),
            ("cases", lambda bundle: bundle["test_cases"]["case"]["box_list"][0].update(lid_id="サンボックス#22Bフタ")),
            ("cases", lambda bundle: bundle["test_cases"]["case"].update(supplier_name="別会社")),
            ("cases", lambda bundle: bundle["approval_state"].clear()),
        ):
            draft = copy.deepcopy(data[key])
            update(draft)
            status, _, body = self.request("POST", "/api/catalog/save",
                                           {"revision": data["revision"], key: draft})
            self.assertEqual(status, 400)
            self.assertEqual(body["status"], "error")
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request("POST", "/api/catalog/save",
                                     {"revision": data["revision"], "migration": {}})[0], 400)

    def test_catalog_crud_and_normalization(self):
        data = self.read_catalog()
        data["parts"]["００００２"] = dict(data["parts"]["00001"], id="００００２")
        self.assertEqual(self.request("POST", "/api/catalog/save",
                                     {"revision": data["revision"], "parts": data["parts"]})[0], 200)
        saved = self.read_catalog()
        self.assertIn("00002", saved["parts"])
        self.assertNotIn("００００２", saved["parts"])
        saved["parts"]["00002"]["box_name"] = "別の箱名称"
        self.assertEqual(self.request("POST", "/api/catalog/save",
                                     {"revision": saved["revision"], "parts": saved["parts"]})[0], 200)
        saved = self.read_catalog()
        del saved["parts"]["00002"]
        self.assertEqual(self.request("POST", "/api/catalog/save",
                                     {"revision": saved["revision"], "parts": saved["parts"]})[0], 200)

    def test_model_rename_requires_confirmed_plan(self):
        payload = {"old_name": "サンボックス#22H", "new_name": "変更後"}
        before = self.snapshot()
        status, _, plan = self.request("POST", "/api/catalog/rename-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["affected_cases"], ["case.json"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request("POST", "/api/catalog/rename", {
            **payload, "confirmation": "invalid"})[0], 400)
        self.assertEqual(self.request("POST", "/api/catalog/rename", {
            **payload, "confirmation": plan["confirmation"]})[0], 200)
        self.assertEqual(self.read_catalog()["parts"]["00001"]["box_model_id"], "変更後")

    def test_deleting_used_part_or_lid_is_rejected(self):
        data = self.read_catalog()
        for key, identifier in (("parts", "00001"), ("lids", "サンボックス#22Bフタ")):
            draft = copy.deepcopy(data[key])
            del draft[identifier]
            self.assertEqual(self.request("POST", "/api/catalog/save",
                                         {"revision": data["revision"], key: draft})[0], 400)

    def test_storage_and_read_errors_are_explicit(self):
        data = self.read_catalog()
        with patch("box_research.catalog_http.save_catalog", side_effect=OSError("disk failure")):
            status, _, body = self.request("POST", "/api/catalog/save",
                                           {"revision": data["revision"], "parts": data["parts"]})
            self.assertEqual(status, 500)
            self.assertIn("disk failure", body["message"])
        path = self.db / "catalog" / "box_type_db.json"
        path.write_text("{", encoding="utf-8")
        status, _, body = self.request("GET", "/api/catalog")
        self.assertEqual(status, 400)
        self.assertEqual(body["status"], "error")

    def test_duplicate_request_keys_are_rejected(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.servers[0][0].server_address[1], timeout=10)
        try:
            connection.request("POST", "/api/catalog/save",
                               '{"revision":"one","revision":"two","parts":{}}',
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 400)
            self.assertIn("重複", body["message"])
        finally:
            connection.close()

    def test_legacy_pallet_save_protects_staged_case_references(self):
        path = self.db / "pallet_db.json"
        pallets = json.loads(path.read_text(encoding="utf-8"))
        pallets["pallets"]["NEW"] = {
            "id": "NEW", "model": "NEW", "length": 1200, "width": 1000,
            "height": 130, "suppliers": ["オティックス"],
        }
        self.write_json(path, pallets)
        data = self.read_catalog()
        data["cases"]["test_cases"]["case"]["pallet_id"] = "NEW"
        self.assertEqual(self.request("POST", "/api/catalog/save",
                                     {"revision": data["revision"], "cases": data["cases"]})[0], 200)
        del pallets["pallets"]["NEW"]
        before = path.read_bytes()
        status, _, body = self.request("POST", "/api/pallets/save_all", pallets)
        self.assertEqual(status, 400)
        self.assertIn("パレット", body["message"])
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
