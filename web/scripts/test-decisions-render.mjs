import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.decisions-render-test-tmp');
const entry = `
import { decisionsHtml } from './features/decisions/render';

const labels = { effective: '生效中', 'under-review': '待复核', superseded: '已被替代' };
const link = (id, title) => ({ id, title, path: 'decisions/' + id });

const effective = {
  path: 'decisions/20260623-registration-entity-is-hii',
  id: '2026-09-14-a103',
  title: '决定：IP 登记主体统一为 Hoffman Institute International, Inc.',
  summary: 'registrations 一律登记在 HII 名下。',
  status: 'effective',
  status_label: '生效中',
  decided_on: '2026-06-23',
  review_on: null,
  project: 'hii-affairs',
  domain: 'ip-trademark',
  tags: ['decision'],
  supersedes: [link('2026-01-01-old', '旧口径')],
  superseded_by: [],
};

const superseded = {
  ...effective,
  path: 'decisions/20260101-old',
  id: '2026-01-01-old',
  title: '旧口径 <&>',
  summary: '已被替代。',
  status: 'superseded',
  status_label: '已被替代',
  decided_on: '2026-01-01',
  review_on: '2026-10-01',
  supersedes: [],
  superseded_by: [link('2026-09-14-a103', '新口径')],
};

const payload = {
  ok: true,
  decisions: [effective],
  counts: { effective: 15, 'under-review': 0, superseded: 0 },
  selected_counts: { effective: 1, 'under-review': 0, superseded: 0 },
  facets: {
    projects: ['hii-affairs', 'it-development'],
    domains: ['ip-trademark', 'royalty'],
    statuses: ['effective', 'under-review', 'superseded'],
  },
  status_labels: labels,
  filters: { project: null, domain: null, status: null, q: null },
  warnings: [],
};

export const cases = {
  full: decisionsHtml(payload, { project: '', domain: '', status: '', q: '' }),
  withFilters: decisionsHtml(payload, { project: 'hii-affairs', domain: 'ip-trademark', status: 'effective', q: '登记' }),
  grouped: decisionsHtml({ ...payload, decisions: [effective, superseded] }, { project: '', domain: '', status: '', q: '' }),
  empty: decisionsHtml(
    { ...payload, decisions: [], selected_counts: { effective: 0, 'under-review': 0, superseded: 0 } },
    { project: 'it-development', domain: '', status: 'under-review', q: '不存在的词' },
  ),
  warned: decisionsHtml({ ...payload, warnings: ['未知状态 "typo"，已忽略该筛选'] }, { project: '', domain: '', status: 'typo', q: '' }),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'decisions-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'decisions-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // 筛选器：四个控件 + 选项来自 facets + 当前值被选中
  assert.match(mod.cases.full, /data-decisions-filter="project"/);
  assert.match(mod.cases.full, /data-decisions-filter="domain"/);
  assert.match(mod.cases.full, /data-decisions-filter="status"/);
  assert.match(mod.cases.full, /data-decisions-filter="q"/);
  assert.match(mod.cases.full, /<option value="hii-affairs">hii-affairs<\/option>/);
  assert.match(mod.cases.full, /<option value="effective">生效中<\/option>/);
  assert.match(
    mod.cases.withFilters,
    /<option value="hii-affairs" selected>hii-affairs<\/option>/,
  );
  assert.match(mod.cases.withFilters, /value="登记"/);

  // 计数与条目
  assert.match(mod.cases.full, /台账：生效中 15　·　待复核 0　·　已被替代 0/);
  assert.match(mod.cases.full, /当前筛选：1 条/);
  assert.match(mod.cases.full, /<span class="badge">生效中<\/span>/);
  assert.match(mod.cases.full, /2026-06-23 · hii-affairs · ip-trademark/);
  assert.match(mod.cases.full, /推翻了：旧口径/);

  // 分组：两种状态各有一个分组标题
  assert.match(mod.cases.grouped, /生效中（1）/);
  assert.match(mod.cases.grouped, /已被替代（1）/);
  assert.match(mod.cases.grouped, /已被推翻：新口径/);
  assert.match(mod.cases.grouped, /复核 2026-10-01/);

  // 转义：标题里的 <&> 必须被转义（决策标题来自文件，可能含尖括号）
  assert.match(mod.cases.grouped, /旧口径 &lt;&amp;&gt;/);
  assert.doesNotMatch(mod.cases.grouped, /旧口径 <&>/);

  // 空态与筛选回退提示
  assert.match(mod.cases.empty, /当前筛选下没有决策/);
  assert.match(mod.cases.empty, /当前筛选：0 条/);

  // 服务端口径警告必须透出，不静默
  assert.match(mod.cases.warned, /未知状态/);

  console.log('Decisions pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
