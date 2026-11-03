const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, 'testcase_viewer.html'), 'utf8');
const defaults = html.match(/const DEFAULT_PALLET_SPEC = \{[\s\S]*?\n    \};/)[0];
const names = [
  'parsePalletNumericInput',
  'toFiniteNumberStrict',
  'pickPositiveFinite',
  'resolvePalletSpecForEdit',
  'getPalletSpecFromForm',
  'sanitizePalletForSave'
];
const blocks = names.map(name => {
  const match = html.match(new RegExp(`    function ${name}\\([^]*?\\n    }`));
  assert.ok(match, name);
  return match[0];
});

const inputs = {
  'input-pallet-length': { value: '1200' },
  'input-pallet-width': { value: '1000' },
  'input-pallet-height': { value: '130' },
  'input-pallet-max-height': { value: '1200' },
  'input-pallet-max-x-span': { value: '1360' },
  'input-pallet-max-y-span': { value: '1100' },
};

const context = vm.createContext({ document: { getElementById: id => inputs[id] } });
vm.runInContext(`${defaults}\n${blocks.join('\n')}`, context);
const normalize = value => JSON.parse(JSON.stringify(value));

const resolved = context.resolvePalletSpecForEdit({ pallet: { length: 1250, max_y_span: 1080 } });
assert.equal(resolved.length, 1250);
assert.equal(resolved.width, 1000);
assert.equal(resolved.height, 130);
assert.equal(resolved.max_x_span, 1360);
assert.equal(resolved.max_y_span, 1080);
assert.equal(resolved.max_height, 1200);

for (const id of Object.keys(inputs)) inputs[id].value = '100';
inputs['input-pallet-length'].value = '1200';
inputs['input-pallet-width'].value = '1000';
inputs['input-pallet-height'].value = '130';
inputs['input-pallet-max-height'].value = '1200';
inputs['input-pallet-max-x-span'].value = '1360';
inputs['input-pallet-max-y-span'].value = '1100';
const formOk = context.getPalletSpecFromForm();
assert.equal(formOk.ok, true);
assert.deepEqual(normalize(formOk.value), {
  length: 1200,
  width: 1000,
  height: 130,
  max_x_span: 1360,
  max_y_span: 1100,
  max_height: 1200,
});

inputs['input-pallet-length'].value = '999';
inputs['input-pallet-width'].value = '1000';
assert.equal(context.getPalletSpecFromForm().ok, false);

inputs['input-pallet-length'].value = '1200';
inputs['input-pallet-width'].value = '1000';
inputs['input-pallet-max-x-span'].value = '1090';
inputs['input-pallet-max-y-span'].value = '1100';
assert.equal(context.getPalletSpecFromForm().ok, false);

const sanitized = context.sanitizePalletForSave({
  length: '1200',
  width: '1000',
  height: '130',
  max_x_span: '1360',
  max_y_span: '1100',
  max_height: '1200',
  max_overhang_x_mm: 20,
  min_y_span: 800,
});
assert.equal(sanitized.hadRetired, true);
assert.deepEqual(normalize(sanitized.pallet), {
  length: 1200,
  width: 1000,
  height: 130,
  max_x_span: 1360,
  max_y_span: 1100,
  max_height: 1200,
});

assert.equal(context.toFiniteNumberStrict(true), null);
assert.equal(context.toFiniteNumberStrict(false), null);
assert.equal(context.toFiniteNumberStrict(''), null);
assert.equal(context.toFiniteNumberStrict('Infinity'), null);
assert.equal(context.toFiniteNumberStrict('12.5'), 12.5);

console.log('PASS: pallet UI six-field config, axis checks, retired-key cleanup, bool rejection');
