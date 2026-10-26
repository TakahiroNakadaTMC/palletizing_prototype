const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, 'testcase_viewer.html'), 'utf8');
const defaults = html.match(/const DEFAULT_PALLET_SPEC = \{[\s\S]*?\n    \};/)[0];
const names = ['parseOverhangInput', 'resolvePalletSpecForEdit', 'getPalletSpecFromForm', 'sanitizePalletForSave'];
const functions = names.map(name => {
  const match = html.match(new RegExp(`    function ${name}\\([^]*?\\n    }`));
  assert.ok(match, name);
  return match[0];
});
const inputs = {'input-overhang-x': {value: '20'}, 'input-overhang-y': {value: '20'}};
const context = vm.createContext({document: {getElementById: id => inputs[id]}});
vm.runInContext(`${defaults}\n${functions.join('\n')}`, context);

const defaultsResult = context.resolvePalletSpecForEdit({pallet: {max_x_span: 1360, max_y_span: 1100}});
assert.equal(defaultsResult.max_overhang_x_mm, 20);
assert.equal(defaultsResult.max_overhang_y_mm, 20);

for (const [text, value] of [['0', 0], ['20', 20], ['12.5', 12.5], ['250', 250]]) {
  inputs['input-overhang-x'].value = text;
  const result = context.parseOverhangInput('input-overhang-x', 'X');
  assert.equal(result.ok, true);
  assert.equal(result.value, value);
}
for (const text of ['', ' ', '-1', 'NaN', 'Infinity', 'text']) {
  inputs['input-overhang-x'].value = text;
  assert.equal(context.parseOverhangInput('input-overhang-x', 'X').ok, false);
  assert.equal(context.getPalletSpecFromForm({}).ok, false);
}
inputs['input-overhang-x'].value = '0';
inputs['input-overhang-y'].value = '12.5';
const base = {length: 1100, width: 900, max_height: 1000, max_small_edge_overhang_mm: 30, custom: 'keep'};
const form = context.getPalletSpecFromForm(base);
assert.equal(form.ok, true);
assert.equal(form.value.max_overhang_x_mm, 0);
assert.equal(form.value.max_overhang_y_mm, 12.5);
assert.equal(form.value.length, 1100);
assert.equal(form.value.custom, 'keep');
assert.equal('max_small_edge_overhang_mm' in form.value, false);
assert.equal(base.max_small_edge_overhang_mm, 30);

const saved = context.sanitizePalletForSave(base);
assert.equal(saved.hadRetired, true);
assert.equal('max_small_edge_overhang_mm' in saved.pallet, false);
assert.equal(saved.pallet.max_overhang_x_mm, 20);
assert.equal(saved.pallet.max_overhang_y_mm, 20);
assert.equal(saved.pallet.custom, 'keep');
for (const key of ['max_overhang_x_mm', 'max_overhang_y_mm']) {
  for (const value of ['', ' ', null, false, -1, Infinity, NaN]) {
    const result = context.sanitizePalletForSave({[key]: value}).pallet[key];
    assert.ok(!Number.isFinite(result) || result < 0, `${key}: ${value} must be rejected before save`);
  }
}
assert.equal(context.sanitizePalletForSave({max_overhang_x_mm: 0}).pallet.max_overhang_x_mm, 0);
assert.equal(context.resolvePalletSpecForEdit({pallet: {max_overhang_x_mm: -1}}).max_overhang_x_mm, -1);
for (const id of ['input-overhang-x', 'input-overhang-y']) {
  const input = html.match(new RegExp(`<input[^>]*id="${id}"[^>]*>`))[0];
  assert.ok(input.includes('step="any"'));
  assert.ok(!input.includes('max="'));
}
console.log('PASS: overhang form defaults, independent axes, decimal/zero settings, validation, migration, and preserved fields');
