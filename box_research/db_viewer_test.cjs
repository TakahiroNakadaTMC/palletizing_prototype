const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { Blob } = require('node:buffer');

const html = fs.readFileSync(path.join(__dirname, 'db_viewer.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'db_viewer.js'), 'utf8');
const boxMaster = JSON.parse(fs.readFileSync(path.join(__dirname, 'box_db.json'), 'utf8'));
const lidMaster = JSON.parse(fs.readFileSync(path.join(__dirname, 'lid_db.json'), 'utf8'));

test('markup keeps specification columns and display filters without box approval controls', () => {
  const boxPanel = html.match(/<section id="panel-boxes"[\s\S]*?<\/section>/)?.[0] || '';
  const lidPanel = html.match(/<section id="panel-lids"[\s\S]*?<\/section>/)?.[0] || '';
  const boxThCount = (boxPanel.match(/<th\b/g) || []).length;
  const lidThCount = (lidPanel.match(/<th\b/g) || []).length;
  assert.equal(boxThCount, 11);
  assert.equal(lidThCount, 10);
  ['stat-total', 'stat-tp', 'stat-nontp', 'stat-lid-count', 'stat-outer-fit', 'stat-inner-fit']
    .forEach(id => assert.match(html, new RegExp(`id="${id}"`)));
  ['data-filter="all"', 'data-filter="TP"', 'data-filter="NON_TP"']
    .forEach(fragment => assert.match(html, new RegExp(fragment)));
  assert.doesNotMatch(html, /採用|承認|stat-approved|btn-select-all|btn-deselect-all|btn-select-tp-only|data-filter="(?:approved|rejected)"/);
  assert.equal(/<svg\b/i.test(html), false);
});

test('box search keeps module_ratio without approval state or row toggles', () => {
  assert.match(script, /module_ratio/);
  assert.doesNotMatch(script, /approval|Approved|data-toggle-status|data-approve-id|採用|承認/);
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
  set innerHTML(value) { this.markup = value; this.children = []; }
  get innerHTML() { return this.markup; }
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
  click() { if (this.listeners.click) return this.listeners.click(); }
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
  const lidRowEdit = new FakeElement('lid-row-edit');
  elements.get('boxes-body').setQuerySelectorAll('button,input,select', [boxRowEdit]);
  elements.get('lids-body').setQuerySelectorAll('button,input,select', [lidRowEdit]);
  const filters = ['all', 'TP', 'NON_TP'].map(value => {
    const button = new FakeElement();
    button.setAttribute('data-filter', value);
    return button;
  });
  const copied = [];
  const downloads = [];
  const blobs = [];
  const revokedUrls = [];
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
      getElementById(id) { return elements.get(id) || null; },
      querySelectorAll(selector) { return selector === '.filter-tab' ? filters : []; },
      createElement(tag) {
        const element = new FakeElement();
        if (tag === 'a') element.click = () => downloads.push({ href: element.href, download: element.download });
        return element;
      },
      createTextNode(text) {
        const node = new FakeElement();
        node.textContent = String(text);
        return node;
      },
    },
    window: windowObj,
    navigator: { clipboard: { async writeText(text) { copied.push(text); } } },
    Blob,
    URL: {
      createObjectURL(blob) { blobs.push(blob); return `blob:test-${blobs.length}`; },
      revokeObjectURL(url) { revokedUrls.push(url); },
    },
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
    filters,
    copied,
    downloads,
    blobs,
    revokedUrls,
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

test('box save includes all registered types and edits regardless of display filters, then survives reload', async () => {
  const app = await setupApp();
  const firstId = Object.keys(boxMaster)[0];
  app.run(`window.__dbViewer.state.draft.boxes[${JSON.stringify(firstId)}].name = 'Edited box'`);
  app.filters[1].click();
  app.elements.get('box-search').value = 'no matching boxes';
  app.elements.get('box-search').listeners.input();
  assert.equal(app.elements.get('boxes-body').children.length, 0);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), true);
  await app.run('window.__dbViewer.saveBoxes()');
  const saveReq = app.requests.filter(r => r.url === '/api/databases/save').at(-1);
  const payload = JSON.parse(saveReq.init.body);
  assert.ok(payload.boxes);
  assert.equal(payload.lids, undefined);
  const expected = clone(boxMaster);
  expected[firstId].name = 'Edited box';
  assert.deepEqual(payload.boxes, expected);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), false);
  await app.run('window.__dbViewer.loadAll()');
  assert.deepEqual(JSON.parse(app.run('JSON.stringify(window.__dbViewer.state.draft.boxes)')), expected);
  assert.equal(app.alerts.length, 0);
});

