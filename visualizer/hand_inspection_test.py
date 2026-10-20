import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from algorithm_programmer.hand_collision_test import fixture, profile
from visualizer import serve_3d_viewer


UI_TEST = """<!doctype html><meta charset="utf-8"><pre id="result">RUNNING</pre>
<iframe src="/" id="viewer"></iframe><script>
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function assert(test, message) { if (!test) throw new Error(message); }
async function waitFor(test) {
  for (let n=0; n<200; n++) { if (test()) return; await sleep(50); }
  throw new Error("UI wait timed out");
}
document.getElementById("viewer").onload = async function() {
  const w=this.contentWindow, d=w.document, $=id=>d.getElementById(id);
  const change = (id, value) => {
    $(id).value=value; $(id).dispatchEvent(new w.Event("change"));
  };
  try {
    await waitFor(() => $("hand-order").options.length === 2 && $("hand-profile").options.length === 1);
    $("hand-check").closest("details").open = true;
    change("hand-order", "2");
    $("hand-check").click();
    await waitFor(() => $("hand-status").textContent.includes("配置位置で干渉あり"));
    assert($("hand-collisions").textContent.includes("先行箱 #1"), "collision partner");
    assert($("step-current").textContent === "2", "placement time step");
    assert(w.eval("handResult.envelope.length") === 4, "hand geometry rendered");
    change("hand-corner", "X_MAX_Y_MAX");
    assert(w.eval("handResult") === null, "stale overlay cleared");
    $("hand-check").click();
    await waitFor(() => $("hand-status").textContent.includes("配置位置で干渉なし"));
    assert($("hand-collisions").children.length === 0, "clear partner list");
    assert($("hand-status").textContent.includes("180°"), "selected hand yaw");
    assert($("hand-status").textContent.includes("経路は未判定"), "static scope");
    for (const view of ["top","front","side","iso"]) {
      d.querySelector(`[data-view="${view}"]`).click();
      await sleep(60);
      assert(w.eval("viewMode") === view, "view preset: "+view);
    }
    const previousZoom = w.eval("zoom");
    $("btn-zoom-in").click();
    assert(w.eval("zoom") > previousZoom, "zoom in");
    $("btn-zoom-out").click();
    assert(w.eval("zoom") < previousZoom * 1.2, "zoom out");
    $("btn-view-reset").click();
    for (const [id, variable] of [["toggle-guides", "showGuides"], ["toggle-labels", "showLabels"]]) {
      $(id).click();
      assert(w.eval(variable) === $(id).checked, "view toggle: "+id);
      $(id).click();
    }
    $("btn-play-prev").click();
    assert(w.eval("handResult") === null, "timeline invalidates result");
    change("hand-order", "1");
    $("hand-check").click();
    await waitFor(() => $("hand-status").textContent.includes("先行箱 0箱"));
    assert($("step-current").textContent === "1", "later box hidden");
    $("hand-clear").click();
    assert(w.eval("handResult") === null, "clear overlay");
    change("hand-order", "2");
    change("hand-corner", "INVALID");
    $("hand-check").click();
    await waitFor(() => $("hand-status").textContent.includes("判定できません"));
    assert(w.eval("handResult") === null, "failed check not shown as clear");
    assert(w.__errors.length === 0, w.__errors.join("\\n"));
    d.getElementById("hand-clear").click();
    $("hand-reload").click();
    await waitFor(() => !$("hand-reload").disabled);
    for (const id of ["hand-select", "hand-sequence", "hand-sequence-mode", "hand-selections", "hand-candidates"]) {
      assert($(id) === null, "obsolete control removed: "+id);
    }
    assert($("hand-result-summary").textContent.includes("旧結果"), "legacy result distinguished");
    const originalFetch = w.fetch.bind(w);
    w.fetch = async (...args) => {
      const response = await originalFetch(...args);
      if (args[0] === "/api/hand_check") await sleep(250);
      return response;
    };
    change("hand-corner", "X_MAX_Y_MAX");
    $("hand-check").click();
    change("hand-profile", $("hand-profile").value);
    await sleep(500);
    assert(w.eval("handResult") === null, "late manual check discarded after equipment change");
    w.fetch = originalFetch;
    w.fetch = async (...args) => {
      const response = await originalFetch(...args);
      if (String(args[0]).startsWith("/api/result/")) {
        const data = await response.json();
        data.hand_sequence = {reverse_verified: true, trajectory_checked: false,
          profile: {id: "saved-equipment", name: "Saved equipment snapshot"}};
        data.boxes[0].hand_grasp = {corner_id: "X_MAX_Y_MAX",
          reference_position: [200, 100, 100], hand_yaw_deg: 180, static_verified: true,
          clearance: 2, envelope: [{name: "test-body", min: [180, 80, 80], max: [220, 120, 110]}]};
        return new w.Response(JSON.stringify(data), {status: 200,
          headers: {"Content-Type": "application/json"}});
      }
      return response;
    };
    await w.eval("loadResultFile(loadedFilename)");
    assert($("hand-result-summary").textContent.includes("正式な配置順"), "saved official order recognized");
    assert($("hand-result-summary").textContent.includes("saved-equipment"), "saved equipment identified");
    w.eval("inspectBox(currentData.boxes[0])");
    assert($("inspector-content").textContent.includes("保存済み把持角：X_MAX_Y_MAX"), "saved grasp displayed");
    assert($("inspector-content").textContent.includes("200, 100, 100"), "saved grasp coordinates displayed");
    w.eval("selectedBoxOrder = currentData.boxes[0].order");
    assert(w.eval("savedGraspBox().hand_grasp.corner_id") === "X_MAX_Y_MAX", "saved marker selected");
    assert(w.eval("savedGraspBox().hand_grasp.envelope.length") === 1, "saved 3D hand geometry available");
    w.eval("setStep(1)");
    assert($("hand-status").textContent.includes("保存済み把持角"), "saved marker step status");
    assert(w.eval("savedGraspBox().order") === 1, "step chooses saved grasp box");
    w.eval("drawHandCheck()");
    assert(w.__errors.length === 0, "saved 3D hand rendered without errors");
    w.eval("setStep(0)");
    assert(w.eval("savedGraspBox()") === null, "empty step has no saved marker");
    w.eval("drawHandCheck()");
    d.querySelector('[data-speed="150"]').click();
    assert(w.eval("playSpeed") === 150, "play speed");
    $("btn-play-toggle").click();
    await waitFor(() => $("step-current").textContent === "2");
    await waitFor(() => w.eval("isPlaying") === false);
    $("btn-play-reset").click();
    assert($("step-current").textContent === "0", "timeline reset");
    $("step-slider").value = "1";
    $("step-slider").dispatchEvent(new w.Event("input"));
    assert(w.eval("savedGraspBox().order") === 1, "slider keeps saved grasp display");
    w.fetch = originalFetch;
    assert(w.__errors.length === 0, w.__errors.join("\\n"));
    document.getElementById("result").textContent="UI_PASS";
  } catch(error) {
    document.getElementById("result").textContent="UI_FAIL: "+error.stack;
  }
};
</script>"""


