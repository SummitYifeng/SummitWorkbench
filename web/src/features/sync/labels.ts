/** 同步冲突弹层的纯文本标签（无 DOM、无状态；从 legacy-main 抽出，Step 1）。 */
import type { ConflictPathDetail, ConflictSelection } from './types';

/**
 * 同步状态的中文口径（单一真源，2026-09-14）。
 *
 * 后端状态码（`diverged-protected`、`dirty-protected`…）是内部标识，不该直接贴给使用者；
 * 顶部横幅与设置页都从这里取标签，原始状态码只在「查看详情」里出现。
 */
const SYNC_STATE_LABELS: Record<string, string> = {
  ready: '已同步',
  unconfigured: '未配置同步',
  syncing: '正在同步',
  'offline-local-ahead': '离线（本机有提交待推送）',
  'remote-ahead': '远端有更新待拉取',
  'local-ahead': '本机有提交待推送',
  'diverged-protected': '本机与远端都有新提交，等你决定怎么处理',
  'dirty-protected': '本机有未提交改动，已暂停自动同步',
  'auth-required': '远端需要重新登录',
  'remote-scheme-unsupported': '远端地址格式不支持',
  error: '同步出错',
};

/** 状态码 → 中文短句；未知码兜底为「需要处理」，绝不把英文码直接显示出来。 */
export function syncStateLabel(state: string): string {
  return SYNC_STATE_LABELS[state] ?? '需要处理';
}

export function conflictKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    'append-only-event': '活动事件（自动收集）',
    'generated-view': '派生视图（重建）',
    'unknown-generated-view': '未知派生视图（保留双方）',
    'manual-markdown': 'Markdown（人工选择）',
    'opaque-binary': '未知/二进制（保留双方）',
  };
  return labels[kind] ?? kind;
}

export function conflictSelectionLabel(choice: ConflictSelection): string {
  const labels: Record<string, string> = {
    'keep-local': '保留本机',
    'keep-remote': '采用远端',
    'preserve-both': '保留双方副本',
  };
  return labels[choice] ?? '请选择处理方式';
}

export function conflictRevision(revision: string): string {
  return revision.length > 12 ? revision.slice(0, 12) + '…' : revision;
}

export function conflictEventSummary(event: Record<string, string> | null | undefined): string {
  if (!event || event.parse_status) return '';
  return '设备 ' + (event.device_id ?? '—') + ' · 时间 ' + (event.occurred_at ?? '—') +
    ' · 操作 ' + (event.causation_operation_id ?? '—');
}

export function conflictDigestSummary(item: ConflictPathDetail): string {
  if (item.kind === 'append-only-event') {
    return [conflictEventSummary(item.local_event), conflictEventSummary(item.remote_event)].filter(Boolean).join(' / ');
  }
  if (item.local_sha256 || item.remote_sha256) {
    return '摘要 本机 ' + conflictRevision(item.local_sha256 ?? '—') + ' · 远端 ' + conflictRevision(item.remote_sha256 ?? '—');
  }
  return '';
}
