import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.source-reader-render-test-tmp');
const entry = [
  "import { sourceReaderHtml } from './features/source-reader';",
  '',
  'export const html = sourceReaderHtml({',
  '  ok: true,',
  "  title: '**来源标题**',",
  "  source_id: 'notes/source.md',",
  "  date: '2026-09-16',",
  "  body: '**正文**\\n<script>alert(1)</script>',",
  "}, 'fallback');",
].join('\n');

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'source-reader-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const outFile = join(tmpDir, 'bundle.mjs');
  writeFileSync(outFile, result.outputFiles[0].text);
  const { html } = await import(pathToFileURL(outFile).href + '?t=' + Date.now());

  assert.match(html, /<h3><strong>来源标题<\/strong><\/h3>/);
  assert.match(html, /<p><strong>正文<\/strong>/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  console.log('Source reader render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