class TestHandler(serve_3d_viewer.ViewerHandler):
    def do_GET(self):
        if self.path in ("/", "/__ui_test"):
            if self.path == "/__ui_test":
                text = UI_TEST
            else:
                text = (Path(serve_3d_viewer.BASE_DIR) / "index.html").read_text(encoding="utf-8")
                # Browser tests do not access third-party CDNs.
                text = re.sub(r'<script src="[^"]+"></script>', "", text)
                text = text.replace("<head>", """<head><script>
                  window.lucide={createIcons(){}};
                  window.__errors=[];
                  window.addEventListener("error",e=>window.__errors.push(e.message));
                  </script>""", 1)
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format, *args):
        pass


class HandInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.result_path = root / "result_fixture.json"
        data = fixture()
        for entry in data["boxes"]:
            entry.update(lid_id="無蓋", lid_fit_type="なし", lid_thickness=0,
                         lid_dimensions={"width": 0, "length": 0})
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        self.profile_path = root / "profiles.txt"
        self.profile_path.write_text(json.dumps({"schema_version": 1, "profiles": [profile()]}),
                                     encoding="utf-8")
        self.result_before = self.result_path.read_bytes()
        self.patches = [
            patch.object(serve_3d_viewer, "RESULTS_DIR", str(root)),
            patch.object(serve_3d_viewer, "HAND_PROFILES_PATH", str(self.profile_path)),
        ]
        for item in self.patches:
            item.start()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def request(self, path, data=None):
        request = urllib.request.Request(self.url + path)
        if data is not None:
            request.data = json.dumps(data).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def payload(self, **changes):
        return dict(filename="result_fixture.json", profile_id="sample-l-hand",
                    order=2, corner="X_MIN_Y_MIN", **changes)

    def test_static_check_api_is_read_only(self):
        status, body = self.request("/api/hand_check", self.payload())
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertTrue(result["has_interference"])
        self.assertEqual(result["checked_orders"], [1])
        self.assertFalse(result["order_changed"])
        self.assertFalse(result["trajectory_checked"])
        self.assertEqual(self.result_path.read_bytes(), self.result_before)
        self.assertEqual(self.request("/api/hand_profiles")[0], 200)
        self.assertEqual(self.request("/api/result/result_fixture.json")[0], 200)
        self.assertEqual(len(json.loads(self.request("/api/results")[1])), 1)

    def test_corner_selection_api_is_read_only_and_returns_four_candidates(self):
        before_profile = self.profile_path.read_bytes()
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_select", request)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["summary"]["selected"], 2)
        self.assertEqual([len(b["candidates"]) for b in result["boxes"]], [4, 4])
        self.assertFalse(result["trajectory_checked"])
        self.assertFalse(result["order_changed"])
        self.assertEqual(self.result_path.read_bytes(), self.result_before)
        self.assertEqual(self.profile_path.read_bytes(), before_profile)
        self.assertEqual(json.loads(self.request("/api/hand_select", request)[1]), result)

    def test_reverse_sequence_api_preserves_sources_and_verifies_loading(self):
        before = self.profile_path.read_bytes()
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_sequence", request)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["status"], "complete")
        self.assertEqual([entry["original_order"] for entry in result["depalletizing"]], [2, 1])
        self.assertEqual([entry["original_order"] for entry in result["palletizing"]], [1, 2])
        self.assertTrue(result["reverse_verified"])
        self.assertEqual(self.result_path.read_bytes(), self.result_before)
        self.assertEqual(self.profile_path.read_bytes(), before)

    def test_reverse_sequence_stall_does_not_return_partial_loading_plan(self):
        from algorithm_programmer.hand_collision_test import box

        data = fixture()
        data["boxes"].append(box(3, 500, 500, width=20, length=20))
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_sequence", request)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(result["palletizing"], [])
        self.assertFalse(result["reverse_verified"])
        self.assertEqual(result["remaining"][0]["status"], "out_of_range")

    def test_reverse_sequence_rejects_inconsistent_supports(self):
        data = fixture()
        data["boxes"][0]["supported_by"] = [2]
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_sequence", request)
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_reverse_sequence_api_enforces_layer_boundary(self):
        from algorithm_programmer.hand_collision_test import box

        data = fixture()
        data["boxes"] = [box(1, 100, 100), box(2, 500, 500), box(3, 100, 100, top=200)]
        data["boxes"][2]["layer_index"] = 1
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        status, body = self.request("/api/hand_sequence",
                                    {"filename": "result_fixture.json", "profile_id": "sample-l-hand"})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual([entry["original_order"] for entry in result["depalletizing"]], [3, 2, 1])
        self.assertEqual([entry["layer_index"] for entry in result["palletizing"]], [0, 0, 1])
        self.assertTrue(result["reverse_verified"])

    def test_reverse_sequence_api_rejects_missing_layer(self):
        data = fixture()
        del data["boxes"][0]["layer_index"]
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        status, body = self.request("/api/hand_sequence",
                                    {"filename": "result_fixture.json", "profile_id": "sample-l-hand"})
        self.assertEqual(status, 400)
        self.assertIn("layer_index", json.loads(body)["error"])

    def test_corner_selection_input_error_is_not_partial_success(self):
        data = fixture()
        data["boxes"][1]["rotation"] = 45
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_select", request)
        self.assertEqual(status, 400)
        result = json.loads(body)
        self.assertIn("error", result)
        self.assertNotIn("summary", result)

    def test_corner_selection_reports_unsupported_boxes_without_skipping_them(self):
        from algorithm_programmer.hand_collision_test import box

        data = fixture()
        data["boxes"].append(box(3, 500, 500, width=20, length=20))
        self.result_path.write_text(json.dumps(data), encoding="utf-8")
        request = {"filename": "result_fixture.json", "profile_id": "sample-l-hand"}
        status, body = self.request("/api/hand_select", request)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["summary"], {
            "total": 3, "selected": 2, "blocked": 0, "out_of_range": 1,
        })
        self.assertIsNone(result["boxes"][2]["selected"])
        self.assertFalse(result["all_corners_selected"])

    def test_invalid_conditions_return_errors_not_clear_results(self):
        for key, value in (("filename", "..\\result_fixture.json"),
                           ("filename", "../result_fixture.json"),
                           ("profile_id", "missing"), ("order", True),
                           ("order", 999), ("corner", "missing")):
            request = self.payload()
            request[key] = value
            status, body = self.request("/api/hand_check", request)
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(body))
        self.assertEqual(self.result_path.read_bytes(), self.result_before)

    def test_missing_file_and_malformed_result(self):
        request = self.payload()
        request["filename"] = "missing.json"
        self.assertEqual(self.request("/api/hand_check", request)[0], 404)
        self.result_path.write_text('{"boxes": []}', encoding="utf-8")
        self.assertEqual(self.request("/api/hand_check", self.payload())[0], 400)

    @unittest.skipUnless(os.environ.get("HAND_VIEWER_BROWSER_TEST") == "1",
                         "Set HAND_VIEWER_BROWSER_TEST=1 for installed Edge")
    def test_browser_static_inspection(self):
        edge = Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        self.assertTrue(edge.is_file())
        process = subprocess.run([
            str(edge), "--headless", "--disable-gpu", "--no-first-run",
            "--disable-background-networking", "--no-default-browser-check",
            "--user-data-dir=" + str(Path(self.temporary.name) / "edge"),
            "--dump-dom", "--virtual-time-budget=25000", self.url + "/__ui_test",
        ], capture_output=True, timeout=90)
        output = process.stdout.decode("utf-8", errors="replace")
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertIn('<pre id="result">UI_PASS</pre>', output, output[-7000:])
        self.assertEqual(self.result_path.read_bytes(), self.result_before)


if __name__ == "__main__":
    unittest.main()
