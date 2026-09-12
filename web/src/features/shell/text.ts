import { MAX_TEXT_CHARS } from '../../core/text';
import { toast } from './toast';

/**
 * 长文本提交前拦截：后端对捕捉/日志/产物正文设了 100,000 字符上限，
 * 直接发送只会得到笼统的 422。这里提前说明原因与当前长度，避免用户以为"保存失败"。
 *
 * 归 shell 而不是 ``core/text``：它需要 ``toast``（L1），而 ``core/*`` 是 L0、不得 import
 * features（§4.1 硬规则 4）。蓝图 §3.1 把它列在 ``core/text.ts``，那条在本仓库分层下不成立。
 */
export function rejectOversizeText(text: string): boolean {
  if (text.length <= MAX_TEXT_CHARS) return false;
  toast('内容超过 10 万字上限（当前 ' + text.length + ' 字），请拆分后重试', 'err');
  return true;
}
