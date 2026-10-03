export interface ReviewEntry {
  candidate_id: string;
  kind: string;
  description: string;
  target_project: string | null;
  route: string | null;
  due_date: string | null;
  /** 知识沉淀目标：`<vault 相对页面路径>#<区块标题>`；仅 route=knowledge-note 时有值 */
  sink_target: string | null;
  start_at: string | null;
  end_at: string | null;
  evidence: string | null;
  decision: string;
  historical: boolean;
  actionable: boolean;
  ai_original: string;
  meeting_date: string;
  meeting_title: string;
  note_link: string;
  transcript_link: string;
  apply_error: string | null;
}

export interface ReviewGroup {
  meeting_date: string;
  meeting_title: string;
  entries: ReviewEntry[];
}

export interface ReviewPayload {
  groups: ReviewGroup[];
  errors: string[];
  content_items?: PendingContent[];
}

export interface PendingContent {
  path: string;
  title: string;
  content_type: string;
  summary: string;
  body: string;
  content_sha256: string;
}

export type ReviewFilter = 'all' | 'pending' | 'approved' | 'rejected';

export interface ReviewRenderOptions {
  filter: ReviewFilter;
  selectedIds: ReadonlySet<string>;
}

export interface ExternalAction {
  operation_id: string;
  candidate_id: string;
  kind: string;
  state: string;
  attempt: number;
  timestamp: string;
  remote_id: string | null;
  error: string | null;
  retry_allowed: boolean;
  executor_id?: string | null;
}
