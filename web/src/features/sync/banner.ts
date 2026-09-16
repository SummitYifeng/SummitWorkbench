import { api } from '../../api/request';
import { formatBusinessTime } from '../../core/time';
import { mutation } from '../../lifecycle/connection';
import { sendNativeMessage } from '../../lifecycle/native-bridge';
import { esc } from '../../md';
import { toast } from '../shell';
import { syncStateLabel } from './labels';
import { getSyncDeps } from './state';
import type { SyncStatusPayload } from './types';

/** 顶部同步保护态横幅、重试与导出（原 legacy-main 逐条搬迁）。 */

/**
 * 一次同步是否在途。按钮与自动拉取共用同一守卫：第二次请求会撞上后端的 workspace 锁，
 * 报出「另一个同步正在进行」，对用户毫无意义。
 */
let syncBusy = false;

/** 读取同步状态并渲染横幅；返回本次读到 payload（失败为 null），供空闲自动拉取判断。 */
export async function refreshSyncBanner(): Promise<SyncStatusPayload | null> {
  const el = document.getElementById('sync-banner') as HTMLElement | null;
  if (!el) return null;
  try {
    const data = await api<SyncStatusPayload>('/api/sync/status');
    const interesting = data.state !== 'ready' && data.state !== 'unconfigured';
    el.hidden = !interesting;
    if (interesting) {
      // 形状（2026-09-14 使用者反馈「状态句太长挤在网格里 + 太高占地方」后重做）：
      //   第 1 行 = 短状态词 + 两个短数字 + 主按钮（右侧）
      //   第 2 行 = 后端那句中文「下一步」建议（小字）
      //   其余全部（状态码 / 分支 / 远端 / 仓库 / 设备 id / 导出）收进折叠区。
      const diverged = data.state === 'diverged-protected';
      const metaBits = ['待推送 ' + String(data.pending_commits ?? 0)];
      if (data.last_sync_at) metaBits.push('最后成功 ' + formatBusinessTime(data.last_sync_at));
      const generation = data.automation_primary_generation;
      const detailRows: Array<[string, string]> = [
        ['状态码', data.state],
        ['本地领先', String(data.ahead ?? 0)],
        ['远端领先', String(data.behind ?? 0)],
        ['分支', data.branch ?? '—'],
        ['远端主机', data.remote_host ?? '—'],
        ['仓库', (data.repo_states ?? []).join('、') || '—'],
        ['主设备', data.automation_primary_device_id ?? '—'],
        ['主设备代际', generation == null ? '—' : '第 ' + String(generation) + ' 代'],
      ];
      const grid = (rows: Array<[string, string]>): string =>
        '<div class="sync-grid">' + rows.map(([label, value]) =>
          '<span class="sync-label">' + esc(label) + '</span><span>' + esc(value) + '</span>').join('') +
        '</div>';
      // 分叉是唯一「必须先看冲突」的状态：它是主按钮，同步退为次要。
      const actions = (diverged
        ? '<button class="primary" data-action="sync-conflict-details">处理冲突</button>'
        : '') +
        '<button class="' + (diverged ? 'ghost' : 'primary') + '" data-action="sync-retry">' +
        (diverged ? '仍然重试' : '立即同步') + '</button>';
      el.innerHTML = '<div class="sync-row">' +
        '<span class="sync-state">同步状态：<b>' + esc(syncStateLabel(data.state)) + '</b></span>' +
        '<span class="sync-meta">' + esc(metaBits.join(' · ')) + '</span>' +
        '<span class="sync-actions">' + actions + '</span>' +
        '</div>' +
        (data.next_step ? '<p class="sync-hint">' + esc(data.next_step) + '</p>' : '') +
        (data.detail ? '<p class="sync-hint">' + esc(data.detail) + '</p>' : '') +
        '<details class="sync-more"><summary>查看详情（分支 / 远端 / 设备 / 状态码）</summary>' +
        grid(detailRows) +
        '<div class="sync-actions sync-actions-inline">' +
        '<button class="ghost" data-action="sync-export">导出本机副本</button></div></details>';
    }
    return data;
  } catch (err) {
    // 读取失败不能静默隐藏：已显示的保护态（如 diverged-protected 及其"查看冲突详情"入口）
    // 必须保留，并明确标注这是上次成功读取的状态。
    if (el.hidden) return null;
    el.querySelector('.sync-read-error')?.remove();
    const note = document.createElement('div');
    note.className = 'sync-detail sync-read-error';
    note.innerHTML = '同步状态读取失败：' + esc(String(err)) +
      '（上方为上次成功读取的状态） <button class="ghost" data-action="sync-refresh">重新读取</button>';
    el.appendChild(note);
    return null;
  }
}

/**
 * 空闲自动拉取（D6）。
 *
 * 背景：``sync_workspace`` 只被 ``/api/sync/run`` 调用，而那个端点此前**只在同步横幅的
 * 「立即重试」**里可达，横幅在状态 ``ready`` 时是隐藏的 ⇒ 一台干净、只读为主的设备
 * 没有任何拉取入口，会一直显示旧数据；它下次写入时又必然撞上分叉。
 *
 * 行为边界（保守）：
 * - 只在**读到的状态是 ready** 时才真正同步一次（即 fetch + 快进；ready 下没有可推送的东西）；
 * - ``dirty-protected`` / ``diverged-protected`` / ``offline-local-ahead`` 等一律**不自动动 git**，
 *   仍由用户点「立即重试」——脏工作树绝不自动合并的既有保护不变；
 * - 失败静默（离线、代理抖动），下一次 tick 自然重试。
 */
export async function autoSyncIfIdle(): Promise<void> {
  const status = await refreshSyncBanner();
  if (syncBusy || !status || status.state !== 'ready') return;
  syncBusy = true;
  try {
    await api('/api/sync/run', { method: 'POST' });
    await Promise.all([refreshSyncBanner(), getSyncDeps()?.refreshState()]);
  } catch {
    // 离线或瞬时失败：保持静默，不打扰用户；下一次 tick 会再试。
  } finally {
    syncBusy = false;
  }
}

export async function retrySync(): Promise<void> {
  if (syncBusy) return;
  syncBusy = true;
  try {
    const data = await mutation(() => api<{ ok: boolean; message?: string }>('/api/sync/run', { method: 'POST' }));
    toast(data.ok ? '同步完成' : (data.message ?? '同步失败'), data.ok ? 'ok' : 'err');
    await Promise.all([refreshSyncBanner(), getSyncDeps()?.refreshState()]);
  } catch (err) {
    toast(err, 'err');
  } finally {
    syncBusy = false;
  }
}

export async function exportSyncSnapshot(): Promise<void> {
  try {
    const data = await api<SyncStatusPayload>('/api/sync/export');
    const content = JSON.stringify(data, null, 2) + '\n';
    if (sendNativeMessage({
      type: 'saveTextFile',
      filename: 'summitworkbench-sync-status.json',
      content,
    })) {
      toast('请选择保存位置', 'info');
      return;
    }
    const blob = new Blob([content], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'summitworkbench-sync-status.json';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(link.href);
      link.remove();
    }, 1000);
  } catch (err) {
    toast(err, 'err');
  }
}

export async function exportSyncConflictPackage(): Promise<void> {
  try {
    const response = await fetch('/api/sync/conflict/export', { cache: 'no-store' });
    if (!response.ok) throw new Error('冲突包导出失败（HTTP ' + response.status + '）');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await response.blob());
    link.download = 'summitworkbench-sync-recovery.zip';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
    toast('冲突包已准备下载', 'ok');
  } catch (err) {
    toast(err, 'err');
  }
}
