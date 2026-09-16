import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { clearEntityDraft, loadEntityDraft } from '../../lifecycle/drafts';
import { esc } from '../../md';
import { projectDisplayName } from '../projects';
import { closeModal, openModal, rejectOversizeText, toast } from '../shell';
import { getThreadsDeps } from './deps';
import type { ArtifactDraft } from './types';

/** AI 产物入库弹层（原 legacy-main 逐条搬迁）。 */

/** 产物保存后的二次确认文案：预览超过 1200 字符即截断（纯函数，便于断言）。 */
export function artifactStateConfirmText(stateText: string): string {
  const preview = stateText.length > 1200 ? stateText.slice(0, 1200) + '\n…（预览已截断）' : stateText;
  return '产物已保存。\n\n即将把以下内容写入主档案「当前状态」：\n\n' + preview + '\n\n确认继续？';
}


/** AI 产物入库弹窗：选线程 + 粘贴阶段总结/PRD/背景包全文 → 自动命名与摘要索引。 */
export function openArtifactModal(defaultProject: string): void {
  const registered = (getThreadsDeps()?.projects() ?? []).filter((p) => p.registered);
  const saved = loadEntityDraft<ArtifactDraft>('artifact:' + defaultProject, Date.now(), getThreadsDeps()?.workspaceId());
  const options = registered
    .map((p) => {
      // 中文显示名优先；项目 ID 收进 option 的 title（hover 可见）。
      const label = projectDisplayName(p);
      const hint = label === p.name ? p.name : label + '（' + p.name + '）';
      return '<option value="' + esc(p.name) + '" label="' + esc(label + '（' + hint + '）') + '"></option>';
    })
    .join('');
  openModal(
    '<h3>存入 AI 产物 / 导入文档</h3>' +
    '<p class="hint">粘贴和 AI 长对话产出的阶段总结 / 背景包 / PRD / 时间线全文，<strong>或直接选择本地 .md/.txt 文件</strong>；' +
    '系统自动命名、生成摘要索引并归入所选线程档案。<strong>也可以直接把文件从访达拖进本窗口</strong>。</p>' +
    '<form id="artifact-form">' +
    '<div class="form-row"><label for="artifact-project">归入线程/项目</label>' +
    '<input id="artifact-project" list="artifact-project-options" placeholder="搜索项目名或 ID…" autocomplete="off">' +
    '<datalist id="artifact-project-options">' + options + '</datalist></div>' +
    '<input id="artifact-title" placeholder="标题（可选；留空则 AI 自动起）">' +
    '<div class="form-row artifact-file-row"><label class="ghost artifact-pick" for="artifact-file">📄 选择本地文件' +
    '<input id="artifact-file" type="file" accept=".md,.txt" class="visually-hidden"></label>' +
    '<span class="hint" id="artifact-file-name"></span></div>' +
    '<textarea id="artifact-text" rows="10" required placeholder="把整份文档粘贴在这里，或点上方按钮读入本地文件…"></textarea>' +
    '<label class="hint artifact-to-state"><input type="checkbox" id="artifact-to-state"> ' +
    '保存后先预览并确认把本文档摘要同步为主档案「当前状态」（会覆盖原内容，旧版可在 vault git 找回）</label>' +
    '<div class="row"><button class="primary" type="submit">存入档案</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  document.getElementById('artifact-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitArtifact();
  });
  const savedProject = saved?.project || defaultProject;
  const projectInput = document.getElementById('artifact-project') as HTMLInputElement | null;
  const titleInput = document.getElementById('artifact-title') as HTMLInputElement | null;
  const textArea = document.getElementById('artifact-text') as HTMLTextAreaElement | null;
  const stateInput = document.getElementById('artifact-to-state') as HTMLInputElement | null;
  if (projectInput && savedProject) projectInput.value = savedProject;
  if (titleInput) titleInput.value = saved?.title ?? '';
  if (textArea) textArea.value = saved?.text ?? '';
  if (stateInput) stateInput.checked = saved?.syncState ?? false;
  const modal = document.getElementById('modal') as HTMLElement | null;
  if (modal) {
    modal.dataset.draftEntity = 'artifact:' + defaultProject;
    modal.dataset.draftDirty = saved ? '1' : '0';
  }
  const persistArtifactDraft = (): void => {
    getThreadsDeps()?.persistEntityDraft('artifact:' + defaultProject, {
      project: (document.getElementById('artifact-project') as HTMLInputElement | null)?.value ?? '',
      title: (document.getElementById('artifact-title') as HTMLInputElement | null)?.value ?? '',
      text: (document.getElementById('artifact-text') as HTMLTextAreaElement | null)?.value ?? '',
      syncState: !!(document.getElementById('artifact-to-state') as HTMLInputElement | null)?.checked,
    });
  };
  document.getElementById('artifact-form')?.addEventListener('input', persistArtifactDraft);
  document.getElementById('artifact-form')?.addEventListener('change', persistArtifactDraft);
  const readArtifactFile = (file: File): void => {
    const reader = new FileReader();
    reader.onload = () => {
      const content = String(reader.result ?? '');
      const titleInput = document.getElementById('artifact-title') as HTMLInputElement | null;
      const textArea = document.getElementById('artifact-text') as HTMLTextAreaElement | null;
      if (titleInput && !titleInput.value.trim()) {
        titleInput.value = file.name.replace(/\.(md|txt)$/i, '');
      }
      if (textArea) textArea.value = content;
      const nameEl = document.getElementById('artifact-file-name');
      if (nameEl) nameEl.textContent = '已读入：' + file.name + '（' + content.length + ' 字符）';
      persistArtifactDraft();
    };
    reader.onerror = () => toast('读取文件失败', 'err');
    reader.readAsText(file, 'utf-8');
  };
  const fileInput = document.getElementById('artifact-file') as HTMLInputElement | null;
  fileInput?.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) readArtifactFile(file);
  });
  // 拖放读入（绕过系统文件选择框：WKWebView 对 picker 的兼容问题）
  const dropTarget = document.getElementById('artifact-form') as HTMLElement | null;
  dropTarget?.addEventListener('dragover', (ev) => {
    ev.preventDefault();
    dropTarget.classList.add('artifact-drop');
  });
  dropTarget?.addEventListener('dragleave', () => dropTarget.classList.remove('artifact-drop'));
  dropTarget?.addEventListener('drop', (ev) => {
    ev.preventDefault();
    dropTarget.classList.remove('artifact-drop');
    const file = ev.dataTransfer?.files?.[0];
    if (file) {
      readArtifactFile(file);
      toast('已读取文件：' + file.name, 'ok');
    }
  });
}

