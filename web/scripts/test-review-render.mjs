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
import { approvableEntries, REVIEW_BATCH_LIMIT, reviewHtml } from './features/review';

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

const mk = (id: string, over: Record<string, unknown>) => ({
  ...baseEntry, candidate_id: id, ...over,
});

export const batchLimit = REVIEW_BATCH_LIMIT;
export const approvable = approvableEntries([
  mk('ok', { actionable: true, route: 'project-main' }),
  mk('no-route', { actionable: true, route: null }),
  mk('not-actionable', { actionable: false, route: 'project-main' }),
  mk('both', { actionable: true, route: 'feishu-task' }),
]).map((e) => e.candidate_id);
export const approvableNone = approvableEntries([
  mk('a', { actionable: false, route: null }),
]).map((e) => e.candidate_id);

export const cases = {
  empty: reviewHtml({ groups: [], errors: [] }, 0, '2026-09-01', [], []),
  pending: reviewHtml({
    groups: [{ meeting_date: '2026-08-27', meeting_title: '排版会', entries: [baseEntry] }],
    errors: [],
  }, 1, '2026-09-01', [{ name: 'Alpha', title: '项目甲' }], [external]),
  interrupted: reviewHtml({ groups: [], errors: [] }, 0, '2026-09-01', [], [{
    ...external,
    state: 'unknown',
    error: 'external_action_interrupted',
  }]),
  scopedBatch: reviewHtml({
    groups: [{
      meeting_date: '2026-08-27',
      meeting_title: '排版会',
      entries: [
        baseEntry,
        { ...baseEntry, candidate_id: 'm1#decision-1', route: null, actionable: false },
      ],
    }],
    errors: [],
  }, 2, '2026-09-01', [], []),
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
  filterPending: reviewHtml({
    groups: [{ meeting_date: '2026-08-27', meeting_title: '排版会', entries: [
      baseEntry,
      { ...baseEntry, candidate_id: 'm1#decision-1', decision: 'approved' },
      { ...baseEntry, candidate_id: 'm1#decision-2', decision: 'rejected' },
    ] }],
    errors: [],
  }, 1, '2026-09-01', [], [], null, {
    filter: 'pending', selectedIds: new Set(['m1#decision-0']),
  }),
  selectedSummary: reviewHtml({
    groups: [{ meeting_date: '2026-08-27', meeting_title: '排版会', entries: [baseEntry] }],
    errors: [],
  }, 1, '2026-09-01', [], [], null, {
    filter: 'all', selectedIds: new Set(['m1#decision-0']),
  }),
  markdown: reviewHtml({
    groups: [{ meeting_date: '2026-08-27', meeting_title: '**排版会**', entries: [{
      ...baseEntry,
      description: '**采用&#xA0;双栏排版**',
      evidence: '**依据**',
    }] }],
    errors: [],
  }, 1, '2026-09-01', [], []),
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

  assert.match(mod.cases.empty, /当前筛选没有候选/);
  assert.match(mod.cases.empty, /一键拒绝过期项/);
  assert.match(mod.cases.pending, /截止：2026-08-31（已过期）/);
  assert.match(mod.cases.pending, /项目甲/);
  assert.match(mod.cases.pending, /重新核对/);
  assert.match(mod.cases.pending, /确认已创建/);
  assert.match(mod.cases.pending, /确认未创建/);
  assert.match(mod.cases.pending, /会议笔记/);
  assert.match(mod.cases.pending, /逐字稿/);
  assert.match(mod.cases.interrupted, /上次执行中断，结果待核对/);
  assert.match(mod.cases.pending, /data-action="source-open"/);
  assert.match(mod.cases.pending, /data-source-id="meetings\/notes\/2026-08-27-排版会\.md"/);
  assert.match(mod.cases.pending, /全批\(1\)/);
  assert.match(mod.cases.scopedBatch, /全批\(1\)/);
  assert.match(mod.cases.scopedBatch, /全拒\(2\)/);
  assert.match(mod.cases.scopedBatch, /仅纳入具备依据和落点的候选；1 条未纳入批准/);
  assert.match(mod.cases.scopedBatch, /disabled title="落点未定，请点「修改」设置后再批准"/);
  assert.match(mod.cases.pending, /保存并批准/);
  assert.match(mod.cases.approvedError, /审批页解析错误：<br>解析失败/);
  assert.match(mod.cases.approvedError, /应用出错：写回失败/);
  assert.match(mod.cases.approvedError, /依据或目标项目缺失，暂不可批准写回/);
  assert.match(mod.cases.approvedError, /确认后重试/);
  assert.match(mod.cases.approvedError, /data-decision="pending"/);
  assert.match(mod.cases.filterPending, /data-review-filter="pending"/);
  assert.match(mod.cases.filterPending, /data-review-select="m1#decision-0" checked/);
  assert.doesNotMatch(mod.cases.filterPending, /data-review-select="m1#decision-1"/);
  assert.doesNotMatch(mod.cases.filterPending, /data-review-select="m1#decision-2"/);
  assert.match(mod.cases.filterPending, /当前筛选：待确认/);
  assert.match(mod.cases.selectedSummary, /已选 1 条/);
  assert.match(mod.cases.selectedSummary, /批量批准/);
  assert.match(mod.cases.selectedSummary, /批量拒绝/);
  assert.match(mod.cases.markdown, /<p class="desc"><strong>采用 双栏排版<\/strong><\/p>/);
  assert.match(mod.cases.markdown, /依据：<strong>依据<\/strong>/);
  assert.match(mod.cases.markdown, /<span class="meeting-title"><strong>排版会<\/strong><\/span>/);
  // 「一键拒绝过期项」必须先显示自身范围，且没有过期项时不可点。
  assert.match(mod.cases.pending, /一键拒绝过期项（1）/);
  assert.match(mod.cases.empty, /data-action="reject-expired"[^>]*disabled[^>]*>一键拒绝过期项（0）</);
  // 批量上限是产品约束（后端与派发器同口径），断言它没有被静默改大/改小。
  assert.equal(mod.batchLimit, 100);
  // 批准只纳入"有依据且已定落点"的条目；拒绝不受该限制。
  assert.deepEqual(mod.approvable, ['ok', 'both']);
  assert.deepEqual(mod.approvableNone, []);
  console.log('Review pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
