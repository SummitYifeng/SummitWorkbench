import { esc } from '../../md';
import type { AskAnswer } from './types';

/** 问答页的纯字符串渲染（Node 下可直接断言，不触碰 DOM）。 */

export function askSourceButton(sourceId: string, label = sourceId): string {
  return '<button type="button" class="link source-link" data-action="source-open" data-source-id="' +
    esc(sourceId) + '" title="打开只读来源">' + esc(label) + '</button>';
}

export function renderAskAnswer(answer: AskAnswer, citedSources: string[], recalledSources: string[]): string {
  const cited = new Set(citedSources);
  const parts = [
    '<p class="answer-summary"><strong>' + esc(answer.summary) + '</strong></p>',
  ];
  if (answer.unanswerable) {
    parts.push('<p class="msg info">当前来源不足以回答，下面内容不会被当作确定事实。</p>');
  }
  if (answer.facts.length) {
    parts.push('<section class="answer-facts"><h4>事实（实际引用）</h4><ul>');
    parts.push(...answer.facts.map((fact) =>
      '<li>' + esc(fact.text) + ' · ' + askSourceButton(fact.source_id, fact.source_id) + '</li>'
    ));
    parts.push('</ul></section>');
  }
  if (answer.conflicts.length) {
    parts.push('<section class="answer-conflicts"><h4>证据冲突（并列保留）</h4>');
    parts.push(...answer.conflicts.map((conflict) =>
      '<div class="answer-conflict"><strong>' + esc(conflict.topic) + '</strong><ul>' +
      conflict.sides.map((side) => '<li>' + esc(side.position) + ' · ' + askSourceButton(side.source_id, side.source_id) + '</li>').join('') +
      '</ul></div>'
    ));
    parts.push('</section>');
  }
  if (answer.suggestions.length) {
    parts.push('<section class="answer-suggestions"><h4>建议（模型推断）</h4><ul>');
    parts.push(...answer.suggestions.map((suggestion) => '<li>' + esc(suggestion) + '</li>'));
    parts.push('</ul></section>');
  }
  const recalledOnly = recalledSources.filter((sourceId) => !cited.has(sourceId));
  if (recalledOnly.length) {
    parts.push('<p class="hint answer-recalled">仅召回、未在回答中引用的材料：' +
      recalledOnly.map((sourceId) => askSourceButton(sourceId, sourceId)).join(' · ') + '</p>');
  }
  return parts.join('');
}
