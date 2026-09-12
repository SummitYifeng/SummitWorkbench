import { setSyncDeps, type SyncDeps } from './state';

/** 同步 feature 边界（类型与纯标签函数见 Step 1）。 */

/** 注入组合根依赖；由组合根在 renderShell 之后调用一次。 */
export function mountSyncBanner(deps: SyncDeps): void {
  setSyncDeps(deps);
}

export { refreshSyncBanner, retrySync, exportSyncSnapshot, exportSyncConflictPackage } from './banner';
export {
  applySyncConflictRecovery,
  conflictRecoveryRequest,
  conflictSelectionRequest,
  missingConflictSelections,
  previewSyncConflictRecovery,
  showSyncConflictDetails,
} from './conflict';
export {
  conflictDigestSummary,
  conflictEventSummary,
  conflictKindLabel,
  conflictRevision,
  conflictSelectionLabel,
} from './labels';
export type {
  ConflictDetails,
  ConflictPathDetail,
  ConflictSelection,
  RecoveryPreparationSummary,
  SyncConflictDetailsPayload,
  SyncConflictRecoveryPayload,
  SyncStatusPayload,
} from './types';
export type { SyncDeps } from './state';
