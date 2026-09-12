import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.ask-render-test-tmp');

// The answer/source renderers in features/ask/render.ts are pure string functions. They used to
// be pinned only by proximity regexes over legacy-main.ts (`renderAskAnswer`,
// `仅召回、未在回答中引用的材料`, `cited_source_ids`, `answer.conflicts`); assert the real output.
const entry = `
import { askSourceButton, renderAskAnswer } from './features/ask';

const answer = (over: Record<string, unknown> = {}) => ({
  summary: '摘要', facts: [], suggestions: [], conflicts: [], unanswerable: false, ...over,
});

export const cases = {
  escaped: askSourceButton('proj/<a>', '标签<&>'),
  simple: askSourceButton('projects/P1'),
  plain: renderAskAnswer(answer(), [], []),
  unanswerable: renderAskAnswer(answer({ unanswerable: true }), [], []),
  facts: renderAskAnswer(answer({ facts: [
    { text: '事实<一>', source_id: 'projects/P1' },
    { text: '事实二', source_id: 'projects/P2' },
  ] }), ['projects/P1', 'projects/P2'], ['projects/P1', 'projects/P2']),
  recalledOnly: renderAskAnswer(answer(), ['projects/P1'], ['projects/P1', 'projects/P9']),
  conflicts: renderAskAnswer(answer({ conflicts: [
    { topic: '冲突<题>', sides: [
      { position: '甲', source_id: 'projects/P1' },
      { position: '乙', source_id: 'projects/P2' },
    ] },
  ] }), [], []),
  suggestions: renderAskAnswer(answer({ suggestions: ['建议一'] }), [], []),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'ask-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'ask-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { cases } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // Source buttons escape both the id and the label, and default the label to the id.
  assert.match(cases.escaped, /data-source-id="proj\/&lt;a&gt;"/);
  assert.match(cases.escaped, />标签&lt;&amp;&gt;<\/button>/);
  assert.ok(!cases.escaped.includes('<a>'), 'raw markup never reaches the source button');
  assert.match(cases.simple, /data-source-id="projects\/P1"[^>]*>projects\/P1<\/button>/);

  // Plain answer: summary only, no optional sections.
  assert.match(cases.plain, /<p class="answer-summary"><strong>摘要<\/strong><\/p>/);
  assert.ok(!cases.plain.includes('<h4>'), 'no sections without facts/conflicts/suggestions');

  // Unanswerable answers carry an explicit warning.
  assert.match(cases.unanswerable, /当前来源不足以回答/);
  assert.match(cases.unanswerable, /不会被当作确定事实/);
  assert.ok(!cases.plain.includes('当前来源不足以回答'));

  // Facts render as a list of escaped text plus a source button each.
  assert.match(cases.facts, /<h4>事实（实际引用）<\/h4>/);
  assert.match(cases.facts, /事实&lt;一&gt;/);
  assert.equal((cases.facts.match(/data-source-id=/g) ?? []).length, 2);

  // Only recalled sources that were NOT cited appear in the "recalled only" hint.
  assert.match(cases.recalledOnly, /仅召回、未在回答中引用的材料/);
  assert.match(cases.recalledOnly, /data-source-id="projects\/P9"/);
  assert.ok(
    !cases.recalledOnly.includes('data-source-id="projects/P1"'),
    'cited sources are not repeated in the recalled-only hint',
  );
  assert.ok(!cases.plain.includes('仅召回'), 'no recalled hint when everything was cited');

  // Structured conflicts keep both sides side by side.
  assert.match(cases.conflicts, /<h4>证据冲突（并列保留）<\/h4>/);
  assert.match(cases.conflicts, /冲突&lt;题&gt;/);
  assert.match(cases.conflicts, /<li>甲 · .*projects\/P1/);
  assert.match(cases.conflicts, /<li>乙 · .*projects\/P2/);

  // Suggestions are labelled as model inference.
  assert.match(cases.suggestions, /<h4>建议（模型推断）<\/h4>/);
  assert.match(cases.suggestions, /建议一/);

  console.log('Ask pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
