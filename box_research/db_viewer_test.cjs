const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, 'db_viewer.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'db_viewer.js'), 'utf8');
const boxMaster = JSON.parse(fs.readFileSync(path.join(__dirname, 'box_db.json'), 'utf8'));
const lidMaster = JSON.parse(fs.readFileSync(path.join(__dirname, 'lid_db.json'), 'utf8'));

test('restored markup keeps original column counts/cards/filter buttons and no diagrams', () => {
  const boxPanel = html.match(/<section id="panel-boxes"[\s\S]*?<\/section>/)?.[0] || '';
  const lidPanel = html.match(/<section id="panel-lids"[\s\S]*?<\/section>/)?.[0] || '';
  const boxThCount = (boxPanel.match(/<th\b/g) || []).length;
  const lidThCount = (lidPanel.match(/<th\b/g) || []).length;
  assert.equal(boxThCount, 13);
  assert.equal(lidThCount, 10);
  ['stat-total', 'stat-approved', 'stat-approved-tp', 'stat-approved-nontp', 'stat-lid-count', 'stat-outer-fit', 'stat-inner-fit']
    .forEach(id => assert.match(html, new RegExp(`id="${id}"`)));
  ['data-filter="all"', 'data-filter="TP"', 'data-filter="NON_TP"', 'data-filter="approved"', 'data-filter="rejected"']
    .forEach(fragment => assert.match(html, new RegExp(fragment)));
  assert.equal(/<svg\b/i.test(html), false);
});

test('box search target keeps module_ratio and status toggle selector is present', () => {
  assert.match(script, /module_ratio/);
  assert.match(script, /data-toggle-status/);
});

