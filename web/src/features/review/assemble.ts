import { esc } from '../../md';
import { getReviewDeps, type ReviewAssembleInput } from './deps';
import { reviewUi } from './state';
import { reviewHtml } from './render';

/** 审批页装配（原 legacy-main 的 renderReview，逐条搬迁）。 */

export function renderReview(view: HTMLElement, input: ReviewAssembleInput): void {
  if (!input.review) {
    view.innerHTML = input.loadError
      ? '<div class="empty load-error"><p>审批数据读取失败：' + esc(input.loadError) + '</p><button class="primary" data-action="retry-review">重试读取</button></div>'
      : '<div class="loading">加载审批页…</div>';
    return;
  }
  const readNotice = input.loadError
    ? '<div class="msg err">本次审批读取失败，保留上次成功数据' +
      (input.lastReadAt ? ' · 最近成功读取于 ' + esc(input.lastReadAt) : '') + '。可稍后重试。</div>'
    : '';
  view.innerHTML = readNotice + reviewHtml(
    input.review,
    input.pendingReview,
    input.day,
    input.projects,
    input.externalActions,
    input.externalActionsError,
    { filter: reviewUi.filter, selectedIds: reviewUi.selected },
  );
  view.querySelectorAll<HTMLFormElement>('.edit-form').forEach((form) => {
    const candidateId = String(new FormData(form).get('candidate_id') ?? '');
    const fields = input.drafts[candidateId];
    if (!fields) return;
    for (const [name, value] of Object.entries(fields)) {
      const input = form.elements.namedItem(name);
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement || input instanceof HTMLSelectElement) {
        input.value = value;
      }
    }
  });
  view.oninput = () => getReviewDeps()?.saveDraftSnapshot();
  view.onchange = () => getReviewDeps()?.saveDraftSnapshot();
  const filter = view.querySelector<HTMLSelectElement>('#review-status-filter');
  filter?.addEventListener('change', () => {
    const next = filter.value;
    if (next !== 'all' && next !== 'pending' && next !== 'approved' && next !== 'rejected') return;
    reviewUi.filter = next;
    reviewUi.selected.clear();
    renderReview(view, input);
    view.querySelector<HTMLSelectElement>('#review-status-filter')?.focus();
  });
  view.querySelectorAll<HTMLInputElement>('[data-review-select]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      const id = checkbox.dataset.reviewSelect ?? '';
      if (!id) return;
      if (checkbox.checked) reviewUi.selected.add(id);
      else reviewUi.selected.delete(id);
      renderReview(view, input);
      const next = Array.from(view.querySelectorAll<HTMLInputElement>('[data-review-select]'))
        .find((candidate) => candidate.dataset.reviewSelect === id);
      next?.focus();
    });
  });
}

/** 由组合根在刷新后调用：用注入的装配输入重绘审批页。 */
export function renderReviewView(): void {
  const view = document.getElementById('view-review') as HTMLElement | null;
  const input = getReviewDeps()?.assemble();
  if (view && input) renderReview(view, input);
}
