import { workspaceScopedKey, workspaceStore } from '../../core/workspace-store';
import type { AskHistoryTurn, AskThread } from './types';

/** 第二大脑的持久化层：纯函数与 localStorage 读写，不持有页面状态。 */

export const ASK_MAX_THREADS = 10;
/** 追问时最多回传的历史轮数（与后端 _MAX_HISTORY_TURNS 同口径） */
export const ASK_MAX_HISTORY = 6;

export function askStorageKey(): string {
  return workspaceScopedKey('wb.ask.threads.v1', workspaceStore.workspaceId);
}

export function askDraftEntity(threadId: string): string {
  return 'ask:' + threadId;
}

/** 持久化快照；null 字段表示存储里没有该项，调用方保持现有值。 */
export interface AskStoreSnapshot {
  threads: AskThread[] | null;
  activeId: string | null;
}

/** 读取持久化会话；返回 null 表示没有可用记录（调用方保持现状）。 */
export function readAskStore(): AskStoreSnapshot | null {
  try {
    const raw = window.localStorage.getItem(askStorageKey());
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { threads?: AskThread[]; activeId?: string | null };
    return {
      threads: Array.isArray(parsed.threads) ? parsed.threads.slice(0, ASK_MAX_THREADS) : null,
      activeId: typeof parsed.activeId === 'string' ? parsed.activeId : null,
    };
  } catch {
    /* localStorage 数据损坏时按空会话处理，不阻断使用 */
    return null;
  }
}

/** 写入持久化会话；配额满/隐私模式静默失败，仅本次不持久化。 */
export function writeAskStore(threads: AskThread[], activeId: string | null): void {
  try {
    window.localStorage.setItem(
      askStorageKey(),
      JSON.stringify({ threads, activeId }),
    );
  } catch {
    /* 配额满/隐私模式等：静默失败，仅本次不持久化 */
  }
}

export function activeAskThread(threads: AskThread[], activeId: string | null): AskThread | null {
  return threads.find((t) => t.id === activeId) ?? null;
}

export function makeThreadTitle(q: string): string {
  const one = q.replace(/\s+/g, ' ').trim();
  if (!one) return '新会话';
  return one.length > 12 ? one.slice(0, 12) + '…' : one;
}

export function askHistoryOf(thread: AskThread): AskHistoryTurn[] {
  const turns: AskHistoryTurn[] = [];
  for (let i = 0; i + 1 < thread.messages.length; i += 2) {
    const userMsg = thread.messages[i];
    const aiMsg = thread.messages[i + 1];
    if (userMsg.role === 'user' && aiMsg?.role === 'ai') {
      turns.push({ question: userMsg.text, sources: aiMsg.sources });
    }
  }
  return turns.slice(-ASK_MAX_HISTORY);
}
