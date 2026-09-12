# ruff: noqa: E501
"""Small, dependency-free HTML wizard used by restricted and full app entry points."""

from __future__ import annotations


def render_onboarding_wizard(*, full_app: bool = False) -> str:
    """Render the resumable three-step connection wizard."""
    page = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>连接工作台 · SummitWorkbench</title>
<style>
:root { --fg:#1f2937; --muted:#6b7280; --card:#fff; --bg:#f7f7f5; --border:#e5e7eb; --accent:#2563eb; --ok:#16803c; --ok-bg:#e9f7ed; --bad:#b42318; }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,"PingFang SC",sans-serif; }
main { max-width:720px; margin:7vh auto; padding:28px; background:var(--card); border:1px solid var(--border); border-radius:16px; box-shadow:0 12px 38px #0000000b; }
h1 { margin:0 0 6px; font-size:24px; } h2 { font-size:18px; margin:20px 0 8px; } p { margin:8px 0; color:var(--muted); }
.steps { display:flex; gap:8px; margin:18px 0; } .step { flex:1; padding:8px 10px; border-radius:8px; background:var(--bg); color:var(--muted); font-size:13px; }
.step.active { background:#eaf1ff; color:var(--accent); font-weight:700; } .step.done { background:var(--ok-bg); color:var(--ok); }
label { display:block; margin:14px 0 4px; font-weight:600; } input { width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:8px; font:inherit; }
button { font:inherit; padding:9px 15px; border:1px solid var(--border); border-radius:8px; background:var(--card); cursor:pointer; }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); } button:disabled { opacity:.5; cursor:not-allowed; }
.row { display:flex; justify-content:space-between; gap:10px; margin-top:22px; } .choices { display:grid; gap:10px; margin-top:18px; }
.choice { text-align:left; } .choice.selected { border-color:var(--ok); color:var(--ok); background:var(--ok-bg); }
.error,.success { margin-top:14px; padding:10px 12px; border-radius:8px; } .error { color:var(--bad); background:#fff1f0; } .success { color:var(--ok); background:var(--ok-bg); }
.skip { color:var(--muted); }
</style></head><body><main>
<h1>设置 SummitWorkbench</h1><p>按三步选好工作区、模型和飞书。每一步都可以跳过，之后可在设置里继续。</p>
<div class="steps" id="steps"></div><section id="content"></section><div id="message"></div>
</main><script>
const fullApp = __FULL_APP__;
const connectionPrefix = __CONNECTION_PREFIX__;
const state = {step: fullApp ? 1 : 0, flow:'create-new', work_root:'', vault_dir:'', workspace_id:null, modelKey:'', modelStatus:'pending', feishuStatus:'pending', feishuState:null};
const labels = ['工作区','AI 模型','飞书']; const $ = id => document.getElementById(id);
function api(url, init = {}) { return fetch(url, {...init, headers:{'Content-Type':'application/json', ...(init.headers || {})}}).then(async response => { const data = await response.json(); if (!response.ok) throw new Error(data.message || '请求失败'); return data; }); }
function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
function persist() { const draft = {flow:state.flow, step:['welcome','model','feishu','done'][state.step], work_root:state.work_root || null, vault_dir:state.vault_dir || null, provider_status:state.modelStatus}; if (fullApp) { sessionStorage.setItem('wb.onboarding.state', JSON.stringify({...state, modelKey:''})); return; } api('/api/onboarding/draft', {method:'PUT', body:JSON.stringify(draft)}).catch(() => {}); }
function draw() {
  $('steps').innerHTML = labels.map((label, index) => '<div class="step '+(index < state.step ? 'done' : index === state.step ? 'active' : '')+'">'+(index < state.step ? '✓ ' : '')+(index+1)+'. '+label+'</div>').join(''); let html = '';
  if (state.step === 0) html = '<h2>选择工作区</h2><p>工作区就是保存会议、任务和项目资料的本地文件夹。</p><div class="choices"><button class="choice '+(state.flow === 'create-new' ? 'selected' : '')+'" data-flow="create-new">新建我的工作台</button><button class="choice '+(state.flow === 'connect-existing' ? 'selected' : '')+'" data-flow="connect-existing">连接已有工作台</button><button class="choice '+(state.flow === 'upgrade-existing' ? 'selected' : '')+'" data-flow="upgrade-existing">升级这台 Mac 上的旧工作台</button></div><label>'+(state.flow === 'create-new' ? '新的 Work 文件夹' : '已有 vault 文件夹')+'</label><input id="path" value="'+escapeHtml(state.flow === 'create-new' ? state.work_root : state.vault_dir)+'" placeholder="~/Documents/Work">';
  if (state.step === 1) html = '<h2>连接 AI 模型</h2><p>只需粘贴 DeepSeek API Key。点击后会发一个最小请求现场验证，不会保存到草稿。</p><label>DeepSeek API Key</label><input id="model-key" type="password" placeholder="sk-…" value="'+escapeHtml(state.modelKey)+'"><div class="row"><button class="primary" id="verify-model">连接并验证</button><button class="skip" data-skip>跳过</button></div>';
  if (state.step === 2) html = '<h2>连接飞书</h2><p>授权后才能读日历和任务，并把完成动作写回飞书。</p><div class="row"><button class="primary" id="authorize-feishu">一键授权</button><button class="skip" data-skip>跳过</button></div>';
  if (state.step === 3) html = '<h2>设置完成</h2><div class="success">工作区已准备好。点击下方按钮进入完整工作台；之后也可以在设置页重新打开连接向导。</div><div class="row"><button class="primary" id="enter-workbench">进入工作台</button></div>';
  $('content').innerHTML = html+(state.step === 3 ? '' : '<div class="row"><button '+(state.step === 0 ? 'disabled' : '')+' data-back>上一步</button><button class="primary" data-next>'+(state.step === 2 ? '完成' : '下一步')+'</button></div>'); bind();
}
function clearMessage() { $('message').innerHTML = ''; }
function nativeMessage(message) { try { return Boolean(window.webkit?.messageHandlers?.wbLifecycle?.postMessage(message)); } catch (_) { return false; } }
function bind() { document.querySelectorAll('[data-flow]').forEach(button => button.onclick = () => { clearMessage(); state.flow = button.dataset.flow; persist(); draw(); }); $('content').querySelector('[data-next]')?.addEventListener('click', next); $('content').querySelector('[data-back]')?.addEventListener('click', () => { clearMessage(); state.step = Math.max(fullApp ? 1 : 0, state.step-1); persist(); draw(); }); $('content').querySelector('[data-skip]')?.addEventListener('click', () => { clearMessage(); state.step = Math.min(3, state.step+1); persist(); draw(); }); $('verify-model')?.addEventListener('click', verifyModel); $('authorize-feishu')?.addEventListener('click', authorizeFeishu); $('enter-workbench')?.addEventListener('click', enterWorkbench); }
async function next() { try { if (state.step === 0) { const path = $('path').value.trim(); if (!path) throw new Error('请先选择工作区文件夹'); if (state.flow === 'create-new') { state.work_root = path; const data = await api('/api/onboarding/create', {method:'POST', body:JSON.stringify({work_root:path})}); state.workspace_id = data.workspace_id; } else { state.vault_dir = path; const endpoint = state.flow === 'upgrade-existing' ? '/api/onboarding/upgrade' : '/api/onboarding/connect'; const data = await api(endpoint, {method:'POST', body:JSON.stringify({vault_dir:path})}); state.workspace_id = data.workspace_id; } } clearMessage(); state.step = Math.min(3, state.step+1); persist(); draw(); } catch (error) { $('message').innerHTML = '<div class="error">'+error.message+'</div>'; } }
async function verifyModel() { try { const key = $('model-key').value.trim(); if (!key) throw new Error('请先粘贴 API Key'); let data; if (fullApp) { await api('/api/settings/provider', {method:'POST', body:JSON.stringify({provider:'model', settings:{capability:'shared', credential_capability:'shared', model_id:'deepseek-v4-flash', base_url:'https://api.deepseek.com/v1', credential_account:'shared'}, secret:key})}); data = await api('/api/settings/provider/verify', {method:'POST', body:JSON.stringify({provider:'model'})}); } else { await api('/api/onboarding/model/save', {method:'POST', body:JSON.stringify({workspace_id:state.workspace_id, secret:key})}); data = await api('/api/onboarding/model/verify', {method:'POST', body:JSON.stringify({workspace_id:state.workspace_id})}); } state.modelKey = ''; state.modelStatus = 'ready'; persist(); $('message').innerHTML = '<div class="success">✓ '+data.message+'</div>'; state.step = 2; draw(); } catch (error) { $('message').innerHTML = '<div class="error">'+error.message+'</div>'; } }
async function authorizeFeishu() { try { const init = fullApp ? {method:'POST'} : {method:'POST', body:JSON.stringify({workspace_id:state.workspace_id})}; const data = await api(connectionPrefix+'/feishu/authorize-url', init); state.feishuState = data.state; sessionStorage.setItem('wb.onboarding.workspace', state.workspace_id || ''); sessionStorage.setItem('wb.onboarding.feishu-state', state.feishuState || ''); persist(); window.location.href = data.authorize_url; pollFeishu(); } catch (error) { $('message').innerHTML = '<div class="error">'+error.message+'</div>'; } }
async function pollFeishu() { if (!state.feishuState) return; const endpoint = connectionPrefix+'/feishu/status?state='+encodeURIComponent(state.feishuState); for (let attempt=0; attempt<120; attempt += 1) { await new Promise(resolve => setTimeout(resolve, 1000)); try { const data = await api(endpoint); if (data.status === 'connected') { state.feishuStatus = 'ready'; state.feishuState = null; sessionStorage.removeItem('wb.onboarding.feishu-state'); state.step = 3; persist(); $('message').innerHTML = '<div class="success">✓ 飞书已连接</div>'; draw(); return; } if (data.status === 'failed') { $('message').innerHTML = '<div class="error">' + escapeHtml(data.reason || '飞书授权未完成，请重新点击授权') + '</div>'; draw(); return; } } catch (_) { return; } } }
function enterWorkbench() { clearMessage(); if (nativeMessage({type:'restartService'})) { $('message').innerHTML = '<div class="success">正在切换到完整工作台…</div>'; return; } window.location.href = '/'; $('message').innerHTML = '<div class="success">请重新启动服务后进入完整工作台。</div>'; }
async function notifyNativeReady() { try { const data = await api('/api/version'); nativeMessage({type:'clientReady', clientBuild:data.frontend_build, serverInstance:data.server_instance}); } catch (_) {} }
async function restore() { try { let saved; if (fullApp) saved = JSON.parse(sessionStorage.getItem('wb.onboarding.state') || 'null'); else { saved = (await api('/api/onboarding/draft')).draft; const active = await api('/api/onboarding/status'); if (active.workspace_id) state.workspace_id = active.workspace_id; } if (saved) { ['flow','step','work_root','vault_dir','modelStatus','feishuStatus','feishuState'].forEach(key => { if (saved[key] !== undefined && saved[key] !== null) state[key] = saved[key]; }); if (saved.provider_status) state.modelStatus = saved.provider_status; state.modelKey = ''; const index = ['welcome','model','feishu','done'].indexOf(state.step); state.step = Math.max(fullApp ? 1 : 0, Math.min(3, index < 0 ? state.step : index)); } state.feishuState = state.feishuState || sessionStorage.getItem('wb.onboarding.feishu-state'); } catch (_) {} draw(); void notifyNativeReady(); if (state.feishuState && state.step === 2) void pollFeishu(); }
restore();
</script></body></html>"""
    return page.replace("__FULL_APP__", "true" if full_app else "false").replace(
        "__CONNECTION_PREFIX__", '"/api/settings"' if full_app else '"/api/onboarding"'
    )


__all__ = ["render_onboarding_wizard"]
