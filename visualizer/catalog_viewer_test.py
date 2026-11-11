"""品番結果と旧結果のHTTP配信・実ブラウザ表示。追加依存は不要。"""

import copy
import json
from pathlib import Path
import re
import socketserver
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from algorithm_programmer.catalog import run_catalog_case
from algorithm_programmer.cli import resolve_box_specs, resolve_pallet_spec
from algorithm_programmer.palletizer import Palletizer
from box_research.catalog_store import catalog_pallets, load_catalog
from visualizer.serve_3d_viewer import ViewerHandler
from visualizer.visualize import generate_html


ROOT = Path(__file__).resolve().parent.parent
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


HARNESS = r"""<!DOCTYPE html><html><body>
<pre id="result">RUNNING</pre><iframe id="app" src="/index.html" width="1400" height="1000"></iframe>
<script>
const frame = document.getElementById('app');
const output = document.getElementById('result');
const sleep = () => new Promise(resolve => setTimeout(resolve, 50));
function assert(value, message) { if (!value) throw new Error(message); }
async function until(test, message) {
  for (let i=0; i<300; i++) { if(test()) return; await sleep(); }
  throw new Error(message);
}
let d, w;
async function loaded(part) {
  await until(() => {
    const text=frame.contentDocument?.getElementById('part-summary')?.textContent || '';
    return part ? text.includes('共通モデル') : text.includes('旧方式');
  }, 'result did not load: '+frame.contentDocument?.getElementById('load-error-message')?.textContent);
  d=frame.contentDocument; w=frame.contentWindow;
}
function inspect() {
  w.inspectBox(w.eval('currentData.boxes[0]'));
  const text=d.getElementById('part-inspector').textContent;
  assert(text.includes('111032402200') && text.includes('NP22C') &&
         text.includes('サンボックス#22H') && text.includes('サンボックス#22Bフタ'), 'part inspector');
}
function timeline() {
  const slider=d.getElementById('step-slider');
  slider.value='1'; slider.dispatchEvent(new w.Event('input'));
  assert(d.getElementById('step-current').textContent==='1', 'timeline step');
  d.querySelector('[data-view="top"]').click();
  assert(w.eval('viewMode')==='top', '2D top view');
  d.querySelector('[data-view="iso"]').click();
  assert(w.eval('viewMode')==='iso', '3D iso view');
  assert(d.getElementById('main-canvas').width>0, 'canvas initialized');
}
(async()=>{
  await loaded(true);
  assert(d.getElementById('part-summary').textContent.includes('投入15・配置9・未配置6'), 'part quantities');
  assert(d.getElementById('unplaced-summary').textContent.includes('111032401100'), 'unplaced part');
  assert(d.getElementById('legend-list').textContent.includes('111032402200'), 'part colors');
  inspect(); timeline();
  const mutated=JSON.parse(JSON.stringify(w.eval('currentData')));
  mutated.part_counts[0].placed_count++;
  let rejected=false; try { w.eval('ResultIdentity').validate(mutated); } catch { rejected=true; }
  assert(rejected, 'inconsistent quantities must be rejected');
  const select=d.getElementById('select-test-case');
  select.value='result_b_legacy.json'; select.dispatchEvent(new w.Event('change'));
  await until(()=>d.getElementById('part-summary').textContent.includes('旧方式'),'legacy selection');
  w.inspectBox(w.eval('currentData.boxes[0]'));
  assert(!d.getElementById('part-inspector'), 'legacy inspector without fabricated part');
  timeline();
  frame.src='/standalone.html'; await loaded(true); inspect(); timeline();
  frame.src='/legacy.html'; await loaded(false); timeline();
  frame.src='/special.html'; await loaded(true);
  w.inspectBox(w.eval('currentData.boxes[0]'));
  assert(d.getElementById('part-inspector').textContent.includes('<img'), 'special name shown literally');
  assert(!d.querySelector('#inspector-content img') && !w.injected, 'names must not become HTML');
  frame.src='/invalid.html';
  await until(()=>frame.contentDocument?.getElementById('load-error-message')?.textContent.includes('数量'),
              'invalid quantities should display load error');
  output.textContent='PASS: integrated/standalone, part identity/counts, legacy, 3D/2D/timeline, special characters, invalid data';
})().catch(error=>{output.textContent='FAIL: '+error.stack;});
</script></body></html>"""


class ViewerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog, revision = load_catalog(ROOT)
        case = catalog["cases"]["test_cases"]["othics_6"]
        cls.new_result = run_catalog_case("othics_6", case, catalog,
                                         resolve_pallet_spec(case, catalog_pallets(ROOT)), revision)
        old_case = json.loads((ROOT / "test_programmer" / "test_cases" / "othics_6.json").read_text(encoding="utf-8"))
        boxes = json.loads((ROOT / "box_research" / "box_db.json").read_text(encoding="utf-8"))
        lids = json.loads((ROOT / "box_research" / "lid_db.json").read_text(encoding="utf-8"))
        pallets = json.loads((ROOT / "box_research" / "pallet_db.json").read_text(encoding="utf-8"))
        specs, rows = resolve_box_specs(old_case["box_list"], boxes, lids)
        cls.old_result = Palletizer(specs, resolve_pallet_spec(old_case, pallets)).run("legacy", rows).to_dict()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.results = self.directory / "results"
        self.results.mkdir()
        for filename, data in (("result_a_part.json", self.new_result), ("result_b_legacy.json", self.old_result)):
            (self.results / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        (self.results / "run_manifest.json").write_text("{}", encoding="utf-8")
        (self.results / "unrelated.json").write_text("{}", encoding="utf-8")
        fixtures = {}

        class Handler(ViewerHandler):
            def do_GET(handler):
                name = handler.path.split("?", 1)[0]
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

    def test_api_lists_only_result_files_and_preserves_snapshots(self):
        with urlopen(self.url + "/api/results") as response:
            data = json.load(response)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual([row["filename"] for row in data], ["result_a_part.json", "result_b_legacy.json"])
        self.assertEqual([row["input_mode"] for row in data], ["part_number", "legacy"])
        with urlopen(self.url + "/api/result/result_a_part.json") as response:
            self.assertEqual(json.load(response), json.loads(json.dumps(self.new_result)))
        with urlopen(self.url + "/result_identity.js") as response:
            self.assertIn(b"ResultIdentity", response.read())

    def test_invalid_filenames_and_invalid_json_are_visible_errors(self):
        for path in ("..%5Cresult_a_part.json", "%2E%2E%2Fresult_a_part.json", "run_manifest.json"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.url + "/api/result/" + path)
            self.assertEqual(error.exception.code, 400)
        (self.results / "result_bad.json").write_text("{", encoding="utf-8")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/results")
        self.assertEqual(error.exception.code, 500)
        self.assertIn("result_bad.json", error.exception.read().decode("utf-8"))

    @unittest.skipUnless(EDGE.exists(), "Edgeがない環境ではHTTPテストのみ実行")
    def test_real_browser_new_legacy_standalone_and_input_errors(self):
        def offline(html):
            return re.sub(r'<script src="https://[^"]+"></script>', "", html).replace(
                "</head>", "<script>const lucide={createIcons(){}};</script></head>")

        self.fixtures["/test.html"] = HARNESS
        self.fixtures["/index.html"] = offline((ROOT / "visualizer" / "index.html").read_text(encoding="utf-8"))
        special = copy.deepcopy(self.new_result)
        special_name = '<img src=x onerror="window.injected=true"></script>'
        for key in ("boxes", "unplaced_boxes", "part_counts", "input_parts", "input_box_variants"):
            for row in special[key]:
                row["box_id"] = row["box_name"] = special_name
        invalid = copy.deepcopy(self.new_result)
        invalid["part_counts"][0]["placed_count"] += 1
        for route, data in (("/standalone.html", self.new_result), ("/legacy.html", self.old_result),
                            ("/special.html", special), ("/invalid.html", invalid)):
            target = self.directory / route[1:]
            generate_html(data, str(target))
            self.fixtures[route] = offline(target.read_text(encoding="utf-8"))
        run = subprocess.run([
            str(EDGE), "--headless", "--disable-gpu", "--no-first-run",
            "--disable-extensions", "--disable-background-networking", "--no-proxy-server",
            "--disable-features=msEdgeSidebarV2", "--user-data-dir=" + str(self.directory / "edge"),
            "--dump-dom", "--virtual-time-budget=30000", self.url + "/test.html",
        ], capture_output=True, timeout=90)
        output = run.stdout.decode("utf-8", errors="replace")
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", errors="replace")[-2000:])
        start = output.find('<pre id="result">')
        end = output.find("</pre>", start)
        self.assertIn("PASS:", output[start:end], output[start:end])


if __name__ == "__main__":
    unittest.main()
