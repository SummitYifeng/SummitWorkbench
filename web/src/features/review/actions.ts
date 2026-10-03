import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { esc } from '../../md';
import { openModal, toast } from '../shell';
import { renderReviewView } from './assemble';
import { getReviewDeps } from './deps';
import { reviewUi } from './state';
import type { ExternalAction, ReviewEntry } from './types';

/** 审批决策与写回动作（原 legacy-main 逐条搬迁）。 */

export const REVIEW_BATCH_LIMIT = 100;

type ReviewActionApi = <T>(url: string, init?: RequestInit) => Promise<T>;
type ReviewActionMutation = <T>(work: () => Promise<T>) => Promise<T>;

export interface ReviewEditDeps {
  api: ReviewActionApi;
  mutation: ReviewActionMutation;
  toast: (message: unknown, tone: 'ok' | 'err' | 'info') => void;
  refreshReview: () => Promise<unknown>;
  refreshState: () => Promise<unknown>;
}

/** 审批编辑表单提交；保存并批准继续复用原有两步 HTTP 顺序。 */
export function submitReviewEdit(
  form: HTMLFormElement,
  submitter: HTMLElement | null,
  deps: ReviewEditDeps,
): void {
  const data = new FormData(form);
  const body: Record<string, string> = {};
  data.forEach((value, key) => { body[key] = String(value); });
  const saveAndApprove = submitter?.dataset?.action === 'save-approve';
  void deps.mutation(async () => {
    const r = await deps.api<{ ok: boolean; message: string }>('/api/review/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      deps.toast(r.message, 'err');
      return;
    }
    if (!saveAndApprove) {
      deps.toast(r.message, 'ok');
      void deps.refreshReview();
      return;
    }
    // 保存并批准：落点未定与后端 apply 的「缺少 route」守卫一致，禁止直接批准。
    if (!body.route) {
      deps.toast('已保存。落点未定无法批准——请选好落点后再批准', 'info');
      void deps.refreshReview();
      return;
    }
    try {
      const decision = await deps.api<{ ok: boolean; message: string }>('/api/review/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: String(body.candidate_id ?? ''), decision: 'approved' }),
      });
      if (decision.ok) {
        deps.toast('✓ 已保存并批准 —— 仅标记，点「应用（写回）」才真正写回/建任务', 'ok');
      } else {
        deps.toast(decision.message, 'err');
      }
    } catch (err) {
      deps.toast(err, 'err');
    }
    void deps.refreshReview();
    void deps.refreshState();
  }).catch((err: unknown) => deps.toast(err, 'err'));
}

/**
 * 批准时只纳入"有依据且已定落点"的条目：缺依据或落点未定的候选必须留在待确认，
 * 由人工逐条处理（原 batchSelectedReview 内联判断，抽成纯函数以便断言）。
 */
export function approvableEntries(entries: ReviewEntry[]): ReviewEntry[] {
  return entries.filter((entry) => entry.actionable && !!entry.route);
}

export async function reconcileExternalAction(operationId: string, decision: string, remoteId?: string): Promise<void> {
  try {
    const r = await mutation(() => api<{ ok: boolean; message?: string }>(
      '/api/external-actions/' + encodeURIComponent(operationId) + '/reconcile',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, remote_id: remoteId, confirm_retry: decision === 'retry' }),
      },
    ));
    toast(r.ok ? '外部写回状态已更新' : (r.message ?? '核对失败'), r.ok ? 'ok' : 'err');
    if (r.ok) await getReviewDeps()?.refreshReview();
  } catch (err) {
    toast(err, 'err');
  }
}
export function selectedReviewEntries(): ReviewEntry[] {
  const byId = new Map((getReviewDeps()?.assemble().review?.groups ?? []).flatMap((group) => group.entries).map((entry) => [entry.candidate_id, entry]));
  return Array.from(reviewUi.selected)
    .map((id) => byId.get(id))
    .filter((entry): entry is ReviewEntry => Boolean(entry && entry.decision === 'pending'));
}
export function batchSelectedReview(decision: 'approved' | 'rejected'): void {
  const picked = selectedReviewEntries();
  const selected = picked.filter((entry) =>
    decision === 'rejected' || approvableEntries([entry]).length === 1,
  );
  if (decision === 'approved' && selected.length === 0) {
    toast('选中的候选缺少依据或落点，未批准', 'info');
    return;
  }
  const blocked = decision === 'approved' ? picked.length - selected.length : 0;
  const note = blocked > 0 ? blocked + ' 条因依据或落点不完整未纳入批准' : '';
  reviewUi.selected.clear();
  void batchDecide(selected.map((entry) => entry.candidate_id), decision, note);
}
export async function decide(candidateId: string, decision: string): Promise<void> {
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/review/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    }));
    if (r.ok) {
      const verb = decision === 'approved' ? '已批准' : decision === 'rejected' ? '已拒绝' : '已改回待确认';
      const tip = decision === 'approved' ? '—— 仅标记，点「应用（写回）」才真正写回/建任务' : '';
      toast('✓ ' + verb + tip, 'ok');
    } else {
      toast(r.message, 'err');
    }
  } catch (err) {
    toast(err, 'err');
  }
  // 决定变化后旧预演失效：必须重新「检查并写回」才能应用。
  reviewUi.planReady = false;
  void getReviewDeps()?.refreshReview();
  void getReviewDeps()?.refreshState();
}

