const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const html = fs.readFileSync(path.join(__dirname, 'box_db_viewer.html'), 'utf8');

test('legacy box viewer directs to the integrated box tab without a separate editor', () => {
  assert.match(html, /http-equiv="refresh" content="0; url=\.\/db_viewer\.html#boxes"/);
  assert.match(html, /href="\.\/db_viewer\.html#boxes"/);
  assert.doesNotMatch(html, /<script\b|採用|承認/);
});
