import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import ts from 'typescript'

const root = path.resolve('src')
const failures = []
let checked = 0
async function walk(folder) {
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const file = path.join(folder, entry.name)
    if (entry.isDirectory()) {
      await walk(file)
      continue
    }
    if (!/\.tsx?$/.test(file)) continue
    checked++
    const name = path.relative(root, file).replaceAll('\\', '/')
    if (!/^[a-z0-9-]+(?:\.test)?\.tsx?$/.test(entry.name))
      failures.push(`${name}: expected kebab-case`)
    const source = ts.createSourceFile(
      file,
      await readFile(file, 'utf8'),
      ts.ScriptTarget.Latest,
      true,
      file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
    )
    const owner = /^features\/([^/]+)\//.exec(name)?.[1]
    function visit(node) {
      if (
        ts.isImportDeclaration(node) &&
        ts.isStringLiteral(node.moduleSpecifier)
      ) {
        const spec = node.moduleSpecifier.text
        const target = spec.startsWith('@/')
          ? spec.slice(2)
          : spec.startsWith('.')
            ? path
                .relative(root, path.resolve(path.dirname(file), spec))
                .replaceAll('\\', '/')
            : null
        const feature = target && /^features\/([^/]+)(.*)$/.exec(target)
        if (
          feature &&
          feature[1] !== owner &&
          feature[2] !== '' &&
          feature[2] !== '/index'
        )
          failures.push(`${name}: private Feature import ${spec}`)
        if (feature && !owner && !name.startsWith('app/'))
          failures.push(`${name}: shared module imports Feature ${spec}`)
      }
      if (node.kind === ts.SyntaxKind.AnyKeyword)
        failures.push(`${name}: explicit any`)
      if (
        (ts.isFunctionDeclaration(node) || ts.isArrowFunction(node)) &&
        node.parameters.length > 3
      )
        failures.push(
          `${name}: use an options object for more than three parameters`,
        )
      ts.forEachChild(node, visit)
    }
    visit(source)
  }
}
await walk(root)
if (failures.length) {
  console.error([...new Set(failures)].join('\n'))
  process.exitCode = 1
} else
  console.log(
    `Architecture: ${checked} TypeScript files; Feature boundaries, naming, any and argument counts passed.`,
  )
