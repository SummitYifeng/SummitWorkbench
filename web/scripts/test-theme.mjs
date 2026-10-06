import assert from 'node:assert/strict';
import fs from 'node:fs';
import { transform } from 'esbuild';

const root = new URL('../', import.meta.url);
const source = fs.readFileSync(new URL('src/theme.ts', root), 'utf8');
const { code } = await transform(source, { loader: 'ts', format: 'esm' });
const theme = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

let preferenceValue = null;
let storageAvailable = true;
let systemDark = false;
let mediaListener;
let changeListener;
class MockSelect {
  constructor(id, value) { this.id = id; this.value = value; }
}
globalThis.HTMLSelectElement = MockSelect;
const rootElement = { dataset: {} };
globalThis.document = {
  documentElement: rootElement,
  addEventListener(type, listener) { if (type === 'change') changeListener = listener; },
};
globalThis.window = {
  get localStorage() {
    if (!storageAvailable) throw new Error('storage blocked');
    return {
      getItem() { return preferenceValue; },
      setItem(_key, value) { if (!storageAvailable) throw new Error('storage blocked'); preferenceValue = value; },
    };
  },
  matchMedia() {
    return {
      get matches() { return systemDark; },
      addEventListener(_type, listener) { mediaListener = listener; },
    };
  },
};

assert.equal(theme.getThemePreference(), 'system', 'missing preference defaults to system');
preferenceValue = 'sepia';
assert.equal(theme.getThemePreference(), 'system', 'invalid preference falls back to system');
theme.initializeTheme();
assert.equal(rootElement.dataset.theme, 'light', 'system preference initially follows light system');
systemDark = true;
mediaListener();
assert.equal(rootElement.dataset.theme, 'dark', 'system changes are followed in system mode');
changeListener({ target: new MockSelect('theme-preference', 'light') });
assert.equal(rootElement.dataset.theme, 'light', 'manual preference applies immediately');
assert.equal(preferenceValue, 'light', 'manual preference is persisted');
systemDark = false;
mediaListener();
assert.equal(rootElement.dataset.theme, 'light', 'system changes do not override manual selection');
changeListener({ target: new MockSelect('theme-preference', 'system') });
assert.equal(rootElement.dataset.theme, 'light', 'returning to system applies current system appearance');
preferenceValue = 'dark';
theme.initializeTheme();
assert.equal(rootElement.dataset.theme, 'dark', 'saved preference is restored on initialization');
storageAvailable = false;
assert.equal(theme.getThemePreference(), 'system', 'unavailable storage safely defaults to system');
assert.equal(theme.setThemePreference('dark'), 'dark', 'page can switch when storage writes fail');
assert.equal(rootElement.dataset.theme, 'dark', 'storage failure does not block applying theme');

function declarations(block) {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[\da-fA-F]{3,8})/g)].map((m) => [m[1], m[2]]));
}
function rgb(hex) {
  let value = hex.slice(1);
  if (value.length === 3) value = [...value].map((char) => char + char).join('');
  return [0, 2, 4].map((index) => Number.parseInt(value.slice(index, index + 2), 16) / 255);
}
function luminance(hex) {
  const channels = rgb(hex).map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}
function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
function assertContrast(tokens, fg, bg, minimum, themeName) {
  const ratio = contrast(tokens[fg], tokens[bg]);
  assert.ok(ratio >= minimum, `${themeName}: ${fg} on ${bg} contrast ${ratio.toFixed(2)}:1 < ${minimum}:1`);
}

const tokensCss = fs.readFileSync(new URL('src/theme-tokens.css', root), 'utf8');
const lightTokens = declarations(tokensCss.slice(tokensCss.indexOf(':root {'), tokensCss.indexOf(':root[data-theme="light"]')));
const darkStart = tokensCss.indexOf(':root[data-theme="dark"] {');
const darkTokens = declarations(tokensCss.slice(darkStart, tokensCss.indexOf('\n}', darkStart)));
for (const [name, tokens] of [['light', lightTokens], ['dark', darkTokens]]) {
  const checks = [['fg', 'bg'], ['muted', 'bg'], ['fg', 'card'], ['muted', 'card'], ['on-accent', 'accent'], ['accent', 'accent-soft'], ['ok', 'ok-soft'], ['warn', 'warn-soft'], ['bad', 'bad-soft'], ['on-bad', 'bad']];
  for (const [fg, bg] of checks) {
    assertContrast(tokens, fg, bg, 4.5, name);
  }
  assertContrast(tokens, 'control-border', 'card', 3, name);
  console.log(`${name} contrast ratios: ${checks.map(([fg, bg]) => `${fg}/${bg} ${contrast(tokens[fg], tokens[bg]).toFixed(2)}:1`).join(' · ')} · control border ${contrast(tokens['control-border'], tokens.card).toFixed(2)}:1`);
}

const indexHtml = fs.readFileSync(new URL('index.html', root), 'utf8');
assert.match(indexHtml, /swb:theme-preference/, 'startup script reads preference before first paint');
assert.match(fs.readFileSync(new URL('scripts/build.mjs', root), 'utf8'), /\['index\.html',/, 'HTML startup script participates in build identity');
console.log('Theme behavior and contrast tests passed');