/** Approve the exact current version rendered on a formal-content review card. */
export async function approveContent(path: string, contentSha256: string, title: string): Promise<void> {
  if (!path || !/^[0-9a-f]{64}$/.test(contentSha256)) {
    toast('审批版本信息无效，请刷新审批页', 'err');
    return;
  }
  if (!window.confirm('批准“' + title + '”的当前版本？批准后该内容将作为正式版本生效。')) return;
  try {
    const response = await mutation(() => api<{ ok: boolean; message: string }>(
      '/api/review/content/approve',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content_sha256: contentSha256 }),
      },
    ));
    toast(response.message, response.ok ? 'ok' : 'err');
    if (response.ok) {
      await getReviewDeps()?.refreshReview();
      await getReviewDeps()?.refreshState();
    }
  } catch (error) {
    toast(error, 'err');
  }
}
export async function batchDecide(candidateIds: string[], decision: string, note = ''): Promise<void> {
  if (candidateIds.length === 0) {
    toast('没有可操作的条目', 'info');
    return;
  }
  if (candidateIds.length > REVIEW_BATCH_LIMIT) {
    toast('本次批量操作包含 ' + candidateIds.length + ' 条，超过单批上限 100 条，未执行；请缩小范围后重试', 'err');
    return;
  }
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string; updated?: number }>('/api/review/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds, decision }),
    }));
    if (r.ok) {
      const verb = decision === 'approved' ? '批准' : decision === 'rejected' ? '拒绝' : '改回待确认';
      const tip = decision === 'approved' ? '—— 仅标记，点「应用（写回）」才真正写回/建任务' : '';
      toast('✓ 已批量' + verb + ' ' + (r.updated ?? '') + ' 条' + (note ? ' · ' + note : '') + tip, 'ok');
    } else {
      toast(r.message, 'err');
    }
  } catch (err) {
    toast(err, 'err');
  }
  // 批量决定同样使旧预演失效。
  reviewUi.planReady = false;
  void getReviewDeps()?.refreshReview();
  void getReviewDeps()?.refreshState();
}
export async function planApply(exec: boolean): Promise<void> {
  if (exec && reviewUi.applyBusy) return;
  if (exec && !reviewUi.planReady) {
    toast('请先查看最新预演，再确认写回', 'info');
    return;
  }
  if (exec) {
    reviewUi.applyBusy = true;
    document.querySelectorAll<HTMLButtonElement>('#modal [data-action="apply"]').forEach((button) => {
      button.disabled = true;
    });
  }
  const planResult = document.getElementById('plan-result');
  try {
    const r = await mutation(() => api<{
      ok: boolean;
      message?: string;
      plan_text?: string;
      executed?: boolean;
      applied?: number;
      rejected?: number;
      failed?: number;
      external_actions?: ExternalAction[];
    }>(
      exec ? '/api/review/apply' : '/api/review/plan',
      { method: 'POST' },
    ));
    if (!r.ok) {
      reviewUi.planReady = false;
      toast(r.message ?? '操作失败', 'err');
      return;
    }
    const text = r.plan_text ?? '';
    const title = exec
      ? (typeof r.failed === 'number' && r.failed > 0 ? '部分完成：仍有条目需处理' : '完成：已应用')
      : '预演计划（未写入）';
    openModal(
      '<h3>' + title + '</h3><pre>' + esc(text) + '</pre>' +
      (exec
        ? '<p class="hint">已应用 ' + String(r.applied ?? 0) + ' 条 · 已拒绝 ' + String(r.rejected ?? 0) +
          ' 条 · 失败 ' + String(r.failed ?? 0) + ' 条。失败项和未知外部结果请在审批页继续处理。</p>'
        : '<div class="row"><button class="primary" data-action="apply">确认应用（写回项目/建任务/归档）</button></div>')
    );
    reviewUi.planReady = !exec;
    if (exec) {
      reviewUi.planReady = false;
      if (r.external_actions) getReviewDeps()?.setExternalActions(r.external_actions);
      toast(typeof r.failed === 'number' && r.failed > 0 ? '应用部分完成，请查看失败项' : '应用完成', r.failed ? 'info' : 'ok');
      void getReviewDeps()?.refreshReview();
      void getReviewDeps()?.refreshState();
    }
  } catch (err) {
    toast(err, 'err');
    if (planResult) planResult.innerHTML = '<div class="msg err">' + esc(String(err)) + '</div>';
  } finally {
    if (exec) reviewUi.applyBusy = false;
  }
}

