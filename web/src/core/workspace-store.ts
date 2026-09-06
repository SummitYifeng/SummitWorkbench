/** Active workspace scope and subscription lifecycle. */

export type WorkspaceListener = (workspaceId: string | null) => void;

export class WorkspaceStore {
  private currentId: string | null = null;
  private readonly listeners = new Set<WorkspaceListener>();

  get workspaceId(): string | null {
    return this.currentId;
  }

  setWorkspace(workspaceId: string | null): void {
    if (this.currentId === workspaceId) return;
    this.currentId = workspaceId;
    for (const listener of this.listeners) listener(workspaceId);
  }

  subscribe(listener: WorkspaceListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  dispose(): void {
    this.listeners.clear();
    this.currentId = null;
  }
}

export function workspaceScopedKey(namespace: string, workspaceId: string | null): string {
  return namespace + '.' + encodeURIComponent(workspaceId || 'unknown');
}

export const workspaceStore = new WorkspaceStore();
