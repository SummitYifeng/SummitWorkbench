import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// Browser-level interaction contract: these user actions must remain wired after feature moves.
//
// The assertions below are deliberately *layout-independent* wherever possible. Reading a single
// monolith made every one of them break the moment content moved to another module, which meant a
// real regression and a stale assertion looked identical. The whole tree is read and concatenated
// instead, so a guard keeps working after its subject moves -- as long as the subject still exists
// somewhere, which is exactly what the contract is about.
//
// Two deliberate exceptions keep a *placement* guarantee:
//   - `fileFor('x.ts')` for modules whose location IS the contract (e.g. review render helpers must
//     stay in the review feature module).
//   - `filesMatching(/\.css$/)` for the stylesheet, so a new CSS file is picked up automatically.
//
// Self-test: `assertAggregateCoversNewModules` below proves the aggregate really does pick up files
// that did not exist when this test was written. Without it, "layout-independent" would be a claim
// rather than a checked property.

const root = path.resolve(import.meta.dirname, '..');
const srcDir = path.join(root, 'src');

/** Every tracked source file the contract may live in, sorted for stable ordering. */
function collectSourceFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...collectSourceFiles(full));
    } else if (/\.(ts|css)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      found.push(full);
    }
  }
  return found.sort();
}

const sourceFiles = collectSourceFiles(srcDir);
const sourceText = new Map(
  sourceFiles.map((full) => [path.relative(root, full).split(path.sep).join('/'), fs.readFileSync(full, 'utf8')]),
);

// Everything, joined: guards survive a move between modules.
const source = [...sourceText.values()].join('\n');
// Tests that assert *which* module something lives in read it explicitly; a missing file is an
// error rather than an empty string, so a rename fails loudly instead of silently passing.
const fileFor = (name) => {
  const text = sourceText.get(name);
  assert.ok(text !== undefined, `contract source file is missing: ${name}`);
  return text;
};
const filesMatching = (pattern) => {
  const hits = [...sourceText.entries()].filter(([name]) => pattern.test(name));
  return hits.map(([, text]) => text).join('\n');
};

// Windowed assertions are evaluated *per file*, never across the concatenation. A bounded window
// is written to span one function body, so running it over joined text would happily match an
// anchor in one module against unrelated code hundreds of characters into the next one -- and the
// negative variants would then fail for a reason that has nothing to do with the contract. Per-file
// also keeps the move-safe property: the assertion follows its anchor wherever the anchor lives.
//
// Requiring at least one file to carry the anchor is deliberate. A missing anchor means the code
// was deleted or renamed, which must fail here rather than quietly leave the guard unenforced.
function perFileAssert(description, anchor, check) {
  const hits = [...sourceText.entries()].filter(([, text]) => anchor.test(text));
  assert.ok(hits.length > 0, `${description}: anchor ${anchor} is not present in any source file`);
  for (const [name, text] of hits) {
    assert.ok(check(text), `${description}: violated in ${name}`);
  }
}

/** `anchor ... window ... required` within one file. */
const assertNearby = (anchor, required, description) =>
  perFileAssert(description, anchor, (text) => {
    const narrowed = new RegExp(anchor.source + required.source);
    return narrowed.test(text);
  });

/** `anchor ... window ... forbidden` must not occur within one file. */
const doesNotMatchNearby = (anchor, forbidden, description) =>
  perFileAssert(description, anchor, (text) => {
    const narrowed = new RegExp(anchor.source + forbidden.source);
    return !narrowed.test(text);
  });

const reviewSource = fileFor('src/features/review/render.ts');
const projectActionsSource = fileFor('src/features/projects/actions.ts');
const reviewActionsSource = fileFor('src/features/review/actions.ts');
const diagnosticsSource = fileFor('src/features/diagnostics.ts');
const legacySource = fileFor('src/legacy-main.ts');
// Settings is a feature directory (Step 8c): the placement guarantee is "inside the feature",
// not "inside one file", so the whole feature is read and the move keeps the guard enforced.
const settingsSource = filesMatching(/^src\/features\/settings\/.*\.ts$/);
const styleSource = filesMatching(/\.css$/);

