import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { esc } from '../../md';
import { closeModal, openModal, toast } from '../shell';
import { getUndoDeps } from './deps';
import type { UndoDiffPayload, UndoHistoryPayload, WbCommitItem } from './types';

/** 撤销（git 自动提交还原）弹层（原 legacy-main 逐条搬迁）。 */

export const UNDO_FLYNOTE =
  '还原只作用于 vault 文件；飞书侧已产生的副作用（已建任务/会议、已完成状态）不可撤销、不受本次还原影响。';

/** 读取失败时的弹层（纯字符串，Node 下可断言）。 */
export function undoErrorHtml(message: string): string {
  return '<h3>撤销系统改动</h3><p class="msg err">' + esc(message) + '</p>';
}

/** 没有任何自动提交时的弹层。 */
export function undoEmptyHtml(note: string): string {
  return '<h3>撤销系统改动</h3>' +
    '<p>' + esc(note) + '</p>' +
    '<p class="hint">每次系统写回成功都会自动留痕（git 提交，消息以 wb: 开头），可在此一键还原。' + UNDO_FLYNOTE + '</p>';
}

/** 有自动提交时的弹层：每条一行，带「查看差异」「还原此提交」。 */
export function undoListHtml(commits: WbCommitItem[]): string {
  const rows = commits.map((c) =>
    '<div class="undo-commit">' +
    '<div class="undo-head"><strong>' + esc(c.message) + '</strong>' +
    '<span class="hint">' + esc(c.short_sha) + ' · ' + esc(c.time.replace('T', ' ').slice(0, 16)) + '</span></div>' +
    '<div class="hint undo-files">触碰文件：' + esc(c.files.join('、')) + '</div>' +
    '<button class="ghost" data-undo="diff" data-sha="' + c.sha + '">查看差异</button> ' +
    '<button class="ok" data-undo="revert" data-sha="' + c.sha + '">还原此提交</button>' +
    '<pre class="undo-diff" hidden></pre>' +
    '</div>'
  ).join('');
  return '<h3>撤销系统改动</h3>' +
    '<p class="hint">' + UNDO_FLYNOTE + ' 工作树有未提交人工改动的文件会被拒绝还原。</p>' + rows;
}

export async function openUndoModal(): Promise<void> {
  // 复用统一 dialog 激活：初始焦点进入弹层、dialog/aria-modal 语义、关闭按钮与返回焦点，
  // 并清掉上一个弹层遗留的草稿标记，避免 Escape 出现无关的"未保存内容"确认。
  const modal = openModal('<div class="loading">正在读取系统自动提交…</div>');
  let history: UndoHistoryPayload;
  try {
    history = await api<UndoHistoryPayload>('/api/undo/history');
  } catch (err) {
    openModal(undoErrorHtml(String(err)));
    return;
  }
  if (!history.ok || !history.commits) {
    openModal(undoErrorHtml(history.message ?? '读取失败'));
    return;
  }
  if (history.commits.length === 0) {
    openModal(undoEmptyHtml(history.note ?? '暂无系统自动提交'));
    return;
  }
  openModal(undoListHtml(history.commits));
  modal.querySelectorAll<HTMLElement>('[data-undo]').forEach((btn) => {
    const sha = btn.dataset.sha ?? '';
    if (btn.dataset.undo === 'diff') {
      btn.addEventListener('click', () => { void loadUndoDiff(btn, sha); });
    } else if (btn.dataset.undo === 'revert') {
      btn.addEventListener('click', () => { void doUndoRevert(sha); });
    }
  });
}

export async function loadUndoDiff(btn: HTMLElement, sha: string): Promise<void> {
  const row = btn.closest<HTMLElement>('.undo-commit');
  const pre = row?.querySelector<HTMLElement>('.undo-diff');
  if (!pre) return;
  if (!pre.hidden && pre.textContent) {
    pre.hidden = true;
    return;
  }
  pre.hidden = false;
  pre.textContent = '正在读取差异…';
  try {
    const r = await api<UndoDiffPayload>('/api/undo/diff?sha=' + encodeURIComponent(sha));
    pre.textContent = r.ok ? (r.diff ?? '') : ('读取失败：' + (r.message ?? ''));
  } catch (err) {
    pre.textContent = String(err);
  }
}

export async function doUndoRevert(sha: string): Promise<void> {
  if (!window.confirm('确定还原该次系统改动？' + UNDO_FLYNOTE)) return;
  try {
    const r = await mutation(() =>
      api<{ ok: boolean; message: string }>('/api/undo/revert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sha }),
      })
    );
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) {
      closeModal();
      void getUndoDeps()?.refreshAll();
    }
  } catch (err) {
    toast(String(err), 'err');
  }
}
