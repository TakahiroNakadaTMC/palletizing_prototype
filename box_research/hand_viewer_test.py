import copy
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from algorithm_programmer.hand_profile import sample_profile
from box_research import serve_viewer


UI_TEST = """<!doctype html><meta charset="utf-8"><pre id="result">RUNNING</pre>
<iframe src="/hand_viewer.html" id="viewer"></iframe><script>
const result = document.getElementById("result");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(test) {
  for (let n=0; n<150; n++) { if (test()) return; await sleep(50); }
  throw new Error("UI wait timed out");
}
function assert(test, message) { if (!test) throw new Error(message); }
document.getElementById("viewer").onload = async function() {
  const w = this.contentWindow, d = w.document, $ = id => d.getElementById(id);
  const change = (id, value, event="change") => {
    $(id).value = value; $(id).dispatchEvent(new w.Event(event));
  };
  const ready = () => $("preview").querySelectorAll("polygon").length > 0;
  try {
    await waitFor(ready);
    const settings = () => [...d.querySelectorAll('input[id^="p_"]')]
      .map(input => [input.id, input.value]);
    const before = JSON.stringify(settings());
    assert(!$("stage") && !$("motionFields") && !$("state"), "no motion configuration");
    assert(!d.querySelector('[id^="p_approach"]'), "no approach fields");
    assert(!$("p_u_release") && !$("p_v_release"), "no claw opening settings");
    assert($("dirty").textContent === "保存済み", "initial settings saved");
    assert($("details").textContent.includes("ハンド向き：0°"), "initial yaw");
    change("box", "TP-341");
    await waitFor(ready);
    assert($("details").textContent.includes("503"), "503mm box");
    assert($("lid").options.length > 1, "compatible lids");
    change("lid", "サンボックス340フタ");
    await waitFor(ready);
    assert($("details").textContent.includes("512"), "combined lid extent");
    change("rotation", "90");
    await waitFor(ready);
    change("corner", "X_MAX_Y_MAX");
    await waitFor(ready);
    assert($("details").textContent.includes("ハンド向き：270°"), "corner and rotation");
    for (const view of ["top", "xz", "yz", "iso"]) {
      change("view", view); assert(ready(), "view " + view);
      assert(!$("preview").innerHTML.match(/NaN|Infinity/), "finite SVG coordinates");
    }
    assert(JSON.stringify(settings()) === before, "preview does not change equipment settings");
    assert($("dirty").textContent === "保存済み", "preview is not a saved setting");
    assert($("details").textContent.includes("設備設定には保存されません"), "preview scope explicit");
    change("p_u_end_distance", "1", "input");
    await waitFor(() => $("status").classList.contains("error"));
    assert(!ready(), "invalid shape cleared");
    change("p_u_end_distance", "50", "input");
    await waitFor(ready);
    $("copy").click();
    await waitFor(ready);
    assert($("profiles").options.length === 2, "duplicate");
    change("profileName", "UI test saved", "input");
    await waitFor(ready);
    $("save").click();
    await waitFor(() => $("dirty").textContent === "保存済み" && !$("save").disabled);
    $("reload").click();
    await waitFor(() => $("profiles").options.length === 2 && ready());
    change("profiles", "1");
    await waitFor(ready);
    assert($("profileName").value === "UI test saved", "save/reload persistence");
    const saved = await (await w.fetch("/api/hand_profiles")).json();
    const profile = saved.profiles[1];
    assert(Object.keys(profile).sort().join(",") === "id,name,parameters", "equipment-only schema");
    assert(!Object.keys(profile.parameters).some(key =>
      /^(approach|retreat|lift|transfer)/.test(key) || key.endsWith("_release")),
      "no saved motion or claw opening settings");
    assert(JSON.stringify(profile.parameters) === JSON.stringify(saved.profiles[0].parameters),
      "common geometry independent of preview box");
    result.textContent = "UI_PASS";
  } catch (error) { result.textContent = "UI_FAIL: " + error.stack; }
};
</script>"""


