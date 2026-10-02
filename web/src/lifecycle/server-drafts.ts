export type DraftApi = <T>(url: string, init?: RequestInit) => Promise<T>;

export async function clearServerDraft(api: DraftApi, type: string, id: string): Promise<void> {
  const key = type + ':' + id;
  const result = await api<{ ok: boolean; deleted?: boolean }>(
    '/api/drafts/' + encodeURIComponent(key),
    { method: 'DELETE' },
  );
  if (result.ok) {
    window.dispatchEvent(new CustomEvent('swb:draft-cleared', { detail: { type, id } }));
  }
}
