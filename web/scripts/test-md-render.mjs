// Markdown 子集渲染器的纯函数测试。
// 用的是**真实档案里的形状**（projects/hii-affairs.md、projects/it-development.md）：
// 多行段落、有序列表 + 缩进续行、任务清单、管道表格、[[目标|显示名]]。
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.md-render-test-tmp');
const entry = `
import { esc, mdToHtml } from './md';

export const cases = {
  // 真实形状：一个段落被硬换行拆成三行——必须并成**一个** <p>。
  softWrap: mdToHtml([
    '三条内部口径已经定下并落成决策：**登记主体统一为 HII**、**IP filing 先于 License Contract 执行**、',
    '**「活满」与「和夫曼之旅」分开管理**（详见 \\\`## 决策记录\\\`）。',
    '',
    'Royalty（Loyalty）结算已形成完整执行版：五层计算逻辑。',
  ].join('\\n')),
  ordered: mdToHtml([
    '1. **9 月**：P0 权限清退收口；相关方培训。',
    '2. **10 月**：启动 AI 知识库 V0.1（知识源 Process / 课程资料，用户 罗艺峰 + 韩文博）；',
    '   启动手机端产品设计（定位 / 用户路径 / 信息架构）。',
    '3. **11 月**：AI 进入内部可用版本。',
  ].join('\\n')),
  taskList: mdToHtml(['- [ ] 待办一', '- [x] 已办二'].join('\\n')),
  nested: mdToHtml(['- 外层', '  - 内层'].join('\\n')),
  tableThenList: mdToHtml([
    '| 主线 | 状态 |',
    '|---|---|',
    '| 报名 | 🟢 运行 |',
    '- [[20260623-entity|决定：登记主体统一为 HII]] —— 一律登记在 HII 名下。',
  ].join('\\n')),
  table: mdToHtml([
    '| 主线 | 状态 | 一句话 |',
    '|---|---|---|',
    '| 报名与课程生命周期 | 🟢 正式生产运行 | 缺站内信 / 退款 |',
    '| 门户 / CMS / 权限 | 🟢 已投入业务使用 | 重心转到稳定性 |',
  ].join('\\n')),
  wikilinkLabel: mdToHtml('- [[20260623-hii-registration-entity|决定：IP 登记主体统一为 HII]] —— 一律登记在 HII 名下。'),
  wikilinkBare: mdToHtml('- 见 [[hii/clusters/ip-trademark#关键结论]]。'),
  blockquote: mdToHtml('> 项目 ID \\\`hii-affairs\\\` · 本页是**唯一入口页**。'),
  headings: mdToHtml('## 小节\\n### 更小\\n正文'),
  xss: mdToHtml([
    '<script>alert(1)</script>',
    '**<img src=x onerror=alert(1)>**',
    '- [[a"onmouseover="alert(1)|标签]]',
  ].join('\\n')),
  escaped: esc('A<&"\\''),
};
`;
mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'md-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const outFile = join(tmpDir, 'bundle.mjs');
  writeFileSync(outFile, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(outFile).href + '?t=' + Date.now());
  const c = mod.cases;

  // 段落软换行合并 + 行内粗体/行内代码
  assert.equal(
    (c.softWrap.match(/<p>/g) || []).length,
    2,
    '被硬换行拆开的一段必须并成一个 <p>',
  );
  assert.doesNotMatch(c.softWrap, /\*\*/);
  assert.match(c.softWrap, /<strong>登记主体统一为 HII<\/strong>/);
  assert.match(c.softWrap, /执行<\/strong>、<strong>「活满」/, '同行内标记相交处也不该缝空格');
  assert.match(c.softWrap, /<strong>「活满」与「和夫曼之旅」分开管理<\/strong>/);
  assert.match(c.softWrap, /<code>## 决策记录<\/code>/);

  // 有序列表：一个 <ol>、三项，且第二项的缩进续行并进同一项
  assert.equal((c.ordered.match(/<ol>/g) || []).length, 1);
  assert.equal((c.ordered.match(/<li>/g) || []).length, 3);
  assert.match(c.ordered, /启动 AI 知识库 V0\.1[^<]*启动手机端产品设计/);
  assert.doesNotMatch(c.ordered, /； 相关方/, '中文软换行不该缝出空格');

  // 任务清单
  assert.match(c.taskList, /<span class="task">☐<\/span> 待办一/);
  assert.match(c.taskList, /<span class="task done">☑<\/span> 已办二/);

  // 嵌套无序列表
  assert.equal((c.nested.match(/<ul>/g) || []).length, 2);
  assert.match(c.nested, /<li>外层<ul><li>内层<\/li><\/ul><\/li>/);

  // 表格
  assert.match(c.table, /<table><thead><tr><th>主线<\/th><th>状态<\/th><th>一句话<\/th><\/tr><\/thead>/);
  assert.equal((c.table.match(/<tr>/g) || []).length, 3);
  assert.match(c.table, /<td>报名与课程生命周期<\/td>/);
  // 表格后面紧跟的列表项不能被当成表格行吞掉
  assert.equal((c.tableThenList.match(/<tr>/g) || []).length, 2);
  assert.match(c.tableThenList, /<\/tbody><\/table>\s*<ul><li><span class="wikilink"/);

  // wikilink：只显示标签；无标签时显示目标；目标进 title
  assert.match(c.wikilinkLabel, /title="20260623-hii-registration-entity">决定：IP 登记主体统一为 HII<\/span>/);
  assert.doesNotMatch(c.wikilinkLabel, /\[\[/);
  assert.match(c.wikilinkBare, /title="hii\/clusters\/ip-trademark#关键结论">hii\/clusters\/ip-trademark#关键结论<\/span>/);

  // 引用 / 标题层级
  assert.match(c.blockquote, /<blockquote><p>/);
  assert.match(c.headings, /<h3>小节<\/h3>/);
  assert.match(c.headings, /<h4>更小<\/h4>/);
  assert.match(c.headings, /<p>正文<\/p>/);

  // XSS：任何路径都不许出现可执行标签
  assert.doesNotMatch(c.xss, /<script/);
  assert.doesNotMatch(c.xss, /<img/);
  assert.match(c.xss, /&lt;script&gt;/);
  assert.match(c.xss, /<strong>&lt;img src=x onerror=alert\(1\)&gt;<\/strong>/);
  // 引号被转义后不可能逃出 title 属性
  assert.doesNotMatch(c.xss, /onmouseover="alert/);
  assert.equal(c.escaped, 'A&lt;&amp;&quot;&#39;');

  console.log('Markdown subset render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
