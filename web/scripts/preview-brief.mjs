// 生成 docs/design/brief-v2-preview.html：用真实生产代码（brief-card.ts + style.css）
// 渲染晨间简报 v2 的静态预览，方便在浏览器里直接验收视觉，不必等简报重新生成。
// 用法：node scripts/preview-brief.mjs

import { build } from 'esbuild';
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const WEB_ROOT = resolve(SCRIPT_PATH, '..', '..');
const SRC_DIR = join(WEB_ROOT, 'src');
const REPO_ROOT = resolve(WEB_ROOT, '..');
const OUT_HTML = join(REPO_ROOT, 'docs', 'design', 'brief-v2-preview.html');
const TMP_DIR = join(WEB_ROOT, '.preview-tmp');

const today = '2026-09-03';

// 与真实 vault 当日快照一致的示例数据（仅预览用）
const entry = `
import { briefCardHtml, type BriefData } from './brief-card';

const today = '${today}';

const real: BriefData = {
  date: today,
  health: { level: 'ok', label: '正常', reasons: [] },
  meetings: [
    { title: '钻石三角双周例会', start_time: '10:00' },
    { title: 'TG+SB本地化反馈', start_time: '20:30' },
  ],
  tasks: [
    { summary: 'Danny的陪同机构和个人', due_date: '2026-09-03', task_id: 'fe1b9094-46b7-4f3f-a414-d4cde15cd20c' },
    { summary: 'Sunny-薪资', due_date: '2026-09-03', task_id: '66d07ef2-fd0e-40c0-9946-93aaed4b4943' },
    { summary: '门户验收', due_date: '2026-09-06', task_id: '7715c269-c0ee-4d06-a29e-3bc356d560ae' },
    { summary: '一对一辅导PRD', due_date: '2026-09-10', task_id: '8020b48b-55e9-4642-8522-2a97e29e2c0b' },
    { summary: '后勤toolkit验收', due_date: '2026-09-12', task_id: 'c3a1dead-0000-4000-8000-000000000012' },
  ],
  actions: [
    { signal_id: 'task-fe1b9094-46b7-4f3f-a414-d4cde15cd20c', title: 'Danny的陪同机构和个人', category_key: 'commitment', category: '近期承诺', evidence: 'E2', source_ref: 'feishu-task:fe1b9094-46b7-4f3f-a414-d4cde15cd20c', project: null, due_date: '2026-09-03', detail: '', rank: 1 },
    { signal_id: 'task-66d07ef2-fd0e-40c0-9946-93aaed4b4943', title: 'Sunny-薪资', category_key: 'commitment', category: '近期承诺', evidence: 'E2', source_ref: 'feishu-task:66d07ef2-fd0e-40c0-9946-93aaed4b4943', project: null, due_date: '2026-09-03', detail: '', rank: 2 },
    { signal_id: 'stall-HIC_Logistics-dirty', title: '提交 HIC_Logistics 的未提交改动', category_key: 'anti-stall', category: '防止停摆', evidence: 'E2', source_ref: '/Users/yifengstudio/Documents/Work/HIC_Logistics', project: 'HIC_Logistics', due_date: null, detail: '工作树有未提交改动', rank: 3 },
    { signal_id: 'task-7715c269-c0ee-4d06-a29e-3bc356d560ae', title: '门户验收', category_key: 'commitment', category: '近期承诺', evidence: 'E2', source_ref: 'feishu-task:7715c269-c0ee-4d06-a29e-3bc356d560ae', project: null, due_date: '2026-09-06', detail: '', rank: 4 },
    { signal_id: 'task-8020b48b-55e9-4642-8522-2a97e29e2c0b', title: '一对一辅导PRD', category_key: 'commitment', category: '近期承诺', evidence: 'E2', source_ref: 'feishu-task:8020b48b-55e9-4642-8522-2a97e29e2c0b', project: null, due_date: '2026-09-10', detail: '', rank: 5 },
  ],
  proposals: [],
  completions: [{ text: 'HIC_Tool_Kit', source_ref: 'feishu-task:944e2db3-d4ab-4bef-88d0-e0d3a7f6e2b8' }],
  pending_review: 0,
  ranking_model: 'deepseek-v4-flash',
};

// 状态示例：降级横幅 / 待确认提示 / 提议与完成折叠 / 空态（合成数据，用于预览）
const states: BriefData = {
  date: today,
  health: { level: 'degraded', label: '降级', reasons: ['采集源失败：飞书日历', '排序降级（确定性回退）'] },
  meetings: [],
  tasks: [{ summary: '招生简章终稿', due_date: '2026-09-02', task_id: 'dead0000-0000-4000-8000-000000000001' }],
  actions: [
    { signal_id: 'stall-Sample-dirty', title: '提交 Sample 的未提交改动', category_key: 'anti-stall', category: '防止停摆', evidence: 'E2', source_ref: '/work/Sample', project: 'Sample', due_date: null, detail: '工作树有未提交改动', rank: 1 },
  ],
  proposals: [
    { signal_id: 'p1', title: '把网课项目里程碑拆细，先交付招生漏斗一版', category_key: 'proposal', category: '提议', evidence: 'E3', source_ref: 'projects/网课项目.md', project: '网课项目', due_date: null, detail: '' },
    { signal_id: 'p2', title: '本周末前完成 HIC 门户的验收清单拆分', category_key: 'proposal', category: '提议', evidence: 'E3', source_ref: 'projects/HIC_门户.md', project: 'HIC_门户', due_date: null, detail: '' },
  ],
  completions: [
    { text: 'HIC_Tool_Kit', source_ref: 'feishu-task:x' },
    { text: '钻石三角双周例会纪要归档', source_ref: 'meetings/notes/2026-09-01-钻石三角双周例会.md' },
  ],
  pending_review: 3,
  ranking_model: 'deepseek-v4-flash',
};

export const cards = {
  real: briefCardHtml(real, today),
  states: briefCardHtml(states, today),
};
`;

