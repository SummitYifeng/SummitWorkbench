/** 设置页写动作的 payload（从 legacy-main 抽出，Step 8c）。 */

export interface RemoteNormalizationPreviewPayload {
  plan_id: string;
  old_url: string;
  candidate_url: string;
  branch: string;
  candidate_fetched: boolean;
  candidate_ahead: number;
  candidate_behind: number;
}

export interface AcceptancePreflightPayload {
  ok: boolean;
  report: string;
  checks: Array<{ name: string; status: string; detail: string }>;
}
