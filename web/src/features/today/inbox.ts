import { esc } from '../../md';
import { clearServerDraft } from '../../lifecycle/server-drafts';
import { closeModal, openModal } from '../shell';
import { api, mutation, refreshState, toast } from './deps';
import type { ProjectChoice } from './actions';
import type { InboxTarget } from './types';

/**
 * 收件箱条目的「提升为…」弹层（契约 §10）。
 *
 * **成本约定**（第九阶段）：
 * - 打开弹层**不调模型**：默认目标用后端给的本地启发式（`suggested_target`），界面不等模型；
 * - 只有使用者点「让 AI 判断这条适合变成什么」才会打一次 `POST /api/inbox/suggest`
 *   （`capture` 能力，便宜），结果标注「AI 建议」并写明仅供参考；
 * - 弹层里的其它交互（切目标、选项目、填日期）都是纯本地。
 *
 * 这个模块是**唯一**引用 `/api/inbox/suggest` 的地方——列表渲染（`render.ts` /
 * `legacy-main.ts` 的状态读取）必须与它无关，机器守卫在 `test-browser-contract.mjs`。
 */
interface Item {
  id: string;
  text: string;
  due: string | null;
  project: string | null;
  projects: string[];
  suggested_target: InboxTarget;
  suggested_reason: string;
}

const TARGET_LABELS: Record<InboxTarget, string> = {
  project: '项目页条目',
  'feishu-task': '飞书待办',
  thought: '一篇工作思考',
};

const TARGET_HINTS: Record<InboxTarget, string> = {
  project: '写进项目页的「下一步」或「跟进事项」（库内可检索）。',
  'feishu-task': '写回飞书（待办的真源），库内不留可检索正文，只在 review/archive/ 留痕。',
  thought: '落在 thinking/，三段式、会被检索（跨项目、组织层面的沉淀）。',
};

let submitting = false;

function projectOptions(projects: ProjectChoice[], selected: string): string {
  if (!projects.length) return '<option value="">（暂无已建档项目）</option>';
  return projects
    .map((project) => {
      const value = esc(project.name);
      const mark = project.name === selected ? ' selected' : '';
      return '<option value="' + value + '"' + mark + '>' + esc(project.title || project.name) + '</option>';
    })
    .join('');
}

function value(id: string): string {
  return (document.getElementById(id) as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | null)?.value ?? '';
}

function checkedTarget(): InboxTarget {
  const picked = document.querySelector<HTMLInputElement>('input[name="inbox-target"]:checked');
  return (picked?.value ?? 'thought') as InboxTarget;
}

/** 只让当前目标相关的字段可见（其余隐藏，避免误填）。 */
function syncTargetFields(): void {
  const target = checkedTarget();
  for (const name of ['project', 'feishu-task', 'thought'] as InboxTarget[]) {
    const block = document.getElementById('inbox-fields-' + name);
    if (block) block.hidden = name !== target;
  }
}

function targetRadios(defaultTarget: InboxTarget): string {
  return (Object.keys(TARGET_LABELS) as InboxTarget[])
    .map((target) => {
      const id = 'inbox-target-' + target;
      return '<label class="inbox-target-option" for="' + id + '">' +
        '<input type="radio" id="' + id + '" name="inbox-target" value="' + target + '"' +
        (target === defaultTarget ? ' checked' : '') + '>' +
        '<span><strong>' + TARGET_LABELS[target] + '</strong>' +
        '<span class="hint">' + TARGET_HINTS[target] + '</span></span></label>';
    })
    .join('');
}

