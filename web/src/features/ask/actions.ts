import { api, isStaleWorkspaceResponse } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { clearEntityDraft, loadEntityDraft } from '../../lifecycle/drafts';
import { esc } from '../../md';
import { projectDisplayName, type ProjectState } from '../projects';
import { toast, viewElement } from '../shell';
import { renderAskAnswer } from './render';
import {
  ASK_MAX_THREADS,
  activeAskThread,
  askDraftEntity,
  askHistoryOf,
  makeThreadTitle,
  readAskStore,
  writeAskStore,
} from './store';
import type { AskMsg, AskResponse, AskThread } from './types';

/** 组合根注入的跨域依赖（§4.2：跨域读取一律走函数入参）。 */
export interface AskDeps {
  /** 检索范围下拉的数据源。 */
  projects: () => ProjectState[];
  /** 实体草稿的 workspace 作用域。 */
  workspaceId: () => string | undefined;
  /** 写实体草稿（保留组合根的配额告警语义）。 */
  persistEntityDraft: <T>(entity: string, value: T) => void;
}

let askDeps: AskDeps | null = null;

/** 由 mountAsk 注入依赖。 */
export function setAskDeps(deps: AskDeps): void {
  askDeps = deps;
}

// 页面状态住在产生它的模块里：ESM 的 import 绑定只读，跨模块赋值会被拒绝。

let askThreads: AskThread[] = [];
let askActiveId: string | null = null;
let askBusy = false;
/** 正在请求的会话 id（切换会话时「思考中…」只出现在真正等待的那个会话） */
let askBusyThreadId: string | null = null;
/** 输入框草稿：renderAskChat 会整体重建输入区，等待期间打的新问题不能丢 */
let askDraft = '';
let askErrors: Record<string, string> = {};
/** 问答检索范围：''=全部；否则为项目/线程名（后端按 registry 解析） */
let askScope = '';

function saveAskStore(): void {
  writeAskStore(askThreads, askActiveId);
}

/** workspace 变化时重载会话（原 loadAskStore，语义逐条保留）。 */
export function reloadAskStore(): void {
  const stored = readAskStore();
  if (!stored) return;
  if (stored.threads) askThreads = stored.threads;
  if (stored.activeId !== null) askActiveId = stored.activeId;
  if (!askThreads.some((t) => t.id === askActiveId)) askActiveId = askThreads[0]?.id ?? null;
}

function newAskThread(): AskThread | null {
  if (askThreads.length >= ASK_MAX_THREADS) {
    toast('已达 ' + ASK_MAX_THREADS + ' 个会话上限，请先删除或清空一个', 'err');
    return null;
  }
  const thread: AskThread = {
    id: 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
    title: '新会话',
    createdAt: new Date().toISOString(),
    messages: [],
  };
  askThreads.push(thread);
  askActiveId = thread.id;
  saveAskStore();
  return thread;
}

export function deleteAskThread(threadId: string): void {
  const idx = askThreads.findIndex((t) => t.id === threadId);
  if (idx < 0) return;
  if (!window.confirm('删除会话「' + askThreads[idx].title + '」？其中的问答记录会一并删除。')) return;
  askThreads.splice(idx, 1);
  if (askActiveId === threadId) {
    askActiveId = askThreads[0]?.id ?? null;
    askDraft = '';
  }
  saveAskStore();
  renderAsk(askView());
}

function askView(): HTMLElement {
  return viewElement('ask') as HTMLElement;
}

/** 草稿快照需要读/写输入框草稿（快照编排归 lifecycle，见蓝图 §3.1）。 */
export function getAskDraft(): string {
  return askDraft;
}

export function setAskDraft(value: string): void {
  askDraft = value;
}

/** workspace 换代时清空问答状态（原 doCheckVersion 内联的 6 行重置，逐字搬迁）。 */
export function resetAskForWorkspace(): void {
  askThreads = [];
  askActiveId = null;
  askDraft = '';
  askErrors = {};
  askBusy = false;
  askBusyThreadId = null;
}

/** data-action="ask-new" 的处理器（原派发器内联分支）。 */
export function askNewThread(): void {
  askDraft = '';
  const thread = newAskThread();
  renderAsk(askView());
  const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (thread && input) input.focus();
}

/** data-action="ask-open" 的处理器（原派发器内联分支）。 */
export function askOpenThread(threadId: string | null): void {
  askDraft = '';
  askActiveId = threadId;
  saveAskStore();
  renderAsk(askView());
}

