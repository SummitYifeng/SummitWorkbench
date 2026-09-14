import { api } from '../../api/request';
import { esc } from '../../md';
import { decisionsHtml } from './render';
import type { DecisionFilters, DecisionsPayload } from './types';

/**
 * 「决策」页：一次筛选一次请求（筛选语义只在服务端实现，界面不重复一份）。
 *
 * 为什么不做客户端筛选：`decisions/*.md` 会随使用增长，而「哪些算生效/待复核/被替代」
 * 与「关系怎么解析」是有口径的逻辑；两份实现（前端+后端）迟早会漂移。
 */

const EMPTY: DecisionFilters = { project: '', domain: '', status: '', q: '' };
let filters: DecisionFilters = { ...EMPTY };
let textTimer: number | null = null;
let latestRequest = 0;

function queryString(current: DecisionFilters): string {
  const params = new URLSearchParams();
  (['project', 'domain', 'status', 'q'] as const).forEach((key) => {
    const value = current[key].trim();
    if (value) params.set(key, value);
  });
  const text = params.toString();
  return text ? '?' + text : '';
}

/** 切换 workspace 时清空筛选（与其它 feature 的 reset* 同一约定）。 */
export function resetDecisionsForWorkspace(): void {
  filters = { ...EMPTY };
}

export async function renderDecisions(): Promise<void> {
  const view = document.getElementById('view-decisions') as HTMLElement | null;
  if (!view) return;
  const request = ++latestRequest;
  try {
    const payload = await api<DecisionsPayload>('/api/decisions' + queryString(filters));
    if (request !== latestRequest) return;
    view.innerHTML = decisionsHtml(payload, filters);
    wireFilters(view);
  } catch (error) {
    if (request !== latestRequest) return;
    view.innerHTML = '<div class="msg">决策台账读取失败：' + esc(String(error)) + '</div>';
  }
}

function wireFilters(view: HTMLElement): void {
  view.querySelectorAll<HTMLElement>('[data-decisions-filter]').forEach((element) => {
    const key = element.dataset.decisionsFilter as keyof DecisionFilters | undefined;
    if (!key) return;
    const apply = (): void => {
      filters = { ...filters, [key]: elementValue(element) };
      void renderDecisions();
    };
    if (key === 'q') {
      // 输入框防抖：每敲一个字都请求一次会把台账刷得跳来跳去。
      element.addEventListener('input', () => {
        if (textTimer !== null) window.clearTimeout(textTimer);
        textTimer = window.setTimeout(apply, 250);
      });
    } else {
      element.addEventListener('change', apply);
    }
  });
}

function elementValue(element: HTMLElement): string {
  if (element instanceof HTMLSelectElement || element instanceof HTMLInputElement) {
    return element.value;
  }
  return '';
}

export type { DecisionFilters, DecisionRow, DecisionsPayload } from './types';
