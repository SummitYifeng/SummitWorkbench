import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

const staticDir = resolve(process.argv[2] ?? 'src/summit_workbench/webapp/static');
const metaPath = join(staticDir, 'build-meta.json');
const indexPath = join(staticDir, 'index.html');

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function walk(directory) {
  const paths = [];
  for (const name of readdirSync(directory).sort()) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) paths.push(...walk(path));
    else paths.push(path);
  }
  return paths;
}

if (!existsSync(metaPath) || !existsSync(indexPath)) {
  throw new Error('static build must contain index.html and build-meta.json');
}

const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
const index = readFileSync(indexPath, 'utf8');
if (sha256(indexPath) !== meta.index_sha256) throw new Error('index.html hash mismatch');

const references = [...index.matchAll(/(?:src|href)="(\/static\/[^\"]+)"/g)].map((m) => m[1]);
for (const reference of references) {
  const path = join(staticDir, reference.slice('/static/'.length));
  if (!existsSync(path)) throw new Error(`index.html references missing asset: ${reference}`);
}

for (const [name, digest] of Object.entries(meta.assets ?? {})) {
  const path = join(staticDir, name);
  if (!existsSync(path)) throw new Error(`manifest references missing asset: ${name}`);
  if (sha256(path) !== digest) throw new Error(`asset hash mismatch: ${name}`);
}

const jsFiles = walk(join(staticDir, 'assets')).filter((path) => path.endsWith('.js'));
if (!jsFiles.some((path) => readFileSync(path, 'utf8').includes(meta.frontend_build))) {
  throw new Error('compiled JavaScript does not contain manifest frontend_build');
}

const metaFiles = walk(staticDir).filter((path) => path.endsWith('build-meta.json'));
if (metaFiles.length !== 1) throw new Error(`expected one build-meta.json, found ${metaFiles.length}`);

console.log(`Build verified: ${meta.frontend_build}`);
