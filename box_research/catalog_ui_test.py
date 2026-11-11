"""追加ライブラリ不要のEdgeヘッドレス検証。テスト用DBだけを編集する。"""

from pathlib import Path
import socketserver
import subprocess
import threading
import unittest
from unittest.mock import patch

from box_research.catalog_store import load_catalog, prepare_cases
from box_research.catalog_store_test import CatalogFixture
from box_research import serve_viewer

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
HARNESS = r"""<!DOCTYPE html><html><body><pre id="result">RUNNING</pre>
<iframe id="app" src="/catalog_viewer.html" style="width:1200px;height:900px"></iframe>
<script>
const frame = document.getElementById('app');
const result = document.getElementById('result');
const sleep = () => new Promise(resolve => setTimeout(resolve, 50));
function assert(value, message) { if (!value) throw new Error(message); }
async function until(test, message) {
  for (let i=0;i<200;i++) { if (test()) return; await sleep(); }
  throw new Error(message);
}
let d, w;
async function ready() {
  await until(() => frame.contentDocument?.getElementById('dirty')?.textContent === '保存済み', 'initial load failed');
  d = frame.contentDocument; w = frame.contentWindow;
  w.confirm = () => true;
}
const el = id => d.getElementById(id);
function click(id) { el(id).click(); }
function field(key, value) {
  const input = el('field-'+key); input.value = value;
  input.dispatchEvent(new w.Event('input', {bubbles:true}));
}
function tab(name) { d.querySelector('[data-tab="'+name+'"]').click(); }
function row(id) { return [...d.querySelectorAll('tbody tr')].find(row => row.dataset.recordId === id); }
function rowButton(id, text) {
  const button = [...row(id).querySelectorAll('button')].find(button => button.textContent === text);
  assert(button, 'missing '+text+' button for '+id); button.click();
}
function submit() { el('edit-form').requestSubmit(); }
async function save() {
  click('save');
  await until(() => el('dirty').textContent === '保存済み' && !el('reload').disabled, 'save failed: '+el('feedback').textContent);
}
(async () => {
  await ready();
  assert(d.querySelectorAll('[data-tab]').length === 4, 'four DB tabs');
  assert(el('table-body').textContent.includes('00001'), 'part table');
  rowButton('00001', '削除');
  assert(el('feedback').textContent.includes('使用中'), 'used part deletion must be blocked');
  tab('models'); click('add');
  field('id', 'ｻﾝﾎﾞｯｸｽ＃９９');
  for (const [k,v] of Object.entries({length:300,width:400,height:150,fitting_depth:5,rib_thickness:10})) field(k,v);
  submit(); assert(!el('editor').open, 'model form confirmed');
  tab('parts'); tab('models');
  assert(row('サンボックス#99'), 'normalized ID and unsaved tab preservation');
  click('save');
  await until(() => el('feedback').className === 'error' && !el('reload').disabled, 'invalid dimensions must show error');
  assert(el('dirty').textContent.includes('未保存'), 'failed save retains drafts');
  rowButton('サンボックス#99', '編集');
  field('length', 500); field('description', 'line one\nline two'); submit();
  await save();
  tab('lids'); click('add');
  field('id','テスト蓋'); field('length',500); field('width',400); field('thickness',10);
  submit(); await save();
  tab('models'); rowButton('サンボックス#99','編集');
  const compatible = [...d.querySelectorAll('[name="compatible_lids"]')].find(input => input.value === 'テスト蓋');
  compatible.checked = true; submit(); await save();
  tab('parts'); click('add');
  field('id','０００１０'); field('supplier_name','オティックス'); field('box_name','表示箱');
  field('box_model_id','サンボックス#99');
  el('field-box_model_id').dispatchEvent(new w.Event('change',{bubbles:true}));
  field('lid_id','テスト蓋'); submit(); await save();
  assert(row('00010').textContent.includes('テスト蓋'), 'fixed lid saved');
  click('add'); field('id','０００１０'); field('supplier_name','オティックス'); field('box_name','重複');
  submit(); assert(el('form-error').textContent.includes('同じID'), 'duplicate ID rejected');
  click('cancel-edit');
  tab('models');
  let confirmation = '';
  w.prompt = () => '変更後モデル';
  w.confirm = text => { confirmation = text; return true; };
  rowButton('サンボックス#99', '名前変更');
  await until(() => Boolean(row('変更後モデル')) && !el('reload').disabled, 'rename failed');
  assert(confirmation.includes('00010'), 'rename impact shows part');
  tab('parts'); assert(row('00010').textContent.includes('変更後モデル'), 'rename updates references');
  tab('pallets'); assert(el('add').disabled && el('table-body').textContent.includes('標準'), 'pallet view');
  frame.src = '/catalog_cases.html';
  await until(() => frame.contentDocument?.getElementById('section-title')?.textContent.includes('品番方式'), 'case page navigation');
  await ready();
  assert(row('case'), 'migrated case listed');
  click('add'); field('id','ui_case'); field('description','UI test case');
  click('add-line');
  const select = d.querySelector('.case-line select');
  select.value='00010'; select.dispatchEvent(new w.Event('change',{bubbles:true}));
  const count = d.querySelector('.case-line input[type="number"]');
  count.value='3'; count.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert(el('line-list').textContent.includes('変更後モデル') && el('line-list').textContent.includes('テスト蓋'), 'automatic box/lid display');
  submit(); await save();
  assert(row('ui_case').textContent.includes('00010'), 'new case saved');
  const approval = row('ui_case').querySelector('input[type="checkbox"]');
  assert(!approval.checked, 'new case starts unapproved');
  approval.click(); await save();
  rowButton('ui_case','編集');
  assert(el('field-id').disabled, 'case ID protected');
  const count2 = d.querySelector('.case-line input[type="number"]');
  count2.value='4'; count2.dispatchEvent(new w.Event('input',{bubbles:true}));
  submit(); await save();
  assert(row('ui_case').textContent.includes('× 4'), 'case edit persisted');
  rowButton('ui_case','削除'); await save();
  assert(!row('ui_case'), 'case deletion persisted');
  result.textContent = 'PASS: tabs, CRUD, normalization, errors, rename, cases, approval, isolation';
})().catch(error => { result.textContent = 'FAIL: '+error.stack; });
</script></body></html>"""


