import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.review-render-test-tmp');
const entry = `
import { reviewHtml } from './features/review';

const baseEntry = {
  candidate_id: 'm1#decision-0',
  kind: 'decision',
  description: '采用双栏排版',
  target_project: 'Alpha',
  route: 'project-main',
  due_date: '2026-08-31',
  start_at: null,
  end_at: null,
  evidence: '00:12:30',
  decision: 'pending',
  historical: false,
  actionable: true,
  ai_original: '采用双栏排版',
  meeting_date: '2026-08-27',
  meeting_title: '排版会',
  note_link: '[[meetings/notes/2026-08-27-排版会.md]]',
  transcript_link: '[[t.md]]',
  apply_error: null,
};

const external = {
  operation_id: 'op-1',
  candidate_id: 'm1#decision-0',
  kind: 'task',
  state: 'unknown',
  attempt: 1,
  timestamp: '2026-08-27T00:00:00Z',
  remote_id: null,
  error: null,
  retry_allowed: false,
};

export const cases = {
  empty: reviewHtml({ groups: [], errors: [] }, 0, '2026-09-01', [], []),
  pending: reviewHtml({
    groups: [{ meeting_date: '2026-08-27', meeting_title: '排版会', entries: [baseEntry] }],
    errors: [],
  }, 1, '2026-09-01', [{ name: 'Alpha', title: '项目甲' }], [external]),
  approvedError: reviewHtml({
    groups: [{
      meeting_date: '2026-08-27',
      meeting_title: '排版会',
      entries: [
        { ...baseEntry, decision: 'approved', apply_error: '写回失败' },
        { ...baseEntry, candidate_id: 'm1#decision-1', route: null, actionable: false, decision: 'rejected' },
      ],
    }],
    errors: ['解析失败'],
  }, 0, '2026-09-01', [], [{
    ...external,
    state: 'reconciled-not-found',
  }]),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'review-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'review-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.match(mod.cases.empty, /暂无待确认候选/);
  assert.match(mod.cases.empty, /一键拒绝过期项/);
  assert.match(mod.cases.pending, /截止：2026-08-31（已过期）/);
  assert.match(mod.cases.pending, /项目甲/);
  assert.match(mod.cases.pending, /重新核对/);
  assert.match(mod.cases.pending, /确认已创建/);
  assert.match(mod.cases.pending, /确认未创建/);
  assert.match(mod.cases.pending, /全批\(1\)/);
  assert.match(mod.cases.pending, /保存并批准/);
  assert.match(mod.cases.approvedError, /审批页解析错误：<br>解析失败/);
  assert.match(mod.cases.approvedError, /应用出错：写回失败/);
  assert.match(mod.cases.approvedError, /依据或目标项目缺失，暂不可批准写回/);
  assert.match(mod.cases.approvedError, /确认后重试/);
  assert.match(mod.cases.approvedError, /data-decision="pending"/);
  console.log('Review pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
