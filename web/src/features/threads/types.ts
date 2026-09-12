/** 线程日志与产物弹层的表单草稿类型（从 legacy-main 抽出，Step 7）。 */

export interface LogDraft {
  projects: string[];
  text: string;
}

export interface ArtifactDraft {
  project: string;
  title: string;
  text: string;
  syncState: boolean;
}
