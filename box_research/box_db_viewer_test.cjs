const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, 'box_db_viewer.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const master = JSON.parse(fs.readFileSync(path.join(__dirname, 'box_db.json'), 'utf8'));
const lids = JSON.parse(fs.readFileSync(path.join(__dirname, 'lid_db.json'), 'utf8'));

function element() {
  return {
    disabled: false,
    value: '',
    textContent: '',
    innerHTML: '',
    children: [],
    listeners: {},
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(event, listener) { this.listeners[event] = listener; },
    appendChild(child) { this.children.push(child); },
    append(...children) { this.children.push(...children); },
    reset() {},
    focus() {},
  };
}

async function viewer(options = {}) {
  const elements = new Map();
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) elements.set(id, element());
  const requests = [];
  const alerts = [];
  let database = structuredClone(master);
  const context = vm.createContext({
    document: {
      getElementById: id => elements.get(id),
      querySelectorAll: selector => selector === 'button, input, select, textarea'
        ? [...elements.values()] : [],
      createElement: element,
    },
    lucide: { createIcons() {} },
    console: { log() {}, warn() {}, error() {} },
    setTimeout() {},
    confirm: () => true,
    alert: message => alerts.push(message),
    fetch: async (url, init = {}) => {
      requests.push({ url, ...init });
      if (options.fetch) {
        const response = await options.fetch(url, init);
        if (response) return response;
      }
      if (url === '/api/lids') return { ok: true, json: async () => structuredClone(lids) };
      if (url === '/api/boxes') return { ok: true, json: async () => structuredClone(database) };
      if (url === '/api/save') {
        database = JSON.parse(init.body);
        return { ok: true, json: async () => ({ status: 'ok' }) };
      }
      throw new Error(`Unexpected request: ${url}`);
    },
  });
  Object.defineProperty(context, 'localStorage', {
    get() { throw new Error('localStorage must not be accessed'); },
  });
  const startup = vm.runInContext(script, context);
  assert.equal(elements.get('btn-direct-save').disabled, true);
  await startup;
  return {
    elements, requests, alerts,
    click: id => elements.get(id).listeners.click(),
    run: source => vm.runInContext(source, context),
    database: () => database,
  };
}

test('loads only the JSON master with no browser storage or hardcoded fallback', async () => {
  const app = await viewer();
  assert.doesNotMatch(script, /localStorage|defaultBoxDB|STORAGE_KEY/);
  assert.equal(app.elements.get('stat-total').textContent, Object.keys(master).length);
  assert.equal(app.run('Object.values(approvalState).every(Boolean)'), true);
  assert.equal(app.elements.get('btn-direct-save').disabled, false);
  const request = app.requests.find(request => request.url === '/api/boxes');
  assert.equal(request.cache, 'no-store');
  assert.deepEqual(JSON.parse(app.run('getApprovedJSON()')), master);
});

test('approval and edits stay in memory until explicit save, then survive reload', async () => {
  const app = await viewer();
  const id = Object.keys(master)[0];
  app.run(`currentBoxDB[${JSON.stringify(id)}].name = 'Edited box'`);
  await app.click('btn-select-tp-only');
  assert.equal(app.requests.some(request => request.method === 'POST'), false);
  await app.click('btn-direct-save');
  const saved = app.database();
  assert.equal(saved[id].name, 'Edited box');
  assert.equal(Object.values(saved).every(box => box.type === 'TP'), true);
  assert.ok(Object.keys(saved).length < Object.keys(master).length);
  app.run('currentBoxDB = {}; approvalState = {}');
  await app.click('btn-reset-db');
  assert.deepEqual(JSON.parse(app.run('getApprovedJSON()')), saved);
  assert.equal(app.alerts.length, 0);
});

test('reload discards unsaved changes and resets approval from the current master', async () => {
  const app = await viewer();
  app.run('currentBoxDB = {}; approvalState = {}');
  await app.click('btn-reset-db');
  assert.deepEqual(JSON.parse(app.run('getApprovedJSON()')), master);
  assert.equal(app.requests.filter(request => request.url === '/api/boxes').length, 2);
});

