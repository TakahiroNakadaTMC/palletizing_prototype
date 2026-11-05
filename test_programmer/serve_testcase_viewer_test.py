import http.client
import json
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch

from box_research.serve_viewer import STANDARD_PALLET, STANDARD_PALLET_ID
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
        for name, value in {
            "BASE_DIR": str(self.root),
            "PROJECT_ROOT": str(self.root),
            "PALLET_DB_PATH": str(self.pallet_db),
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


if __name__ == "__main__":
    unittest.main()
