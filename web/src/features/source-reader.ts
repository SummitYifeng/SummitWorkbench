import { api } from '../api/request';
import { esc, inlineMd, mdToHtml } from '../md';
import { modalBackdrop, openModal } from './shell';

/**
 * 只读来源弹层（审批页的证据「查看原件」用它；原属问答 feature，问答页签下线后独立成域）。
 *
 * 在途序号与守卫必须同模块（§4.2 不变量）；弹层关闭时经 shell 的关闭钩子作废在途读取（§4.4）。
 */

export interface SourceReadPayload {
  ok: boolean;
  message?: string;
  source_id?: string;
  title?: string;
  date?: string | null;
  body?: string;
  truncated?: boolean;
}

let sourceReadSequence = 0;

export function sourceReaderHtml(result: SourceReadPayload, id: string): string {
  return '<h3>' + inlineMd(result.title ?? id) + '</h3>' +
    '<p class="hint">来源：' + esc(result.source_id ?? id) + ' · 日期：' + esc(result.date ?? '未知') + '</p>' +
    (result.truncated ? '<p class="hint">正文已截断，以下内容仅供核查。</p>' : '') +
    '<div class="source-reader">' + mdToHtml(result.body ?? '') + '</div>';
}

export function invalidateSourceReads(): void {
  sourceReadSequence += 1;
}

export async function openSource(sourceId: string): Promise<void> {
  const id = sourceId.trim();
  if (!id) return;
  const requestId = ++sourceReadSequence;
  openModal('<h3>正在读取来源…</h3><p class="hint">只读请求，不会修改工作区。</p>');
  try {
    const result = await api<SourceReadPayload>('/api/sources/read?source_id=' + encodeURIComponent(id));
    const backdrop = modalBackdrop();
    if (requestId !== sourceReadSequence || backdrop?.hidden) return;
    if (!result.ok || result.body === undefined) {
      openModal('<h3>来源暂时不可读</h3><p class="msg err">' + esc(result.message ?? '来源不存在或已失效') +
        '</p><p class="hint">请刷新审批后重试；系统不会用猜测内容替代来源。</p>');
      return;
    }
    openModal(sourceReaderHtml(result, id));
  } catch (err) {
    const backdrop = modalBackdrop();
    if (requestId !== sourceReadSequence || backdrop?.hidden) return;
    openModal('<h3>来源暂时不可读</h3><p class="msg err">' + esc(String(err)) + '</p>');
  }
}
