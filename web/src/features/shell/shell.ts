import { appRoot, modalBackdrop } from './dom';
import { requestModalClose } from './modal';
import { normalizeTab, type ShellTab } from './tabs';

/**
 * 外壳需要组合根提供的动作。
 *
 * shell 只负责 DOM 结构与接线，不 import 任何 domain feature；按钮的行为体（刷新编排、
 * 检查更新、撤销、退出）留在组合根，避免 shell 反向依赖各域。
 */
export interface ShellActions {
  onSelectTab: (tab: ShellTab) => void;
  onRefresh: () => void;
  /** 立即同步：拉取远端新提交（只 fetch/快进/推送，绝不 force）。 */
  onSync: () => void;
  onCheckUpdates: () => void;
  onUndo: () => void;
  onQuit: () => void;
}

/** 建立 DOM 外壳、接线顶部栏与弹层焦点陷阱（原 renderShell，行为逐条保留）。 */
export function mountShell(actions: ShellActions): void {
  appRoot().innerHTML =
    '<a class="skip-link" href="#main-content">跳到主内容</a>' +
    '<div class="nav-shell"><header class="topbar">' +
    '<div class="brand"><span class="logo">SW</span><div><h1>SummitWorkbench</h1>' +
    '<p class="tagline">外置执行管理层</p></div></div>' +
    '<div class="header-right">' +
    '<span class="version-status checking" id="version-status">正在检查版本</span>' +
    '<span class="day-pill" id="day-pill">—</span>' +
    '<button class="ghost" id="btn-refresh" title="刷新">↻</button>' +
    '<button class="ghost" id="btn-sync" title="立即同步：拉取远端新提交（只 fetch/快进/推送，绝不 force）">⇅ 立即同步</button>' +
    '<button class="ghost" id="btn-check-updates" title="检查更新">检查更新</button>' +
    '<button class="ghost" id="btn-undo" title="撤销系统改动（只作用于 vault 文件）">↩ 撤销</button>' +
    '<button class="ghost" id="btn-quit" title="退出工作台（停止本地服务）">退出</button>' +
    '</div></header>' +
    '<div class="sync-banner" id="sync-banner" hidden></div>' +
    '<div class="version-error-banner" id="version-error-banner" hidden>' +
    '<span>工作台更新未完成。你的草稿已保留。</span>' +
    '<button class="ghost" data-action="retry-update">重试更新</button>' +
    '<button class="ghost" data-action="copy-diagnostics">复制诊断信息</button>' +
    '</div>' +
    '<nav class="tabs" role="tablist" aria-label="工作台页面">' +
    '<button class="tab" id="tab-today" data-tab="today" aria-controls="view-today" role="tab">今日</button>' +
    '<button class="tab" id="tab-review" data-tab="review" aria-controls="view-review" role="tab">审批 <span class="tab-badge" id="tab-badge-review"></span></button>' +
    '<button class="tab" id="tab-projects" data-tab="projects" aria-controls="view-projects" role="tab">项目</button>' +
    '<button class="tab" id="tab-settings" data-tab="settings" aria-controls="view-settings" role="tab">设置</button>' +
    '</nav></div>' +
    '<main id="main-content" tabindex="-1">' +
    '<section id="view-today" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-review" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-projects" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-settings" class="view" role="tabpanel" tabindex="0"></section>' +
    '</main>' +
    '<div class="modal-backdrop" id="modal-backdrop" hidden><div class="modal" id="modal"></div></div>';

  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    b.addEventListener('click', () => {
      actions.onSelectTab(normalizeTab(b.dataset.tab));
      b.focus();
    });
    b.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>('.tab'));
      const index = tabs.indexOf(b);
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
        (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      const nextButton = tabs[nextIndex];
      actions.onSelectTab(normalizeTab(nextButton?.dataset.tab));
      nextButton?.focus();
    });
  });
  (document.getElementById('btn-refresh') as HTMLButtonElement).addEventListener('click', () => {
    actions.onRefresh();
  });
  (document.getElementById('btn-sync') as HTMLButtonElement).addEventListener('click', () => {
    actions.onSync();
  });
  (document.getElementById('btn-check-updates') as HTMLButtonElement).addEventListener('click', () => {
    actions.onCheckUpdates();
  });
  (document.getElementById('btn-undo') as HTMLButtonElement)?.addEventListener('click', () => {
    actions.onUndo();
  });
  (document.getElementById('btn-quit') as HTMLButtonElement).addEventListener('click', () => {
    actions.onQuit();
  });
  const backdrop = modalBackdrop();
  backdrop.addEventListener('click', (ev) => {
    if (ev.target === backdrop) requestModalClose();
  });
  document.addEventListener('keydown', (event) => {
    if (backdrop.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      requestModalClose();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(backdrop.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex="0"]',
    ));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}
