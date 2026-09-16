import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const WEB_ROOT = resolve(SCRIPT_PATH, '..', '..');
const REPO_ROOT = resolve(WEB_ROOT, '..');
const STATIC_DIR = join(REPO_ROOT, 'src', 'summit_workbench', 'webapp', 'static');

export function computeSourceHash(entries) {
  const hash = createHash('sha256');
  for (const entry of [...entries].sort((a, b) => a.path.localeCompare(b.path))) {
    hash.update(entry.path);
    hash.update('\0');
    hash.update(entry.content);
    hash.update('\0');
  }
  return hash.digest('hex');
}

export function makeBuildIdentity({ sourceHash, builtAt, gitRevision }) {
  const date = builtAt.slice(0, 10).replaceAll('-', '.');
  return {
    frontendBuild: `v${date}-${gitRevision}-${sourceHash.slice(0, 8)}`,
    gitRevision,
    sourceHash,
    builtAt,
  };
}

function walkFiles(directory) {
  const result = [];
  for (const name of readdirSync(directory).sort()) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) result.push(...walkFiles(path));
    else result.push(path);
  }
  return result;
}

function sourceEntries() {
  const paths = walkFiles(join(WEB_ROOT, 'src'));
  for (const name of ['package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json']) {
    const path = join(WEB_ROOT, name);
    if (existsSync(path)) paths.push(path);
  }
  return paths.map((path) => ({
    path: relative(REPO_ROOT, path).replaceAll('\\', '/'),
    content: readFileSync(path),
  }));
}

function gitOutput(args, fallback) {
  try {
    return execFileSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8' }).trim() || fallback;
  } catch {
    return fallback;
  }
}

function run(command, args) {
  execFileSync(command, args, { cwd: WEB_ROOT, stdio: 'inherit' });
}

function writeBuildMeta(identity) {
  const assets = {};
  for (const path of walkFiles(join(STATIC_DIR, 'assets'))) {
    const name = relative(STATIC_DIR, path).replaceAll('\\', '/');
    assets[name] = createHash('sha256').update(readFileSync(path)).digest('hex');
  }
  const index = readFileSync(join(STATIC_DIR, 'index.html'));
  const meta = {
    schema_version: 1,
    product_id: 'com.summitworkbench.panel',
    frontend_build: identity.frontendBuild,
    git_revision: identity.gitRevision,
    source_hash: identity.sourceHash,
    built_at: identity.builtAt,
    index_sha256: createHash('sha256').update(index).digest('hex'),
    assets,
  };
  writeFileSync(join(STATIC_DIR, 'build-meta.json'), `${JSON.stringify(meta, null, 2)}\n`);
}

export function build() {
  const builtAt = new Date().toISOString();
  const sourceHash = computeSourceHash(sourceEntries());
  const identity = makeBuildIdentity({
    sourceHash,
    builtAt,
    gitRevision: gitOutput(['rev-parse', '--short', 'HEAD'], 'nogit'),
  });
  const env = {
    ...process.env,
    WB_FRONTEND_BUILD: identity.frontendBuild,
    WB_BUILD_TIME: identity.builtAt,
  };
  execFileSync(join(WEB_ROOT, 'node_modules', '.bin', 'tsc'), ['--noEmit'], {
    cwd: WEB_ROOT,
    stdio: 'inherit',
    env,
  });
  execFileSync(join(WEB_ROOT, 'node_modules', '.bin', 'vite'), ['build'], {
    cwd: WEB_ROOT,
    stdio: 'inherit',
    env,
  });
  writeBuildMeta(identity);
  return identity;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === pathToFileURL(SCRIPT_PATH).href) {
  build();
}
