const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'platform_features.js'),
    'utf8',
);
const window = {};
const document = { addEventListener() {} };
vm.runInNewContext(script, { window, document });

test('live badge counts use 1-9, then 9+, and hide zero text', () => {
    const formatBadgeCount = window.vgrowhubFormatBadgeCount;
    assert.equal(formatBadgeCount(0), '0');
    assert.equal(formatBadgeCount(1), '1');
    assert.equal(formatBadgeCount(9), '9');
    assert.equal(formatBadgeCount(10), '9+');
    assert.equal(formatBadgeCount(-2), '0');
});
