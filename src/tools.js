import fs from 'node:fs/promises'
import fsSync from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'

const SKIP = new Set(['node_modules', '.git', 'dist', 'target', '.next', '.marc'])
const MAX_READ = 400_000

export const AGENT_TOOLS = [
  {
    type: 'function',
    name: 'list_dir',
    description: 'List files under a workspace-relative path.',
    parameters: {
      type: 'object',
      properties: { path: { type: 'string' } },
    },
  },
  {
    type: 'function',
    name: 'read_file',
    description: 'Read a UTF-8 text file from the workspace.',
    parameters: {
      type: 'object',
      properties: { path: { type: 'string' } },
      required: ['path'],
    },
  },
  {
    type: 'function',
    name: 'write_file',
    description: 'Create or overwrite a UTF-8 file. Path must be in this worker allowlist.',
    parameters: {
      type: 'object',
      properties: { path: { type: 'string' }, content: { type: 'string' } },
      required: ['path', 'content'],
    },
  },
  {
    type: 'function',
    name: 'apply_patch',
    description: 'Apply a unified diff to an allowlisted file.',
    parameters: {
      type: 'object',
      properties: { path: { type: 'string' }, patch: { type: 'string' } },
      required: ['path', 'patch'],
    },
  },
  {
    type: 'function',
    name: 'grep',
    description: 'Search workspace file contents (case-insensitive).',
    parameters: {
      type: 'object',
      properties: { query: { type: 'string' }, glob: { type: 'string' } },
      required: ['query'],
    },
  },
  {
    type: 'function',
    name: 'glob',
    description: 'Find files by glob, e.g. **/*.js',
    parameters: {
      type: 'object',
      properties: { pattern: { type: 'string' } },
      required: ['pattern'],
    },
  },
  {
    type: 'function',
    name: 'run_command',
    description: 'Run PowerShell with cwd = workspace root. Do not leave the workspace.',
    parameters: {
      type: 'object',
      properties: { command: { type: 'string' } },
      required: ['command'],
    },
  },
]

