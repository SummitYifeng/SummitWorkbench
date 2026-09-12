/** 撤销（git 自动提交还原）域的 DTO（从 legacy-main 抽出，Step 1）。 */

export interface WbCommitItem {
  sha: string;
  short_sha: string;
  message: string;
  time: string;
  files: string[];
}

export interface UndoHistoryPayload {
  ok: boolean;
  commits?: WbCommitItem[];
  note?: string | null;
  message?: string;
}

export interface UndoDiffPayload {
  ok: boolean;
  diff?: string;
  message?: string;
}
