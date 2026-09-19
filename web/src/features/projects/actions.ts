import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { toast } from '../shell';
import { getProjectDeps } from './deps';

/** 项目激活/归档动作（原 legacy-main 逐条搬迁）。 */

type ProjectActionApi = <T>(url: string, init?: RequestInit) => Promise<T>;
type ProjectActionMutation = <T>(work: () => Promise<T>) => Promise<T>;

export interface ProjectCreateDeps {
  api: ProjectActionApi;
  mutation: ProjectActionMutation;
  toast: (message: unknown, tone: 'ok' | 'err' | 'info') => void;
  refreshAll: () => Promise<unknown>;
}

/** data-action 对应的项目建档表单提交；所有组合根能力通过参数注入。 */
export function submitProjectCreate(form: HTMLFormElement, deps: ProjectCreateDeps): void {
  const data = new FormData(form);
  const projectId = String(data.get('project_id') ?? '').trim();
  if (!projectId) {
    deps.toast('请输入项目 ID', 'err');
    return;
  }
  const aliases = String(data.get('aliases') ?? '')
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
  void deps.mutation(async () => {
    const r = await deps.api<{ ok: boolean; message: string }>('/api/projects/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, aliases }),
    });
    deps.toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) form.reset();
    void deps.refreshAll();
  }).catch((err: unknown) => deps.toast(err, 'err'));
}

export async function setProjectState(action: 'activate' | 'archive', name: string): Promise<void> {
  if (!name) return;
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/projects/' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }));
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(err, 'err');
  }
  void getProjectDeps()?.refreshAll();
}

/** data-action="project-archive"：归档前可选一次确认（原派发器内联分支）。 */
export function archiveProject(name: string, confirmFirst: boolean): void {
  if (
    confirmFirst &&
    !window.confirm(
      '归档后将从首页移除（文件夹与笔记不动），可在「项目」页随时恢复。确定归档「' + name + '」？',
    )
  ) {
    return;
  }
  void setProjectState('archive', name);
}