test('form edits and additions update the working database without writing the master', async () => {
  const app = await viewer();
  const id = Object.keys(master)[0];
  const submit = () => app.elements.get('form-box').listeners.submit({ preventDefault() {} });
  app.run(`openModal(${JSON.stringify(id)})`);
  app.elements.get('input-name').value = 'Edited in form';
  submit();
  assert.equal(app.run(`currentBoxDB[${JSON.stringify(id)}].name`), 'Edited in form');
  app.run('openModal()');
  for (const [field, value] of Object.entries({
    id: 'TEST-BOX', name: 'New box', type: 'TP', length: '400', width: '300',
    height: '200', fitting: '10', rib: '22', module: '1x1', desc: 'Test',
  })) app.elements.get(`input-${field}`).value = value;
  submit();
  assert.equal(app.run('currentBoxDB["TEST-BOX"].length'), 400);
  assert.equal(app.run('currentBoxDB["TEST-BOX"].width'), 300);
  assert.equal(app.run('approvalState["TEST-BOX"]'), true);
  assert.equal(app.requests.some(request => request.method === 'POST'), false);
  assert.deepEqual(app.database(), master);
  assert.equal(app.alerts.length, 0);
});

test('load failures are visible and block editing and saving until retry succeeds', async t => {
  for (const failure of ['network', 'http', 'json', 'shape']) {
    await t.test(failure, async () => {
      let failing = true;
      const app = await viewer({
        fetch: async url => {
          if (url !== '/api/boxes' || !failing) return;
          if (failure === 'network') throw new Error('offline');
          if (failure === 'http') return { ok: false, status: 500 };
          if (failure === 'json') return { ok: true, json: async () => { throw new SyntaxError('invalid JSON'); } };
          return { ok: true, json: async () => [] };
        },
      });
      assert.match(app.elements.get('db-status').textContent, /読み込みに失敗/);
      assert.equal(app.elements.get('btn-direct-save').disabled, true);
      assert.equal(app.elements.get('btn-open-modal').disabled, true);
      assert.equal(app.elements.get('btn-reset-db').disabled, false);
      assert.equal(app.run('Object.keys(currentBoxDB).length'), 0);
      failing = false;
      await app.click('btn-reset-db');
      assert.equal(app.elements.get('btn-direct-save').disabled, false);
      assert.deepEqual(JSON.parse(app.run('getApprovedJSON()')), master);
    });
  }
});

test('failed reload retains the working database and approval state', async () => {
  let failReload = false;
  const app = await viewer({
    fetch: async url => {
      if (url === '/api/boxes' && failReload) throw new Error('offline');
    },
  });
  await app.click('btn-select-tp-only');
  const before = app.run('getApprovedJSON()');
  failReload = true;
  await app.click('btn-reset-db');
  assert.equal(app.run('getApprovedJSON()'), before);
  assert.match(app.elements.get('db-status').textContent, /読み込みに失敗/);
});

test('save errors retain edits and never fall back to a download', async t => {
  for (const failure of ['network', 'http', 'api']) {
    await t.test(failure, async () => {
      const app = await viewer({
        fetch: async url => {
          if (url !== '/api/save') return;
          if (failure === 'network') throw new Error('offline');
          if (failure === 'http') return { ok: false, status: 500 };
          return { ok: true, json: async () => ({ status: 'error', message: 'write failed' }) };
        },
      });
      await app.click('btn-select-tp-only');
      const before = app.run('getApprovedJSON()');
      await app.click('btn-direct-save');
      assert.equal(app.run('getApprovedJSON()'), before);
      assert.equal(app.alerts.length, 1);
      assert.match(app.alerts[0], /保存に失敗/);
      assert.deepEqual(app.database(), master);
    });
  }
});
