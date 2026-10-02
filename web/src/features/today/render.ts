import { briefCardHtml, emptyBriefCardHtml } from '../../brief-card';
import { esc } from '../../md';
import { projectDisplayName } from '../projects';
import type { ImportReceipt, InboxItem, TodayRenderOptions } from './types';

/**
 * 收件箱块（契约 §10）：待处理条目 + 每条一个「提升为…」按钮。
 *
 * **只读渲染**：这里绝不发请求、更不调模型——条目由 `refreshState()` 通过
 * `GET /api/inbox` 一次性取回后传进来（成本约定：列表渲染不花钱）。
 * 空收件箱只留一句轻提示，不占大块版面。
 */
function inboxBlock(items: InboxItem[], error?: string | null): string {
  const head = '<div class="today-inbox-head"><span class="bf-sec-title">收件箱（' +
    items.length + ' 条）</span><span class="hint">提升后移出收件箱；系统先建议、你逐条确认</span></div>';
  if (error) {
    return '<section class="today-inbox today-inbox-error" id="today-inbox">' + head +
      '<p class="hint">收件箱读取失败：' + esc(error) + '</p></section>';
  }
  if (!items.length) {
    return '<section class="today-inbox today-inbox-empty" id="today-inbox">' + head +
      '<p class="hint">收件箱是空的——「记点什么」会先落到这里，再决定提升成什么。</p></section>';
  }
  const rows = items.map((item) => {
    const meta: string[] = [];
    if (item.project) meta.push('#' + esc(item.project));
    if (item.due) meta.push('截止 ' + esc(item.due));
    if (item.kind) meta.push(item.kind === 'task' ? '承诺' : '想法');
    return '<li class="today-inbox-item">' +
      '<div class="today-inbox-text">' + esc(item.text) + '</div>' +
      '<div class="today-inbox-side">' +
      (meta.length ? '<span class="hint">' + meta.join(' · ') + '</span>' : '') +
      '<button class="ghost" type="button" data-action="inbox-promote" data-id="' + esc(item.id) +
      '" title="把这条提升为项目页条目 / 飞书待办 / 工作思考">提升为…</button>' +
      '</div></li>';
  }).join('');
  return '<section class="today-inbox" id="today-inbox">' + head +
    '<ul class="today-inbox-list">' + rows + '</ul></section>';
}

function importDrawer(open: boolean, importing: boolean, results: ImportReceipt[] = []): string {
  const panel = importing
    ? '<div class="dropzone busy"><div class="spinner"></div><p>正在归档并结构化…（模型处理中，稍候）</p></div>'
    : '<div class="dropzone" id="dropzone"><div class="dz-icon">⤓</div>' +
      '<p><strong>拖入会议逐字稿</strong>（.md / .txt，带说话人+时间戳）</p>' +
      '<p class="hint">或 <button class="link" id="btn-pick">点击选择文件</button> · 可多选，系统会按顺序处理</p>' +
      '<input type="file" id="file-input" accept=".md,.txt" multiple hidden></div>';
  const resultHtml = results.length
    ? '<div class="import-result" id="import-result" aria-live="polite">' + results.map((result) =>
      '<div class="import-receipt ' + result.status + '"><strong>' + esc(result.fileName) + '</strong>' +
      '<span class="hint">' + (result.bytes / 1024 / 1024).toFixed(2) + ' MiB · ' + esc(result.message) + '</span>' +
      (result.details?.length ? '<ul>' + result.details.map((item) => '<li>' + esc(item) + '</li>').join('') + '</ul>' : '') +
      (result.estimate?.crosses_soft_budget ? '<span class="hint">本次估算接近软预算，仅提示，不阻断导入。</span>' : '') +
      ((result.status === 'error' || result.status === 'partial') && result.jobId ? '<button class="ghost import-retry" data-action="import-retry" data-job-id="' + esc(result.jobId) + '">' + (result.status === 'partial' ? '继续处理失败项' : '继续处理') + '</button>' : '') +
      '</div>'
    ).join('') + '</div>' : '';
  return '<div class="import-drawer' + (open ? ' open' : '') + '" id="import-drawer"' +
    (open ? '' : ' hidden') + '><div class="import-drawer-head"><strong>导入会议纪要</strong>' +
    '<button class="ghost" id="btn-import-close" type="button" aria-label="关闭">✕</button></div>' +
    '<p class="hint">导入后自动归档原文、生成结构化笔记，提取项进入审批页，等你逐条确认。</p>' +
    panel + resultHtml + '</div>';
}