export function renderAsk(view: HTMLElement): void {
  const full = askThreads.length >= ASK_MAX_THREADS;
  const threadOptions = askThreads.map((thread) =>
    '<option value="' + esc(thread.id) + '"' + (thread.id === askActiveId ? ' selected' : '') + '>' +
    esc(thread.title) + '</option>'
  ).join('');
  view.innerHTML =
    '<div class="ask-layout">' +
    '<aside class="ask-side">' +
    '<div class="ask-side-head">' +
    '<button class="primary ask-new-btn" data-action="ask-new"' + (full ? ' disabled title="已达 10 个会话上限，请先删除或清空一个"' : '') + '>＋ 新会话</button>' +
    '<span class="ask-side-count">' + askThreads.length + '/' + ASK_MAX_THREADS + '</span>' +
    '</div>' +
    '<label class="ask-mobile-select">当前会话<select id="ask-thread-select"><option value="">选择会话</option>' + threadOptions + '</select></label>' +
    '<div class="ask-side-list" id="ask-side-list"></div>' +
    '</aside>' +
    '<div class="ask-main" id="ask-main"></div>' +
    '</div>';
  renderAskSide();
  renderAskChat();
  const selector = document.getElementById('ask-thread-select') as HTMLSelectElement | null;
  selector?.addEventListener('change', () => {
    if (!selector.value || selector.value === askActiveId) return;
    askActiveId = selector.value;
    askDraft = '';
    renderAsk(view);
  });
}

export function renderAskSide(): void {
  const listEl = document.getElementById('ask-side-list');
  if (!listEl) return;
  if (askThreads.length === 0) {
    listEl.innerHTML = '<p class="hint">还没有会话。点「＋ 新会话」开始提问。</p>';
    return;
  }
  listEl.innerHTML = askThreads.map((t) => {
    const active = t.id === askActiveId;
    return '<div class="ask-item' + (active ? ' active' : '') + '" data-thread="' + t.id + '">' +
      '<button class="ask-item-main" data-action="ask-open" data-thread="' + t.id + '" title="' + esc(t.title) + '">' + esc(t.title) + '</button>' +
      '<button class="ask-item-op" data-action="ask-rename" data-thread="' + t.id + '" title="重命名会话">✎</button>' +
      '<button class="ask-item-op danger" data-action="ask-del" data-thread="' + t.id + '" title="删除会话">✕</button>' +
      '</div>';
  }).join('');
}

function renderAskChat(): void {
  const main = document.getElementById('ask-main');
  if (!main) return;
  const existing = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (existing && askActiveId) {
    askDraft = existing.value;
    askDeps?.persistEntityDraft(askDraftEntity(askActiveId), askDraft);
  }
  const scopeEl = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeEl) askScope = scopeEl.value;
  const full = askThreads.length >= ASK_MAX_THREADS;
  const thread = activeAskThread(askThreads, askActiveId);
  if (!thread) {
    main.innerHTML =
      '<div class="ask-welcome"><h3>问第二大脑</h3>' +
      '<p>基于工作 vault 召回<strong>带来源</strong>的事实回答：做过什么、为什么这样决定、接下来最该做什么。</p>' +
      '<p class="hint">例如：「网课项目最近的决策是什么？」 · 追问如：「那后来呢？」</p>' +
      '<button class="primary" data-action="ask-new"' + (full ? ' disabled title="已达 10 个会话上限"' : '') + '>＋ 开始新对话</button>' +
      '</div>';
    return;
  }
  askDraft = loadEntityDraft<string>(askDraftEntity(thread.id), Date.now(), askDeps?.workspaceId()) ?? '';
  const bubbles = thread.messages.map((m) =>
    m.role === 'user'
      ? '<div class="chat-msg user"><div class="bubble">' + esc(m.text).replace(/\n/g, '<br>') + '</div></div>'
      : '<div class="chat-msg ai"><div class="bubble">' + m.text + '</div></div>'
  ).join('');
  const showTyping = askBusy && thread.id === askBusyThreadId;
  const typing = showTyping ? '<div class="chat-msg ai"><div class="bubble typing">思考中…</div></div>' : '';
  const errorBubble = askErrors[thread.id]
    ? '<div class="chat-msg ai"><div class="bubble"><p class="err-text">' + esc(askErrors[thread.id]) + '</p><p class="hint">问题未加入下一轮上下文，可以直接重试。</p></div></div>'
    : '';
  const scopeOptions = (askDeps?.projects() ?? [])
    .filter((p) => p.registered)
    .map((p) =>
      '<option value="' + esc(p.name) + '"' + (askScope === p.name ? ' selected' : '') + '>' +
      esc(projectDisplayName(p)) + (p.is_thread ? '（线程）' : '') +
      (projectDisplayName(p) !== p.name ? ' · ' + esc(p.name) : '') + '</option>'
    )
    .join('');
  main.innerHTML =
    '<div class="ask-chat" id="ask-chat">' + bubbles + errorBubble + typing + '</div>' +
    '<div class="ask-inputbar">' +
    '<form class="ask" id="ask-form" autocomplete="off">' +
    '<div class="ask-scope-row"><label class="hint">检索范围</label>' +
    '<select id="ask-scope"><option value="">全部（整个第二大脑）</option>' + scopeOptions + '</select></div>' +
    '<textarea id="ask-input" rows="2" placeholder="问第二大脑…（Enter 提问，Shift+Enter 换行）"></textarea>' +
    '<div class="form-row"><span class="hint ask-keyhint">Enter 提问 · Shift+Enter 换行</span>' +
    '<button class="primary" type="submit"' + (askBusy ? ' disabled' : '') + '>提问</button></div>' +
    '</form></div>';
  bindAskInput();
  const inputEl = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (inputEl) inputEl.value = askDraft;
  const scopeSet = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeSet) scopeSet.value = askScope;
  const chat = document.getElementById('ask-chat');
  if (chat?.lastElementChild) chat.lastElementChild.scrollIntoView({ block: 'nearest' });
}