assert.match(source, /window\.location\.href = '\/onboarding'/, 'onboarding remains reachable from the workbench');
assert.match(source, /data-action="sync-retry"/, 'sync retry remains wired');
assert.match(source, /data-action="sync-conflict-details"/, 'protected sync opens conflict details');
assert.match(source, /\/api\/sync\/conflict\/selection\/validate/, 'manual conflict choices are validated');
assertNearby(
  /\/api\/sync\/conflict\/selection\/validate/,
  /[\s\S]{0,350}conflictSelectionRequest\(\)/,
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
assert.match(source, /function openSource/, 'review evidence opens the shared read-only source panel');
assert.match(source, /\/api\/sources\/read\?source_id=/, 'source reader uses the vault-scoped API');
assert.match(source, /result\.truncated/, 'source reader surfaces the truncation notice for oversized-but-capped bodies');
assert.match(source, /e\.actionable && !!e\.route/, 'batch approval filters incomplete candidates');
assert.match(source, /REVIEW_BATCH_LIMIT/, 'batch review operations have a client-side limit');
assert.match(source, /超过单批上限 100 条/, 'batch limit explains how to recover');
assert.match(reviewSource, /data-review-filter=/, 'review exposes a status filter');
assert.match(reviewSource, /data-review-select=/, 'review entries expose safe selection controls');
assert.match(reviewSource, /当前筛选：/, 'review explains the current selection scope');
assert.match(source, /reviewUi\.selected/, 'review selection state is explicit');
assert.match(source, /reviewUi\.filter/, 'review filter state is explicit');
assert.match(source, /reviewUi\.selected\.clear\(\)/, 'changing review filter clears selection');
assert.match(source, /batchDecide\(selected/, 'selected review actions reuse the batch decision path');
// The guard must hold in whichever module the dispatch lives in. A single-file reader let this
// pass silently as soon as the code moved, which is a lost guard rather than a failing test.
assert.doesNotMatch(source, /selected[^\n]*\/api\/review\/apply/, 'selected actions do not bypass review apply');
assert.match(settingsSource, /data-action="profile-switch"/, 'profile switch remains wired');
// The dispatcher branch for profile-remove survived for months with no rendered entry point
// (cb1bd34 dropped the old settings section, the new page never grew one), so a local profile
// could not be removed from the UI at all. Pin the entry point, not just the handler.
assert.match(
  settingsSource,
  /data-action="profile-remove"/,
  'removing a local profile is reachable from the settings page, not only dispatched',
);
// D6: the toolbar must expose 立即同步. Before this, /api/sync/run was reachable only through the
// banner's 立即重试, which is hidden whenever the state is ready — so a clean device had no way to
// pull at all.
assert.match(
  fileFor('src/features/shell/shell.ts'),
  /id="btn-sync"/,
  'the toolbar exposes 立即同步, not only the banner retry',
);
assert.match(settingsSource, /data-action="diagnostics-preview"/, 'diagnostics preview remains wired');
assert.match(diagnosticsSource, /export function createDiagnosticsActions/, 'diagnostics actions stay in their feature module');
assert.match(diagnosticsSource, /\/api\/diagnostics\/preview/, 'diagnostics preview uses the feature API');
assert.match(diagnosticsSource, /\/api\/diagnostics\/export/, 'diagnostics export uses the feature API');
assert.doesNotMatch(legacySource, /function (copy|preview|export)Diagnostics/, 'diagnostics implementation does not return to the composition root');
assert.match(projectActionsSource, /export function submitProjectCreate/, 'project creation submit stays in the projects feature');
assert.match(projectActionsSource, /\/api\/projects\/create/, 'project creation endpoint remains in the projects feature');
assert.match(reviewActionsSource, /export function submitReviewEdit/, 'review editing submit stays in the review feature');
assert.match(reviewActionsSource, /\/api\/review\/edit/, 'review editing endpoint remains in the review feature');
assert.match(reviewActionsSource, /\/api\/review\/decide/, 'save-and-approve endpoint remains in the review feature');
assert.doesNotMatch(legacySource, /\/api\/(projects\/create|review\/edit|review\/decide)/, 'form submission HTTP details do not return to the composition root');
// G2: a workspace with no origin had no in-app path to bind one (only manual git commands);
// the publish entry point and its dispatch must both exist.
assert.match(
  settingsSource,
  /data-action="git-remote-publish"/,
  'the settings page exposes the first-publish entry point',
);
assert.match(source, /action === 'git-remote-publish'/, 'first-publish dispatch is wired');
// G1: the automation-primary claim/takeover endpoint existed but nothing in the UI could reach it,
// so a machine whose profile said `secondary` could never become primary (and never downgrade).
assert.match(
  settingsSource,
  /data-action="primary-claim"/,
  'the settings page exposes the automation-primary claim/takeover entry point',
);
assert.match(
  settingsSource,
  /data-action="primary-downgrade"/,
  'the settings page exposes the downgrade-to-secondary entry point',
);
assert.match(
  settingsSource,
  /id="primary-takeover-ack"/,
  'takeover requires an explicit acknowledgement in the rendered card',
);
// 设置页主区只留三张常用卡（工作区 / AI 模型 / 飞书），每张独占一行；
// 「自动化与更新」「模型参数（只读）」收进「高级与维护」——2026-09-18 使用者要求。
assert.match(
  settingsSource,
  /settings-grid settings-grid-single/,
  'the settings main area renders one card per row',
);
assert.match(
  settingsSource,
  /高级与维护（自动化 · 模型参数 · 多工作台 · Git 同步 · 诊断）/,
  'the advanced block advertises that automation and model parameters live inside it',
);
assert.match(
  settingsSource,
  /section-title">自动化与更新<\/h3>[\s\S]{0,400}automationCard/,
  'the automation card is mounted inside the advanced block',
);
assert.match(
  settingsSource,
  /section-title">模型参数（只读）<\/h3>[\s\S]{0,200}modelParameters/,
  'the read-only model-parameter card is mounted inside the advanced block',
);
// The dispatch branch must exist too: a rendered button without a handler is a dead entry point.
assert.match(source, /action === 'primary-claim'/, 'primary claim dispatch is wired');
assert.match(source, /action === 'primary-downgrade'/, 'primary downgrade dispatch is wired');
assert.match(source, /\/api\/diagnostics\/export/, 'diagnostics export remains wired');
assert.match(settingsSource, /verification-failed/, 'settings distinguishes provider verification failures');
assert.match(settingsSource, /conn-badge failed/, 'settings exposes failed connection state');
assert.match(settingsSource, /needs_reauthorize/, 'settings exposes Feishu reauthorization state');
// 授权失败必须被用户看见：回跳后要把原因取回来显示，而不是静默回到设置页。
// 分发包内置凭据，同事本机没有可改的配置，界面不说原因就只能反复点。
assert.match(source, /reportFeishuCallbackResult/, 'Feishu callback outcome is surfaced, not silently dropped');
assert.match(
  source,
  /\/api\/settings\/feishu\/status\?state=/,
  'Feishu callback outcome is explained by the authorization state reason',
);
assert.match(source, /FEISHU_STATE_KEY/, 'the authorization state is remembered across the OAuth redirect');
assert.match(settingsSource, /settingsRenderSequence/, 'settings renders carry a request sequence');
assert.match(
  settingsSource,
  /if \(requestId !== settingsRenderSequence\) return;/,
  'stale settings responses do not overwrite newer settings content',
);
assertNearby(
  /\/api\/settings\/git\/remote\/preview/,
  /[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote preview sends JSON content type',
);
assertNearby(
  /\/api\/settings\/git\/remote\/apply/,
  /[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote apply sends JSON content type',
);
assertNearby(
  /\/api\/settings\/acceptance-preflight/,
  /[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'acceptance preflight sends JSON content type',
);
assert.match(fileFor('src/lifecycle/native-bridge.ts'), /openLogDirectory/, 'log directory action remains wired');
assert.match(fileFor('src/api/client.ts'), /dispose\(\): void/, 'requests have a disposal boundary');
assert.match(fileFor('src/core/workspace-store.ts'), /currentGeneration/, 'workspace generation invalidates stale requests');
assert.match(source, /X-WB-Workspace-Generation/, 'API requests carry workspace generation');
assert.match(source, /latestStateRequest|latestReviewRequest/, 'stale refresh responses are ignored');
assert.match(source, /saveEntityDraft|loadEntityDraft|clearEntityDraft/, 'entity drafts have an explicit storage contract');
assert.match(source, /requestModalClose/, 'modal close is routed through the unsaved-draft guard');
assertNearby(/const action = btn\.dataset\.action \?\? '';/, /[\s\S]{0,120}btn\.focus\(\)/, 'action dispatch restores the triggering control as the modal return target');
assert.match(source, /function activateModal/, 'specialized modals use the shared focus setup');
// The anchor needs its opening brace: `if (backdrop.hidden) return;` is the unrelated keydown
// guard in the shell, and once the modal base moves to its own module that bare anchor would make
// this guard fail in a file that legitimately contains no `modalReturnFocus`.
assertNearby(/if \(backdrop\.hidden\) \{/, /[\s\S]{0,180}modalReturnFocus/, 'nested modal content preserves the original return focus');
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
assert.match(source, /reviewUi\.applyBusy/, 'review apply has a single in-flight guard');
assert.match(source, /if \(exec && reviewUi\.applyBusy\) return/, 'repeat apply clicks cannot fire a second writeback request');
assert.match(source, /reviewUi\.planReady = false;\s*\n\s*void getReviewDeps\(\)\?\.refreshReview\(\)/, 'changing decisions invalidates the previous dry-run plan');
// 撤销弹层必须复用统一 dialog 激活（初始焦点、dialog 语义、关闭按钮、返回焦点）。
assertNearby(
  /async function openUndoModal/,
  /[\s\S]{0,500}openModal\(/,
  'undo dialog uses the shared modal activation',
);
// 后台轮询只在可见页运行；回到前台时同时刷新同步状态。
assertNearby(
  /document\.visibilityState !== 'visible'\) return;/,
  /[\s\S]{0,80}checkVersion\('interval'\)/,
  'the 60s version poll pauses while the page is hidden',
);
// D6 之后 60s 同步轮询走的是 autoSyncIfIdle()（先读状态，仅 ready 时才真正同步一次）；
// "隐藏页不跑" 的守卫必须还在。
assertNearby(
  /document\.visibilityState !== 'visible'\) return;/,
  /[\s\S]{0,80}autoSyncIfIdle\(\)/,
  'the 60s sync poll pauses while the page is hidden',
);
// 同步状态读取失败时不能把已显示的保护态横幅静默隐藏。
assert.match(source, /同步状态读取失败/, 'sync banner read failures stay visible instead of hiding protection state');
doesNotMatchNearby(
  /async function refreshSyncBanner/,
  /[\s\S]{0,1800}\} catch \{\s*\n\s*el\.hidden = true;/,
  'sync banner read failure does not silently hide the protection banner',
);
// 服务端省略 workspace_id 时，workspace 切换检测仍必须成立（否则跨工作区状态不会重置）。
assert.match(
  source,
  /let loadedWorkspaceId: string \| null = null/,
  'workspace switch guard still works when the server omits workspace_id',
);
assert.match(source, /function activateConflictModal/, 'sync conflict uses the shared modal activation path');
assert.match(source, /activateConflictModal\(/, 'sync conflict modal content gets initial focus and return-focus handling');
assert.match(source, /const returnFocus = document\.querySelector<HTMLElement>\('\[data-action="sync-conflict-details"\]'\)/, 'sync conflict captures a stable return-focus trigger before async loading');
assert.match(source, /if \(returnFocus\) modalReturnFocus = returnFocus/, 'sync conflict restores focus to its banner trigger after async modal activation');
assert.match(source, /persistEntityDraft\('sync-conflict'/, 'sync conflict choices have a recoverable entity draft');
assert.match(source, /requestModalClose\(\)/, 'sync conflict close uses the unsaved-draft guard');
// Anchored on the artifact-specific confirmation call, not on `window.confirm` itself (the split
// places confirms in several domain modules) and not on the确认 copy (that now lives in the pure
// `artifactStateConfirmText`, asserted in test-threads-render.mjs). What this guard is about is
// the *ordering*: the state write-back must sit behind the final confirmation.
assert.match(source, /const confirmed = window\.confirm\(/, 'artifact state sync asks for a final confirmation');
assertNearby(/const confirmed = window\.confirm\(/, /[\s\S]{0,500}\/api\/threads\/state/, 'artifact state sync requires a final preview confirmation');
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
assert.match(fileFor('src/features/today/render.ts'), /esc\(result\.message\)/, 'import receipts preserve the server idempotency message');
assert.match(fileFor('src/features/today/render.ts'), /multiple hidden/, 'the transcript picker allows multiple files');
assert.match(fileFor('src/features/today/index.ts'), /let currentOpen = options\.importOpen/, 'import drawer open state is local and reversible');
assert.match(fileFor('src/features/today/index.ts'), /setOpen\(!currentOpen\)/, 'import drawer can close and reopen without a stale closure');
assert.match(fileFor('src/features/today/index.ts'), /if \(!open\) importButton\?\.focus\(\)/, 'closing the import drawer restores focus to its trigger');
// 收件箱提升（契约 §10）：列表在「今日」页渲染，弹层放在 today feature 自己的模块里，
// 两个动作都经全局 data-action 分派。
assert.match(fileFor('src/features/today/render.ts'), /data-action="inbox-promote"/, '每个收件箱条目都有提升入口');
assert.match(fileFor('src/features/today/render.ts'), /inboxBlock\(options\.inboxItems/, '收件箱块由今日页渲染');
assert.match(source, /data-action === 'inbox-promote'|action === 'inbox-promote'/, 'inbox promote is dispatched from the global action handler');
assert.match(source, /action === 'inbox-ai-suggest'/, 'the AI suggestion button has its own explicit dispatch');
assert.match(fileFor('src/features/today/inbox.ts'), /syncTargetFields/, '提升弹层只显示当前目标相关的字段');
// **成本放置守卫**：`/api/inbox/suggest` 只允许出现在提升弹层模块里。列表渲染（render.ts / 状态
// 读取）一旦也去调模型，这里立刻红——「打开弹层扫一遍」是最容易被顺手写成的成本回归。
assert.match(fileFor('src/features/today/inbox.ts'), /\/api\/inbox\/suggest/, 'the AI suggestion endpoint lives in the promote modal');
for (const modulePath of ['src/features/today/render.ts', 'src/legacy-main.ts']) {
  assert.doesNotMatch(
    fileFor(modulePath),
    /\/api\/inbox\/suggest/,
    `list rendering must not call the model (found in ${modulePath})`,
  );
}
assert.doesNotMatch(source, /api\/inbox\/suggest[\s\S]{0,400}forEach|forEach[\s\S]{0,400}api\/inbox\/suggest/, 'the AI suggestion is never run in a loop over the list');
assertNearby(/@media \(max-width: 900px\)/, /[\s\S]{0,280}\.header-right \.version-status/, 'tablet header hides non-essential version text before it can overflow');
assertNearby(/@media \(max-width: 380px\)/, /[\s\S]{0,320}#btn-quit\s*\{\s*display: none/, 'very narrow header hides the non-essential quit control before it can overflow');
assertNearby(/@media \(max-width: 380px\)/, /[\s\S]{0,320}\.header-right #btn-refresh,[^\n]{0,120}\{\s*display: none/, 'very narrow header hides the refresh control before it can overflow');
assertNearby(/@media \(max-width: 380px\)/, /[\s\S]{0,420}\.automation-enabled\s*\{[\s\S]{0,180}white-space: normal[\s\S]{0,180}overflow-wrap: anywhere/, 'very narrow settings labels wrap before they can overflow the page');

// ---------------------------------------------------------------------------------------------
// Self-tests for the harness itself. The aggregate reader only helps if guards keep firing after
// code moves, and per-file windows only help if they stop cross-module bleed. Both are asserted
// here against a real file written to disk, because an unchecked "layout-independent" claim is
// worth nothing -- a future refactor could reintroduce single-file coupling and leave every
// assertion looking green.
// ---------------------------------------------------------------------------------------------
const probeName = 'src/__contract-probe__.ts';
const probePath = path.join(root, probeName);
const probeAnchor = /async function refreshSyncBanner/;
const probeForbidden = /[\s\S]{0,1800}\} catch \{\s*\n\s*el\.hidden = true;/;
const probeBody = [
  '/* temporary probe: stands in for a guard that moved into a newly created module */',
  'async function refreshSyncBanner(): Promise<void> {',
  '  try {',
  '    await fetch("/api/state");',
  '  } catch {',
  '    el.hidden = true;',
  '  }',
  '}',
].join('\n');
try {
  fs.writeFileSync(probePath, probeBody, 'utf8');
  const withProbe = new Map(sourceText);
  withProbe.set(probeName, probeBody);
  const joined = [...withProbe.values()].join('\n');
  const narrowed = new RegExp(probeAnchor.source + probeForbidden.source);
  const probeMatches = (text) => probeAnchor.test(text) && narrowed.test(text);

  // 1. The guard fires on the probe, which is the move case: the function now lives in a module
  //    that did not exist when this test was written. If it did not fire, the guard would be
  //    silently unenforced after the move -- the exact failure this whole step exists to prevent.
  assert.equal(probeMatches(probeBody), true, 'guard still fires when its subject moves to a new module');

  // 2. Per-file evaluation keeps that true while refusing to match across a file boundary. Over the
  //    joined text the window happily reaches into unrelated modules; per file it stops at the edge.
  assert.equal(narrowed.test(joined), true, 'sanity: an unbounded join really does match across files');
  const perFile = [...withProbe.values()].filter(probeMatches);
  assert.equal(perFile.length, 1, 'per-file windows match the moved module once, and never span files');

  // 3. A deleted or renamed anchor fails loudly rather than leaving the guard unenforced.
  const absent = /async function refreshSyncBannerAbsentSentinel/;
  assert.equal(
    [...withProbe.values()].some((text) => absent.test(text)),
    false,
    'a missing anchor is detectable, so the guard cannot pass merely by finding nothing',
  );

  // 4. New modules are discovered by the same scan the contract uses, with no test edit needed.
  const discovered = collectSourceFiles(srcDir).map((full) =>
    path.relative(root, full).split(path.sep).join('/'),
  );
  assert.ok(discovered.includes(probeName), 'the source scan discovers modules created after this test was written');
} finally {
  fs.rmSync(probePath, { force: true });
}
assert.equal(fs.existsSync(probePath), false, 'harness self-test cleans up after itself');

console.log(`Browser interaction contract tests passed (${sourceFiles.length} source files)`);