export function todayHtml(options: TodayRenderOptions, captureValue: string): string {
  const state = options.state;
  if (!state) {
    return options.loadError
      ? '<div class="empty load-error"><p>今日数据读取失败：' + esc(options.loadError) + '</p>' +
        '<button class="primary" data-action="retry-state" type="button">重试读取</button></div>'
      : '<div class="loading">正在连接工作台…</div>';
  }
  // 项目 ID → 中文显示名：行动项只显示中文名（ID 收进来源）。
  const projectNames: Record<string, string> = {};
  for (const p of state.projects) projectNames[p.name] = projectDisplayName(p);
  const briefBody = state.brief
    ? briefCardHtml(state.brief, state.day, projectNames)
    : emptyBriefCardHtml();
  const capture = '<div class="today-tool today-capture"><h3>记一句</h3><p class="hint">快速收下一个想法或承诺，稍后再整理。</p><form id="capture-form" autocomplete="off">' +
    '<input id="capture-input" type="text" placeholder="写下一句话…（可用 #项目 标注）" value="' +
    esc(captureValue) + '"><button class="primary" type="submit"' + (options.capturing ? ' disabled' : '') + '>' +
    (options.capturing ? '保存中…' : '记入') + '</button></form>' +
    '<p class="hint">回车保存。条目会出现在收件箱，之后可以决定放到哪里。</p>' +
    '<div class="row today-journal-actions">' +
    '<button class="ghost" type="button" data-action="journal-log" title="记录今天的进展、待办和卡点">工作日志</button>' +
    '<button class="ghost" type="button" data-action="journal-thought" title="整理一个问题、思考过程和结论">工作思考</button>' +
    '</div></div>';
  const header = '<div class="brief-head"><div class="brief-head-main"><p class="kicker">今天</p>' +
    '<h2>' + esc(state.day) + '</h2></div><div class="brief-head-side"><span class="health ' +
    options.health.tone + '"></span><span>' + esc(options.health.label) + '</span></div>' +
    '<div class="brief-head-actions"><button class="ghost" data-action="run-brief" type="button" title="重新生成今日简报（约 30 秒）">↻ 重新生成</button></div></div>';
  const readStatus = options.readStatus?.error
    ? '<p class="stale-data">本次读取失败，保留上次成功数据' +
      (options.readStatus.lastSuccessfulAt ? ' · 最近成功读取于 ' + esc(options.readStatus.lastSuccessfulAt) : '') +
      '。可点击右上角刷新重试。</p>'
    : (options.readStatus?.lastSuccessfulAt ? '<p class="read-data">本地数据读取于 ' + esc(options.readStatus.lastSuccessfulAt) + '</p>' : '');
  const briefNotice = state.brief
    ? ''
    : '<p class="brief-status">今日结构化简报暂不可用，请点击页头「重新生成」。</p>';
  const importTool = '<div class="today-tool today-import"><h3>导入会议纪要</h3>' +
    '<p class="hint">导入逐字稿后自动归档原文、生成结构化笔记，提取项进入审批页。</p>' +
    '<button class="ghost" id="btn-import-meeting" type="button" title="导入会议纪要（拖入逐字稿）">打开导入</button>' +
    importDrawer(options.importOpen, options.importing, options.importResults) + '</div>';
  return '<section class="brief brief2 brief-today">' + header +
    '<div class="today-tools">' + capture + importTool + '</div>' +
    inboxBlock(options.inboxItems ?? [], options.inboxError) +
    readStatus + briefNotice + '<div class="brief-body">' + briefBody + '</div>' +
    '</section>';
}
