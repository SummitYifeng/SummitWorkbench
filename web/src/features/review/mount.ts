import { setReviewDeps, type ReviewDeps } from './deps';

/** 审批 feature 的挂载点：注入组合根依赖。 */
export function mountReview(deps: ReviewDeps): void {
  setReviewDeps(deps);
}
