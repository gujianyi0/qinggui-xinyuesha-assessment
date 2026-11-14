import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const result = spawnSync(
  process.execPath,
  ['node_modules/vite/bin/vite.js', 'build', '--mode', 'v2-local'],
  {
    stdio: 'inherit',
    env: { ...process.env, VITE_PUBLIC_MODE: '0', VITE_API_BASE: '/api' },
  },
)
if (result.status !== 0) process.exit(result.status ?? 1)
async function filesIn(folder) {
  const files = []
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const file = path.join(folder, entry.name)
    if (entry.isDirectory()) files.push(...(await filesIn(file)))
    else files.push(file.replaceAll('\\', '/'))
  }
  return files.sort()
}
const sourceFiles = [
  ...(await filesIn('src')),
  ...(await filesIn('scripts')),
  ...(await filesIn('public')),
  'index.html',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  'vite.config.ts',
  'biome.json',
  'nginx.v2-local.conf',
].sort()
const sourceHash = createHash('sha256')
for (const file of sourceFiles)
  sourceHash
    .update(file)
    .update('\0')
    .update(await readFile(file))
const artifacts = {}
for (const file of await filesIn('dist')) {
  if (file === 'dist/v2-build.json') continue
  artifacts[file.slice(5)] = createHash('sha256')
    .update(await readFile(file))
    .digest('hex')
}
const { version } = JSON.parse(await readFile('package.json', 'utf8'))
await writeFile(
  'dist/v2-build.json',
  `${JSON.stringify(
    {
      version,
      scope: 'local-internal-preview',
      buildMode: 'v2-local',
      builtAt: new Date().toISOString(),
      sourceSha256: sourceHash.digest('hex'),
      sourceFiles: sourceFiles.length,
      artifacts,
    },
    null,
    2,
  )}\n`,
)
console.log(
  `Local manifest: ${version}; ${sourceFiles.length} source files; ${Object.keys(artifacts).length} artifacts.`,
)
