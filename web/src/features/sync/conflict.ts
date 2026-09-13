import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { clearEntityDraft, loadEntityDraft } from '../../lifecycle/drafts';
import { esc } from '../../md';
import { activateModal, closeModal, setModalReturnFocus, toast } from '../shell';
import { refreshSyncBanner } from './banner';
import { conflictDigestSummary, conflictKindLabel, conflictRevision, conflictSelectionLabel } from './labels';
import { getSyncDeps } from './state';
import type { ConflictDetails, ConflictSelection, RecoveryPreparationSummary, SyncConflictDetailsPayload, SyncConflictRecoveryPayload } from './types';

/** 同步冲突详情弹层、预检与恢复（原 legacy-main 逐条搬迁）。 */

let conflictDetails: ConflictDetails | null = null;
let conflictSelections: Record<string, ConflictSelection> = {};
let conflictPreparation: RecoveryPreparationSummary | null = null;
let conflictMessage: string | null = null;
let conflictBusy = false;

export function conflictSelectionsPayload(): Record<string, string> {
  return Object.fromEntries(Object.entries(conflictSelections).filter(([, choice]) => choice)) as Record<string, string>;
}

export function missingConflictSelections(): string[] {
  return conflictDetails?.paths.filter((item) => !item.automatic && !conflictSelections[item.path]).map((item) => item.path) ?? [];
}

export function activateConflictModal(html: string): HTMLElement {
  const modal = activateModal(html);
  modal.dataset.draftEntity = 'sync-conflict';
  modal.dataset.draftDirty = Object.values(conflictSelections).some(Boolean) ? '1' : '0';
  return modal;
}

export function renderSyncConflictModal(): void {
  const modal = document.getElementById('modal') as HTMLElement | null;
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement | null;
  if (!modal || !backdrop || !conflictDetails) return;
  const details = conflictDetails;
  const missing = missingConflictSelections();
  const preparation = conflictPreparation;
  const message = conflictMessage
    ? '<div class="msg ' + (preparation?.ok ? 'ok' : 'err') + '">' + esc(conflictMessage) + '</div>' : '';
  const pathRows = details.paths.map((item) => {
    const changedOn = item.changed_on.map((side) => side === 'local' ? '本机' : '远端').join('、');
    const metadata = conflictDigestSummary(item);
    const selector = item.automatic
      ? '<span class="conflict-auto">' + esc(item.action === 'rebuild' ? '合并后重建' : '自动收集') + '</span>'
      : '<label class="conflict-choice"><span class="sr-only">' + esc(item.path) + '处理方式</span>' +
        '<select data-conflict-path="' + esc(item.path) + '"' + (conflictBusy ? ' disabled' : '') + '>' +
        '<option value="">请选择处理方式</option>' +
        ((item.kind === 'unknown-generated-view' || item.kind === 'opaque-binary')
          ? ['preserve-both'] as ConflictSelection[]
          : ['keep-local', 'keep-remote', 'preserve-both'] as ConflictSelection[]).map((choice) =>
          '<option value="' + choice + '"' + (conflictSelections[item.path] === choice ? ' selected' : '') + '>' +
          conflictSelectionLabel(choice) + '</option>').join('') + '</select></label>';
    return '<div class="conflict-path"><div class="conflict-path-main"><code>' + esc(item.path) + '</code>' +
      '<span class="hint">' + esc(conflictKindLabel(item.kind)) + ' · 变更：' + esc(changedOn) + '</span>' +
      (metadata ? '<span class="hint conflict-metadata">' + esc(metadata) + '</span>' : '') + '</div>' +
      '<div class="conflict-path-action">' + selector + '</div></div>';
  }).join('');
  const status = preparation
    ? '<div class="conflict-preflight"><strong>' + (preparation.ok ? '临时预检通过' : '临时预检未通过') + '</strong>' +
      '<span>事件 ' + preparation.event_count + ' · 聚合 ' + preparation.aggregate_count +
      ' · 重建视图 ' + preparation.rebuilt_view_count + ' · 候选文件 ' + preparation.candidate_path_count + '</span>' +
      (preparation.error_code ? '<span class="hint">原因：' + esc(preparation.error_code) + '</span>' : '') + '</div>' : '';
  activateConflictModal('<h3>同步冲突详情</h3>' +
    '<p class="hint">当前处于保护态。这里只读取已存在的分叉快照，不展示正文；确认前不会修改 vault。</p>' +
    '<div class="conflict-revisions"><span>共同基线 <code>' + esc(conflictRevision(details.base_revision)) + '</code></span>' +
    '<span>本机 <code>' + esc(conflictRevision(details.local.revision)) + '</code></span>' +
    '<span>远端 <code>' + esc(conflictRevision(details.remote.revision)) + '</code></span></div>' +
    '<div class="conflict-summary">自动处理 ' + details.automatic_path_count + ' 项 · 需要选择 ' + details.manual_path_count + ' 项</div>' +
    '<div class="conflict-paths">' + (pathRows || '<p class="hint">没有可处理的分叉文件。</p>') + '</div>' + message + status +
    '<p class="hint conflict-safety">恢复只会创建普通的本地双父提交，并尝试普通同步；不会 force-push、reset、rebase 或 stash。若远端已再次变化，仍会回到保护态。</p>' +
    '<div class="row"><button class="primary" data-action="sync-conflict-preview"' +
    (conflictBusy || missing.length > 0 ? ' disabled' : '') + '>临时预检（不写入）</button>' +
    (preparation?.ok ? '<button class="ok" data-action="sync-conflict-apply"' + (conflictBusy ? ' disabled' : '') + '>确认恢复并创建提交</button>' : '') +
    '<button class="ghost" data-action="sync-conflict-export"' + (conflictBusy ? ' disabled' : '') + '>导出冲突包</button>' +
    '<button class="ghost" data-action="copy-diagnostics"' + (conflictBusy ? ' disabled' : '') + '>复制诊断</button>' +
    '<button class="ghost" data-action="close-modal"' + (conflictBusy ? ' disabled' : '') + '>稍后处理</button></div>');
  backdrop.hidden = false;
  modal.querySelectorAll<HTMLSelectElement>('[data-conflict-path]').forEach((select) => {
    select.addEventListener('change', () => {
      const path = select.dataset.conflictPath ?? '';
      if (path) conflictSelections[path] = select.value as ConflictSelection;
      getSyncDeps()?.persistEntityDraft('sync-conflict', conflictSelectionsPayload());
      conflictMessage = null;
      renderSyncConflictModal();
      if (path) modal.querySelector<HTMLSelectElement>('[data-conflict-path="' + CSS.escape(path) + '"]')?.focus();
    });
  });
}