let artifactSubmitting = false;

export async function submitArtifact(): Promise<void> {
  if (artifactSubmitting) return;
  const text = ((document.getElementById('artifact-text') as HTMLTextAreaElement | null)?.value ?? '').trim();
  const project = ((document.getElementById('artifact-project') as HTMLInputElement | null)?.value ?? '').trim();
  const title = ((document.getElementById('artifact-title') as HTMLInputElement | null)?.value ?? '').trim();
  const syncState = !!((document.getElementById('artifact-to-state') as HTMLInputElement | null)?.checked);
  if (!text) {
    toast('产物内容为空', 'err');
    return;
  }
  if (rejectOversizeText(text)) return;
  if (!project) {
    toast('请选择归入的线程/项目', 'err');
    return;
  }
  // 双击「存入档案」不能创建两份产物（产物保存后才可能触发状态预览确认）。
  artifactSubmitting = true;
  const submitButton = document.querySelector<HTMLButtonElement>('#artifact-form button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string; summary?: string }>('/api/threads/artifacts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, text, title: title || null }),
    }));
    if (!r.ok) {
      toast(r.message, 'err');
      return;
    }
    let extra = '';
    if (syncState) {
      const stateText = r.summary || title || text.slice(0, 80).replace(/\s+/g, ' ');
      const confirmed = window.confirm(artifactStateConfirmText(stateText));
      if (confirmed) {
        const s = await mutation(() => api<{ ok: boolean; message: string }>('/api/threads/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project, text: stateText }),
        }));
        extra = s.ok ? ' · 已同步当前状态' : '（当前状态同步失败：' + s.message + '）';
      } else {
        extra = ' · 已保存产物，未修改当前状态';
      }
    }
    const modal = document.getElementById('modal') as HTMLElement | null;
    const draftEntity = modal?.dataset.draftEntity;
    if (draftEntity) clearEntityDraft(draftEntity, getThreadsDeps()?.workspaceId());
    if (draftEntity !== 'artifact:' + project) {
      clearEntityDraft('artifact:' + project, getThreadsDeps()?.workspaceId());
    }
    closeModal();
    toast(r.message + extra, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(err, 'err');
  } finally {
    artifactSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}
