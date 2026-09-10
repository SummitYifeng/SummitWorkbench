export interface ProjectState {
  name: string;
  dirty: boolean;
  ahead: number;
  behind: number;
  has_upstream: boolean;
  inbox_pending: number;
  next_step: string | null;
  git_error: string | null;
  /** ADR 0023：已建档（有效 project-main 档案）与否及其 status */
  registered: boolean;
  status: string | null;
  /** 知识线程项目（无 Work 文件夹的 vault 档案）标记；仓库项目为 false/缺省 */
  is_thread?: boolean;
  /** 档案 frontmatter 的 updated（实质更新：建档/激活/归档/改名/状态确认，YYYY-MM-DD）。停滞点名读它。 */
  updated?: string | null;
  /** 档案 frontmatter 的 activity_at（活动痕迹：日志/产物入库等，可缺省；首页「最近活跃」展示用） */
  activity_at?: string | null;
  /** 显示名（frontmatter `title`，可选）：展示用，规范 ID/别名/文件夹不受影响 */
  title?: string | null;
}

/** 线视图（P2）：项目/线程档案区块 + 时间线聚合。 */
export interface ProjectView {
  ok: boolean;
  message?: string;
  name: string;
  title?: string;
  status: string;
  updated: string;
  blocks: Record<string, string[]>;
  followup_pending: number;
  inbox_pending: number;
  timeline: { date: string; kind: string; label: string; title: string; snippet: string }[];
}

export type ProjectListFilter = 'all' | 'active' | 'new' | 'archived';
