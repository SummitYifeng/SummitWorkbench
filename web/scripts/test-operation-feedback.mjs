import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(fileURLToPath(import.meta.url), '..', '..');
const tmp = join(root, '.operation-feedback-test-tmp');
mkdirSync(tmp, { recursive: true });
const entry = join(tmp, 'entry.mjs');
const output = join(tmp, 'bundle.mjs');
writeFileSync(entry, `
import { workspaceStore } from '../src/core/workspace-store';
import { mountOperationFeedback, publishOperationFeedback } from '../src/features/shell/operation-feedback';
export { workspaceStore, mountOperationFeedback, publishOperationFeedback };
`);

try {
  await build({ entryPoints: [entry], bundle: true, platform: 'node', format: 'esm', outfile: output });
  const rootElement = {
    hidden: true,
    textContent: '',
    children: [],
    replaceChildren(...children) { this.children = children; },
    setAttribute() {},
    appendChild(child) { this.children.push(child); },
  };
  globalThis.localStorage = (() => {
    const values = new Map();
    return {
      getItem(key) { return values.get(key) ?? null; },
      setItem(key, value) { values.set(key, value); },
      removeItem(key) { values.delete(key); },
      values,
    };
  })();
  globalThis.document = {
    getElementById(id) { return id === 'operation-notice' ? rootElement : null; },
    createElement(tag) {
      return {
        tagName: tag,
        textContent: '',
        children: [],
        dataset: {},
        appendChild(child) { this.children.push(child); },
        addEventListener() {},
      };
    },
  };
  const { workspaceStore, mountOperationFeedback, publishOperationFeedback } = await import(pathToFileURL(output).href);
  const visibleText = () => {
    const read = (node) => [node.textContent ?? '', ...(node.children ?? []).map(read)].join(' ');
    return read(rootElement);
  };

  workspaceStore.setWorkspace('workspace-a');
  publishOperationFeedback('operation-a', { ok: true, message: '甲工作区的记录' });
  assert.match(visibleText(), /甲工作区的记录/);

  workspaceStore.setWorkspace('workspace-b');
  mountOperationFeedback();
  assert.equal(rootElement.hidden, true, 'a different workspace must not display the prior receipt');
  publishOperationFeedback('operation-b', { ok: true, message: '乙工作区的记录' });
  assert.match(visibleText(), /乙工作区的记录/);
  assert.doesNotMatch(visibleText(), /甲工作区的记录/);

  workspaceStore.setWorkspace('workspace-a');
  mountOperationFeedback();
  assert.match(visibleText(), /甲工作区的记录/, 'switching back restores that workspace receipts');
  console.log('Workspace-scoped operation feedback tests passed');
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
