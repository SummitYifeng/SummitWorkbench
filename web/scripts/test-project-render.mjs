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
  markdown: projectsListHtml('', [{
    ...base,
    next_step: '**&#xA0;先完成验收**',
  }], '2026-09-01', true),
  archivedOnly: projectsListHtml('', [base, { ...base, name: 'Archived', status: 'archived' }], '2026-09-01', true, 'archived'),
  grouped: projectsListHtml('', [base, { ...base, name: 'New folder', registered: false, status: null }, { ...base, name: 'Archived', status: 'archived' }], '2026-09-01', true),
  detail: projectDetailHtml({
    ok: true,
    name: 'Alpha',
    title: '显示名',
    status: 'active',
    updated: '2026-09-01',
    blocks: {
      '当前状态': [
        '三条内部口径已经定下并落成决策：**登记主体统一为 HII**、',
        '**「活满」与「和夫曼之旅」分开管理**。',
        '| 主线 | 状态 |',
        '|---|---|',
        '| 报名与课程生命周期 | 🟢 正式生产运行 |',
      ],
      '下一步': ['1. **9 月**：P0 权限清退收口；', '   相关方培训。', '2. **10 月**：启动 AI 知识库。'],
      '决策记录': ['- [[20260623-hii-registration-entity|决定：登记主体统一为 HII]] —— 一律登记在 HII 名下。'],
      '跟进事项': ['- [ ] 待办一', '- [x] 已办二'],
    },
    followup_pending: 1,
    inbox_pending: 0,
    timeline: [
      { date: '2026-09-01', kind: 'log', label: '日志', title: '**已检查**', snippet: '合成记录' },
      { date: '2026-09-02', kind: 'meeting-note', label: '会议', title: '对齐', snippet: '缺口在**网课与老师账户未绑定**' },
    ],
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
    '<section class="project-group active-group"><h4>在工作台</h4><div class="project-group-grid"><div class="card project-row"><div class="project-row-main"><div class="project-row-title"><button class="project-name project-link" data-action="open-view" data-name="Alpha" title="打开项目详情">Alpha</button><span class="badge is-home">在工作台</span></div></div><div class="project-row-actions"><button class="ghost" data-action="project-archive" data-name="Alpha">归档</button></div></div></div></section>',
  );
  assert.ok(mod.cases.homeCard.includes('<div class="card project">'));
  assert.ok(mod.cases.homeCard.includes('class="project-clear-state">未发现同步提醒</span>'));
  assert.ok(mod.cases.homeCard.includes('class="project-step"><span class="step-label">下一步</span>'));
  assert.ok(!mod.cases.stale14.includes('⚠'));
  assert.doesNotMatch(mod.cases.stale15, /⚠ 15 天未更新/);
  assert.equal(
    mod.cases.missingDate,
    '<section class="project-group active-group"><h4>在工作台</h4><div class="project-group-grid"><div class="card project-row"><div class="project-row-main"><div class="project-row-title"><button class="project-name project-link" data-action="open-view" data-name="Thread-no-date" title="打开项目详情">Thread-no-date</button><span class="badge is-home">在工作台</span></div></div><div class="project-row-actions"><button class="ghost" data-action="project-archive" data-name="Thread-no-date">归档</button></div></div></div></section>',
  );
  assert.match(mod.cases.escaped, /data-name="A&lt;&amp;".*>显示名<\/button>/);
  assert.match(mod.cases.titleSearch, /data-name="A&lt;&amp;".*显示名/);
  assert.doesNotMatch(mod.cases.markdown, /下一步/);
  assert.doesNotMatch(mod.cases.archivedOnly, />Alpha</);
  assert.match(mod.cases.archivedOnly, /data-name="Archived"/);
  assert.match(mod.cases.grouped, /在工作台/);
  assert.match(mod.cases.grouped, /新文件夹/);
  assert.match(mod.cases.grouped, /已归档 1/);
  assert.match(mod.cases.grouped, /<details class="project-group archived-group"/);
  assert.doesNotMatch(mod.cases.grouped, /data-action="open-log"/);
  assert.doesNotMatch(mod.cases.grouped, /data-action="open-artifact"/);
  assert.match(mod.cases.grouped, /data-action="open-view" data-name="Alpha"/);
  assert.doesNotMatch(mod.cases.grouped, /data-action="open-view" data-name="New folder"/);
  assert.match(mod.cases.detail, /data-action="project-detail-back"/);
  assert.match(mod.cases.detail, /返回今日/);
  assert.match(mod.cases.detail, /显示名/);
  assert.match(mod.cases.detail, /合成记录/);
  assert.match(mod.cases.detail, /<span class="tl-title"><strong>已检查<\/strong><\/span>/);
  // 档案区块正文是真 Markdown：不许再把源码漏给使用者看
  assert.doesNotMatch(mod.cases.detail, /\*\*/);
  assert.doesNotMatch(mod.cases.detail, /\[\[/);
  assert.match(mod.cases.detail, /<strong>登记主体统一为 HII<\/strong>/);
  assert.match(mod.cases.detail, /<table><thead><tr><th>主线<\/th>/);
  assert.match(mod.cases.detail, /pv-block-wide/, '含表格的区块要横跨整行');
  assert.match(mod.cases.detail, /<ol><li><strong>9 月<\/strong>：P0 权限清退收口；相关方培训。<\/li>/);
  assert.match(mod.cases.detail, /title="20260623-hii-registration-entity">决定：登记主体统一为 HII<\/span>/);
  assert.match(mod.cases.detail, /<div class="tl-snippet">缺口在<strong>网课与老师账户未绑定<\/strong><\/div>/, '时间线摘要里的行内标记也要渲染');
  assert.match(mod.cases.detail, /<span class="task">☐<\/span> 待办一/);
  assert.match(mod.cases.detail, /<span class="task done">☑<\/span> 已办二/);
  console.log('Project pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