test('new boxes persist and deleted unused boxes are removed only on explicit save', async () => {
  const app = await setupApp();
  app.run('window.__dbViewer.openBoxDialog()');
  assert.equal(app.elements.get('box-submit-label').textContent, '登録する');
  for (const [field, value] of Object.entries({
    id: 'TEST-BOX', name: 'New box', type: 'NON_TP', length: '400', width: '300',
    height: '200', fitting: '10', rib: '22', module: '', description: 'Test',
  })) app.elements.get(`box-${field}`).value = value;
  app.run('window.__dbViewer.submitBoxForm({preventDefault(){}})');
  const deletedId = Object.keys(boxMaster)[0];
  app.run(`window.__dbViewer.deleteBox(${JSON.stringify(deletedId)})`);
  assert.deepEqual(app.persistedBoxes(), boxMaster);
  assert.equal(app.requests.some(r => r.init.method === 'POST'), false);
  await app.run('window.__dbViewer.saveBoxes()');
  await app.run('window.__dbViewer.loadAll()');
  assert.equal(app.run('window.__dbViewer.state.draft.boxes["TEST-BOX"].length'), 400);
  assert.equal(app.run(`window.__dbViewer.state.draft.boxes[${JSON.stringify(deletedId)}]`), undefined);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), false);
  assert.equal(app.alerts.length, 0);
});

test('display filters and search leave statistics and both JSON exports complete', async () => {
  const app = await setupApp();
  const firstId = Object.keys(boxMaster)[0];
  app.run(`window.__dbViewer.state.draft.boxes[${JSON.stringify(firstId)}].name = 'Export edit'`);
  const tpCount = Object.values(boxMaster).filter(box => box.type === 'TP').length;
  assert.equal(app.elements.get('stat-total').textContent, String(Object.keys(boxMaster).length));
  assert.equal(app.elements.get('stat-tp').textContent, String(tpCount));
  assert.equal(app.elements.get('stat-nontp').textContent, String(Object.keys(boxMaster).length - tpCount));
  app.filters[1].click();
  assert.equal(app.elements.get('boxes-body').children.length, tpCount);
  app.filters[2].click();
  assert.equal(app.elements.get('boxes-body').children.length, Object.keys(boxMaster).length - tpCount);
  app.elements.get('box-search').value = 'no matching boxes';
  app.elements.get('box-search').listeners.input();
  assert.equal(app.elements.get('boxes-body').children.length, 0);
  await app.elements.get('btn-copy-json').click();
  app.elements.get('btn-download-json').click();
  const expected = clone(boxMaster);
  expected[firstId].name = 'Export edit';
  assert.deepEqual(JSON.parse(app.copied[0]), expected);
  assert.deepEqual(JSON.parse(await app.blobs[0].text()), expected);
  assert.deepEqual(app.downloads, [{ href: 'blob:test-1', download: 'box_db.json' }]);
  assert.deepEqual(app.revokedUrls, ['blob:test-1']);
  assert.equal(app.requests.some(r => r.init.method === 'POST'), false);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), true);
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
  assert.deepEqual(Object.keys(payload.boxes), Object.keys(boxMaster));
  assert.deepEqual(payload.boxes, app.persistedBoxes());
  assert.ok(app.confirms.some(message => /同時保存/.test(message)));
});

test('lid save confirms and persists all box edits and deletions in a joint save', async () => {
  let confirmAnswer = false;
  const app = await setupApp({ confirm: () => confirmAnswer });
  const firstId = Object.keys(boxMaster)[0];
  app.run(`
    const draft = window.__dbViewer.state.draft;
    draft.boxes[${JSON.stringify(firstId)}].name = 'Joint save edit';
    draft.lids[Object.keys(draft.lids)[0]].description = 'Lid edit';
  `);
  app.filters[1].click();
  await app.run('window.__dbViewer.saveLids()');
  assert.equal(app.requests.some(r => r.init.method === 'POST'), false);
  assert.match(app.confirms.at(-1), /登録箱すべて/);
  confirmAnswer = true;
  await app.run('window.__dbViewer.saveLids()');
  const payload = JSON.parse(app.requests.filter(r => r.url === '/api/databases/save').at(-1).init.body);
  assert.deepEqual(Object.keys(payload.boxes), Object.keys(boxMaster));
  assert.equal(payload.boxes[firstId].name, 'Joint save edit');
  assert.ok(payload.lids);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), false);
  app.run(`window.__dbViewer.deleteBox(${JSON.stringify(firstId)})`);
  app.run('window.__dbViewer.state.draft.lids[Object.keys(window.__dbViewer.state.draft.lids)[0]].description = "Second edit"');
  await app.run('window.__dbViewer.saveLids()');
  await app.run('window.__dbViewer.loadAll()');
  assert.equal(app.run(`window.__dbViewer.state.draft.boxes[${JSON.stringify(firstId)}]`), undefined);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), false);
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

