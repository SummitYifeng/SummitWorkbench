/** Active workspace scope and generation lifecycle. */

export class WorkspaceStore {
  private currentId: string | null = null;
  private currentGeneration = 0;

  get workspaceId(): string | null {
    return this.currentId;
  }

  get generation(): number {
    return this.currentGeneration;
  }

  setWorkspace(workspaceId: string | null): void {
    if (this.currentId === workspaceId) return;
    this.currentId = workspaceId;
    this.currentGeneration += 1;
  }

  dispose(): void {
    this.currentId = null;
    this.currentGeneration += 1;
  }
}

export function workspaceScopedKey(namespace: string, workspaceId: string | null): string {
  return namespace + '.' + encodeURIComponent(workspaceId || 'unknown');
}

export const workspaceStore = new WorkspaceStore();
