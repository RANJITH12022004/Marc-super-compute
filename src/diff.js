import fs from 'node:fs/promises'
import path from 'node:path'

export async function snapshotFiles(root, rels, destDir) {
  await fs.mkdir(destDir, { recursive: true })
  for (const rel of rels) {
    const src = path.join(root, rel)
    try {
      const data = await fs.readFile(src)
      const out = path.join(destDir, rel)
      await fs.mkdir(path.dirname(out), { recursive: true })
      await fs.writeFile(out, data)
    } catch {
      await fs.writeFile(path.join(destDir, `${rel.replaceAll('/', '__')}.missing`), '', 'utf8')
    }
  }
}

export async function fileDiff(root, baselineDir, rel) {
  let before = ''
  let after = ''
  try {
    before = await fs.readFile(path.join(baselineDir, rel), 'utf8')
  } catch {
    before = ''
  }
  try {
    after = await fs.readFile(path.join(root, rel), 'utf8')
  } catch {
    after = ''
  }
  if (before === after) return null
  return { path: rel, before, after }
}

export function unified(rel, before, after) {
  const a = before.split('\n')
  const b = after.split('\n')
  const lines = [`--- a/${rel}`, `+++ b/${rel}`, `@@ -1,${a.length} +1,${b.length} @@`]
  for (const line of a) lines.push(`-${line}`)
  for (const line of b) lines.push(`+${line}`)
  return lines.join('\n')
}
