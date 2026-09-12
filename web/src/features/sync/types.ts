/** 同步状态与冲突详情域的 DTO（从 legacy-main 抽出，Step 1）。 */

export interface SyncStatusPayload {
  ok: boolean;
  workspace_id?: string;
  state: string;
  pending_commits?: number;
  last_sync_at?: string | null;
  ahead?: number;
  behind?: number;
  branch?: string | null;
  remote_host?: string | null;
  repo_states?: string[];
  automation_primary_device_id?: string | null;
  automation_primary_generation?: number | null;
  detail?: string;
  next_step?: string;
}

export type ConflictSelection = 'keep-local' | 'keep-remote' | 'preserve-both' | '';
export interface ConflictPathDetail {
  path: string;
  kind: string;
  action: string;
  automatic: boolean;
  changed_on: string[];
  local_sha256: string | null;
  remote_sha256: string | null;
  local_event?: Record<string, string> | null;
  remote_event?: Record<string, string> | null;
}
export interface ConflictDetails {
  base_revision: string;
  local: { revision: string; authored_at: string; changed_path_count: number };
  remote: { revision: string; authored_at: string; changed_path_count: number };
  automatic_path_count: number;
  manual_path_count: number;
  paths: ConflictPathDetail[];
}
export interface SyncConflictDetailsPayload {
  ok: boolean;
  available: boolean;
  state: string;
  details?: ConflictDetails;
  reason?: string;
}
export interface RecoveryPreparationSummary {
  status: string;
  ok: boolean;
  event_count: number;
  aggregate_count: number;
  generated_view_count: number;
  rebuilt_view_count: number;
  candidate_path_count: number;
  staging_ready: boolean;
  error_code: string | null;
}
export interface SyncConflictRecoveryPayload {
  ok: boolean;
  available: boolean;
  state: string;
  preparation?: RecoveryPreparationSummary;
  recovery?: {
    status: string;
    revision?: string | null;
    error_code?: string | null;
    audit?: { status: string; error_code?: string | null };
  };
  push?: { ok: boolean; state: string; detail?: string | null } | null;
  reason?: string;
}
