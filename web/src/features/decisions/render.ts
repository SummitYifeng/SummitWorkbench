import { esc } from '../../md';
import type { DecisionFilters, DecisionLink, DecisionRow, DecisionsPayload } from './types';

/**
 * 决策台账页的纯渲染（不碰 DOM，便于 `web/scripts/test-decisions-render.mjs` 直接断言）。
 *
 * 展示口径：按状态分组（生效中 → 待复核 → 已被替代），每条给出
 * 「日期 · 管线 · 主题」+ 标题 + 一句话摘要 + 演进关系（推翻了哪条 / 被哪条推翻）。
 */

const STATUS_ORDER = ['effective', 'under-review', 'superseded'] as const;

function options(values: string[], current: string, label: (value: string) => string): string {
  return ['<option value="">全部</option>']
    .concat(
      values.map(
        (value) =>
          '<option value="' +
          esc(value) +
          '"' +
          (value === current ? ' selected' : '') +
          '>' +
          esc(label(value)) +
          '</option>'
      )
    )
    .join('');
}

function relations(row: DecisionRow): string {
  const parts: string[] = [];
  if (row.supersedes.length > 0) {
    const names = row.supersedes.map((link: DecisionLink) => esc(link.title)).join('、');
    parts.push('推翻了：' + names);
  }
  if (row.superseded_by.length > 0) {
    const names = row.superseded_by.map((link: DecisionLink) => esc(link.title)).join('、');
    parts.push('已被推翻：' + names);
  }
  return parts.length > 0 ? '<div class="decision-rel">' + parts.join('　|　') + '</div>' : '';
}

function meta(row: DecisionRow): string {
  const bits = [row.decided_on || '日期未记'];
  if (row.project) bits.push(row.project);
  if (row.domain) bits.push(row.domain);
  if (row.review_on) bits.push('复核 ' + row.review_on);
  return bits.map((bit) => esc(bit)).join(' · ');
}

function decisionCard(row: DecisionRow): string {
  return (
    '<div class="card decision-card" data-status="' +
    esc(row.status) +
    '">' +
    '<div class="card-head"><span class="badge">' +
    esc(row.status_label) +
    '</span> ' +
    esc(row.title) +
    '</div>' +
    '<div class="card-sub">' +
    meta(row) +
    '</div>' +
    (row.summary ? '<div>' + esc(row.summary) + '</div>' : '') +
    relations(row) +
    '</div>'
  );
}

export function decisionsHtml(payload: DecisionsPayload, filters: DecisionFilters): string {
  const labels = payload.status_labels;
  const label = (status: string): string => labels[status] ?? status;

  const bar =
    '<div class="decisions-bar">' +
    '<label>管线<select data-decisions-filter="project">' +
    options(payload.facets.projects, filters.project, (value) => value) +
    '</select></label>' +
    '<label>主题<select data-decisions-filter="domain">' +
    options(payload.facets.domains, filters.domain, (value) => value) +
    '</select></label>' +
    '<label>状态<select data-decisions-filter="status">' +
    options(payload.facets.statuses, filters.status, label) +
    '</select></label>' +
    '<label>关键词<input type="search" data-decisions-filter="q" value="' +
    esc(filters.q) +
    '" placeholder="标题或摘要"></label>' +
    '</div>';

  const counts = STATUS_ORDER.map(
    (status) => label(status) + ' ' + String(payload.counts[status] ?? 0)
  ).join('　·　');
  const selected = payload.decisions.length;

  const warnings = payload.warnings
    .map((text) => '<div class="msg">' + esc(text) + '</div>')
    .join('');

  const groups = STATUS_ORDER.map((status) => {
    const rows = payload.decisions.filter((row) => row.status === status);
    if (rows.length === 0) return '';
    return (
      '<div class="section-title">' +
      esc(label(status)) +
      '（' +
      String(rows.length) +
      '）</div>' +
      rows.map(decisionCard).join('')
    );
  }).join('');

  const empty =
    selected === 0
      ? '<div class="msg">当前筛选下没有决策。把「管线 / 主题 / 状态」调回「全部」试试。</div>'
      : '';

  return (
    '<div class="decisions-view">' +
    bar +
    '<div class="decisions-counts">台账：' +
    counts +
    '　|　当前筛选：' +
    String(selected) +
    ' 条</div>' +
    warnings +
    groups +
    empty +
    '</div>'
  );
}