export function normalizeRel(rel) {
  return String(rel || '')
    .replaceAll('\\', '/')
    .replace(/^\.\//, '')
    .replace(/^\/+/, '')
}

function assertInWorkspace(root, rel) {
  const resolvedRoot = path.resolve(root)
  const resolved = path.resolve(resolvedRoot, rel)
  const parent = path.relative(resolvedRoot, resolved)
  if (parent.startsWith('..') || path.isAbsolute(parent)) {
    throw new Error(`Path is outside the workspace: ${rel}`)
  }
  return resolved
}

export function isAllowed(rel, allowlist) {
  const n = normalizeRel(rel)
  if (!allowlist?.length) return false
  if (allowlist.some((rule) => rule === '*' || rule === '**')) return true
  return allowlist.some((rule) => {
    const r = normalizeRel(rule)
    if (r.endsWith('/')) return n === r.slice(0, -1) || n.startsWith(r)
    return n === r || n.startsWith(`${r}/`)
  })
}

function blocked(rel, constraints) {
  const n = normalizeRel(rel)
  return (constraints || []).some((c) => n === normalizeRel(c) || n.startsWith(`${normalizeRel(c)}/`))
}

export function applyUnifiedDiff(original, patch) {
  const hunks = [...patch.matchAll(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$/gm)]
  if (!hunks.length) throw new Error('No unified-diff hunks found')
  const lines = original.replaceAll('\r\n', '\n').replaceAll('\r', '\n').split('\n')
  let offset = 0
  hunks.forEach((hunk, i) => {
    const start = Number(hunk[1]) - 1
    const oldCount = hunk[2] === undefined ? 1 : Number(hunk[2])
    const next = hunks[i + 1]
    const body = patch.slice(hunk.index + hunk[0].length, next ? next.index : undefined)
    const replacement = []
    for (const line of body.split('\n')) {
      if (line.startsWith('+')) replacement.push(line.slice(1))
      else if (line.startsWith('-')) continue
      else if (line.startsWith('\\') || line.startsWith('@@') || line.startsWith('diff') || line.startsWith('---') || line.startsWith('+++')) {
        continue
      } else if (line.startsWith(' ')) replacement.push(line.slice(1))
      else if (line === '') continue
    }
    const idx = start + offset
    lines.splice(idx, oldCount, ...replacement)
    offset += replacement.length - oldCount
  })
  return lines.join('\n')
}

export async function executeTool(root, name, rawArgs, { allowlist, constraints, changed }) {
  let args = {}
  try {
    args = JSON.parse(rawArgs || '{}')
  } catch {
    return `Invalid JSON arguments: ${rawArgs}`
  }
  const rel = normalizeRel(args.path || args.rel || '')
  try {
    if (name === 'list_dir') {
      const abs = rel ? assertInWorkspace(root, rel) : path.resolve(root)
      const entries = await fs.readdir(abs, { withFileTypes: true })
      return entries
        .filter((e) => !SKIP.has(e.name) && !e.name.startsWith('.'))
        .map((e) => `${e.isDirectory() ? 'dir' : 'file'} ${rel ? `${rel}/${e.name}` : e.name}`)
        .join('\n') || '(empty)'
    }
    if (name === 'read_file') {
      const abs = assertInWorkspace(root, rel)
      const stat = await fs.stat(abs)
      if (stat.size > MAX_READ) return `File too large (${stat.size} bytes)`
      return await fs.readFile(abs, 'utf8')
    }
    if (name === 'write_file' || name === 'apply_patch') {
      if (blocked(rel, constraints)) return `Blocked by constraints: ${rel}`
      if (!isAllowed(rel, allowlist)) return `Not on this worker allowlist: ${rel}`
      const abs = assertInWorkspace(root, rel)
      await fs.mkdir(path.dirname(abs), { recursive: true })
      if (name === 'write_file') {
        await fs.writeFile(abs, String(args.content ?? ''), 'utf8')
        changed.add(rel)
        return `Wrote ${rel}`
      }
      const original = fsSync.existsSync(abs) ? await fs.readFile(abs, 'utf8') : ''
      const next = applyUnifiedDiff(original, String(args.patch ?? ''))
      await fs.writeFile(abs, next, 'utf8')
      changed.add(rel)
      return `Patched ${rel}`
    }
    if (name === 'grep') {
      const hits = []
      async function walk(dir, prefix = '') {
        if (hits.length > 80) return
        const entries = await fs.readdir(dir, { withFileTypes: true })
        for (const entry of entries) {
          if (SKIP.has(entry.name) || entry.name.startsWith('.')) continue
          const childRel = prefix ? `${prefix}/${entry.name}` : entry.name
          const abs = path.join(dir, entry.name)
          if (entry.isDirectory()) await walk(abs, childRel)
          else {
            try {
              const text = await fs.readFile(abs, 'utf8')
              text.split(/\r?\n/).forEach((line, i) => {
                if (hits.length > 80) return
                if (line.toLowerCase().includes(String(args.query).toLowerCase())) {
                  hits.push(`${childRel}:${i + 1}: ${line.slice(0, 200)}`)
                }
              })
            } catch {
              /* skip */
            }
          }
        }
      }
      await walk(root)
      return hits.join('\n') || 'No matches'
    }
    if (name === 'glob') {
      const needle = String(args.pattern || '').replaceAll('**/', '').replaceAll('*', '')
      const files = []
      async function walk(dir, prefix = '') {
        if (files.length > 200) return
        const entries = await fs.readdir(dir, { withFileTypes: true })
        for (const entry of entries) {
          if (SKIP.has(entry.name) || entry.name.startsWith('.')) continue
          const childRel = prefix ? `${prefix}/${entry.name}` : entry.name
          if (entry.isDirectory()) await walk(path.join(dir, entry.name), childRel)
          else if (!needle || childRel.includes(needle) || childRel.endsWith(needle)) files.push(childRel)
        }
      }
      await walk(root)
      return files.join('\n') || 'No files'
    }
    if (name === 'run_command') {
      const command = String(args.command || '')
      const result = await new Promise((resolve) => {
        const child = spawn('powershell.exe', ['-NoProfile', '-Command', command], {
          cwd: root,
          windowsHide: true,
        })
        let stdout = ''
        let stderr = ''
        const timer = setTimeout(() => child.kill(), 30_000)
        child.stdout.on('data', (d) => {
          stdout += d.toString()
          if (stdout.length > 80_000) child.kill()
        })
        child.stderr.on('data', (d) => (stderr += d.toString()))
        child.on('close', (code) => {
          clearTimeout(timer)
          resolve({ code, stdout: stdout.slice(0, 80_000), stderr: stderr.slice(0, 20_000) })
        })
      })
      return `exit ${result.code}\n${result.stdout}\n${result.stderr}`
    }
    return `Unknown tool ${name}`
  } catch (err) {
    return `Tool error: ${err instanceof Error ? err.message : String(err)}`
  }
}
