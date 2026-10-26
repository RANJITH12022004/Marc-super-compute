import fs from 'node:fs/promises'
import fsSync from 'node:fs'
import path from 'node:path'
import { loadMetaKey } from './key.js'
import { snapshotFiles, fileDiff, unified } from './diff.js'
import { runWorker } from './worker.js'
import { stitch } from './stitch.js'
import { normalizeRel } from './tools.js'

function assertExclusive(tasks) {
  const owner = new Map()
  const overlaps = []
  for (const task of tasks) {
    for (const raw of task.files || []) {
      const file = normalizeRel(raw)
      if (owner.has(file)) overlaps.push(`${file} claimed by ${owner.get(file)} and ${task.id}`)
      else owner.set(file, task.id)
    }
  }
  if (overlaps.length) {
    throw new Error(
      `Tasks share files. Re-break the job so each file belongs to one worker:\n- ${overlaps.join('\n- ')}`,
    )
  }
}

async function mapPool(items, limit, fn) {
  const out = new Array(items.length)
  let i = 0
  async function worker() {
    while (i < items.length) {
      const idx = i
      i += 1
      out[idx] = await fn(items[idx], idx)
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()))
  return out
}

export async function runJob({ cwd, jobPath, concurrency = 3 }) {
  const root = path.resolve(cwd)
  const absJob = path.resolve(root, jobPath)
  let raw
  try {
    raw = await fs.readFile(absJob, 'utf8')
  } catch {
    throw new Error(`No job file at ${absJob}. Copy .marc/job.example.json to .marc/job.json after Cursor plans the tasks.`)
  }
  const job = JSON.parse(raw)
  if (!job.goal || !Array.isArray(job.tasks) || job.tasks.length === 0) {
    throw new Error('job.json needs goal and tasks[]')
  }
  assertExclusive(job.tasks)

  const key = await loadMetaKey()
  const runId = new Date().toISOString().replaceAll(':', '').replaceAll('.', '-')
  const runDir = path.join(root, '.marc', 'runs', runId)
  await fs.mkdir(runDir, { recursive: true })
  await fs.writeFile(path.join(runDir, 'job.json'), JSON.stringify(job, null, 2), 'utf8')

  const allFiles = job.tasks.flatMap((t) => (t.files || []).map(normalizeRel))
  await snapshotFiles(root, allFiles, path.join(runDir, 'baseline'))

  const limit = Math.max(1, Math.min(concurrency, job.tasks.length))
  console.log(`marc-workers run ${runId}`)
  console.log(`goal: ${job.goal}`)
  console.log(`tasks: ${job.tasks.length}  parallel: ${limit}  model: muse-spark-1.3`)
  console.log('')

  const results = await mapPool(job.tasks, limit, async (task) => {
    const taskDir = path.join(runDir, task.id)
    await fs.mkdir(taskDir, { recursive: true })
    const logFile = path.join(taskDir, 'log.txt')
    const log = (chunk) => {
      process.stdout.write(chunk)
      fsSync.appendFileSync(logFile, chunk, 'utf8')
    }
    console.log(`→ worker ${task.id}: ${task.title}`)
    try {
      const result = await runWorker({
        key,
        root,
        task,
        constraints: job.constraints || [],
        taskDir,
        log,
      })
      const diffs = []
      for (const rel of result.files) {
        const d = await fileDiff(root, path.join(runDir, 'baseline'), rel)
        if (d) {
          const patch = unified(rel, d.before, d.after)
          diffs.push({ path: rel, patch })
          await fs.writeFile(path.join(taskDir, `${rel.replaceAll('/', '__')}.diff`), patch, 'utf8')
        }
      }
      await fs.writeFile(path.join(taskDir, 'patch.json'), JSON.stringify(diffs, null, 2), 'utf8')
      console.log(`✓ worker ${task.id} files: ${result.files.join(', ') || '(none)'}`)
      return result
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err)
      console.error(`✗ worker ${task.id}: ${error}`)
      await fs.writeFile(path.join(taskDir, 'error.txt'), error, 'utf8')
      return { id: task.id, title: task.title, files: [], ok: false, error }
    }
  })

  console.log('\n→ stitcher muse-wonder-1.0')
  let stitched
  try {
    stitched = await stitch({
      key,
      root,
      goal: job.goal,
      results,
      runDir,
      constraints: job.constraints || [],
      log: (chunk) => process.stdout.write(`[stitch] ${chunk}`),
    })
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    console.error(`✗ stitcher: ${error}`)
    stitched = { files: [], text: error, summary: error }
    await fs.writeFile(
      path.join(runDir, 'summary.md'),
      `# Run stitch\n\nGoal: ${job.goal}\n\nStitcher failed: ${error}\n`,
      'utf8',
    )
  }

  const report = {
    runId,
    goal: job.goal,
    results,
    stitchFiles: stitched.files,
    summaryPath: path.join(runDir, 'summary.md'),
  }
  await fs.writeFile(path.join(runDir, 'report.json'), JSON.stringify(report, null, 2), 'utf8')
  console.log(`\nsummary: ${report.summaryPath}`)
  return report
}
