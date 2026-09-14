/** 「决策」页的数据形状（与 `GET /api/decisions` 一一对应）。 */

export interface DecisionLink {
  id: string;
  title: string;
  /** vault 相对路径（无 `.md`）；目标不在库里时为空串。 */
  path: string;
}

export interface DecisionRow {
  path: string;
  id: string;
  title: string;
  summary: string;
  status: string;
  status_label: string;
  decided_on: string;
  review_on: string | null;
  /** 管线（项目 ID）；跨项目的决策为 null。 */
  project: string | null;
  /** 主题簇 slug。 */
  domain: string | null;
  tags: string[];
  /** 这条决策推翻了哪些（已被解析成标题，界面不必再查 id）。 */
  supersedes: DecisionLink[];
  /** 被哪些决策推翻。 */
  superseded_by: DecisionLink[];
}

export interface DecisionFilters {
  project: string;
  domain: string;
  status: string;
  q: string;
}

export interface DecisionsPayload {
  ok: boolean;
  decisions: DecisionRow[];
  /** 全量按状态计数。 */
  counts: Record<string, number>;
  /** 当前筛选结果按状态计数。 */
  selected_counts: Record<string, number>;
  facets: { projects: string[]; domains: string[]; statuses: string[] };
  status_labels: Record<string, string>;
  filters: {
    project: string | null;
    domain: string | null;
    status: string | null;
    q: string | null;
  };
  warnings: string[];
}
