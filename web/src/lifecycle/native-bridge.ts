export interface NativeClientReady {
  type: 'clientReady';
  clientBuild: string;
  serverInstance: string;
}

export type NativeMessage = NativeClientReady | { type: 'quit' } | { type: 'restartService' } | { type: 'copyDiagnostics' } | { type: 'openLogDirectory' } | {
  type: 'openExternal';
  url: string;
} | {
  type: 'saveTextFile';
  filename: string;
  content: string;
};

interface NativeHandler {
  postMessage(message: NativeMessage): void;
}

interface WebKitWindow extends Window {
  webkit?: { messageHandlers?: { wbLifecycle?: NativeHandler } };
}

export function isNativeShell(): boolean {
  return Boolean((window as WebKitWindow).webkit?.messageHandlers?.wbLifecycle);
}

export function sendNativeMessage(message: NativeMessage): boolean {
  const handler = (window as WebKitWindow).webkit?.messageHandlers?.wbLifecycle;
  if (!handler) return false;
  try {
    handler.postMessage(message);
    return true;
  } catch {
    return false;
  }
}

export function notifyClientReady(clientBuild: string, serverInstance: string): void {
  sendNativeMessage({ type: 'clientReady', clientBuild, serverInstance });
}