/** data-action="review-select-all"：按当前筛选全选/全不选（原派发器内联分支）。 */
export function selectAllReview(): void {
  const all = getReviewDeps()?.assemble().review?.groups ?? [];
  const selectable = all
    .flatMap((group) => group.entries)
    .filter((entry) => entry.decision === 'pending' && (reviewUi.filter === 'all' || reviewUi.filter === 'pending'))
    .map((entry) => entry.candidate_id);
  const allSelected = selectable.length > 0 && selectable.every((id) => reviewUi.selected.has(id));
  selectable.forEach((id) => {
    if (allSelected) reviewUi.selected.delete(id);
    else reviewUi.selected.add(id);
  });
  renderReviewView();
}

/** data-action="group-decide"：按分组批量决定（原派发器内联分支）。 */
export function decideGroup(groupIndex: number, decision: string): void {
  const group = getReviewDeps()?.assemble().review?.groups[groupIndex];
  if (!group) return;
  const pendingEntries = group.entries.filter((e) => e.decision === 'pending');
  const entries = decision === 'approved'
    ? approvableEntries(pendingEntries)
    : pendingEntries;
  const blocked = decision === 'approved' ? pendingEntries.length - entries.length : 0;
  const note = blocked > 0 ? blocked + ' 条因依据或落点不完整未纳入批准' : '';
  void batchDecide(entries.map((e) => e.candidate_id), decision, note);
}

/** data-action="reject-expired"：拒绝已过截止的待确认项（原派发器内联分支）。 */
export function rejectExpired(): void {
  const today = getReviewDeps()?.assemble().day ?? '';
  const ids = (getReviewDeps()?.assemble().review?.groups ?? [])
    .flatMap((g) => g.entries)
    .filter((e) => e.decision === 'pending' && !!e.due_date && !!today && e.due_date < today)
    .map((e) => e.candidate_id);
  void batchDecide(ids, 'rejected');
}

/** data-action="external-confirm-created"（原派发器内联分支）。 */
export function confirmExternalCreated(operationId: string): void {
  const remoteId = window.prompt('请输入飞书侧已创建对象的 ID：');
  if (remoteId?.trim()) void reconcileExternalAction(operationId, 'succeeded', remoteId.trim());
}

/** data-action="external-confirm-not-found"（原派发器内联分支）。 */
export function confirmExternalNotFound(operationId: string): void {
  if (window.confirm('确认飞书侧没有创建该对象？确认后仍需再次点击“确认后重试”才能重新创建。')) {
    void reconcileExternalAction(operationId, 'not-found');
  }
}

/** data-action="external-retry"（原派发器内联分支）。 */
export function retryExternalAction(operationId: string): void {
  if (window.confirm('再次确认飞书侧未创建，并允许重新创建？')) {
    void reconcileExternalAction(operationId, 'retry');
  }
}
