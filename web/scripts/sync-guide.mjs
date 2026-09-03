// 构建前同步：把 docs/product/WEB_USAGE_GUIDE.md（使用指南唯一事实源）拷贝为
// web/src/guide.md，供 SPA「指南」页签以 ?raw 导入内置渲染（离线可用）。
// 用法：npm run sync-guide（已并入 dev / build）
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '../../docs/product/WEB_USAGE_GUIDE.md');
const dst = join(here, '../src/guide.md');

try {
  const md = readFileSync(src, 'utf8');
  mkdirSync(dirname(dst), { recursive: true });
  writeFileSync(dst, md);
  console.log(`✓ 使用指南已同步 → ${dst}（${md.length} 字符）`);
} catch (err) {
  console.error('✗ 同步使用指南失败：', err instanceof Error ? err.message : err);
  process.exit(1);
}
