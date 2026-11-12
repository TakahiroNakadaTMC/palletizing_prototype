"""追加ライブラリ不要のEdgeヘッドレス検証。テスト用DBだけを編集する。"""

from pathlib import Path
import base64
import ctypes
import hashlib
import json
import os
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from box_research.catalog_store import load_catalog
from box_research.catalog_store_test import CatalogFixture
from box_research import serve_viewer

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class CdpConnection:
    """Minimal loopback-only WebSocket client for the browser test."""

    def __init__(self, port, path):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).format(path, port, key)
        self.socket.sendall(request.encode("ascii"))
        response = b""
        while not response.endswith(b"\r\n\r\n"):
            response += self.socket.recv(1)
        expected = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest())
        if b" 101 " not in response or expected not in response:
            raise RuntimeError("CDP WebSocket handshake rejected: " + repr(response))
        self.counter = 0

    def _read(self, size):
        result = b""
        while len(result) < size:
            chunk = self.socket.recv(size - len(result))
            if not chunk:
                raise ConnectionError("CDP connection closed")
            result += chunk
        return result

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size <= 65535:
            header += b"\xfe" + struct.pack("!H", size)
        else:
            header += b"\xff" + struct.pack("!Q", size)
        self.socket.sendall(header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))

    def _receive(self):
        message = b""
        while True:
            first, second = self._read(2)
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if second & 128 else None
            data = self._read(size)
            if mask:
                data = bytes(value ^ mask[i % 4] for i, value in enumerate(data))
            opcode = first & 15
            if opcode == 8:
                raise ConnectionError("CDP connection closed")
            if opcode == 9:
                self._send(data, 10)
                continue
            if opcode in (0, 1):
                message += data
                if first & 128:
                    return json.loads(message.decode("utf-8"))

    def call(self, method, params=None):
        self.counter += 1
        request = {"id": self.counter, "method": method, "params": params or {}}
        self._send(json.dumps(request).encode("utf-8"))
        while True:
            response = self._receive()
            if response.get("id") != self.counter:
                continue
            if "error" in response:
                raise RuntimeError(response["error"])
            return response.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def close(self):
        self.socket.close()


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
let d, w, requests;
async function ready() {
  await until(() => frame.contentDocument?.getElementById('dirty')?.textContent === '保存済み', 'initial load failed');
  d = frame.contentDocument; w = frame.contentWindow;
  w.confirm = () => true;
  requests = [];
  const originalFetch = w.fetch.bind(w);
  w.fetch = (url, options) => {
    requests.push({url, body: options?.body ? JSON.parse(options.body) : null});
    return originalFetch(url, options);
  };
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
function change(key, value) {
  field(key,value); el('field-'+key).dispatchEvent(new w.Event('change',{bubbles:true}));
}
function quantity(part, value) {
  const input = d.querySelector('[aria-label="'+part+'の数量"]');
  assert(input, 'missing quantity '+part); input.value=value;
  input.dispatchEvent(new w.Event('input',{bubbles:true})); return input;
}
async function catalog() { return await (await fetch('/api/catalog')).json(); }
async function post(path, body) {
  const response = await fetch('/api/catalog'+path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result = await response.json(); assert(response.ok, 'API '+path+': '+JSON.stringify(result)); return result;
}
async function save() {
  click('save');
  await until(() => el('dirty').textContent === '保存済み' && !el('reload').disabled, 'save failed: '+el('feedback').textContent);
}
(async () => {
  await ready();
  assert(d.querySelectorAll('[data-tab]').length === 6, 'six DB tabs including skids and suppliers');
  assert(el('table-body').textContent.includes('00001'), 'part table');
  tab('suppliers');
  assert(row('0001') && row('0001').textContent.includes('Supplier A'), 'fixture mapping listed');
  click('add'); field('id','０００２'); field('supplier_name','Supplier B'); submit();
  tab('parts'); rowButton('00001','編集'); field('box_name','Fixture updated'); submit();
  let mappingPreview='';
  requests.length=0;
  w.confirm=text=>{mappingPreview=text;return true;}; await save();
  assert(mappingPreview.includes('Supplier B') && (await catalog()).suppliers['0002'].supplier_name==='Supplier B', 'new mapping saved with preview');
  const mappingPlan=requests.find(r=>r.url.endsWith('/skid-preview')).body;
  const mappingSave=requests.find(r=>r.url.endsWith('/save')).body;
  assert(mappingPlan.parts && mappingPlan.suppliers && JSON.stringify(mappingPlan.parts)===JSON.stringify(mappingSave.parts)
    && JSON.stringify(mappingPlan.suppliers)===JSON.stringify(mappingSave.suppliers), 'preview includes all dirty collections unchanged from save');
  tab('suppliers');
  click('add'); field('id','0003'); field('supplier_name','Supplier A'); submit(); await save();
  rowButton('0002','編集'); assert(el('field-id').disabled, 'registered supplier number immutable'); click('cancel-edit');
  tab('parts');
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
  field('id','０００１０'); field('supplier_name','Supplier A'); field('box_name','表示箱');
  field('box_model_id','サンボックス#99');
  el('field-box_model_id').dispatchEvent(new w.Event('change',{bubbles:true}));
  field('lid_id','テスト蓋'); submit(); await save();
  assert(row('00010').textContent.includes('テスト蓋'), 'fixed lid saved');
  click('add'); field('id','０００１０'); field('supplier_name','Supplier A'); field('box_name','重複');
  submit(); assert(el('form-error').textContent.includes('同じID'), 'duplicate ID rejected');
  click('cancel-edit');
  click('add'); field('id','00020'); field('supplier_name','Supplier B'); field('box_name','<img src=x onerror=alert(1)>');
  submit(); await save();
  assert(row('00020').textContent.includes('<img') && !row('00020').querySelector('img'), 'untrusted values rendered as text');
  tab('models');
  let confirmation = '';
  w.prompt = () => '変更後モデル';
  w.confirm = text => { confirmation = text; return true; };
  rowButton('サンボックス#99', '名前変更');
  await until(() => Boolean(row('変更後モデル')) && !el('reload').disabled, 'rename failed');
  assert(confirmation.includes('00010'), 'rename impact shows part');
  tab('parts'); assert(row('00010').textContent.includes('変更後モデル'), 'rename updates references');
  tab('models'); rowButton('変更後モデル','編集');
  assert(el('field-id').disabled, 'existing model ID cannot be edited directly');
  click('cancel-edit');
  tab('pallets'); assert(!el('add').disabled && el('table-body').textContent.includes('標準'), 'pallet view');
  click('add'); field('id','PALLET-UI'); field('model','UI pallet');
  field('length',900); field('width',1100); field('height',125); field('suppliers','Supplier A\nNITTAN');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('長さL'), 'reversed pallet dimensions rejected');
  field('length',1100); field('width',900); field('suppliers','Supplier A\nBad\tSupplier');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('制御文字'), 'supplier control characters rejected per line');
  field('suppliers',' Supplier A \nＮＩＴＴＡＮ');
  submit(); await save(); assert(row('PALLET-UI'), 'pallet created');
  click('reload');
  await until(() => !el('reload').disabled && el('feedback').textContent.includes('読み込み'), 'pallet reload failed');
  rowButton('PALLET-UI','編集');
  assert(el('field-suppliers').value === 'Supplier A\nニッタン', 'multiline suppliers and server alias persisted');
  click('cancel-edit');
  rowButton('PALLET-UI','編集'); field('height',135); submit(); await save();
  assert(row('PALLET-UI').textContent.includes('135'), 'pallet edited');
  tab('skids'); click('add');
  field('supplier_number','9999'); field('work_area','x'); field('course','a');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('先に仕入先対応表'), 'unknown number requires registration');
  field('supplier_number','０００１'); field('work_area','ｘ'); field('course','ａ');
  assert(el('field-id').readOnly && el('field-id').value==='0001XA' && el('field-supplier_name').readOnly && el('field-supplier_name').value==='Supplier A', 'four component normalized preview and mapped read-only supplier');
  const catalogForSkid = await (await fetch('/api/catalog')).json();
  assert([...d.querySelectorAll('[name="part_numbers"]')].every(input => catalogForSkid.parts[input.value].supplier_name === 'Supplier A'), 'skid candidates restricted to selected supplier');
  assert([...el('field-pallet_id').options].every(option => !option.value || catalogForSkid.pallets[option.value].standard || catalogForSkid.pallets[option.value].suppliers.includes('Supplier A')), 'skid pallets filtered by supplier');
  const skidPallet = el('field-pallet_id'); skidPallet.value = 'PALLET-UI'; skidPallet.dispatchEvent(new w.Event('change',{bubbles:true}));
  field('max_x_span',1000); field('max_y_span',900); field('max_height',1200);
  const candidate = [...d.querySelectorAll('[name="part_numbers"]')].find(input => input.value === '00010');
  assert(candidate, 'skid candidate limited to supplier parts'); candidate.checked = true;
  candidate.dispatchEvent(new w.Event('change',{bubbles:true}));
  const optionalCandidate = [...d.querySelectorAll('[name="part_numbers"]')].find(input => input.value !== '00010');
  if (optionalCandidate) { optionalCandidate.checked = true; optionalCandidate.dispatchEvent(new w.Event('change',{bubbles:true})); }
  submit(); assert(!el('editor').open, 'complete skid confirmed');
  let skidConfirmation = '';
  requests.length=0;
  w.confirm = text => { skidConfirmation=text; return false; };
  click('save');
  await until(() => !el('reload').disabled && Boolean(skidConfirmation), 'preview cancel did not finish');
  assert(requests.some(r=>r.url.endsWith('/skid-preview')) && !requests.some(r=>r.url.endsWith('/save')), 'cancel sends preview only, not save');
  assert(el('dirty').textContent.includes('未保存') && !(await catalog()).skids['0001XA'], 'cancel retains draft without persistence');
  requests.length=0;
  w.confirm = text => { skidConfirmation = text; return true; };
  await save();
  assert(skidConfirmation.includes('0001XA') && skidConfirmation.includes('→'), 'skid save uses preview confirmation');
  const previewRequest=requests.find(r=>r.url.endsWith('/skid-preview')).body;
  const saveRequest=requests.find(r=>r.url.endsWith('/save')).body;
  assert(JSON.stringify(previewRequest.skids)===JSON.stringify(saveRequest.skids) && previewRequest.revision===saveRequest.revision && saveRequest.confirmation, 'preview and save share revision/skids and server confirmation');
  const createdSkid=(await catalog()).skids['0001XA'];
  assert(createdSkid.updated_at && createdSkid.history.length===1 && createdSkid.history[0].before===null, 'server populated initial timestamp and before-null history');
  assert(row('0001XA').textContent.includes('1000') && el('table-head').textContent.includes('更新日時'), 'skid table shows bounds and update time');
  rowButton('0001XA','編集');
  assert(el('skid-history-list').textContent.includes('影響ケース'), 'skid editor shows history');
  click('cancel-edit');
  click('add'); field('supplier_number','0001'); field('work_area','b'); field('course','a');
  const incompletePart = [...d.querySelectorAll('[name="part_numbers"]')].find(input => input.value === '00010');
  incompletePart.checked = true; incompletePart.dispatchEvent(new w.Event('change',{bubbles:true}));
  submit(); await save();
  assert(row('0001BA'), 'incomplete skid with blank pallet and limits can be saved');
  const incomplete=(await catalog()).skids['0001BA'];
  assert(incomplete.pallet_id===null && Object.values(incomplete.pallet).every(v=>v===null), 'blank skid conditions saved as null');
  click('add'); field('supplier_number','0001'); field('work_area','x'); field('course','a');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('同じID'), 'normalized duplicate rejected before draft changes');
  click('cancel-edit');
  click('add'); field('supplier_number','0001'); field('work_area','9'); field('shipping_area','ｚ１ｂ'); field('course','ｃ');
  assert(el('field-id').value==='00019Z1BC', 'optional three-character shipping area is uppercased');
  field('shipping_area','ab'); submit(); assert(el('form-error').textContent.includes('出荷場'), 'shipping area length validated');
  click('cancel-edit');
  const orderedCatalog=await catalog();
  orderedCatalog.skids['0001XA'].part_numbers=['00010','00001'];
  const orderingPlan=await post('/skid-preview',{revision:orderedCatalog.revision,skids:orderedCatalog.skids});
  await post('/save',{revision:orderedCatalog.revision,skids:orderedCatalog.skids,confirmation:orderingPlan.confirmation});
  frame.src = '/catalog_cases.html';
  await until(() => frame.contentDocument?.getElementById('section-title')?.textContent.includes('品番方式'), 'case page navigation');
  await ready();
  assert(row('case'), 'migrated case listed');
  rowButton('case','編集');
  assert(el('field-skid_id').value==='0001AA', 'existing fixture case selects KEY2');
  assert(!el('field-pallet_id') && !el('field-max_x_span') && el('case-skid-info').textContent.includes('1360'), 'case conditions are derived read-only text');
  click('cancel-edit');
  click('add'); field('id','ui_case'); field('description','UI test case');
  const caseSupplier = el('field-supplier_name');
  caseSupplier.value = 'Supplier A'; caseSupplier.dispatchEvent(new w.Event('change',{bubbles:true}));
  const caseSkid = el('field-skid_id');
  caseSkid.value = '0001BA'; caseSkid.dispatchEvent(new w.Event('change',{bubbles:true}));
  assert(!el('case-skid-blocked').hidden, 'incomplete skid visibly blocks calculations');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('新規ケース'), 'new case rejects incomplete skid');
  caseSkid.value = '0001XA'; caseSkid.dispatchEvent(new w.Event('change',{bubbles:true}));
  const allQuantityInputs=[...d.querySelectorAll('.case-line input[type="number"]')];
  assert(allQuantityInputs.length===2, 'all skid candidates shown without adding rows');
  assert(allQuantityInputs.map(input=>input.getAttribute('aria-label')).join(',')==='00010の数量,00001の数量', 'new candidate rows follow skid candidate order');
  submit(); assert(el('editor').open && el('form-error').textContent.includes('少なくとも'), 'all blank quantities rejected');
  for (const invalid of ['-1','1.5','501']) {
    const invalidInput=quantity('00010',invalid);
    assert(!invalidInput.checkValidity(), 'native invalid quantity '+invalid);
    el('edit-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
    assert(el('editor').open && el('form-error').textContent.includes('整数'), 'application rejects invalid quantity '+invalid);
  }
  assert(quantity('00010',1).checkValidity() && quantity('00001',500).checkValidity(), 'integer boundaries 1 and 500 accepted');
  assert(el('line-summary').textContent.includes('箱数合計: 501'), 'quantity summary includes boundary quantities');
  quantity('00010',3); quantity('00001',0);
  let clearPrompt='';
  w.confirm=text=>{clearPrompt=text;return false;};
  change('skid_id','0001AA');
  assert(clearPrompt.includes('クリア') && el('field-skid_id').value==='0001XA' && d.querySelector('[aria-label="00010の数量"]').value==='3', 'cancel skid switch preserves quantities');
  change('supplier_name','Supplier B');
  assert(el('field-supplier_name').value==='Supplier A', 'cancel supplier switch restores supplier');
  w.confirm=()=>true;
  change('supplier_name','Supplier B');
  assert(!d.querySelector('.case-line') && el('field-skid_id').options.length===1, 'supplier switch clears quantities and filters skids');
  change('supplier_name','Supplier A'); change('skid_id','0001XA');
  const count = d.querySelector('[aria-label="00010の数量"]');
  assert(count, 'all skid candidate parts rendered as quantity inputs');
  count.value='3'; count.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert(el('line-list').textContent.includes('変更後モデル') && el('line-list').textContent.includes('テスト蓋'), 'automatic box/lid display');
  assert(el('line-summary').textContent.includes('選択品番数: 1') && el('line-summary').textContent.includes('箱数合計: 3'), 'case quantity summary');
  submit(); await save();
  assert(row('ui_case').textContent.includes('00010'), 'new case saved');
  const approval = row('ui_case').querySelector('input[type="checkbox"]');
  assert(!approval.checked, 'new case starts unapproved');
  approval.click(); await save();
  rowButton('ui_case','編集');
  assert(el('field-id').disabled, 'case ID protected');
  const count2 = d.querySelector('[aria-label="00010の数量"]');
  count2.value='4'; count2.dispatchEvent(new w.Event('input',{bubbles:true}));
  submit(); await save();
  assert(row('ui_case').textContent.includes('× 4'), 'case edit persisted');
  const saved = await (await fetch('/api/catalog')).json();
  const savedCase = saved.cases.test_cases.ui_case;
  assert(savedCase.skid_id === '0001XA' && !('pallet_id' in savedCase) && !('pallet' in savedCase), 'case saves only skid reference, not pallet data');
  assert(savedCase.box_list.length === 1 && savedCase.box_list[0].part_number === '00010', 'blank candidate quantities are omitted and input order saved');
  rowButton('ui_case','編集');
  quantity('00001',2); submit(); await save();
  const orderedCase=(await catalog()).cases.test_cases.ui_case;
  assert(orderedCase.box_list.map(r=>r.part_number).join(',')==='00010,00001', 'existing box_list order preserved when adding a candidate');
  frame.src='/catalog_viewer.html';
  await until(()=>frame.contentDocument?.getElementById('db-tabs')?.hidden===false && frame.contentDocument?.getElementById('dirty')?.textContent==='保存済み','return to DB');
  await ready(); tab('skids');
  rowButton('0001XA','削除');
  assert(el('feedback').textContent.includes('使用中'), 'used skid deletion proactively blocked');
  const unchangedSkid=(await catalog()).skids['0001XA'];
  rowButton('0001XA','編集'); submit(); await save();
  const afterNoop=(await catalog()).skids['0001XA'];
  assert(JSON.stringify(afterNoop)===JSON.stringify(unchangedSkid), 'unchanged skid edit preserves candidate order, timestamp and history');
  rowButton('0001XA','編集');
  const usedCandidate=[...d.querySelectorAll('[name="part_numbers"]')].find(input=>input.value==='00010');
  usedCandidate.checked=false; usedCandidate.dispatchEvent(new w.Event('change',{bubbles:true})); submit();
  requests.length=0; click('save');
  await until(()=>!el('reload').disabled && el('feedback').className==='error','used candidate rejection missing');
  assert(requests.some(r=>r.url.endsWith('/skid-preview')) && !requests.some(r=>r.url.endsWith('/save')), 'backend preview blocks removal of a used candidate');
  assert(JSON.stringify((await catalog()).skids['0001XA'])===JSON.stringify(unchangedSkid), 'blocked candidate removal leaves server data unchanged');
  click('reload'); await until(()=>!el('reload').disabled && el('dirty').textContent==='保存済み','reload after rejected candidate removal');
  rowButton('0001XA','編集'); field('max_height',''); submit();
  let impact='';
  w.confirm=text=>{impact=text;return true;}; await save();
  assert(impact.includes('ui_case') && impact.includes('未設定') && impact.includes('→'), 'condition change confirmation identifies before/after and affected case');
  const changedSkid=(await catalog()).skids['0001XA'];
  assert(changedSkid.history.length===3 && changedSkid.history.at(-1).affected_cases.includes('ui_case') && changedSkid.updated_at===changedSkid.history.at(-1).updated_at, 'server timestamps/history record affected case');
  rowButton('0001XA','編集');
  assert(el('skid-history-list').textContent.includes('ui_case') && el('skid-updated-at').textContent.includes(changedSkid.updated_at), 'updated time/history displayed');
  click('cancel-edit');
  rowButton('0001AA','編集');
  const originalHeight=el('field-max_height').value;
  assert(el('field-supplier_number').value==='0001' && el('field-work_area').value==='A'
    && el('field-shipping_area').value==='' && el('field-course').value==='A', 'existing six-character ID decomposed');
  field('work_area','x'); submit();
  assert(el('editor').open && el('form-error').textContent.includes('同じID') && row('0001AA'), 'rename collision leaves original draft intact');
  field('work_area','c'); field('max_height','0'); submit();
  assert(el('editor').open && el('form-error').textContent.includes('正数') && row('0001AA') && !row('0001CA'), 'invalid rename leaves original draft intact');
  field('max_height',originalHeight);
  field('work_area','c'); submit(); assert(row('0001CA') && !row('0001AA'), 'existing skid rename changes draft key');
  rowButton('0001CA','削除'); assert(el('feedback').textContent.includes('先に変更を保存'), 'staged renamed skid cannot be deleted');
  rowButton('0001CA','編集'); field('work_area','d'); field('shipping_area','ｚ１ｂ'); field('course','ｃ'); submit();
  assert(row('0001DZ1BC') && !row('0001CA'), 'repeated rename updates draft key');
  rowButton('0001DZ1BC','編集');
  assert(el('field-shipping_area').value==='Z1B' && el('field-course').value==='C', 'nine-character ID decomposed');
  field('work_area','a'); field('shipping_area',''); field('course','a'); submit();
  assert(row('0001AA') && !row('0001DZ1BC'), 'rename can be undone to original');
  rowButton('0001AA','編集'); field('work_area','d'); field('shipping_area','ｚ１ｂ'); field('course','ｃ'); submit();
  let renameImpact=''; requests.length=0; w.confirm=text=>{renameImpact=text;return true;}; await save();
  const renamePreview=requests.find(r=>r.url.endsWith('/skid-preview')).body;
  const renameSave=requests.find(r=>r.url.endsWith('/save')).body;
  assert(renamePreview.skid_renames['0001AA']==='0001DZ1BC'
    && JSON.stringify(renameSave.skid_renames)===JSON.stringify(renamePreview.skid_renames), 'original-to-final rename included in preview and save');
  assert(renameImpact.includes('0001AA') && renameImpact.includes('0001DZ1BC') && renameImpact.includes('case'), 'rename confirmation identifies IDs and affected case');
  const renamedCatalog=await catalog();
  assert(renamedCatalog.cases.test_cases.case.skid_id==='0001DZ1BC' && !renamedCatalog.skids['0001AA'], 'confirmed rename cascades to case');
  rowButton('0001DZ1BC','編集');
  assert(el('skid-history-list').textContent.includes('0001AA → 0001DZ1BC'), 'rename history shows original and new ID');
  click('cancel-edit');
  rowButton('0001BA','削除'); requests.length=0;
  await save();
  assert(requests.some(r=>r.url.endsWith('/skid-preview')) && !(await catalog()).skids['0001BA'], 'unused skid deletion uses preview and confirmed save');
  frame.src='/catalog_cases.html';
  await until(()=>frame.contentDocument?.getElementById('section-title')?.textContent.includes('品番方式'),'return to cases');
  await ready();
  assert(row('ui_case').textContent.includes('計算ブロック') && row('ui_case').textContent.includes(changedSkid.updated_at), 'incomplete existing case visible blocked with update notice');
  rowButton('ui_case','編集');
  assert(!el('case-skid-blocked').hidden, 'incomplete existing case warning visible');
  quantity('00010',5); submit(); await save();
  assert((await catalog()).cases.test_cases.ui_case.box_list[0].count===5, 'existing incomplete case quantities remain editable');
  rowButton('case','編集'); change('skid_id','0001XA'); quantity('00010',1);
  submit(); assert(el('editor').open && el('form-error').textContent.includes('変更できません'), 'existing case cannot switch to incomplete skid');
  click('cancel-edit');
  click('add'); field('id','incomplete_new'); field('description','blocked'); change('skid_id','0001XA'); quantity('00010',1);
  submit(); assert(el('editor').open && el('form-error').textContent.includes('新規ケース'), 'new incomplete case blocked even with valid quantity');
  click('cancel-edit');
  rowButton('ui_case','削除'); await save();
  assert(!row('ui_case'), 'case deletion persisted');
  frame.src='/catalog_viewer.html';
  await until(()=>frame.contentDocument?.getElementById('db-tabs')?.hidden===false && frame.contentDocument?.getElementById('dirty')?.textContent==='保存済み','return for mapping correction');
  await ready(); tab('suppliers'); rowButton('0001','編集'); field('supplier_name','Supplier A corrected'); submit();
  let correctionImpact=''; requests.length=0; w.confirm=text=>{correctionImpact=text;return false;};
  click('save'); await until(()=>!el('reload').disabled && Boolean(correctionImpact), 'mapping correction cancel preview');
  assert(correctionImpact.includes('Supplier A → Supplier A corrected')
    && !requests.some(r=>r.url.endsWith('/save')) && el('dirty').textContent.includes('未保存')
    && (await catalog()).suppliers['0001'].supplier_name==='Supplier A', 'cancel correction keeps draft and leaves server unchanged');
  requests.length=0; w.confirm=text=>{correctionImpact=text;return true;}; await save();
  assert(correctionImpact.includes('Supplier A → Supplier A corrected')
    && correctionImpact.includes('0001') && correctionImpact.includes('0003')
    && correctionImpact.includes('00001') && correctionImpact.includes('0001DZ1BC')
    && correctionImpact.includes('case') && correctionImpact.includes('PALLET-UI'), 'mapping correction confirms all affected categories');
  const corrected=await catalog();
  assert(corrected.suppliers['0001'].supplier_name==='Supplier A corrected'
    && corrected.suppliers['0003'].supplier_name==='Supplier A corrected'
    && corrected.parts['00001'].supplier_name==='Supplier A corrected'
    && corrected.skids['0001DZ1BC'].supplier_name==='Supplier A corrected'
    && corrected.cases.test_cases.case.supplier_name==='Supplier A corrected'
    && corrected.pallets['PALLET-UI'].suppliers.includes('Supplier A corrected'), 'mapping correction cascades and reloads');
  rowButton('0001','削除'); requests.length=0; click('save');
  await until(()=>!el('reload').disabled && el('feedback').className==='error','used mapping deletion must be refused');
  assert(requests.some(r=>r.url.endsWith('/skid-preview')) && !requests.some(r=>r.url.endsWith('/save'))
    && (await catalog()).suppliers['0001'], 'backend rejects used mapping deletion without saving');
  click('reload'); await until(()=>!el('reload').disabled && el('dirty').textContent==='保存済み','reload after rejected mapping deletion');
  result.textContent = 'PASS: 6 tabs; CRUD/normalization/safe text; skid preview cancel+confirm+delete; supplier filtering; server timestamps/history/affected cases; KEY2/read-only conditions; all candidates/order; blank+0 omission; integer limits; switch confirmation; incomplete new/switch blocked + existing editable; approval; isolation';
})().catch(error => { result.textContent = 'FAIL: '+error.stack; });
</script></body></html>"""


@unittest.skipUnless(
    EDGE.exists() and os.environ.get("PALLETIZER_RUN_BROWSER_TESTS") == "1",
    "Set PALLETIZER_RUN_BROWSER_TESTS=1 in a headless-Edge-capable environment",
)
class CatalogBrowserTest(CatalogFixture, unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        with patch.object(tempfile, "tempdir", str(project)):
            super().setUp()

    def test_real_browser_editing_workflow(self):
        patcher = patch.object(serve_viewer, "BASE_DIR", str(self.root / "box_research"))
        patcher.start()
        self.addCleanup(patcher.stop)

        class Handler(serve_viewer.ViewerRequestHandler):
            def log_message(self, format, *args):
                pass

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
        process = None
        connection = None
        browser_connection = None
        process_handles = []
        try:
            process = subprocess.Popen([
                str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run",
                "--disable-extensions", "--disable-background-networking",
                "--disable-features=msEdgeSidebarV2", "--no-proxy-server", "--no-startup-window",
                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                "--user-data-dir=" + str(self.root / "edge-profile"),
                "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            active_port = self.root / "edge-profile" / "DevToolsActivePort"
            deadline = time.monotonic() + 30
            while not active_port.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertTrue(active_port.exists(), "Edge CDP did not become ready; PID={}".format(process.pid))
            port = int(active_port.read_text().splitlines()[0])
            with urlopen("http://127.0.0.1:{}/json/version".format(port), timeout=5) as response:
                version = json.load(response)
            print("Edge CDP ready: {} (owned PID={})".format(version["Browser"], process.pid))
            browser_path = version["webSocketDebuggerUrl"].split(str(port), 1)[1]
            browser_connection = CdpConnection(port, browser_path)
            created = browser_connection.call("Target.createTarget", {"url": "about:blank"})
            with urlopen("http://127.0.0.1:{}/json/list".format(port), timeout=5) as response:
                targets = json.load(response)
            target = next(item for item in targets if item["id"] == created["targetId"])
            path = target["webSocketDebuggerUrl"].split(str(port), 1)[1]
            connection = CdpConnection(port, path)
            connection.call("Runtime.enable")
            connection.call("Page.enable")
            connection.call("Page.navigate", {
                "url": "http://127.0.0.1:{}/ui-check.html".format(server.server_address[1]),
            })
            deadline = time.monotonic() + 90
            output = None
            while time.monotonic() < deadline:
                output = connection.evaluate("document.getElementById('result')?.textContent")
                if output and output != "RUNNING":
                    break
                time.sleep(.1)
            self.assertTrue(output and output.startswith("PASS:"), output)
            syntax = connection.evaluate(
                "(async () => { const source = await (await fetch('/catalog_viewer.js')).text(); "
                "new Function(source); return 'catalog_viewer.js syntax OK'; })()"
            )
            print(syntax)
            print(output)
            data, _ = load_catalog(self.root)
            self.assertEqual(data["parts"]["00010"]["box_model_id"], "変更後モデル")
            self.assertNotIn("ui_case", data["cases"]["test_cases"])
            self.assertIn("テスト蓋", data["lids"])
        finally:
            if connection:
                connection.close()
            if browser_connection:
                try:
                    owned_processes = browser_connection.call("SystemInfo.getProcessInfo")["processInfo"]
                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                    kernel.OpenProcess.restype = ctypes.c_void_p
                    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                    for item in owned_processes:
                        handle = kernel.OpenProcess(0x00100000, False, int(item["id"]))
                        if handle:
                            process_handles.append((int(item["id"]), handle))
                    browser_connection.call("Browser.close")
                except (ConnectionError, OSError):
                    pass
                browser_connection.close()
                for pid, handle in process_handles:
                    try:
                        if kernel.WaitForSingleObject(handle, 5000) == 258:
                            subprocess.run(
                                ["powershell", "-NoProfile", "-Command",
                                 "Stop-Process -Id {} -Force -ErrorAction SilentlyContinue".format(pid)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                            kernel.WaitForSingleObject(handle, 5000)
                    finally:
                        kernel.CloseHandle(handle)
            if process:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Stop-Process -Id {} -Force -ErrorAction SilentlyContinue".format(process.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    process.wait(timeout=10)
                time.sleep(1)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
