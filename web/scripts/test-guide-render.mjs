import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.guide-render-test-tmp');

// guide.md is a gitignored build artifact produced by `npm run sync-guide` (which the build runs).
// This test must survive its absence: CI runs `test:frontend` before the build, so a fresh checkout
// has no guide.md at all. The FAQ logic is therefore exercised on synthetic markdown, and the
// generated-guide assertions only run when the file happens to be present.
const guidePath = join(srcDir, 'guide.md');
const hasGuide = existsSync(guidePath);

// features/guide/render.ts imports the generated guide through Vite's `?raw` suffix; esbuild has
// no such loader, so implement the same contract here (the file contents as a default export).
const rawPlugin = {
  name: 'vite-raw',
  setup(pluginBuild) {
    pluginBuild.onResolve({ filter: /\?raw$/ }, (args) => ({
      path: resolve(args.resolveDir, args.path.replace(/\?raw$/, '')),
      namespace: 'vite-raw',
    }));
    pluginBuild.onLoad({ filter: /.*/, namespace: 'vite-raw' }, (args) => ({
      contents: `export default ${JSON.stringify(
        existsSync(args.path) ? readFileSync(args.path, 'utf8') : '',
      )};`,
      loader: 'js',
    }));
  },
};

// The guide page is pure string work (features/guide/render.ts), so it can be exercised under
// Node. The FAQ grouping is driven off the generated guide.md in production; the synthetic
// markdown here keeps the assertion independent of the generated content.
const entry = `
import {
  guideBodyFrom,
  guideBodyHtml,
  guideHtml,
  guideSummaryHtml,
  resetGuideCache,
} from './features/guide';

const synthetic = [
  '# 使用指南',
  '',
  '正文段落。',
  '',
  '## 常见问题',
  '',
  '**Q：问题一？**',
  '',
  '答案一。',
  '',
  '**Q：问题二？**',
  '',
  '答案二。',
  '',
  '## 附录',
  '',
  '尾部内容。',
].join('\\n');

export const cases = {
  escapeScript: guideSummaryHtml('<script>alert(1)</script>'),
  inlineCode: guideSummaryHtml('用 \`wb web\` 启动'),
  codeWithMarkup: guideSummaryHtml('\`a<b>\`'),
  faq: guideBodyFrom(synthetic),
  noFaq: guideBodyFrom('# 只有标题\\n\\n内容'),
  hasGuide: __HAS_GUIDE__,
  real: (() => { resetGuideCache(); return guideBodyHtml(); })(),
  cached: (() => { const first = guideBodyHtml(); resetGuideCache(); return first === guideBodyHtml(); })(),
  page: guideHtml(),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'guide-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
    plugins: [rawPlugin],
    define: { __HAS_GUIDE__: String(hasGuide) },
  });
  const bundlePath = join(tmpDir, 'guide-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { cases } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // <summary> must never let markup through; inline code is the only allowed formatting.
  assert.ok(!cases.escapeScript.includes('<script>'), 'summary escapes raw markup');
  assert.match(cases.escapeScript, /&lt;script&gt;/);
  assert.match(cases.inlineCode, /<code>wb web<\/code>/);
  assert.match(cases.codeWithMarkup, /<code>a&lt;b&gt;<\/code>/);

  // FAQ grouping: `**Q：**` entries become <details>, the trailing section is rendered after.
  assert.match(cases.faq, /<h3>常见问题<\/h3>/);
  assert.equal((cases.faq.match(/faq-item/g) ?? []).length, 2);
  assert.match(cases.faq, /<summary>问题一？<\/summary>/);
  assert.match(cases.faq, /<summary>问题二？<\/summary>/);
  assert.match(cases.faq, /faq-answer/);
  assert.match(cases.faq, /附录/);
  assert.ok(!cases.noFaq.includes('<h3>常见问题</h3>'), 'no FAQ heading without a FAQ section');

  // The generated guide (when present) still groups its FAQ, and the cache is resettable either way.
  if (cases.hasGuide) {
    assert.ok(cases.real.length > 0, 'real guide renders');
    assert.match(cases.real, /<h3>常见问题<\/h3>/);
  } else {
    console.log('  note: web/src/guide.md absent, skipping the generated-guide assertions');
  }
  assert.equal(cases.cached, true, 'resetGuideCache invalidates the module cache cleanly');

  // Page skeleton keeps the search box, directory container and empty hint.
  assert.match(cases.page, /id="guide-search"/);
  assert.match(cases.page, /id="guide-index-links"/);
  assert.match(cases.page, /id="guide-no-results"/);
  if (cases.hasGuide) assert.match(cases.page, /<h3>常见问题<\/h3>/);

  console.log('Guide pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
