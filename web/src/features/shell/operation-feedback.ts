export interface OperationFeedback {
  id: string;
  status: 'success' | 'partial' | 'failed' | 'unknown' | 'not_found';
  message: string;
  detail?: string;
  path?: string;
  updatedAt: string;
}

const STORAGE_KEY = 'swb:recent-operation-feedback';

function readFeedback(): OperationFeedback[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.id === 'string') : [];
  } catch { return []; }
}

function sourceId(path: unknown): string | undefined {
  if (typeof path !== 'string' || !path) return undefined;
  const marker = '/_vault/';
  const index = path.lastIndexOf(marker);
  const relative = index >= 0 ? path.slice(index + marker.length) : path;
  return relative.startsWith('/') || relative.split('/').includes('..') ? undefined : relative;
}

function locationLabel(path: string): string {
  if (path === 'inbox.md' || path.endsWith('/inbox.md')) return '记录位置：收件箱';
  if (path.startsWith('logs/')) return '记录位置：工作日志';
  if (path.startsWith('thinking/')) return '记录位置：工作思考';
  if (path.startsWith('projects/')) return '记录位置：项目记录';
  if (path.includes('/projects/')) return '记录位置：项目记录';
  return '记录位置：已保存';
}

function render(): void {
  const root = document.getElementById('operation-notice');
  if (!root) return;
  const entries = readFeedback();
  root.replaceChildren();
  if (!entries.length) {
    root.hidden = true;
    return;
  }
  root.hidden = false;
  root.setAttribute('aria-label', '最近操作结果');
  const heading = document.createElement('strong');
  heading.textContent = '最近操作结果';
  root.appendChild(heading);
  const list = document.createElement('ul');
  for (const entry of entries.slice(0, 3)) {
    const row = document.createElement('li');
    row.className = 'operation-feedback-row ' + entry.status;
    const summary = document.createElement('span');
    summary.textContent = entry.message;
    row.appendChild(summary);
    if (entry.status === 'unknown') {
      const query = document.createElement('button');
      query.type = 'button';
      query.className = 'ghost';
      query.dataset.action = 'operation-query';
      query.dataset.operationId = entry.id;
      query.textContent = '重新核实';
      row.appendChild(query);
    }
    if (entry.detail) {
      const detail = document.createElement('span');
      detail.className = 'hint';
      detail.textContent = entry.detail;
      row.appendChild(detail);
    }
    if (entry.path) {
      const location = document.createElement('span');
      location.className = 'hint';
      location.textContent = locationLabel(entry.path);
      row.appendChild(location);
      const id = sourceId(entry.path);
      if (id?.endsWith('.md')) {
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'link';
        open.dataset.action = 'source-open';
        open.dataset.sourceId = id;
        open.textContent = '查看记录';
        row.appendChild(open);
      }
    }
    list.appendChild(row);
  }
  root.appendChild(list);
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.className = 'ghost operation-feedback-dismiss';
  dismiss.textContent = '清除提示';
  dismiss.addEventListener('click', () => {
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* optional persistence */ }
    render();
  });
  root.appendChild(dismiss);
}

export function publishOperationFeedback(
  id: string,
  response: Record<string, unknown>,
): void {
  const unknown = response.status === 'unknown';
  const notFound = response.status === 'not_found';
  const ok = response.ok === true;
  const commit = response.commit && typeof response.commit === 'object'
    ? response.commit as Record<string, unknown> : null;
  const push = response.push && typeof response.push === 'object'
    ? response.push as Record<string, unknown> : null;
  const commitStatus = typeof commit?.status === 'string' ? commit.status : null;
  const pushStatus = typeof push?.status === 'string' ? push.status : null;
  const commitIncomplete = ['failed', 'busy(locked)', 'index-not-clean', 'not-git'].includes(commitStatus ?? '');
  const pushIncomplete = Boolean(pushStatus && !['ready', 'unconfigured'].includes(pushStatus));
  const partial = ok && (commitIncomplete || pushIncomplete);
  const detail = [
    commitIncomplete ? (commitStatus === 'not-git' ? '内容已保存；当前未启用版本留痕。' : '内容已保存；提交留痕未完成。') : '',
    pushStatus === 'ready' ? '同步已完成。' : '',
    pushStatus === 'unconfigured' ? '同步尚未配置；内容已保存在本机。' : '',
    pushStatus === 'skipped' ? '自动同步已跳过；内容已保存在本机。' : '',
    pushStatus && !['ready', 'unconfigured', 'skipped'].includes(pushStatus)
      ? '内容已保存；同步尚未完成，请查看同步状态。' : '',
  ].filter(Boolean).join(' ');
  const entry: OperationFeedback = {
    id,
    status: unknown ? 'unknown' : notFound ? 'not_found' : !ok ? 'failed' : partial ? 'partial' : 'success',
    message: typeof response.message === 'string'
      ? response.message
      : unknown ? '本次操作结果正在核实' : '操作已完成',
    detail: detail || undefined,
    path: sourceId(response.path) ?? (typeof response.path === 'string' ? response.path : undefined),
    updatedAt: new Date().toISOString(),
  };
  const entries = [entry, ...readFeedback().filter((item) => item.id !== id)].slice(0, 10);
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(entries)); } catch { /* save must not fail */ }
  render();
}

export function mountOperationFeedback(): void {
  render();
}

export function unresolvedOperationIds(): string[] {
  return readFeedback().filter((entry) => entry.status === 'unknown').map((entry) => entry.id);
}

export function operationFeedbackHtml(): string {
  return '<section id="operation-notice" class="operation-notice" role="status" aria-live="polite" hidden></section>';
}
