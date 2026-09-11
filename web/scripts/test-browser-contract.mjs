import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/legacy-main.ts'), 'utf8');
const reviewSource = fs.readFileSync(path.join(root, 'src/features/review/render.ts'), 'utf8');
const settingsSource = fs.readFileSync(path.join(root, 'src/features/settings/index.ts'), 'utf8');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const styleSource = read('src/style.css');

// Browser-level interaction contract: these user actions must remain wired after feature moves.
assert.match(source, /window\.location\.href = '\/onboarding'/, 'onboarding remains reachable from the workbench');
assert.match(source, /data-action="sync-retry"/, 'sync retry remains wired');
assert.match(source, /data-action="sync-conflict-details"/, 'protected sync opens conflict details');
assert.match(source, /\/api\/sync\/conflict\/selection\/validate/, 'manual conflict choices are validated');
assert.match(
  source,
  /\/api\/sync\/conflict\/selection\/validate[\s\S]{0,350}conflictSelectionRequest\(\)/,
  'selection validation does not send the recovery confirmation field',
);
assert.match(source, /\/api\/sync\/conflict\/recover/, 'conflict recovery remains wired');
assert.match(source, /\/api\/sync\/conflict\/export/, 'conflict package export remains wired');
assert.match(source, /unknown-generated-view/, 'unknown generated views have a safe fallback label');
assert.match(source, /preserve-both/, 'unknown generated views keep both copies');
assert.match(source, /脱敏审计记录未完成/, 'audit failure remains visible after recovery commit');
assert.match(source, /conflictRecoveryRequest\(false\)/, 'recovery preview is explicit and write-free');
assert.match(source, /确认恢复并创建提交/, 'recovery requires an explicit confirmation action');
assert.match(source, /\/api\/review\/apply/, 'review apply remains wired');
assert.match(reviewSource, /data-action="source-open"/, 'review evidence links open the shared source panel');
assert.match(source, /function openSource/, 'ask and review evidence share a source reader');
assert.match(source, /\/api\/sources\/read\?source_id=/, 'source reader uses the vault-scoped API');
assert.match(source, /result\.truncated/, 'source reader surfaces the truncation notice for oversized-but-capped bodies');
assert.match(source, /renderAskAnswer/, 'structured ask answers have a dedicated renderer');
assert.match(source, /仅召回、未在回答中引用的材料/, 'ask distinguishes recalled-only materials');
assert.match(source, /cited_source_ids/, 'ask response preserves actual citations separately');
assert.match(source, /answer\.conflicts/, 'ask answer renders structured conflicts');
assert.match(source, /ask-thread-select/, 'narrow ask view has a keyboard-friendly session selector');
assert.match(source, /guide-search/, 'guide has local search');
assert.match(source, /guide-index-links/, 'guide has a local directory');
assert.match(source, /node\.tagName === 'H2' \|\| node\.tagName === 'H3'/, 'guide search groups rendered major headings');
assert.match(source, /data-guide-section/, 'guide directory records section ownership');
assert.match(source, /link\.hidden = Boolean\(sectionId && document\.getElementById\(sectionId\)\?\.hidden\)/, 'guide directory follows filtered sections');
assert.match(source, /e\.actionable && !!e\.route/, 'batch approval filters incomplete candidates');
assert.match(source, /REVIEW_BATCH_LIMIT/, 'batch review operations have a client-side limit');
assert.match(source, /超过单批上限 100 条/, 'batch limit explains how to recover');
assert.match(reviewSource, /data-review-filter=/, 'review exposes a status filter');
assert.match(reviewSource, /data-review-select=/, 'review entries expose safe selection controls');
assert.match(reviewSource, /当前筛选：/, 'review explains the current selection scope');
assert.match(source, /reviewSelectedIds/, 'review selection state is explicit');
assert.match(source, /reviewFilter/, 'review filter state is explicit');
assert.match(source, /reviewSelectedIds\.clear\(\)/, 'changing review filter clears selection');
assert.match(source, /batchDecide\(selected/, 'selected review actions reuse the batch decision path');
assert.doesNotMatch(source, /selected[^\n]*\/api\/review\/apply/, 'selected actions do not bypass review apply');
assert.match(settingsSource, /data-action="profile-switch"/, 'profile switch remains wired');
assert.match(settingsSource, /data-action="diagnostics-preview"/, 'diagnostics preview remains wired');
assert.match(source, /\/api\/diagnostics\/export/, 'diagnostics export remains wired');
assert.match(settingsSource, /verification-failed/, 'settings distinguishes provider verification failures');
assert.match(settingsSource, /conn-badge failed/, 'settings exposes failed connection state');
assert.match(settingsSource, /needs_reauthorize/, 'settings exposes Feishu reauthorization state');
assert.match(settingsSource, /settingsRenderSequence/, 'settings renders carry a request sequence');
assert.match(
  settingsSource,
  /if \(requestId !== settingsRenderSequence\) return;/,
  'stale settings responses do not overwrite newer settings content',
);
assert.match(
  source,
  /\/api\/settings\/git\/remote\/preview[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote preview sends JSON content type',
);
assert.match(
  source,
  /\/api\/settings\/git\/remote\/apply[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote apply sends JSON content type',
);
assert.match(
  source,
  /\/api\/settings\/acceptance-preflight[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'acceptance preflight sends JSON content type',
);
assert.match(read('src/lifecycle/native-bridge.ts'), /openLogDirectory/, 'log directory action remains wired');
assert.match(read('src/api/client.ts'), /dispose\(\): void/, 'requests have a disposal boundary');
assert.match(read('src/core/workspace-store.ts'), /currentGeneration/, 'workspace generation invalidates stale requests');
assert.match(source, /X-WB-Workspace-Generation/, 'API requests carry workspace generation');
assert.match(source, /latestStateRequest|latestReviewRequest/, 'stale refresh responses are ignored');
assert.match(source, /saveEntityDraft|loadEntityDraft|clearEntityDraft/, 'entity drafts have an explicit storage contract');
assert.match(source, /requestModalClose/, 'modal close is routed through the unsaved-draft guard');
assert.match(source, /const action = btn\.dataset\.action \?\? '';[\s\S]{0,120}btn\.focus\(\)/, 'action dispatch restores the triggering control as the modal return target');
assert.match(source, /function activateModal/, 'specialized modals use the shared focus setup');
assert.match(source, /if \(backdrop\.hidden\)[\s\S]{0,180}modalReturnFocus/, 'nested modal content preserves the original return focus');
assert.match(source, /projectDetailHtml/, 'project details render inside the project page');
assert.match(source, /projectReturnContext/, 'project detail keeps list context across page navigation');
assert.match(source, /projectFocusAfterRenderName/, 'project detail queues a visible return-focus target for the rebuilt page');
assert.match(source, /function focusVisibleProjectLink/, 'project detail has one visibility-aware return-focus helper');
assert.match(source, /getComputedStyle\(el\)\.display !== 'none'/, 'project detail fallback focus ignores display-hidden duplicate project links');
assert.match(source, /getClientRects\(\)\.length > 0/, 'project detail fallback focus ignores links hidden by an ancestor');
assert.match(source, /window\.scrollTo\(\{ top: context\?\.scrollY/, 'project detail restores the previous list scroll position');
assert.doesNotMatch(source, /activateModal\(projectViewHtml\(view\)\)/, 'project details do not use the generic modal container');
// 过期详情响应不得覆盖用户已经离开详情的导航，也不得在稍后进入项目页时"复活"旧详情。
assert.match(source, /latestProjectViewRequest/, 'project detail reads carry a request sequence');
assert.match(source, /const requestId = \+\+latestProjectViewRequest/, 'each project detail read takes a fresh sequence number');
assert.match(source, /latestProjectViewRequest \+= 1/, 'leaving a project detail invalidates its in-flight read');
assert.match(
  source,
  /requestId !== latestProjectViewRequest/,
  'stale project detail responses are discarded before touching shared state',
);
// 写回前置的 apply 必须有单次在途保护，双击不能发出第二次 /api/review/apply。
assert.match(source, /reviewApplyBusy/, 'review apply has a single in-flight guard');
assert.match(source, /if \(exec && reviewApplyBusy\) return/, 'repeat apply clicks cannot fire a second writeback request');
assert.match(source, /reviewPlanReady = false;\s*\n\s*void refreshReview\(\)/, 'changing decisions invalidates the previous dry-run plan');
// 撤销弹层必须复用统一 dialog 激活（初始焦点、dialog 语义、关闭按钮、返回焦点）。
assert.match(
  source,
  /async function openUndoModal[\s\S]{0,500}openModal\(/,
  'undo dialog uses the shared modal activation',
);
// 后台轮询只在可见页运行；回到前台时同时刷新同步横幅。
assert.match(
  source,
  /document\.visibilityState !== 'visible'\) return;[\s\S]{0,80}checkVersion\('interval'\)/,
  'the 60s version poll pauses while the page is hidden',
);
assert.match(
  source,
  /document\.visibilityState !== 'visible'\) return;[\s\S]{0,80}refreshSyncBanner\(\)/,
  'the 60s sync poll pauses while the page is hidden',
);
// 同步状态读取失败时不能把已显示的保护态横幅静默隐藏。
assert.match(source, /同步状态读取失败/, 'sync banner read failures stay visible instead of hiding protection state');
assert.doesNotMatch(
  source,
  /async function refreshSyncBanner[\s\S]{0,1800}\} catch \{\s*\n\s*el\.hidden = true;/,
  'sync banner read failure does not silently hide the protection banner',
);
// 服务端省略 workspace_id 时，问答历史仍必须加载。
assert.match(
  source,
  /let loadedAskWorkspace: string \| null = null/,
  'ask history loads even when the server omits workspace_id',
);
assert.match(source, /function activateConflictModal/, 'sync conflict uses the shared modal activation path');
assert.match(source, /activateConflictModal\(/, 'sync conflict modal content gets initial focus and return-focus handling');
assert.match(source, /const returnFocus = document\.querySelector<HTMLElement>\('\[data-action="sync-conflict-details"\]'\)/, 'sync conflict captures a stable return-focus trigger before async loading');
assert.match(source, /if \(returnFocus\) modalReturnFocus = returnFocus/, 'sync conflict restores focus to its banner trigger after async modal activation');
assert.match(source, /persistEntityDraft\('sync-conflict'/, 'sync conflict choices have a recoverable entity draft');
assert.match(source, /requestModalClose\(\)/, 'sync conflict close uses the unsaved-draft guard');
assert.match(source, /window\.confirm[\s\S]{0,350}产物已保存[\s\S]{0,500}\/api\/threads\/state/, 'artifact state sync requires a final preview confirmation');
assert.match(source, /askErrors/, 'failed ask requests remain visible without entering history');
assert.match(source, /restoreFailedQuestion/, 'failed ask requests restore the question without duplicating history');
// 外部写回状态读取同样需要乱序保护：并发的旧列表不能覆盖新列表。
assert.match(source, /latestExternalActionsRequest/, 'external action reads carry a request sequence');
assert.match(source, /requestId !== latestExternalActionsRequest/, 'stale external action reads are discarded');
// 长文本提交（日志/产物/捕捉）与外部行内编辑都需要在途保护：双击不能重复保存或重复写回。
assert.match(source, /MAX_TEXT_CHARS = 100_000/, 'client pins the backend long-text limit');
assert.match(source, /超过 10 万字上限/, 'long-form submits explain the size limit before sending');
assert.match(source, /let artifactSubmitting = false/, 'artifact save has a single in-flight guard');
assert.match(source, /let logSubmitting = false/, 'work log save has a single in-flight guard');
assert.match(source, /let rowEditSubmitting = false/, 'task/meeting edit has a single in-flight guard');
assert.match(source, /importFiles/, 'today import accepts a batch of local files');
assert.match(source, /status === 'partial'/, 'partial import results remain visually distinct');
assert.match(read('src/features/today/render.ts'), /esc\(result\.message\)/, 'import receipts preserve the server idempotency message');
assert.match(read('src/features/today/render.ts'), /multiple hidden/, 'the transcript picker allows multiple files');
assert.match(read('src/features/today/index.ts'), /let currentOpen = options\.importOpen/, 'import drawer open state is local and reversible');
assert.match(read('src/features/today/index.ts'), /setOpen\(!currentOpen\)/, 'import drawer can close and reopen without a stale closure');
assert.match(read('src/features/today/index.ts'), /if \(!open\) importButton\?\.focus\(\)/, 'closing the import drawer restores focus to its trigger');
assert.match(styleSource, /@media \(max-width: 900px\)[\s\S]{0,280}\.header-right \.version-status/, 'tablet header hides non-essential version text before it can overflow');
assert.match(styleSource, /@media \(max-width: 380px\)[\s\S]{0,320}#btn-quit\s*\{\s*display: none/, 'very narrow header hides the non-essential quit control before it can overflow');
assert.match(styleSource, /@media \(max-width: 380px\)[\s\S]{0,320}#btn-refresh, \.header-right #btn-quit\s*\{\s*display: none/, 'very narrow header hides the refresh control before it can overflow');
assert.match(styleSource, /@media \(max-width: 380px\)[\s\S]{0,420}\.automation-enabled\s*\{[\s\S]{0,180}white-space: normal[\s\S]{0,180}overflow-wrap: anywhere/, 'very narrow settings labels wrap before they can overflow the page');
console.log('Browser interaction contract tests passed');