@unittest.skipUnless(EDGE.exists(), "Edgeがない環境ではHTTP・保存処理のテストを使用します")
class CatalogBrowserTest(CatalogFixture, unittest.TestCase):
    def test_real_browser_editing_workflow(self):
        prepare_cases(self.root)
        patcher = patch.object(serve_viewer, "BASE_DIR", str(self.db))
        patcher.start()
        self.addCleanup(patcher.stop)

        class Handler(serve_viewer.ViewerRequestHandler):
            def do_GET(self):
                if self.path == "/ui-check.html":
                    body = HARNESS.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    super().do_GET()

        server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            process = subprocess.run([
                str(EDGE), "--headless", "--disable-gpu", "--no-first-run",
                "--disable-extensions", "--disable-background-networking",
                "--disable-features=msEdgeSidebarV2", "--no-proxy-server",
                "--user-data-dir=" + str(self.root / "edge-profile"),
                "--dump-dom", "--virtual-time-budget=30000",
                "http://127.0.0.1:{}/ui-check.html".format(server.server_address[1]),
            ], capture_output=True, timeout=90)
            output = process.stdout.decode("utf-8", errors="replace")
            self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace")[-2000:])
            start = output.find('<pre id="result">')
            end = output.find("</pre>", start)
            self.assertIn("PASS:", output[start:end], output[start:end])
            data, _ = load_catalog(self.root)
            self.assertEqual(data["parts"]["00010"]["box_model_id"], "変更後モデル")
            self.assertNotIn("ui_case", data["cases"]["test_cases"])
            self.assertIn("テスト蓋", data["lids"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