test('referenced boxes cannot be deleted, renamed or excluded from any save', async () => {
  const targetId = Object.keys(boxMaster).find(id => boxMaster[id].type !== 'TP');
  assert.ok(targetId);
  const app = await setupApp({ boxReferences: { [targetId]: ['used.json', 'other.json'] } });
  const target = JSON.stringify(targetId);
  app.run(`window.__dbViewer.deleteBox(${target})`);
  assert.match(app.alerts.at(-1), /削除できません/);
  assert.match(app.alerts.at(-1), /used.json, other.json/);
  assert.equal(app.confirms.length, 0);
  assert.ok(app.run(`window.__dbViewer.state.draft.boxes[${target}]`));
  app.run(`window.__dbViewer.openBoxDialog(${target})`);
  app.elements.get('box-id').value = `${targetId}-RENAMED`;
  app.run('window.__dbViewer.submitBoxForm({preventDefault(){}})');
  assert.match(app.alerts.at(-1), /ID変更できません/);
  assert.ok(app.run(`window.__dbViewer.state.draft.boxes[${target}]`));
  app.run(`delete window.__dbViewer.state.draft.boxes[${target}]`);
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
  app.run(`window.__dbViewer.deleteBox(${JSON.stringify(Object.keys(boxMaster)[0])})`);
  assert.match(app.alerts.at(-1), /箱参照を取得できない/);
});

test('save failures visibly retain unsaved edits without downloading a fallback', async t => {
  for (const failure of ['network', 'http', 'api']) {
    await t.test(failure, async () => {
      const app = await setupApp({
        fetch: async url => {
          if (url !== '/api/databases/save') return;
          if (failure === 'network') throw new Error('Simulated failure');
          return {
            ok: failure !== 'http',
            status: 500,
            json: async () => ({ status: 'error', message: 'Simulated failure' }),
          };
        },
      });
      const firstId = JSON.stringify(Object.keys(boxMaster)[0]);
      app.run(`window.__dbViewer.state.draft.boxes[${firstId}].name = 'Retained edit'`);
      await app.run('window.__dbViewer.saveBoxes()');
      assert.match(app.elements.get('save-feedback').textContent, /Simulated failure/);
      assert.match(app.alerts.at(-1), /Simulated failure/);
      assert.equal(app.run(`window.__dbViewer.state.draft.boxes[${firstId}].name`), 'Retained edit');
      assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), true);
      assert.equal(app.elements.get('btn-box-save').disabled, false);
      assert.deepEqual(app.persistedBoxes(), boxMaster);
      assert.equal(app.downloads.length, 0);
    });
  }
});

test('lid-only save leaves the unchanged box master untouched', async () => {
  const app = await setupApp();
  app.run('window.__dbViewer.state.draft.lids[Object.keys(window.__dbViewer.state.draft.lids)[0]].description = "Lid only edit"');
  await app.run('window.__dbViewer.saveLids()');
  const payload = JSON.parse(app.requests.filter(r => r.url === '/api/databases/save').at(-1).init.body);
  assert.equal(payload.boxes, undefined);
  assert.ok(payload.lids);
  assert.deepEqual(app.persistedBoxes(), boxMaster);
  assert.equal(app.confirms.length, 0);
});

test('tab switching retains edits and guarded reload discards them only after confirmation', async () => {
  let confirmAnswer = false;
  const app = await setupApp({ confirm: () => confirmAnswer });
  const firstId = JSON.stringify(Object.keys(boxMaster)[0]);
  app.run(`window.__dbViewer.state.draft.boxes[${firstId}].name = 'Unsaved edit'`);
  app.elements.get('tab-lids').click();
  app.elements.get('tab-boxes').click();
  assert.equal(app.run(`window.__dbViewer.state.draft.boxes[${firstId}].name`), 'Unsaved edit');
  const beforeReloadCount = app.requests.filter(r => r.url === '/api/boxes').length;
  await app.elements.get('btn-reload-all').listeners.click();
  const afterCancelled = app.requests.filter(r => r.url === '/api/boxes').length;
  assert.equal(afterCancelled, beforeReloadCount);
  assert.equal(app.run(`window.__dbViewer.state.draft.boxes[${firstId}].name`), 'Unsaved edit');
  confirmAnswer = true;
  await app.elements.get('btn-reload-all').listeners.click();
  const afterReload = app.requests.filter(r => r.url === '/api/boxes').length;
  assert.equal(afterReload, beforeReloadCount + 1);
  assert.equal(app.run('window.__dbViewer.computeDirty().boxesDirty'), false);
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
