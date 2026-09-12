/** 同步冲突弹层的纯文本标签（无 DOM、无状态；从 legacy-main 抽出，Step 1）。 */
import type { ConflictPathDetail, ConflictSelection } from './types';

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
