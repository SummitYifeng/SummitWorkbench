/**
 * 同步域的组合根依赖（Step 6）。
 *
 * 冲突弹层的 5 个状态变量（details/selections/preparation/message/busy）与它们的**唯一**
 * 修改者同在 ``conflict.ts``：ESM 的 import 绑定只读，把 ``let`` 放在别处会让跨模块赋值
 * 直接失败。所以本模块只承载"注入了什么"，页面状态留在产生它的域内（§4.2）。
 *
 * 依赖放在这里而不是 banner/conflict 之一，是为了让 ``conflict → banner`` 保持单向。
 */

export interface SyncDeps {
  /** 组合根的只读状态刷新（同步重试、冲突恢复成功后联动）。 */
  refreshState: () => Promise<boolean>;
  /** 实体草稿的 workspace 作用域。 */
  workspaceId: () => string | undefined;
  /** 写实体草稿（保留组合根的配额告警语义）。 */
  persistEntityDraft: <T>(entity: string, value: T) => void;
}

let syncDeps: SyncDeps | null = null;

export function setSyncDeps(deps: SyncDeps): void {
  syncDeps = deps;
}

/** 组合根尚未注入时返回 null；调用点用可选链，语义与"注入前不动作"一致。 */
export function getSyncDeps(): SyncDeps | null {
  return syncDeps;
}