function bindAskInput(): void {
  const form = document.getElementById('ask-form') as HTMLFormElement | null;
  if (form) form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void askSubmit();
  });
  const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (!input) return;
  input.addEventListener('input', () => {
    askDraft = input.value;
    if (askActiveId) askDeps?.persistEntityDraft(askDraftEntity(askActiveId), askDraft);
  });
  // Enter 提问（中文输入法组词时的回车不触发）；Shift+Enter 换行。
  input.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || ev.shiftKey) return;
    if (ev.isComposing || ev.keyCode === 229) return;
    ev.preventDefault();
    void askSubmit();
  });
}

async function askSubmit(): Promise<void> {
  const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (!input || askBusy) return;
  const q = input.value.trim();
  if (!q) return;
  let thread = activeAskThread(askThreads, askActiveId);
  if (!thread) {
    thread = newAskThread();
    if (!thread) return;
  }
  if (thread.messages.length === 0) thread.title = makeThreadTitle(q);
  const history = askHistoryOf(thread);
  const scopeInput = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeInput) askScope = scopeInput.value;
  const pendingMessage: AskMsg = { role: 'user', text: q, ts: new Date().toISOString(), sources: [] };
  thread.messages.push(pendingMessage);
  input.value = '';
  askDraft = '';
  clearEntityDraft(askDraftEntity(thread.id), askDeps?.workspaceId());
  delete askErrors[thread.id];
  askBusy = true;
  askBusyThreadId = thread.id;
  saveAskStore();
  renderAskSide();
  renderAskChat();
  let staleCompletion = false;
  const restoreFailedQuestion = (message: string): void => {
    const pendingIndex = thread.messages.lastIndexOf(pendingMessage);
    if (pendingIndex >= 0) thread.messages.splice(pendingIndex, 1);
    askDraft = q;
    askDeps?.persistEntityDraft(askDraftEntity(thread.id), askDraft);
    askErrors[thread.id] = message;
  };
  try {
    const r = await mutation(() => api<AskResponse>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history, project: askScope || null }),
    }));
    if (!r.ok || !r.answer_html) {
      restoreFailedQuestion(r.message ?? '提问失败');
      return;
    }
    const html = r.answer
      ? renderAskAnswer(r.answer, r.cited_source_ids ?? [], r.source_ids ?? [])
      : r.answer_html;
    if (!html) {
      restoreFailedQuestion('问答没有返回可显示内容');
      return;
    }
    thread.messages.push({
      role: 'ai',
      text: html,
      ts: new Date().toISOString(),
      sources: r.source_ids ?? [],
      citedSources: r.cited_source_ids ?? [],
    });
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) {
      staleCompletion = true;
    } else {
      restoreFailedQuestion(String(err));
    }
  } finally {
    askBusy = false;
    askBusyThreadId = null;
    if (!staleCompletion) {
      saveAskStore();
      renderAskSide();
      renderAskChat();
    }
  }
}

export function beginAskRename(threadId: string): void {
  const item = document.querySelector<HTMLElement>('.ask-item[data-thread="' + threadId + '"]');
  const thread = askThreads.find((t) => t.id === threadId);
  if (!item || !thread) return;
  const input = document.createElement('input');
  input.className = 'ask-rename-input';
  input.value = thread.title;
  input.maxLength = 40;
  item.innerHTML = '';
  item.appendChild(input);
  input.focus();
  input.select();
  const commit = (): void => {
    const value = input.value.trim();
    if (value) thread.title = value;
    saveAskStore();
    renderAskSide();
  };
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      commit();
    } else if (ev.key === 'Escape') {
      renderAskSide();
    }
  });
  input.addEventListener('blur', commit);
}