export async function showSyncConflictDetails(): Promise<void> {
  const modal = document.getElementById('modal') as HTMLElement | null;
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement | null;
  if (!modal || !backdrop) return;
  const returnFocus = document.querySelector<HTMLElement>('[data-action="sync-conflict-details"]');
  conflictDetails = null;
  conflictSelections = {};
  conflictPreparation = null;
  conflictMessage = null;
  conflictBusy = false;
  activateConflictModal('<div class="loading">正在读取分叉详情（只读）…</div>');
  setModalReturnFocus(returnFocus);
  try {
    const data = await api<SyncConflictDetailsPayload>('/api/sync/conflict/details');
    if (!data.ok || !data.available || !data.details) {
      activateConflictModal('<h3>无法读取同步冲突</h3><p class="msg err">' + esc(data.reason ?? '当前已不在冲突保护态，请刷新同步状态。') + '</p>' +
        '<div class="row"><button class="ghost" data-action="close-modal">关闭</button></div>');
      return;
    }
    conflictDetails = data.details;
    const saved = loadEntityDraft<Record<string, string>>('sync-conflict', Date.now(), getSyncDeps()?.workspaceId()) ?? {};
    conflictSelections = Object.fromEntries(data.details.paths.filter((item) => !item.automatic).map((item) => {
      const allowed: ConflictSelection[] = item.kind === 'unknown-generated-view' || item.kind === 'opaque-binary'
        ? ['preserve-both']
        : ['keep-local', 'keep-remote', 'preserve-both'];
      const choice = saved[item.path] as ConflictSelection;
      return [item.path, allowed.includes(choice) ? choice : ''];
    }));
    renderSyncConflictModal();
  } catch (err) {
    activateConflictModal('<h3>无法读取同步冲突</h3><p class="msg err">' + esc(String(err)) + '</p>' +
      '<div class="row"><button class="ghost" data-action="close-modal">关闭</button></div>');
  }
}

export function conflictRecoveryRequest(confirmed: boolean): Record<string, unknown> {
  if (!conflictDetails) throw new Error('缺少分叉快照');
  return {
    base_revision: conflictDetails.base_revision,
    local_revision: conflictDetails.local.revision,
    remote_revision: conflictDetails.remote.revision,
    selections: conflictSelectionsPayload(),
    confirmed,
  };
}

export function conflictSelectionRequest(): Record<string, unknown> {
  if (!conflictDetails) throw new Error('缺少分叉快照');
  return {
    base_revision: conflictDetails.base_revision,
    local_revision: conflictDetails.local.revision,
    remote_revision: conflictDetails.remote.revision,
    selections: conflictSelectionsPayload(),
  };
}

