import { briefCardHtml } from '../../brief-card';
import { esc, mdToHtml } from '../../md';
import { projectsHtml } from '../projects';
import type { TodayRenderOptions } from './types';

function reviewCard(pending: number, oldest: number | null): string {
  return pending > 0
    ? '<div class="card warn"><div class="card-head"><span class="dot warn"></span><strong>待确认审批</strong>' +
      '<span class="count-badge">' + pending + ' 条待确认</span></div>' +
      '<p class="card-sub">' + (oldest != null ? '最老已等待 ' + oldest + ' 天 · ' : '') +
      '处理完才会写回执行系统</p><button class="primary" data-action="go-review">去处理 →</button></div>'
    : '<div class="card ok"><div class="card-head"><span class="dot ok"></span><strong>审批已清空</strong></div>' +
      '<p class="card-sub">无待确认候选，执行系统状态干净。</p></div>';
}

function importDrawer(open: boolean, importing: boolean): string {
  const panel = importing
    ? '<div class="dropzone busy"><div class="spinner"></div><p>正在归档并结构化…（模型处理中，稍候）</p></div>'
    : '<div class="dropzone" id="dropzone"><div class="dz-icon">⤓</div>' +
      '<p><strong>拖入会议逐字稿</strong>（.md / .txt，带说话人+时间戳）</p>' +
      '<p class="hint">或 <button class="link" id="btn-pick">点击选择文件</button> · 文件名建议 YYYY-MM-DD-会议标题.txt</p>' +
      '<input type="file" id="file-input" accept=".md,.txt" hidden></div>' +
      '<div class="import-result" id="import-result"></div>';
  return '<div class="import-drawer' + (open ? ' open' : '') + '" id="import-drawer"' +
    (open ? '' : ' hidden') + '><div class="import-drawer-head"><strong>导入会议纪要</strong>' +
    '<button class="ghost" id="btn-import-close" type="button" aria-label="关闭">✕</button></div>' +
    '<p class="hint">导入后自动归档原文、生成结构化笔记，提取项进入审批页，等你逐条确认。</p>' +
    panel + '</div>';
}

export function todayHtml(options: TodayRenderOptions, captureValue: string): string {
  const state = options.state;
  if (!state) return '<div class="loading">正在连接工作台…</div>';
  const briefBody = state.brief
    ? briefCardHtml(state.brief, state.day)
    : state.brief_generated
      ? '<div class="brief-md-body">' + mdToHtml(state.brief_md ?? '') + '</div>'
      : '<div class="empty"><p>今日简报还没生成。</p><button class="primary" data-action="run-brief">⚡ 现在生成（约 30 秒）</button></div>';
  const capture = '<div class="brief-capture"><form id="capture-form" autocomplete="off">' +
    '<input id="capture-input" type="text" placeholder="记点什么…（想法 / 承诺，可用 #项目 标注）" value="' +
    esc(captureValue) + '"><button class="primary" type="submit">记入</button></form>' +
    '<p class="hint">回车即记入全局 inbox；说清「要做什么 + 截止 + #项目」的，AI 会帮你分类。</p></div>';
  const header = '<div class="brief-head"><div class="brief-head-main"><p class="kicker">今天</p>' +
    '<h2>' + esc(state.day) + '</h2></div><div class="brief-head-side"><span class="health ' +
    options.health.tone + '"></span><span>' + esc(options.health.label) + '</span></div>' +
    '<div class="brief-head-actions"><button class="ghost" id="btn-import-meeting" type="button" title="导入会议纪要（拖入逐字稿）">＋ 导入会议纪要</button>' +
    '<button class="ghost" data-action="run-brief" type="button" title="重新生成今日简报（约 30 秒）">↻ 重新生成</button></div></div>';
  return '<section class="brief brief2 brief-today">' + header + capture +
    '<div class="brief-body">' + briefBody + '</div>' + importDrawer(options.importOpen, options.importing) +
    '</section><section class="block">' + reviewCard(state.status.pending_review, state.status.backlog.oldest_age_days) +
    '</section>' + projectsHtml(state.projects, state.day);
}
