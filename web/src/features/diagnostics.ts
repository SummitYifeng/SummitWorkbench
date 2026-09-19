export interface DiagnosticsVersion {
  frontend_build?: string | null;
  server_version?: string | null;
  server_instance?: string | null;
  mode?: string | null;
  api_protocol?: number | null;
}

interface DiagnosticsPreviewPayload {
  ok: boolean;
  files: Array<{ name: string; description: string }>;
  snapshot: Record<string, unknown>;
}

type DiagnosticsApi = <T>(url: string, init?: RequestInit) => Promise<T>;
type DiagnosticsToast = (message: unknown, tone: 'ok' | 'err' | 'info') => void;

export interface DiagnosticsDeps {
  api: DiagnosticsApi;
  fetch: typeof fetch;
  toast: DiagnosticsToast;
  clientBuild: string;
  getVersion: () => DiagnosticsVersion | null;
  escapeHtml: (value: string) => string;
}

/** 诊断动作由设置页组合根注入能力，避免回流到 legacy-main。 */
export function createDiagnosticsActions(deps: DiagnosticsDeps) {
  async function copyDiagnostics(): Promise<void> {
    const remoteVersion = deps.getVersion();
    const lines = [
      'App frontend client build: ' + deps.clientBuild,
      'Served frontend build: ' + (remoteVersion?.frontend_build ?? 'unknown'),
      'Server version/instance: ' + (remoteVersion?.server_version ?? 'unknown') +
        '/' + (remoteVersion?.server_instance ?? 'unknown'),
      'Panel mode: ' + (remoteVersion?.mode ?? 'unknown'),
      'API protocol: ' + (remoteVersion?.api_protocol ?? 'unknown'),
    ];
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      deps.toast('诊断信息已复制', 'ok');
    } catch {
      deps.toast(lines.join(' · '), 'info');
    }
  }

  async function previewDiagnostics(): Promise<void> {
    const target = document.getElementById('diagnostics-preview');
    try {
      const result = await deps.api<DiagnosticsPreviewPayload>('/api/diagnostics/preview');
      if (target) {
        target.innerHTML = '<div class="success"><strong>导出内容预览</strong><ul>' +
          result.files.map((file) => '<li><code>' + deps.escapeHtml(file.name) + '</code>：' + deps.escapeHtml(file.description) + '</li>').join('') +
          '</ul></div>';
      }
      deps.toast('诊断包预览已生成', 'ok');
    } catch (err) {
      deps.toast(err, 'err');
    }
  }

  async function exportDiagnostics(): Promise<void> {
    try {
      const response = await deps.fetch('/api/diagnostics/export', { cache: 'no-store' });
      if (!response.ok) throw new Error('诊断包导出失败（HTTP ' + response.status + '）');
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'summitworkbench-diagnostics.zip';
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      window.setTimeout(() => {
        URL.revokeObjectURL(link.href);
        link.remove();
      }, 1000);
      deps.toast('诊断包已导出', 'ok');
    } catch (err) {
      deps.toast(err, 'err');
    }
  }

  return { copyDiagnostics, previewDiagnostics, exportDiagnostics };
}
