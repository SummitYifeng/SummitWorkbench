import { workspaceScopedKey } from '../core/workspace-store';

export const DRAFT_STORAGE_KEY = 'wb.draft.snapshot.v1';
export const ENTITY_DRAFT_STORAGE_KEY = 'wb.draft.entity.v1';
const MAX_DRAFT_AGE_MS = 30 * 60 * 1000;

function draftStorageKey(workspaceId?: string): string {
  return workspaceScopedKey(DRAFT_STORAGE_KEY, workspaceId ?? null);
}

function entityDraftStorageKey(entity: string, workspaceId?: string): string {
  return workspaceScopedKey(ENTITY_DRAFT_STORAGE_KEY, workspaceId ?? null) + '.' + encodeURIComponent(entity);
}

export interface ReviewDraftFields {
  description: string;
  target_project: string;
  route: string;
  due_date: string;
  start_at?: string;
  end_at?: string;
  /** 知识沉淀目标（`<页面路径>#<区块标题>`）；只有 route=knowledge-note 时使用 */
  sink_target?: string;
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

export function saveDraftSnapshot(snapshot: DraftSnapshot, workspaceId?: string): boolean {
  try {
    window.sessionStorage.setItem(draftStorageKey(workspaceId), JSON.stringify(snapshot));
    return true;
  } catch {
    return false;
  }
}

interface EntityDraftEnvelope<T> {
  schema: 1;
  saved_at: string;
  value: T;
}

/** 保存非敏感、可恢复的实体草稿；调用方可据 false 显示存储不可用。 */
export function saveEntityDraft<T>(
  entity: string,
  value: T,
  workspaceId?: string,
): boolean {
  try {
    const envelope: EntityDraftEnvelope<T> = {
      schema: 1,
      saved_at: new Date().toISOString(),
      value,
    };
    window.sessionStorage.setItem(entityDraftStorageKey(entity, workspaceId), JSON.stringify(envelope));
    return true;
  } catch {
    return false;
  }
}

export function loadEntityDraft<T>(
  entity: string,
  nowMs = Date.now(),
  workspaceId?: string,
): T | null {
  try {
    const raw = window.sessionStorage.getItem(entityDraftStorageKey(entity, workspaceId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<EntityDraftEnvelope<T>>;
    const savedAt = typeof value.saved_at === 'string' ? Date.parse(value.saved_at) : NaN;
    if (value.schema !== 1 || !Number.isFinite(savedAt) || nowMs - savedAt > MAX_DRAFT_AGE_MS) return null;
    return value.value === undefined ? null : value.value;
  } catch {
    return null;
  }
}

export function clearEntityDraft(entity: string, workspaceId?: string): boolean {
  try {
    window.sessionStorage.removeItem(entityDraftStorageKey(entity, workspaceId));
    return true;
  } catch {
    return false;
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
