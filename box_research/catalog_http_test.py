import copy
import http.client
import json
import socketserver
import threading
import unittest
from unittest.mock import patch

from box_research.catalog_store import FILES
from box_research.catalog_store_test import CatalogFixture
from box_research import serve_viewer
from test_programmer import serve_testcase_viewer


class CatalogHttpTest(CatalogFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.test_programmer_dir = self.root / "test_programmer"
        self.test_programmer_dir.mkdir()
        patches = (
            patch.object(serve_viewer, "BASE_DIR", str(self.root / "box_research")),
            patch.object(serve_testcase_viewer, "BASE_DIR", str(self.test_programmer_dir)),
            patch.object(serve_testcase_viewer, "PROJECT_ROOT", str(self.root)),
        )
        for patcher in patches:
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

    def read_catalog(self, server_index=0):
        status, _, result = self.request("GET", "/api/catalog", server_index=server_index)
        self.assertEqual(status, 200)
        return result

    def test_new_catalog_assets_and_data_are_available_on_both_servers(self):
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
            data = self.read_catalog(index)
            self.assertEqual(data["cases"]["test_cases"]["case"]["box_list"],
                             [{"part_number": "00001", "count": 10}])
            self.assertIn("PALLET-A", data["pallets"])

    def test_default_and_legacy_ui_urls_open_the_new_editors(self):
        for index, expected in ((0, "/catalog_viewer.html"), (1, "/catalog_cases.html")):
            for path in ("/", "/index.html"):
                status, headers, _ = self.request("GET", path, server_index=index)
                self.assertEqual(status, 302)
                self.assertEqual(headers["Location"], expected)
        for index, old_path, expected in (
            (0, "/box_db_viewer.html", "/catalog_viewer.html"),
            (0, "/lid_db_viewer.html", "/catalog_viewer.html"),
            (1, "/testcase_viewer.html", "/catalog_cases.html"),
        ):
            status, headers, _ = self.request("GET", old_path, server_index=index)
            self.assertEqual(status, 302)
            self.assertEqual(headers["Location"], expected)

    def test_old_apis_are_explicitly_retired(self):
        for index, route in (
            (0, "/api/boxes"), (0, "/api/lids"), (0, "/api/pallets"),
            (1, "/api/testcases"), (1, "/api/testcase/approval_state"),
        ):
            status, _, body = self.request("GET", route, server_index=index)
            self.assertEqual(status, 410)
            self.assertEqual(body["status"], "error")
        for index, route in (
            (0, "/api/save"), (0, "/api/pallets/save_all"),
            (1, "/api/testcase/save_all"),
        ):
            status, _, body = self.request("POST", route, {}, server_index=index)
            self.assertEqual(status, 410)
            self.assertEqual(body["status"], "error")

    def test_case_save_uses_catalog_and_rejects_stale_revisions(self):
        data = self.read_catalog()
        data["cases"]["test_cases"]["case"]["box_list"][0]["count"] = 7
        payload = {"revision": data["revision"], "cases": data["cases"]}
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 200)
        saved = self.read_catalog()
        self.assertEqual(saved["cases"]["test_cases"]["case"]["box_list"][0]["count"], 7)
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 400)

    def test_skid_preview_confirmation_history_and_db_only_update(self):
        data = self.read_catalog()
        skids = copy.deepcopy(data["skids"])
        skids["0001AA"]["pallet"]["max_height"] = 826
        payload = {"revision": data["revision"], "skids": skids}
        before = self.snapshot()
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 400)
        self.assertEqual(self.snapshot(), before)
        status, _, plan = self.request("POST", "/api/catalog/skid-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["changes"][0]["affected_cases"], ["case"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 200)
        saved = self.read_catalog()
        self.assertEqual(saved["skids"]["0001AA"]["pallet"]["max_height"], 826)
        self.assertEqual(len(saved["skids"]["0001AA"]["history"]), 2)
        self.assertNotIn("pallet", saved["cases"]["test_cases"]["case"])
        cases_path = self.catalog_dir.relative_to(self.root) / "test_cases.json"
        self.assertEqual(before[cases_path], self.snapshot()[cases_path])
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 400)

    def test_invalid_saves_are_rejected_without_writing(self):
        data = self.read_catalog()
        before = self.snapshot()
        for key, update in (
            ("parts", lambda records: records["00001"].update(lid_id="UNKNOWN")),
            ("cases", lambda bundle: bundle["test_cases"]["case"]["box_list"][0].update(count=501)),
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

    def test_confirmed_skid_id_change_updates_references_on_server(self):
        data = self.read_catalog()
        skids = copy.deepcopy(data["skids"])
        skid = skids.pop("0001AA")
        skid["id"] = "0001A030J"
        skids[skid["id"]] = skid
        payload = dict(revision=data["revision"], skids=skids,
                       skid_renames={"0001AA": "0001A030J"})
        status, _, plan = self.request("POST", "/api/catalog/skid-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["changes"][0]["old_skid_id"], "0001AA")
        self.assertEqual(plan["changes"][0]["affected_cases"], ["case"])
        before = self.snapshot()
        self.assertEqual(self.request("POST", "/api/catalog/save", payload)[0], 400)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 200)
        saved = self.read_catalog(1)
        self.assertEqual(saved["cases"]["test_cases"]["case"]["skid_id"], "0001A030J")
        self.assertEqual(saved["skids"]["0001A030J"]["history"][-1]["previous_id"], "0001AA")
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 400)

    def test_supplier_mapping_creation_correction_and_used_deletion(self):
        data = self.read_catalog()
        mapping = copy.deepcopy(data["suppliers"])
        mapping["0002"] = dict(id="0002", supplier_name="Supplier B")
        payload = dict(revision=data["revision"], suppliers=mapping)
        status, _, plan = self.request("POST", "/api/catalog/skid-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["supplier_changes"][0]["affected_suppliers"], ["0002"])
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 200)
        data = self.read_catalog()
        data["suppliers"]["0001"]["supplier_name"] = "Corrected A"
        payload = dict(revision=data["revision"], suppliers=data["suppliers"])
        status, _, plan = self.request("POST", "/api/catalog/skid-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["supplier_changes"][0]["affected_cases"], ["case"])
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            **payload, "confirmation": plan["confirmation"],
        })[0], 200)
        data = self.read_catalog()
        self.assertEqual(data["parts"]["00001"]["supplier_name"], "Corrected A")
        self.assertEqual(data["skids"]["0001AA"]["supplier_name"], "Corrected A")
        self.assertEqual(data["cases"]["test_cases"]["case"]["supplier_name"], "Corrected A")
        del data["suppliers"]["0001"]
        before = self.snapshot()
        self.assertEqual(self.request("POST", "/api/catalog/skid-preview", {
            "revision": data["revision"], "suppliers": data["suppliers"],
        })[0], 400)
        self.assertEqual(self.snapshot(), before)

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
        payload = {"old_name": "MODEL-A", "new_name": "MODEL-B"}
        before = self.snapshot()
        status, _, plan = self.request("POST", "/api/catalog/rename-preview", payload)
        self.assertEqual(status, 200)
        self.assertEqual(plan["affected_cases"], ["case.json"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request("POST", "/api/catalog/rename", {
            **payload, "confirmation": "invalid"})[0], 400)
        self.assertEqual(self.request("POST", "/api/catalog/rename", {
            **payload, "confirmation": plan["confirmation"]})[0], 200)
        self.assertEqual(self.read_catalog()["parts"]["00001"]["box_model_id"], "MODEL-B")

    def test_regular_api_rejects_coordinated_rename_and_bypass_fields(self):
        data = self.read_catalog()
        before = self.snapshot()
        models, parts = copy.deepcopy(data["models"]), copy.deepcopy(data["parts"])
        model = models.pop("MODEL-A")
        model["id"] = "MODEL-B"
        models["MODEL-B"] = model
        parts["00001"]["box_model_id"] = "MODEL-B"
        payload = {"revision": data["revision"], "models": models, "parts": parts}
        status, _, body = self.request("POST", "/api/catalog/save", payload)
        self.assertEqual(status, 400)
        self.assertIn("名前変更", body["message"])
        self.assertEqual(self.snapshot(), before)
        for field in ("rename", "confirmation", "migration"):
            status, _, _ = self.request("POST", "/api/catalog/save", {**payload, field: {}})
            self.assertEqual(status, 400)
        self.assertEqual(self.snapshot(), before)

    def test_api_rejects_reversed_pallet_dimensions_without_writing(self):
        data = self.read_catalog()
        pallets = copy.deepcopy(data["pallets"])
        pallets["PALLET-A"].update(length=900, width=1000)
        before = self.snapshot()
        status, _, body = self.request("POST", "/api/catalog/save", {
            "revision": data["revision"], "pallets": pallets,
        })
        self.assertEqual(status, 400)
        self.assertIn("length L", body["message"])
        self.assertEqual(self.snapshot(), before)

    def test_pallet_crud_persists_to_existing_database(self):
        data = self.read_catalog()
        pallets = copy.deepcopy(data["pallets"])
        pallets["PALLET-B"] = {
            "id": "PALLET-B", "model": "Pallet B", "length": 1100,
            "width": 900, "height": 125, "suppliers": ["Supplier A"],
        }
        status, _, _ = self.request("POST", "/api/catalog/save", {
            "revision": data["revision"], "pallets": pallets,
        })
        self.assertEqual(status, 200)
        on_disk = json.loads(self.pallet_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["pallets"]["PALLET-B"]["length"], 1100)

        updated = self.read_catalog()
        pallets = copy.deepcopy(updated["pallets"])
        pallets["PALLET-B"]["height"] = 140
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            "revision": updated["revision"], "pallets": pallets,
        })[0], 200)
        updated = self.read_catalog()
        pallets = copy.deepcopy(updated["pallets"])
        del pallets["PALLET-B"]
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            "revision": updated["revision"], "pallets": pallets,
        })[0], 200)
        self.assertNotIn("PALLET-B", json.loads(
            self.pallet_path.read_text(encoding="utf-8"))["pallets"])

    def test_pallet_deletion_and_supplier_changes_respect_case_references(self):
        data = self.read_catalog()
        skids = copy.deepcopy(data["skids"])
        skids["0001AA"]["pallet_id"] = "PALLET-A"
        status, _, plan = self.request("POST", "/api/catalog/skid-preview", {
            "revision": data["revision"], "skids": skids,
        })
        self.assertEqual(status, 200)
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            "revision": data["revision"], "skids": skids, "confirmation": plan["confirmation"],
        })[0], 200)
        referenced = self.read_catalog()
        pallets = copy.deepcopy(referenced["pallets"])
        del pallets["PALLET-A"]
        before = self.pallet_path.read_bytes()
        status, _, body = self.request("POST", "/api/catalog/save", {
            "revision": referenced["revision"], "pallets": pallets,
        })
        self.assertEqual(status, 400)
        self.assertIn("パレット", body["message"])
        self.assertEqual(self.pallet_path.read_bytes(), before)

        pallets = copy.deepcopy(referenced["pallets"])
        pallets["PALLET-A"]["suppliers"] = ["Other supplier"]
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            "revision": referenced["revision"], "pallets": pallets,
        })[0], 400)

    def test_stale_catalog_revision_rejects_pallet_edit_from_other_server(self):
        first = self.read_catalog(0)
        second = self.read_catalog(1)
        pallets = copy.deepcopy(first["pallets"])
        pallets["PALLET-A"]["height"] += 1
        self.assertEqual(self.request("POST", "/api/catalog/save", {
            "revision": first["revision"], "pallets": pallets,
        }, server_index=0)[0], 200)
        stale = copy.deepcopy(second["pallets"])
        stale["PALLET-A"]["height"] += 2
        status, _, body = self.request("POST", "/api/catalog/save", {
            "revision": second["revision"], "pallets": stale,
        }, server_index=1)
        self.assertEqual(status, 400)
        self.assertIn("別の画面", body["message"])

    def test_storage_and_read_errors_are_explicit(self):
        data = self.read_catalog()
        with patch("box_research.catalog_http.save_catalog", side_effect=OSError("disk failure")):
            status, _, body = self.request("POST", "/api/catalog/save",
                                           {"revision": data["revision"], "parts": data["parts"]})
            self.assertEqual(status, 500)
            self.assertIn("disk failure", body["message"])
        path = self.catalog_dir / FILES["parts"]
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


if __name__ == "__main__":
    unittest.main()