mkdirSync(TMP_DIR, { recursive: true });
const result = await build({
  stdin: { contents: entry, resolveDir: SRC_DIR, sourcefile: 'preview-entry.ts', loader: 'ts' },
  bundle: true,
  write: false,
  format: 'esm',
  platform: 'node',
  target: 'node18',
  logLevel: 'error',
});
const bundlePath = join(TMP_DIR, 'preview.mjs');
writeFileSync(bundlePath, result.outputFiles[0].text);
const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

const css = readFileSync(join(SRC_DIR, 'style.css'), 'utf-8');
const html = `<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>晨间简报 v2 预览 · SummitWorkbench</title>
<style>${css}
/* 预览专用 */
body { padding: 24px; }
.preview-shell { max-width: 880px; margin: 0 auto; display: grid; gap: 40px; }
.preview-head { color: var(--muted); font-size: 13px; }
.preview-caption { display: flex; align-items: baseline; gap: 12px; margin: 0 0 10px; }
.preview-caption h2 { font-size: 16px; margin: 0; }
.preview-caption span { font-size: 12px; color: var(--muted); }
</style></head><body>
<div class="preview-shell">
  <div>
    <div class="preview-caption"><h2>晨间简报 v2 · 今日真实数据</h2><span>2026-09-03 · 结构化渲染（生产同一套代码输出）</span></div>
    <div class="brief brief2">${mod.cards.real}</div>
  </div>
  <div>
    <div class="preview-caption"><h2>状态示例</h2><span>降级横幅 · 待确认提示 · 空会议 · 提议/最近完成折叠</span></div>
    <div class="brief brief2">${mod.cards.states}</div>
  </div>
</div>
</body></html>`;

mkdirSync(dirname(OUT_HTML), { recursive: true });
writeFileSync(OUT_HTML, html);
rmSync(TMP_DIR, { recursive: true, force: true });
console.log('preview →', OUT_HTML);