async function submitPromote(url: string, body: Record<string, unknown>): Promise<void> {
  if (submitting) return;
  submitting = true;
  const submit = document.querySelector<HTMLButtonElement>('#inbox-promote-form button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const result = await mutation(() =>
      api<{ ok: boolean; message: string; path?: string }>(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    );
    if (result.ok) {
      try {
        await clearServerDraft(api, 'inbox-promote', String(body.id ?? ''));
      } catch { /* retain the draft if cleanup cannot be confirmed */ }
      closeModal();
      const rel = result.path ? result.path.replace(/^.*\/_vault\//, '') : '';
      toast(rel && !result.message.includes(rel) ? result.message + ' · ' + rel : result.message, 'ok');
      void refreshState();
    } else {
      // 弹层留着好改：后端的点名提示（缺截止 / 缺段落 / 项目未建档…）原样显示。
      toast(result.message, 'err');
    }
  } catch (err) {
    toast(err, 'err');
  } finally {
    submitting = false;
    if (submit) submit.disabled = false;
  }
}

/** 打开某条收件箱条目的提升弹层。`projects` 来自今日页已有的项目列表（不再请求）。 */
export function openInboxPromoteModal(item: Item, projects: ProjectChoice[] = []): void {
  const defaultProject = item.project ?? item.projects[0] ?? '';
  openModal(
    '<h3>提升这条</h3>' +
    '<p class="inbox-source">' + esc(item.text) + '</p>' +
    '<p class="hint" id="inbox-suggest-line">默认：' + TARGET_LABELS[item.suggested_target] +
    ' —— ' + esc(item.suggested_reason) + '</p>' +
    '<div class="row"><button class="ghost" type="button" data-action="inbox-ai-suggest" data-id="' +
    esc(item.id) + '">让 AI 判断这条适合变成什么</button>' +
    '<span class="hint">点它才会调一次模型（便宜）；不点就完全按上面的默认来</span></div>' +
    '<form id="inbox-promote-form" data-draft-type="inbox-promote" data-draft-id="' + esc(item.id) + '">' +
    '<div class="inbox-targets">' + targetRadios(item.suggested_target) + '</div>' +
    '<div id="inbox-fields-project">' +
    '<label>写入哪个项目</label><select id="inbox-project">' +
    projectOptions(projects, defaultProject) + '</select>' +
    '<label>写进哪个区块</label><select id="inbox-block">' +
    '<option value="next-step">下一步（我要做的）</option>' +
    '<option value="followup">跟进事项（等别人回）</option>' +
    '</select></div>' +
    '<div id="inbox-fields-feishu-task" hidden>' +
    '<label>截止日期</label><input id="inbox-due" type="date" value="' + esc(item.due ?? '') + '">' +
    '<label>开始日期（默认与截止同一天）</label><input id="inbox-start" type="date" value="' +
    esc(item.due ?? '') + '">' +
    '<p class="hint">飞书任务同时写全天开始与截止；库内只留审计痕迹，不留待办正文。</p></div>' +
    '<div id="inbox-fields-thought" hidden>' +
    '<label>问题缘起</label><textarea id="inbox-problem" rows="3">' + esc(item.text) + '</textarea>' +
    '<label>思考展开</label><textarea id="inbox-thinking" rows="4"></textarea>' +
    '<label>当前结论</label><textarea id="inbox-conclusion" rows="3"></textarea>' +
    '<label>一句话摘要（可留空）</label><input id="inbox-summary">' +
    '<p class="hint">三段都要写（与「写工作思考」同一套落盘）。</p></div>' +
    '<div class="row"><button class="primary" type="submit">提升并移出收件箱</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>',
  );
  syncTargetFields();
  for (const radio of Array.from(document.querySelectorAll<HTMLInputElement>('input[name="inbox-target"]'))) {
    radio.addEventListener('change', syncTargetFields);
  }
  document.getElementById('inbox-promote-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    void submitPromote('/api/inbox/promote', promoteBody(item.id, checkedTarget()));
  });
}

/** 按目标只提交相关字段（后端按目标读取，多余字段忽略）。 */
function promoteBody(id: string, target: InboxTarget): Record<string, unknown> {
  const body: Record<string, unknown> = { id, target };
  if (target === 'project') {
    body.project = value('inbox-project');
    body.block = value('inbox-block');
  } else if (target === 'feishu-task') {
    body.due_date = value('inbox-due');
    body.start_date = value('inbox-start');
  } else {
    body.problem = value('inbox-problem');
    body.thinking = value('inbox-thinking');
    body.conclusion = value('inbox-conclusion');
    body.summary = value('inbox-summary');
  }
  return body;
}

/**
 * 「让 AI 判断」：**显式点击**才调一次模型，只给建议、不写任何东西。
 *
 * 结果只做两件事：选中它建议的目标 + 把理由显示成「AI 建议：…（建议仅供参考，最终由你确认）」。
 * 不自动提交——使用者仍然要自己按「提升并移出收件箱」。
 */
export async function requestInboxSuggestion(id: string): Promise<void> {
  const line = document.getElementById('inbox-suggest-line');
  try {
    const result = await api<{
      ok: boolean;
      message?: string;
      target?: InboxTarget;
      reason?: string;
      model_used?: boolean;
    }>('/api/inbox/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    if (!result.ok) {
      toast(result.message ?? 'AI 判断失败', 'err');
      return;
    }
    if (result.target) {
      const radio = document.getElementById('inbox-target-' + result.target) as HTMLInputElement | null;
      if (radio) radio.checked = true;
      syncTargetFields();
    }
    if (line && result.reason) {
      line.textContent = (result.model_used ? '' : '（未用 AI）') + result.reason;
    }
    toast(result.model_used ? 'AI 给了一个建议，最终由你确认' : 'AI 不可用，已保留本地默认', 'info');
  } catch (err) {
    toast(err, 'err');
  }
}
