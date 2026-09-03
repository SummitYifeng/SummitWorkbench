type MutationIdleHandler = (targetBuild: string) => Promise<void> | void;

let mutationCount = 0;
let pendingReloadBuild: string | null = null;
let mutationIdleHandler: MutationIdleHandler | null = null;

export function isMutationInFlight(): boolean {
  return mutationCount > 0;
}

export function setMutationIdleHandler(handler: MutationIdleHandler): void {
  mutationIdleHandler = handler;
}

export function deferReloadUntilMutationsComplete(targetBuild: string): void {
  pendingReloadBuild = targetBuild;
  if (mutationCount === 0) void flushPendingReload();
}

export async function mutation<T>(work: () => Promise<T>): Promise<T> {
  mutationCount += 1;
  try {
    return await work();
  } finally {
    mutationCount -= 1;
    if (mutationCount === 0) await flushPendingReload();
  }
}

async function flushPendingReload(): Promise<void> {
  if (!pendingReloadBuild || !mutationIdleHandler) return;
  const targetBuild = pendingReloadBuild;
  pendingReloadBuild = null;
  await mutationIdleHandler(targetBuild);
}
