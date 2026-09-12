import type { ReviewDraftFields } from '../../lifecycle/drafts';
import type { ExternalAction, ReviewPayload } from './types';
import type { ProjectState } from '../projects';

/**
 * 审批域的组合根依赖（Step 8b）。
 *
 * `review`/`state`/`externalActions` 这几个大快照按 §4.2 有意留在组合根（跨三个域，下沉只会
 * 制造环），因此这里只暴露装配输入与两个写回点。
 */
export interface ReviewAssembleInput {
  review: ReviewPayload | null;
  loadError: string | null;
  lastReadAt: string | null;
  pendingReview: number;
  day: string;
  projects: ProjectState[];
  externalActions: ExternalAction[];
  externalActionsError: string | null;
  drafts: Record<string, ReviewDraftFields>;
}

export interface ReviewDeps {
  /** 组合根扇出的装配输入。 */
  assemble: () => ReviewAssembleInput;
  setReview: (payload: ReviewPayload | null) => void;
  setExternalActions: (actions: ExternalAction[]) => void;
  /** 组合根的草稿快照（审批表单本地草稿）。 */
  saveDraftSnapshot: () => void;
  /** 触发组合根重新渲染。 */
  render: () => void;
  refreshState: () => Promise<boolean>;
  refreshReview: () => Promise<boolean>;
}

let reviewDeps: ReviewDeps | null = null;

export function setReviewDeps(deps: ReviewDeps): void {
  reviewDeps = deps;
}

/** 组合根尚未注入时返回 null；调用点用可选链或显式兜底。 */
export function getReviewDeps(): ReviewDeps | null {
  return reviewDeps;
}
