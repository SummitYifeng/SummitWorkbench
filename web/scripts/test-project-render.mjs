import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.project-render-test-tmp');
const entry = `
import { projectDetailHtml, projectDisplayName, projectsHtml, projectsListHtml } from './features/projects';

const base = {
  name: 'Alpha',
  dirty: false,
  ahead: 0,
  behind: 0,
  has_upstream: true,
  inbox_pending: 0,
  next_step: '先完成验收',
  git_error: null,
  registered: true,
  status: 'active',
};

export const cases = {
  displayName: projectDisplayName({ ...base, title: '显示名' }),
  unloaded: projectsListHtml('', [], '2026-09-01', false),
  empty: projectsListHtml('', [], '2026-09-01', true),
  activeRow: projectsListHtml('', [base], '2026-09-01', true),
  homeCard: projectsHtml([base], '2026-09-01'),
  stale14: projectsListHtml('', [{
    ...base,
    name: 'Thread-14',
    is_thread: true,
    updated: '2026-08-18',
    activity_at: null,
  }], '2026-09-01', true),
  stale15: projectsListHtml('', [{
    ...base,
    name: 'Thread-15',
    is_thread: true,
    updated: '2026-08-17',
    activity_at: null,
  }], '2026-09-01', true),
  missingDate: projectsListHtml('', [{
    ...base,
    name: 'Thread-no-date',
    is_thread: true,
    updated: null,
    activity_at: null,
  }], '2026-09-01', true),
  escaped: projectsListHtml('', [{
    ...base,
    name: 'A<&',
    title: '显示名',
  }], '2026-09-01', true),
  titleSearch: projectsListHtml('显示名', [{
    ...base,
    name: 'A<&',
    title: '显示名',
  }], '2026-09-01', true),
  archivedOnly: projectsListHtml('', [base, { ...base, name: 'Archived', status: 'archived' }], '2026-09-01', true, 'archived'),
  detail: projectDetailHtml({
    ok: true,
    name: 'Alpha',
    title: '显示名',
    status: 'active',
    updated: '2026-09-01',
    blocks: { '当前状态': ['- 正常'], '下一步': ['- [ ] 继续验收'] },
    followup_pending: 1,
    inbox_pending: 0,
    timeline: [{ date: '2026-09-01', kind: 'log', label: '日志', title: '已检查', snippet: '合成记录' }],
  }, '返回今日'),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'project-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'project-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.equal(mod.cases.displayName, '显示名');
  assert.equal(mod.cases.unloaded, '<div class="loading">加载中…</div>');
  assert.equal(mod.cases.empty, '<div class="empty"><p>暂无项目文件夹</p></div>');
  assert.equal(
    mod.cases.activeRow,
    '<div class="card project-row"><div class="project-row-main"><div class="project-row-title"><button class="project-name project-link" data-action="open-view" data-name="Alpha" title="打开线视图">Alpha</button><span class="badge is-home">在工作台</span></div><div class="project-step"><span class="step-label">下一步</span><span class="step-text">先完成验收</span></div></div><div class="project-row-actions"><button class="ghost" data-action="open-log" data-project="Alpha" title="追加推进日志">✎ 日志</button><button class="ghost" data-action="open-artifact" data-project="Alpha" title="把 AI 产物存入本线程/项目档案">存产物</button><button class="ghost" data-action="project-archive" data-name="Alpha">归档</button></div></div>',
  );
  assert.ok(mod.cases.homeCard.includes('<div class="card project">'));
  assert.ok(mod.cases.homeCard.includes('class="project-clear-state">未发现同步提醒</span>'));
  assert.ok(mod.cases.homeCard.includes('class="project-step"><span class="step-label">下一步</span>'));
  assert.ok(!mod.cases.stale14.includes('⚠'));
  assert.match(mod.cases.stale15, /⚠ 15 天未更新/);
  assert.equal(
    mod.cases.missingDate,
    '<div class="card project-row"><div class="project-row-main"><div class="project-row-title"><button class="project-name project-link" data-action="open-view" data-name="Thread-no-date" title="打开线视图">Thread-no-date</button><span class="badge is-home">在工作台</span></div><div class="chips"><span class="chip">知识线程</span></div><div class="project-step"><span class="step-label">下一步</span><span class="step-text">先完成验收</span></div></div><div class="project-row-actions"><button class="ghost" data-action="open-log" data-project="Thread-no-date" title="追加推进日志">✎ 日志</button><button class="ghost" data-action="open-artifact" data-project="Thread-no-date" title="把 AI 产物存入本线程/项目档案">存产物</button><button class="ghost" data-action="project-archive" data-name="Thread-no-date">归档</button></div></div>',
  );
  assert.match(mod.cases.escaped, /data-name="A&lt;&amp;".*>显示名<\/button>/);
  assert.match(mod.cases.titleSearch, /data-name="A&lt;&amp;".*显示名/);
  assert.doesNotMatch(mod.cases.archivedOnly, />Alpha</);
  assert.match(mod.cases.archivedOnly, /data-name="Archived"/);
  assert.match(mod.cases.detail, /data-action="project-detail-back"/);
  assert.match(mod.cases.detail, /返回今日/);
  assert.match(mod.cases.detail, /显示名/);
  assert.match(mod.cases.detail, /合成记录/);
  console.log('Project pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