/**
 * 恢复失败的稳定原因码 → 用户能照着做的一句话（D7）。
 *
 * 这条路径此前只显示「恢复准备未完成」：后端把原因放在 `preparation.error_code`
 * / `recovery.error_code` 里，而前端只读 `data.reason`（那种分支不返回它），于是
 * 用户既不知道发生了什么、也不知道下一步做什么（2026-09-13 双机复跑实测）。
 */
const RECOVERY_FAILURE_HINTS: Record<string, string> = {
  conflict_snapshot_stale: '远端或本机在上次读取之后又变了：请关掉本弹层、重新打开「查看冲突详情」再试。',
  current_worktree_dirty: '工作树里还有未提交改动：请先提交或撤销它们，再重新打开冲突详情。',
  manual_selection_incomplete: '还有文件没有选择处理方式：请逐个选完再预检。',
  manual_selection_invalid: '选择不合法：未知派生视图与二进制文件只能选「保留双方副本」。',
  preserve_both_path_collision: '同目录已存在上次保留的远端副本：请改选「保留本机」或「采用远端」。',
  event_projection_failed: '恢复暂存阶段的投影重建失败：请导出冲突包后反馈。',
  remote_content_missing: '远端那一侧缺少该文件内容：请重新打开冲突详情再试。',
};

export async function previewSyncConflictRecovery(): Promise<void> {
  if (!conflictDetails || conflictBusy) return;
  const missing = missingConflictSelections();
  if (missing.length) {
    conflictMessage = '请先为所有人工文件选择处理方式。';
    renderSyncConflictModal();
    return;
  }
  conflictBusy = true;
  conflictMessage = '正在临时环境预检，当前 vault 不会写入…';
  renderSyncConflictModal();
  try {
    const request = conflictRecoveryRequest(false);
    if (conflictDetails.manual_path_count > 0) {
      const selection = await api<{ ok: boolean; selection?: { error_code?: string | null }; reason?: string }>(
        '/api/sync/conflict/selection/validate',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conflictSelectionRequest()) },
      );
      if (!selection.ok) {
        conflictMessage = selection.reason ?? selection.selection?.error_code ?? '人工选择未通过校验。';
        conflictBusy = false;
        renderSyncConflictModal();
        return;
      }
    }
    const data = await api<SyncConflictRecoveryPayload>('/api/sync/conflict/recover', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
    });
    conflictPreparation = data.preparation ?? null;
    if (data.preparation?.ok) {
      conflictMessage = '预检完成。请确认后才会写回并创建提交。';
    } else {
      const code = data.preparation?.error_code ?? data.recovery?.error_code ?? null;
      conflictMessage = data.reason ?? (code
        ? RECOVERY_FAILURE_HINTS[code] ?? ('恢复准备未通过（' + code + '）：请重新打开冲突详情后重试。')
        : '恢复准备未完成。');
    }
  } catch (err) {
    conflictMessage = String(err);
  } finally {
    conflictBusy = false;
    renderSyncConflictModal();
  }
}

export async function applySyncConflictRecovery(): Promise<void> {
  if (!conflictDetails || !conflictPreparation?.ok || conflictBusy) return;
  if (!window.confirm('确认将预检结果写回当前 vault，创建普通的本地双父合并提交，并尝试普通同步？')) return;
  conflictBusy = true;
  let committed = false;
  conflictMessage = '正在写回并创建本地恢复提交…';
  renderSyncConflictModal();
  try {
    const data = await mutation(() => api<SyncConflictRecoveryPayload>('/api/sync/conflict/recover', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conflictRecoveryRequest(true)),
    }));
    if (data.recovery?.status === 'committed') {
      committed = true;
      clearEntityDraft('sync-conflict', getSyncDeps()?.workspaceId());
      closeModal();
      const auditFailed = data.recovery.audit?.status === 'failed';
      const message = auditFailed
        ? (data.push?.ok
          ? '恢复提交已同步，但脱敏审计记录未完成。'
          : '恢复提交已创建；普通同步与脱敏审计记录均未完成。')
        : (data.push?.ok
          ? '恢复提交已创建并完成普通同步。'
          : '恢复提交已创建，普通同步暂未完成，请稍后点击“立即重试”。');
      toast(message, data.push?.ok && !auditFailed ? 'ok' : 'info');
      await Promise.all([refreshSyncBanner(), getSyncDeps()?.refreshState()]);
      return;
    }
    conflictMessage = data.reason ?? '恢复未提交：' + (data.recovery?.error_code ?? data.recovery?.status ?? '未知原因');
  } catch (err) {
    conflictMessage = String(err);
  } finally {
    conflictBusy = false;
    if (!committed && conflictDetails) renderSyncConflictModal();
  }
}
