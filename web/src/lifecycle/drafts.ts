export const DRAFT_STORAGE_KEY = 'wb.draft.snapshot.v1';
const MAX_DRAFT_AGE_MS = 30 * 60 * 1000;

function draftStorageKey(workspaceId?: string): string {
  return workspaceId ? DRAFT_STORAGE_KEY + '.' + workspaceId : DRAFT_STORAGE_KEY;
}

export interface ReviewDraftFields {
  description: string;
  target_project: string;
  route: string;
  due_date: string;
  start_at?: string;
  end_at?: string;
}

export interface DraftSnapshot {
  schema: 1;
  saved_at: string;
  source_build: string;
  tab: string;
  scroll_y: number;
  capture_text: string;
  ask_draft: string;
  review_forms: Record<string, ReviewDraftFields>;
}

export function saveDraftSnapshot(snapshot: DraftSnapshot, workspaceId?: string): void {
  try {
    window.sessionStorage.setItem(draftStorageKey(workspaceId), JSON.stringify(snapshot));
  } catch {
    // 隐私模式或配额不足时不阻断版本更新。
  }
}

export function loadDraftSnapshot(nowMs = Date.now(), workspaceId?: string): DraftSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(draftStorageKey(workspaceId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<DraftSnapshot>;
    const savedAt = typeof value.saved_at === 'string' ? Date.parse(value.saved_at) : NaN;
    if (value.schema !== 1 || !Number.isFinite(savedAt) || nowMs - savedAt > MAX_DRAFT_AGE_MS) {
      return null;
    }
    if (
      typeof value.source_build !== 'string' ||
      typeof value.tab !== 'string' ||
      typeof value.scroll_y !== 'number' ||
      typeof value.capture_text !== 'string' ||
      typeof value.ask_draft !== 'string' ||
      !value.review_forms ||
      typeof value.review_forms !== 'object'
    ) {
      return null;
    }
    return value as DraftSnapshot;
  } catch {
    return null;
  }
}

export function clearDraftSnapshot(workspaceId?: string): void {
  try {
    window.sessionStorage.removeItem(draftStorageKey(workspaceId));
    // 清掉 P0-11B 之前无 workspace 命名空间的草稿，避免切换后误恢复。
    if (workspaceId) window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    // 存储不可用时无需额外处理。
  }
}
