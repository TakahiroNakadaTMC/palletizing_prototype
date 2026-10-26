const fs = require('fs');
const path = require('path');
const vm = require('vm');
const test = require('node:test');
const assert = require('node:assert/strict');

function extractFunctionBlock(source, startToken, endToken) {
  const s = source.indexOf(startToken);
  if (s < 0) throw new Error(`start token not found: ${startToken}`);
  const e = source.indexOf(endToken, s);
  if (e < 0) throw new Error(`end token not found: ${endToken}`);
  return source.slice(s, e);
}

function loadResolveGuideConfigFromIndex(filePath) {
  const source = fs.readFileSync(filePath, 'utf8');
  const block = extractFunctionBlock(source, 'function hasOwn(obj, key)', 'function updateGuideLegend(data)');
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${block}\nthis.resolveGuideConfig = resolveGuideConfig;`, context);
  return context.resolveGuideConfig;
}

function loadResolveGuideConfigFromTemplatePy(filePath) {
  const source = fs.readFileSync(filePath, 'utf8');
  let block = extractFunctionBlock(source, 'function hasOwn(obj, key) {{', 'function updateGuideLegend(data) {{');
  block = block.replace(/\{\{/g, '{').replace(/\}\}/g, '}');
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${block}\nthis.resolveGuideConfig = resolveGuideConfig;`, context);
  return context.resolveGuideConfig;
}

const root = path.resolve(__dirname, '..');
const resolvers = [
  {
    name: 'index.html',
    resolveGuideConfig: loadResolveGuideConfigFromIndex(path.join(__dirname, 'index.html')),
  },
  {
    name: 'visualize.py template',
    resolveGuideConfig: loadResolveGuideConfigFromTemplatePy(path.join(__dirname, 'visualize.py')),
  }
];

for (const entry of resolvers) {
  const fn = entry.resolveGuideConfig;

  test(`${entry.name}: metadata missing -> fail closed`, () => {
    const cfg = fn({ pallet: {}, boxes: [{ box_id: 'TP-362', lid_id: '', dimensions: { width: 670, length: 300 } }] });
    assert.equal(cfg.metadataReady, false);
    assert.equal(cfg.exceptionAxisX, false);
    assert.equal(cfg.exceptionAxisY, false);
  });

  test(`${entry.name}: mixed input variants -> fail closed`, () => {
    const cfg = fn({
      input_box_variants: [{ box_id: 'TP-362', lid_id: '' }, { box_id: 'TP-331', lid_id: '' }],
      boxes: [{ box_id: 'TP-362', lid_id: '', dimensions: { width: 700, length: 700 } }],
      pallet: {}
    });
    assert.equal(cfg.metadataReady, false);
    assert.equal(cfg.exceptionAxisX, false);
    assert.equal(cfg.exceptionAxisY, false);
  });

  test(`${entry.name}: sole variant with empty lid id can qualify`, () => {
    const cfg = fn({
      input_box_variants: [{ box_id: 'TP-362', lid_id: '' }],
      boxes: [{ box_id: 'TP-362', lid_id: '', dimensions: { width: 670, length: 669.999 } }],
      pallet: {}
    });
    assert.equal(cfg.metadataReady, true);
    assert.equal(cfg.identityMatched, true);
    assert.equal(cfg.exceptionAxisX, true);
    assert.equal(cfg.exceptionAxisY, false);
  });

  test(`${entry.name}: identity mismatch blocks exception`, () => {
    const cfg = fn({
      input_box_variants: [{ box_id: 'TP-362', lid_id: '' }],
      boxes: [{ box_id: 'TP-362', lid_id: 'LID-010', dimensions: { width: 700, length: 700 } }],
      pallet: {}
    });
    assert.equal(cfg.metadataReady, true);
    assert.equal(cfg.identityMatched, false);
    assert.equal(cfg.exceptionAxisX, false);
    assert.equal(cfg.exceptionAxisY, false);
  });

  test(`${entry.name}: 669.999 vs 670 threshold`, () => {
    const cfg = fn({
      input_box_variants: [{ box_id: 'TP-362', lid_id: 'LID-X' }],
      boxes: [{ box_id: 'TP-362', lid_id: 'LID-X', dimensions: { width: 669.999, length: 670 } }],
      pallet: {}
    });
    assert.equal(cfg.exceptionAxisX, false);
    assert.equal(cfg.exceptionAxisY, true);
  });

  test(`${entry.name}: uses actual max spans and clips normal guide to cap`, () => {
    const cfg = fn({
      pallet: {
        length: 1200,
        width: 1000,
        max_overhang_x_mm: 200,
        max_overhang_y_mm: 120,
        max_x_span: 1260,
        max_y_span: 1020,
      },
      input_box_variants: [{ box_id: 'TP-362', lid_id: '' }],
      boxes: [{ box_id: 'TP-362', lid_id: '', dimensions: { width: 700, length: 700 } }]
    });

    assert.equal(cfg.capSpanX, 1260);
    assert.equal(cfg.capSpanY, 1020);
    assert.equal(cfg.capMinX, -30);
    assert.equal(cfg.capMaxX, 1230);
    assert.equal(cfg.rawNormalMinX, -200);
    assert.equal(cfg.rawNormalMaxX, 1400);
    assert.equal(cfg.normalMinX, -30);
    assert.equal(cfg.normalMaxX, 1230);
    assert.equal(cfg.normalMinY, -10);
    assert.equal(cfg.normalMaxY, 1010);
  });

  test(`${entry.name}: X/Y zero independent`, () => {
    const cfg = fn({
      pallet: { max_overhang_x_mm: 0, max_overhang_y_mm: 0, max_x_span: 1360, max_y_span: 1100 },
      input_box_variants: [{ box_id: 'TP-362', lid_id: '' }],
      boxes: [{ box_id: 'TP-362', lid_id: '', dimensions: { width: 670, length: 670 } }]
    });
    assert.equal(Math.abs(cfg.normalMinX), 0);
    assert.equal(cfg.normalMaxX, 1200);
    assert.equal(Math.abs(cfg.normalMinY), 0);
    assert.equal(cfg.normalMaxY, 1000);
  });
}
