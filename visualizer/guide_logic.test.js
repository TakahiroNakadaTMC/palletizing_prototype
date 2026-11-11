const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

function extractFunctionBlock(source, startToken, endToken) {
  const s = source.indexOf(startToken);
  if (s < 0) throw new Error(`start token not found: ${startToken}`);
  const e = source.indexOf(endToken, s);
  if (e < 0) throw new Error(`end token not found: ${endToken}`);
  return source.slice(s, e);
}

for (const filename of ['visualize.py', 'index.html']) {
const source = fs.readFileSync(path.join(__dirname, filename), 'utf8');
const decode = text => filename.endsWith('.py')
  ? text.replace(/\{\{/g, '{').replace(/\}\}/g, '}') : text;
const block = decode(extractFunctionBlock(source, 'function hasOwn(obj, key)', 'function updateGuideLegend(data)'));
const context = {};
vm.createContext(context);
vm.runInContext(`${block}\nthis.resolveGuideConfig = resolveGuideConfig;`, context);
const resolveGuideConfig = context.resolveGuideConfig;

test(`${filename}: defaults: pallet height is 130 and max spans are 1360/1100`, () => {
  const cfg = resolveGuideConfig({ pallet: {} });
  assert.equal(cfg.pW, 1200);
  assert.equal(cfg.pL, 1000);
  assert.equal(cfg.pH, 130);
  assert.equal(cfg.maxH, 1200);
  assert.equal(cfg.capSpanX, 1360);
  assert.equal(cfg.capSpanY, 1100);
});

test(`${filename}: uses per-case six pallet fields directly`, () => {
  const cfg = resolveGuideConfig({
    pallet: { length: 1300, width: 900, height: 140, max_x_span: 1500, max_y_span: 1000, max_height: 1250 },
  });
  assert.equal(cfg.pW, 1300);
  assert.equal(cfg.pL, 900);
  assert.equal(cfg.pH, 140);
  assert.equal(cfg.maxH, 1250);
  assert.equal(cfg.capSpanX, 1500);
  assert.equal(cfg.capSpanY, 1000);
});

test(`${filename}: limit frame is centered from per-case spans`, () => {
  const cfg = resolveGuideConfig({
    pallet: { length: 1200, width: 1000, max_x_span: 1260, max_y_span: 1020 },
  });
  assert.equal(cfg.capMinX, -30);
  assert.equal(cfg.capMaxX, 1230);
  assert.equal(cfg.capMinY, -10);
  assert.equal(cfg.capMaxY, 1010);
});

test(`${filename}: explicit invalid values throw clear errors`, () => {
  assert.throws(() => resolveGuideConfig({ pallet: { height: 0 } }), /pallet\.height/);
  assert.throws(() => resolveGuideConfig({ pallet: { max_x_span: 'abc' } }), /pallet\.max_x_span/);
  assert.throws(() => resolveGuideConfig({ pallet: { max_y_span: false } }), /pallet\.max_y_span|真偽値/);
  assert.throws(() => resolveGuideConfig({ pallet: { max_height: null } }), /pallet\.max_height/);
  assert.throws(() => resolveGuideConfig({ pallet: { height: [130] } }), /pallet\.height/);
});

test(`${filename}: axis convention violations throw`, () => {
  assert.throws(() => resolveGuideConfig({
    pallet: { length: 1000, width: 1200, height: 130, max_x_span: 1360, max_y_span: 1100, max_height: 1200 },
  }), /length.*width/);
  assert.throws(() => resolveGuideConfig({
    pallet: { length: 1200, width: 1000, height: 130, max_x_span: 1000, max_y_span: 1100, max_height: 1200 },
  }), /max_x_span.*max_y_span/);
});

test(`${filename}: full height and maximum frame fit all four views`, () => {
  const camera = decode(extractFunctionBlock(source, 'function resetViewTransform()', 'function renderLoop()'));
  const fitContext = {window: {innerWidth: 1000, innerHeight: 700}};
  vm.createContext(fitContext);
  vm.runInContext(`${block}
    let currentData, viewMode, zoom, panX, panY;
    let angleX = 35 * Math.PI / 180, angleZ = 45 * Math.PI / 180;
    ${camera}
    this.fit = (data, mode) => {
      currentData = data; viewMode = mode; resetViewTransform();
      const cfg = resolveGuideConfig(data);
      const halfX = Math.max(cfg.pW, cfg.capSpanX) / 2;
      const halfY = Math.max(cfg.pL, cfg.capSpanY) / 2;
      const points = [];
      for (const x of [-halfX, halfX]) for (const y of [-halfY, halfY])
        for (const z of [-cfg.pH, cfg.maxH])
          points.push(project3D(cfg.pW / 2 + x, cfg.pL / 2 + y, z));
      return points;
    };`, fitContext);
  for (const mode of ['iso', 'top', 'front', 'side']) {
    const points = fitContext.fit({pallet: {
      length: 6000, width: 4000, height: 5000,
      max_x_span: 6500, max_y_span: 4500, max_height: 3000,
    }}, mode);
    for (const point of points) {
      assert.ok(point.x >= 0 && point.x <= 1000, `${mode}: x=${point.x}`);
      assert.ok(point.y >= 0 && point.y <= 700, `${mode}: y=${point.y}`);
    }
  }
});

test(`${filename}: physical pallet drawing uses configured height below origin`, () => {
  const draw = decode(extractFunctionBlock(source, 'function drawGridAndPallet()', 'function drawGuides()'));
  let geometry;
  const drawingContext = {
    currentData: {pallet: {height: 220}},
    ctx: new Proxy({}, {get: () => () => {}}),
    project3D: (x, y) => ({x, y}),
    drawSolidBox: (...args) => { geometry = args.slice(0, 6); },
  };
  vm.createContext(drawingContext);
  vm.runInContext(`${block}\n${draw}\ndrawGridAndPallet();`, drawingContext);
  assert.deepEqual(geometry, [0, 0, -220, 1200, 1000, 220]);
});
}

test('current editor and viewer JavaScript parses in full', () => {
  for (const filename of [
    path.join(__dirname, 'index.html'),
    path.join(__dirname, '..', 'box_research', 'catalog_viewer.html'),
  ]) {
    const html = fs.readFileSync(filename, 'utf8');
    for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
      if (match[1].trim()) new vm.Script(match[1], {filename});
    }
  }
  for (const filename of [
    path.join(__dirname, 'result_identity.js'),
    path.join(__dirname, '..', 'box_research', 'catalog_viewer.js'),
  ]) {
    new vm.Script(fs.readFileSync(filename, 'utf8'), {filename});
  }
});
