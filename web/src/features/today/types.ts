import type { BriefData } from '../../brief-card';
import type { ProjectState } from '../projects/types';

export interface TodayStatus {
  pending_review: number;
  backlog: { oldest_age_days: number | null };
}

export interface TodayState {
  day: string;
  status: TodayStatus;
  brief_md: string | null;
  brief_generated: boolean;
  brief?: BriefData | null;
  projects: ProjectState[];
}

export interface ImportReceipt {
  jobId?: string;
  fileName: string;
  bytes: number;
  status: 'processing' | 'success' | 'partial' | 'error';
  message: string;
  details?: string[];
  estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
}

/** 提升目标（契约 §10）：项目页条目 / 飞书待办 / 一篇工作思考。 */
export type InboxTarget = 'project' | 'feishu-task' | 'thought';

/**
 * 一条收件箱待处理条目（`GET /api/inbox`）。
 *
 * `suggested_target` / `suggested_reason` 由**后端本地启发式**给出（不调模型），
 * 用作弹层的默认单选；`id` 是稳定标识，提升时原样回传。
 */
export interface InboxItem {
  id: string;
  text: string;
  kind: string | null;
  due: string | null;
  project: string | null;
  projects: string[];
  candidate_id: string | null;
  suggested_target: InboxTarget;
  suggested_reason: string;
}

export interface TodayRenderOptions {
  state: TodayState | null;
  importing: boolean;
  importOpen: boolean;
  capturing?: boolean;
  loadError?: string | null;
  importResults?: ImportReceipt[];
  readStatus?: { lastSuccessfulAt: string | null; error: string | null };
  health: { tone: string; label: string };
  /** 收件箱待处理条目（只读列表，渲染时**不**调模型）。 */
  inboxItems?: InboxItem[];
  inboxError?: string | null;
}

export interface TodayActions {
  capture: (text: string) => Promise<{ ok: boolean }>;
  importFiles: (files: File[]) => Promise<void>;
  toggleImport: (open: boolean) => void;
  refresh: () => void;
}
