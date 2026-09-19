import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.today-render-test-tmp');
const entry = [
  "import { todayHtml } from './features/today';",
  '',
  'const state = {',
  "  day: '2026-09-16',",
  "  status: { pending_review: 2, backlog: { oldest_age_days: 3 } },",
  "  brief_md: '## 项目推进\\n**不应出现在今日页**\\n## AI 提议\\n## 最近完成\\n## 待确认审批',",
  '  brief_generated: true,',
  '  brief: {',
  "    date: '2026-09-16',",
  "    health: { level: 'alert', label: '需关注', reasons: ['重复告警'] },",
  "    meetings: [{ title: '**周会**', start_time: '10:00', event_id: 'evt-1', start_ts: '2026-09-16T10:00', end_ts: '2026-09-16T11:00' }],",
  "    tasks: [{ summary: '**跟进事项**', due_date: null, task_id: 'task-1' }],",
  "    actions: [{ signal_id: 'action-1', title: '**给项目甲发邮件**', category_key: 'commitment', category: '承诺', evidence: 'E1', source_ref: 'notes.md', project: 'alpha', due_date: null, detail: '**明天前发送**', rank: 1 }],",
  "    proposals: [{ signal_id: 'proposal-1', title: '不应显示的提议', category_key: 'proposal', category: '提议', evidence: '', source_ref: '', project: null, due_date: null, detail: '' }],",
  "    completions: [{ text: '不应显示的完成项', source_ref: 'done.md' }],",
  "    pending_review: 2, ranking_model: 'model',",
  '  },',
  "  projects: [{ name: 'alpha', title: '项目甲', registered: true, status: 'active' }],",
  '};',
  "const emptyState = { ...state, brief: null, brief_md: '## 项目推进\\n这份旧版简报不应被整份展示' };",
  "const options = { state, importOpen: false, importing: false, health: { tone: 'ok', label: '正常' } };",
  'const inbox = [',
  "  { id: 'web-a', text: '把翻译流程定稿 #it-development', kind: null, due: null, project: 'it-development', projects: ['it-development'], candidate_id: 'web-a', suggested_target: 'project', suggested_reason: '有 #it-development ⇒ 归到该项目页（下一步 / 跟进事项）' },",
  "  { id: 'web-b', text: '给 Coach 发邮件', kind: 'task', due: '2026-09-25', project: null, projects: [], candidate_id: 'web-b', suggested_target: 'feishu-task', suggested_reason: '有截止日期 2026-09-25 ⇒ 按待办处理（真源在飞书）' },",
  '];',
  'export const full = todayHtml({ ...options, inboxItems: inbox }, "");',
  'export const empty = todayHtml({ ...options, state: emptyState, inboxItems: [] }, "");',
  'export const broken = todayHtml({ ...options, inboxItems: [], inboxError: "重复区块" }, "");',
].join('\n');

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'today-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const outFile = join(tmpDir, 'bundle.mjs');
  writeFileSync(outFile, result.outputFiles[0].text);
  const { full, empty, broken } = await import(pathToFileURL(outFile).href + '?t=' + Date.now());

  for (const html of [full, empty, broken]) {
    // 收件箱是**第三块**、用独立类名：工具栏仍是 2 个、简报面板仍是 3 个（契约计数不变）。
    assert.equal((html.match(/class="today-tool /g) || []).length, 2);
    assert.equal((html.match(/class="today-panel/g) || []).length, 3);
    assert.equal((html.match(/id="today-inbox"/g) || []).length, 1);
    assert.match(html, /记点什么/);
    assert.match(html, /导入会议纪要/);
    assert.match(html, /id="capture-form"/);
    assert.match(html, /id="capture-input"/);
    assert.match(html, /id="btn-import-meeting"/);
    assert.match(html, /id="import-drawer"/);
    assert.match(html, /id="dropzone"/);
    assert.match(html, /id="file-input"/);
    assert.match(html, /id="btn-pick"/);
    assert.match(html, /data-action="run-brief"/);
    // 「今日」页两个新入口（写工作日志 / 写工作思考）必须在「记点什么」附近可见
    assert.match(html, /data-action="journal-log"/);
    assert.match(html, /data-action="journal-thought"/);
    assert.match(html, /写工作日志/);
    assert.match(html, /写工作思考/);
    const taskAt = html.indexOf('class="bf-sec-title">待办任务');
    const meetingAt = html.indexOf('class="bf-sec-title">会议');
    const actionAt = html.indexOf('class="bf-sec-title">需要行动');
    assert.ok(taskAt < meetingAt);
    assert.ok(meetingAt < actionAt);
    assert.doesNotMatch(html, /项目推进|待确认审批|AI 提议|最近完成/);
  }

  assert.match(full, /项目甲/);
  assert.match(full, /<span class="bf-task-title"><strong>跟进事项<\/strong><\/span>/);
  assert.match(full, /<span class="bf-mt-title"><strong>周会<\/strong><\/span>/);
  assert.match(full, /<strong>给项目甲发邮件<\/strong>/);
  assert.match(full, /<strong>明天前发送<\/strong>/);
  assert.doesNotMatch(empty, /这份旧版简报不应被整份展示/);
  // 收件箱：有条目时每条一个「提升为…」按钮；空收件箱只一句轻提示（不占大块版面）
  assert.match(full, /收件箱（2 条）/);
  assert.equal((full.match(/data-action="inbox-promote"/g) || []).length, 2);
  assert.match(full, /把翻译流程定稿/);
  assert.match(full, /#it-development/);
  assert.match(full, /截止 2026-09-25/);
  assert.match(full, /承诺/);
  assert.match(empty, /收件箱（0 条）/);
  assert.doesNotMatch(empty, /data-action="inbox-promote"/);
  assert.match(empty, /收件箱是空的/);
  assert.match(broken, /收件箱读取失败：重复区块/);
  // 列表渲染**不得**内置 AI 建议入口（成本约定：只有弹层里的显式按钮才调模型）
  assert.doesNotMatch(full, /inbox-ai-suggest/);
  assert.doesNotMatch(full, /\/api\/inbox\/suggest/);

  assert.match(empty, /今日无待办任务/);
  assert.match(empty, /今日无会议/);
  assert.match(empty, /当前没有任务清单之外的行动/);
  console.log('Today layout render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
