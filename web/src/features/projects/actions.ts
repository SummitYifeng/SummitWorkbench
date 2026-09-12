import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { toast } from '../shell';
import { getProjectDeps } from './deps';

/** 项目激活/归档动作（原 legacy-main 逐条搬迁）。 */

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
    toast(String(err), 'err');
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
