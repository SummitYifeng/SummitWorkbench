import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/**
 * 界面语言口径守卫（2026-09-14，使用者选择题 ④）：
 * 「主显中文名，英文 ID 放次要位置（小字 / hover），只有『引用来源』保留完整路径」。
 *
 * 这一组断言把口径钉成机器判据——把中文映射去掉、或把英文 ID 放回可见文本，
 * 立刻会红。覆盖：简报里的项目 ID 与文件名、审批的 target_project / unresolved、
 * 外部写回的 candidate_id、以及错误文案归一化。
 */
const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.ui-language-test-tmp');

const entry = `
import { briefCardHtml, briefSourceLabel } from './brief-card';
import { errorText } from './api/client';
import { reviewHtml } from './features/review';
import { logProjectChoices } from './features/threads';

const brief = {
  date: '2026-09-14',
  health: { level: 'ok', label: '正常', reasons: [] },
  meetings: [],
  tasks: [],
  actions: [
    {
      signal_id: 's1', title: '把合同条款落到书面', category_key: 'commitment', category: '承诺',
      evidence: '00:12', source_ref: 'logistics/sources/2026-09-14-1977-hotel.md',
      project: 'huoman-logistics', due_date: null, detail: '', rank: 1,
    },
    {
      // 项目自身页面的引用：不能再把项目 ID 当「出处」显示一遍（真实数据验证发现）。
      signal_id: 'next-huoman-logistics', title: '按材料推进合同', category_key: 'main-push', category: '主线推进',
      evidence: 'E2', source_ref: 'projects/huoman-logistics.md#下一步',
      project: 'huoman-logistics', due_date: null, detail: '', rank: 2,
    },
  ],
  proposals: [
    {
      signal_id: 's2', title: '补一份供应商名录', category_key: 'proposal', category: '提议',
      evidence: '', source_ref: 'logistics/notes/2026-09-14-vendor.md',
      project: 'huoman-logistics', due_date: null, detail: '',
    },
  ],
  completions: [],
  pending_review: 0,
  ranking_model: null,
};

const entry0 = {
  candidate_id: '2026-09-14-meeting#decision-0',
  kind: 'decision',
  description: '采用 Gross 口径',
  target_project: 'huoman-logistics',
  route: 'project-main',
  due_date: null, start_at: null, end_at: null, evidence: null,
  decision: 'pending', historical: false, actionable: true,
  ai_original: '', meeting_date: '2026-09-14', meeting_title: '后勤沟通',
  note_link: '', transcript_link: '', apply_error: null,
};
const unresolvedEntry = { ...entry0, candidate_id: 'x#0', target_project: 'unresolved' };
const external = {
  operation_id: 'op-1', candidate_id: '2026-09-14-meeting#decision-0', kind: 'decision',
  state: 'unknown', attempt: 1, timestamp: '2026-09-14T00:00:00Z',
  remote_id: 'om_abc123', error: null, retry_allowed: false,
};

const projectNames = { 'huoman-logistics': '活满后勤&行政' };
const review = (e) => reviewHtml(
  { groups: [{ meeting_date: '2026-09-14', meeting_title: '后勤沟通', entries: [e] }], errors: [] },
  1, '2026-09-14',
  [{ name: 'huoman-logistics', title: '活满后勤&行政', is_thread: true, registered: true, status: 'active' }],
  [external],
);

export const labels = {
  sourceLabel: briefSourceLabel('logistics/sources/2026-09-14-1977-hotel.md'),
  feishuRef: briefSourceLabel('feishu-task:abc'),
  anchored: briefSourceLabel('projects/hii-affairs.md#下一步'),
};
export const briefHtml = briefCardHtml(brief, '2026-09-14', projectNames);
export const reviewHtmlText = review(entry0);
export const unresolvedHtml = review(unresolvedEntry);
export const networkError = errorText(new TypeError('Failed to fetch'));
export const logChoices = logProjectChoices(
  [{ name: 'huoman-logistics', title: '活满后勤&行政', is_thread: true, registered: true, status: 'active' }],
  ['huoman-logistics'],
);
// 今日页三个独立内容区（旧的两列网格标记必须消失）。
export const todayPanels = { count: (briefHtml.match(/class="today-panel"/g) || []).length, hasGrid: briefHtml.indexOf('bf-grid') >= 0 };
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'ui-language-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'ui-language-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // ① 简报：项目显示中文名、出处只留可读标题（不显示英文项目 ID / 文件名 / 目录）。
  assert.match(mod.briefHtml, /活满后勤&amp;行政/);
  assert.ok(!mod.briefHtml.includes('huoman-logistics'), 'brief must not print the raw project id');
  assert.ok(!mod.briefHtml.includes('logistics/sources/'), 'brief must not print source paths');
  assert.match(mod.briefHtml, /1977-hotel/, 'brief keeps the readable part of the source name');
  assert.equal(mod.labels.sourceLabel, '1977-hotel');
  // 带 `#区块` 锚点的引用必须先剥锚点（否则会留下 `xxx.md#区块` 的残渣）。
  assert.equal(mod.labels.anchored, 'hii-affairs');
  assert.equal(mod.labels.feishuRef, '', 'feishu task refs have no readable file name');
  assert.ok(
    !mod.briefHtml.includes('projects/huoman-logistics.md'),
    'a project page reference must not be echoed as a source label',
  );
  assert.equal(mod.labels.feishuRef, '', 'feishu task refs have no readable file name');

  // ② 审批：目标项目显示中文名；内部标记 unresolved 显示为「未定」。
  assert.match(mod.reviewHtmlText, /目标：活满后勤&amp;行政/);
  assert.ok(!mod.reviewHtmlText.includes('目标：huoman-logistics'), 'review must not print the raw project id');
  assert.match(mod.unresolvedHtml, /目标：未定/);
  assert.ok(!mod.unresolvedHtml.includes('unresolved'), 'the internal unresolved marker must not reach the UI');
  // 外部写回：可读标签在主位，内部 ID 与远端 id 只在 hover。
  assert.match(mod.reviewHtmlText, /会议 2026-09-14/);
  assert.ok(
    !/external-action-row"><span><strong[^>]*>.*?<\/strong> · 2026-09-14-meeting#decision-0/.test(mod.reviewHtmlText),
    'external action rows must not print the raw candidate id',
  );
  assert.match(mod.reviewHtmlText, /title="远端记录：om_abc123｜内部标识：2026-09-14-meeting#decision-0"/);

  // ③ 错误文案：网络错误不把 `TypeError: Failed to fetch` 原样给使用者。
  assert.equal(mod.networkError, '连不上本地服务，请确认工作台还在运行');

  // ④ 今日页三个独立内容区：新标记在、旧的两列网格标记不在。
  assert.equal(mod.todayPanels.count, 3, 'the brief must keep three content panels');
  assert.equal(mod.todayPanels.hasGrid, false, 'the old two-column brief grid must be gone');

  // ⑤ 「追加推进日志」的项目勾选：可见文本只有中文名，英文 ID 只进 title 属性。
  // 去掉属性（title 与表单 value 都允许携带 ID），只看剩下的可见文本。
  const visibleChoices = mod.logChoices.replace(/ (?:title|value)="[^"]*"/g, '');
  assert.match(visibleChoices, /活满后勤&amp;行政/);
  assert.ok(!visibleChoices.includes('huoman-logistics'), 'log modal must not print the raw project id');
  assert.match(mod.logChoices, /title="[^"]*huoman-logistics[^"]*"/, 'the project id stays available on hover');
  assert.match(mod.logChoices, /checked/, 'already selected projects stay checked');

  console.log('UI language contract tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