class TestHandler(serve_viewer.ViewerRequestHandler):
    def do_GET(self):
        if self.path == "/__ui_test":
            body = UI_TEST.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format, *args):
        pass


class HandViewerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "profiles.json"
        self.store = {"schema_version": 1, "profiles": [sample_profile()]}
        self.path.write_text(json.dumps(self.store), encoding="utf-8")
        self.profile_patch = patch.object(serve_viewer, "HAND_PROFILES_PATH", str(self.path))
        self.profile_patch.start()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.profile_patch.stop()
        self.temporary.cleanup()

    def request(self, path, data=None, origin=None):
        request = urllib.request.Request(self.url + path)
        if data is not None:
            request.data = json.dumps(data).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        if origin:
            request.add_header("Origin", origin)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def test_existing_routes_and_new_page(self):
        for path in ("/", "/box_db_viewer.html", "/lid_db_viewer.html",
                     "/hand_viewer.html", "/api/boxes", "/api/lids"):
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
        with patch.object(serve_viewer, "VIEWER_MODE", "hand"):
            self.assertIn("第1段階".encode("utf-8"), self.request("/")[1])

    def test_save_reload_and_invalid_save_preserves_file(self):
        changed = copy.deepcopy(self.store)
        changed["profiles"][0]["name"] = "設備1"
        self.assertEqual(self.request("/api/hand_profiles/save", changed)[0], 200)
        self.assertEqual(json.loads(self.request("/api/hand_profiles")[1]), changed)
        before = self.path.read_bytes()
        changed["profiles"][0]["parameters"]["finger_depth"] = -1
        self.assertEqual(self.request("/api/hand_profiles/save", changed)[0], 400)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(Path(self.temporary.name).glob("*.tmp")), [])

    def test_preview_combined_lid_and_rotation(self):
        data = {
            "profile": sample_profile(), "box_id": "TP-341",
            "lid_id": "サンボックス340フタ", "rotation": 90, "corner": "X_MAX_Y_MAX",
        }
        status, body = self.request("/api/hand_preview", data)
        self.assertEqual(status, 200)
        preview = json.loads(body)
        self.assertEqual(preview["box_size"][:2], [512, 345])
        self.assertEqual(preview["hand_yaw_deg"], 270)
        self.assertFalse(preview["feasibility_checked"])
        data["lid_id"] = "nonexistent"
        self.assertEqual(self.request("/api/hand_preview", data)[0], 400)
        data["box_id"] = []
        self.assertEqual(self.request("/api/hand_preview", data)[0], 400)

    def test_failed_read_is_not_a_successful_empty_store(self):
        self.path.write_text("broken JSON", encoding="utf-8")
        status, body = self.request("/api/hand_profiles")
        self.assertEqual(status, 500)
        self.assertIn("error", json.loads(body))

    def test_cross_origin_save_is_rejected(self):
        self.assertEqual(self.request("/api/hand_profiles/save", self.store,
                                      "http://other.invalid")[0], 403)

    @unittest.skipUnless(os.environ.get("HAND_VIEWER_BROWSER_TEST") == "1",
                         "Set HAND_VIEWER_BROWSER_TEST=1 to run installed Edge headless")
    def test_settings_in_real_browser(self):
        edge = Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        self.assertTrue(edge.is_file(), "Installed Microsoft Edge is required")
        profile = Path(self.temporary.name) / "edge-profile"
        process = subprocess.run([
            str(edge), "--headless", "--disable-gpu", "--no-first-run",
            "--disable-background-networking", "--no-default-browser-check",
            "--user-data-dir=" + str(profile), "--dump-dom", "--virtual-time-budget=20000",
            self.url + "/__ui_test",
        ], capture_output=True, timeout=90)
        output = process.stdout.decode("utf-8", errors="replace")
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertIn('<pre id="result">UI_PASS</pre>', output, output[-8000:])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["profiles"][1]["name"],
                         "UI test saved")


if __name__ == "__main__":
    unittest.main()