test('compatible lid cards render no-lid note and L×W second line', async () => {
  const app = await setupApp();
  app.run('window.__dbViewer.openBoxDialog()');
  const container = app.elements.get('box-compatible-lids');
  const allText = flattenText(container);
  assert.match(allText, /無蓋はすべての箱で選択できます（互換蓋への登録は不要です）。|蓋DBに「無蓋」の定義がありません。/);
  const physicalLid = Object.values(lidMaster).find(lid => lid.type !== 'NONE');
  assert.ok(physicalLid);
  const expected = `${physicalLid.id} • ${physicalLid.length}×${physicalLid.width} mm`;
  assert.match(allText, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

class FakeClassList {
  constructor() { this.set = new Set(); }
  add(...names) { names.forEach(name => this.set.add(name)); }
  remove(...names) { names.forEach(name => this.set.delete(name)); }
  toggle(name, force) {
    if (force === true) this.set.add(name);
    else if (force === false) this.set.delete(name);
    else if (this.set.has(name)) this.set.delete(name);
    else this.set.add(name);
  }
  contains(name) { return this.set.has(name); }
}

class FakeElement {
  constructor(id = '') {
    this.id = id;
    this.disabled = false;
    this.value = '';
    this.textContent = '';
    this.innerHTML = '';
    this.checked = false;
    this.listeners = {};
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.attributes = {};
    this.classList = new FakeClassList();
    this.queryMap = {};
  }
  addEventListener(event, listener) { this.listeners[event] = listener; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  querySelectorAll(selector) { return this.queryMap[selector] || []; }
  setQuerySelectorAll(selector, elements) { this.queryMap[selector] = elements; }
  reset() { this.value = ''; }
  focus() {}
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  removeAttribute(name) { delete this.attributes[name]; }
  close() {}
}

function createElementsFromHtml() {
  const elements = new Map();
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) elements.set(id, new FakeElement(id));
  return elements;
}

function clone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function flattenText(node) {
  let out = node && node.textContent ? String(node.textContent) : '';
  const children = (node && Array.isArray(node.children)) ? node.children : [];
  for (const child of children) out += flattenText(child);
  return out;
}

async function setupApp(options = {}) {
  const elements = createElementsFromHtml();
  const boxRowEdit = new FakeElement('box-row-edit');
  const boxRowCheckbox = new FakeElement('box-row-checkbox');
  const lidRowEdit = new FakeElement('lid-row-edit');
  elements.get('boxes-body').setQuerySelectorAll('button,input,select', [boxRowEdit, boxRowCheckbox]);
  elements.get('lids-body').setQuerySelectorAll('button,input,select', [lidRowEdit]);
  const requests = [];
  const alerts = [];
  const confirms = [];
  let persistedBoxes = clone(boxMaster);
  let persistedLids = clone(lidMaster);
  const listeners = {};
  const windowObj = {
    addEventListener(type, listener) { listeners[type] = listener; },
  };
  const context = vm.createContext({
    document: {
      getElementById(id) { return elements.get(id) || new FakeElement(id); },
      createElement() { return new FakeElement(); },
      createTextNode(text) {
        const node = new FakeElement();
        node.textContent = String(text);
        return node;
      },
    },
    window: windowObj,
    history: { replaceState() {} },
    location: { hash: '#boxes' },
    alert(message) { alerts.push(message); },
    confirm(message) {
      confirms.push(message);
      if (typeof options.confirm === 'function') return options.confirm(message, confirms.length);
      return options.confirmResult ?? true;
    },
    fetch: async (url, init = {}) => {
      requests.push({ url, init });
      if (options.fetch) {
        const custom = await options.fetch(url, init);
        if (custom) return custom;
      }
      if (url === '/api/boxes') return { ok: true, json: async () => clone(persistedBoxes) };
      if (url === '/api/lids') return { ok: true, json: async () => clone(persistedLids) };
      if (url === '/api/lid_references') return { ok: true, json: async () => ({}) };
      if (url === '/api/box_references') return { ok: true, json: async () => options.boxReferences || {} };
      if (url === '/api/databases/save') {
        const payload = JSON.parse(init.body);
        if (payload.boxes) persistedBoxes = clone(payload.boxes);
        if (payload.lids) persistedLids = clone(payload.lids);
        return { ok: true, json: async () => ({ status: 'ok' }) };
      }
      throw new Error(`Unexpected fetch ${url}`);
    },
    setTimeout(callback) { callback(); },
  });
  vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  return {
    context,
    elements,
    requests,
    alerts,
    confirms,
    listeners,
    run(source) { return vm.runInContext(source, context); },
    boxRowEdit,
    lidRowEdit,
    persistedBoxes: () => persistedBoxes,
    persistedLids: () => persistedLids,
  };
}

test('initial load uses no-store and enables editing', async () => {
  const app = await setupApp();
  const noStoreTargets = app.requests
    .filter(r => ['/api/boxes', '/api/lids', '/api/lid_references', '/api/box_references'].includes(r.url))
    .map(r => r.init.cache);
  assert.deepEqual(noStoreTargets, ['no-store', 'no-store', 'no-store', 'no-store']);
  assert.equal(app.elements.get('btn-box-save').disabled, false);
  assert.equal(app.elements.get('btn-lid-save').disabled, false);
  assert.equal(app.run('window.__dbViewer.state.loaded'), true);
});

test('failed initial load blocks editing and retry succeeds', async () => {
  let fail = true;
  const app = await setupApp({
    fetch: async url => {
      if (fail && url === '/api/boxes') throw new Error('offline');
    },
  });
  assert.equal(app.run('window.__dbViewer.state.loaded'), false);
  assert.equal(app.elements.get('btn-box-save').disabled, true);
  assert.equal(app.elements.get('btn-lid-save').disabled, true);
  assert.match(app.elements.get('error-text').textContent, /offline/);
  fail = false;
  await app.run('window.__dbViewer.loadAll()');
  assert.equal(app.run('window.__dbViewer.state.loaded'), true);
  assert.equal(app.elements.get('btn-box-save').disabled, false);
});

test('beforeunload warning reflects dirty form and cancel clears it', async () => {
  const app = await setupApp();
  app.run('window.__dbViewer.openBoxDialog()');
  app.elements.get('box-name').value = 'tmp';
  app.elements.get('box-name').listeners.input();
  assert.equal(app.run('window.__dbViewer.state.formDirty.box'), true);
  let prevented = false;
  const unloadEvent = { preventDefault() { prevented = true; }, returnValue: '' };
  app.listeners.beforeunload(unloadEvent);
  assert.equal(prevented, true);
  app.run('window.__dbViewer.closeBoxDialog()');
  assert.equal(app.run('window.__dbViewer.state.formDirty.box'), false);
});

test('box save posts approved boxes only to unified endpoint', async () => {
  const app = await setupApp();
  const firstId = Object.keys(boxMaster)[0];
  app.run(`window.__dbViewer.state.approval[${JSON.stringify(firstId)}] = false`);
  await app.run('window.__dbViewer.saveBoxes()');
  const saveReq = app.requests.filter(r => r.url === '/api/databases/save').at(-1);
  const payload = JSON.parse(saveReq.init.body);
  assert.ok(payload.boxes);
  assert.equal(payload.lids, undefined);
  assert.equal(Object.prototype.hasOwnProperty.call(payload.boxes, firstId), false);
});

test('box save with unsaved lid dependency triggers joint save', async () => {
  const app = await setupApp();
  const boxId = Object.keys(boxMaster)[0];
  app.run(`
    window.__dbViewer.state.draft.lids['LID-NEW'] = {
      id:'LID-NEW', name:'new', type:'TP', length:100, width:100, thickness:1, fit_type:'外嵌め', color:'', description:''
    };
    window.__dbViewer.state.draft.boxes[${JSON.stringify(boxId)}].compatible_lids = ['LID-NEW'];
  `);
  await app.run('window.__dbViewer.saveBoxes()');
  const saveReq = app.requests.filter(r => r.url === '/api/databases/save').at(-1);
  const payload = JSON.parse(saveReq.init.body);
  assert.ok(payload.boxes);
  assert.ok(payload.lids);
  assert.ok(app.confirms.some(message => /同時保存/.test(message)));
});

test('rename/delete of referenced lids are blocked fail-closed', async () => {
  const app = await setupApp();
  const targetId = Object.keys(lidMaster)[0];
  app.run(`
    window.__dbViewer.state.lidReferencesLoaded = true;
    window.__dbViewer.state.lidReferences[${JSON.stringify(targetId)}] = ['case-1'];
  `);
  app.run(`window.__dbViewer.openLidDialog(${JSON.stringify(targetId)})`);
  app.elements.get('lid-id').value = `${targetId}-RENAMED`;
  app.elements.get('lid-name').value = 'renamed';
  app.elements.get('lid-length').value = '100';
  app.elements.get('lid-width').value = '90';
  app.elements.get('lid-thickness').value = '1';
  app.run('window.__dbViewer.submitLidForm({preventDefault(){}})');
  assert.match(app.alerts.at(-1), /ID変更できません/);
  app.run(`window.__dbViewer.deleteLid(${JSON.stringify(targetId)})`);
  assert.match(app.alerts.at(-1), /削除できません/);
});

test('referenced boxes cannot be deleted, renamed, deselected or excluded from any save', async () => {
  const targetId = Object.keys(boxMaster).find(id => boxMaster[id].type !== 'TP');
  assert.ok(targetId);
  const app = await setupApp({ boxReferences: { [targetId]: ['used.json', 'other.json'] } });
  const target = JSON.stringify(targetId);
  app.run(`window.__dbViewer.deleteBox(${target})`);
  assert.match(app.alerts.at(-1), /削除できません/);
  assert.match(app.alerts.at(-1), /used.json, other.json/);
  assert.equal(app.confirms.length, 0);
  assert.ok(app.run(`window.__dbViewer.state.draft.boxes[${target}]`));
  app.run(`window.__dbViewer.setBoxApproval(${target}, false)`);
  assert.equal(app.run(`window.__dbViewer.state.approval[${target}]`), true);
  assert.match(app.alerts.at(-1), /採用解除できません/);
  for (const button of ['btn-deselect-all', 'btn-select-tp-only']) {
    app.elements.get(button).listeners.click();
    assert.match(app.alerts.at(-1), /採用解除できません/);
    assert.equal(app.run('Object.values(window.__dbViewer.state.approval).every(v => v === true)'), true);
  }
  app.run(`window.__dbViewer.openBoxDialog(${target})`);
  app.elements.get('box-id').value = `${targetId}-RENAMED`;
  app.run('window.__dbViewer.submitBoxForm({preventDefault(){}})');
  assert.match(app.alerts.at(-1), /ID変更できません/);
  assert.ok(app.run(`window.__dbViewer.state.draft.boxes[${target}]`));
  app.run(`window.__dbViewer.state.approval[${target}] = false`);
  await app.run('window.__dbViewer.saveBoxes()');
  assert.match(app.alerts.at(-1), /保存対象から除外できません/);
  app.run('window.__dbViewer.state.boxLidSyncTouched = true; window.__dbViewer.state.draft.lids[Object.keys(window.__dbViewer.state.draft.lids)[0]].description = "changed"');
  await app.run('window.__dbViewer.saveLids()');
  assert.match(app.alerts.at(-1), /保存対象から除外できません/);
  assert.equal(app.requests.filter(r => r.url === '/api/databases/save').length, 0);
});

test('unreferenced box deletion and rename still work, existing IDs cannot be overwritten', async () => {
  const app = await setupApp();
  const [first, second] = Object.keys(boxMaster);
  app.run(`window.__dbViewer.openBoxDialog(${JSON.stringify(first)})`);
  app.elements.get('box-id').value = second;
  app.run('window.__dbViewer.submitBoxForm({preventDefault(){}})');
  assert.match(app.alerts.at(-1), /既に存在します/);
  app.elements.get('box-id').value = 'RENAMED-BOX';
  app.run('window.__dbViewer.submitBoxForm({preventDefault(){}})');
  assert.ok(app.run('window.__dbViewer.state.draft.boxes["RENAMED-BOX"]'));
  app.run('window.__dbViewer.deleteBox("RENAMED-BOX")');
  assert.equal(app.run('window.__dbViewer.state.draft.boxes["RENAMED-BOX"]'), undefined);
});

test('box reference failure blocks edits and retry loads references', async () => {
  let fail = true;
  const app = await setupApp({
    fetch: async url => {
      if (fail && url === '/api/box_references') return { ok: false, status: 500 };
    },
  });
  assert.equal(app.run('window.__dbViewer.state.loaded'), false);
  assert.equal(app.elements.get('btn-box-save').disabled, true);
  assert.match(app.elements.get('error-text').textContent, /箱参照取得に失敗/);
  fail = false;
  await app.run('window.__dbViewer.loadAll()');
  assert.equal(app.run('window.__dbViewer.state.boxReferencesLoaded'), true);
  app.run('window.__dbViewer.state.boxReferencesLoaded = false');
  app.run(`window.__dbViewer.setBoxApproval(${JSON.stringify(Object.keys(boxMaster)[0])}, false)`);
  assert.match(app.alerts.at(-1), /箱参照を取得できない/);
});

test('save non-2xx message is visibly surfaced to status banner', async () => {
  const app = await setupApp({
    fetch: async url => {
      if (url !== '/api/databases/save') return;
      return {
        ok: false,
        status: 500,
        json: async () => ({ status: 'error', message: 'Simulated failure' }),
      };
    },
  });
  await app.run('window.__dbViewer.saveBoxes()');
  assert.match(app.elements.get('save-feedback').textContent, /Simulated failure/);
  assert.match(app.alerts.at(-1), /Simulated failure/);
});

test('legacy approval actions and guarded reload are available', async () => {
  let confirmAnswer = false;
  const app = await setupApp({ confirm: () => confirmAnswer });
  app.elements.get('btn-deselect-all').listeners.click();
  assert.equal(app.run('Object.values(window.__dbViewer.state.approval).every(v => v === false)'), true);
  app.elements.get('btn-select-tp-only').listeners.click();
  assert.equal(app.run(`Object.entries(window.__dbViewer.state.draft.boxes).every(([id,box]) => window.__dbViewer.state.approval[id] === (box.type === 'TP'))`), true);
  app.elements.get('btn-select-all').listeners.click();
  assert.equal(app.run('Object.values(window.__dbViewer.state.approval).every(v => v === true)'), true);
  app.run('window.__dbViewer.state.formDirty.box = true');
  const beforeReloadCount = app.requests.filter(r => r.url === '/api/boxes').length;
  await app.elements.get('btn-reload-all').listeners.click();
  const afterCancelled = app.requests.filter(r => r.url === '/api/boxes').length;
  assert.equal(afterCancelled, beforeReloadCount);
  confirmAnswer = true;
  await app.elements.get('btn-reload-all').listeners.click();
  const afterReload = app.requests.filter(r => r.url === '/api/boxes').length;
  assert.equal(afterReload, beforeReloadCount + 1);
});

test('row editing controls unlock after save success and save failure', async () => {
  const app = await setupApp({
    fetch: async url => {
      if (url === '/api/databases/save') {
        return { ok: false, status: 500, json: async () => ({ status: 'error', message: 'fail once' }) };
      }
    },
  });
  app.run('window.__dbViewer.state.draft.lids["LID-NEW"]={id:"LID-NEW",name:"N",type:"TP",length:100,width:100,thickness:1,fit_type:"外嵌め",color:"",description:""};');
  app.run('window.__dbViewer.state.draft.boxes[Object.keys(window.__dbViewer.state.draft.boxes)[0]].compatible_lids=["LID-NEW"];');
  await app.run('window.__dbViewer.saveBoxes()');
  assert.equal(app.boxRowEdit.disabled, false);
  assert.equal(app.lidRowEdit.disabled, false);

  const app2 = await setupApp();
  app2.run('window.__dbViewer.state.draft.lids["LID-NEW"]={id:"LID-NEW",name:"N",type:"TP",length:100,width:100,thickness:1,fit_type:"外嵌め",color:"",description:""};');
  app2.run('window.__dbViewer.state.draft.boxes[Object.keys(window.__dbViewer.state.draft.boxes)[0]].compatible_lids=["LID-NEW"];');
  await app2.run('window.__dbViewer.saveBoxes()');
  assert.equal(app2.boxRowEdit.disabled, false);
  assert.equal(app2.lidRowEdit.disabled, false);
});
