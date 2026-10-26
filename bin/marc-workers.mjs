#!/usr/bin/env node
import path from 'node:path'
import { runJob } from '../src/run.js'

const [cmd, ...rest] = process.argv.slice(2)

function help() {
  console.log(`marc-workers — Cursor plans, Meta codes

Usage:
  node bin/marc-workers.mjs run [job.json]
  npm run workers

Default job file: .marc/job.json
Workers: muse-spark-1.3 (parallel)
Stitcher: muse-wonder-1.0
Key: MODEL_API_KEY or %AppData%\\Marc\\secrets.dpapi.json
`)
}

if (!cmd || cmd === '-h' || cmd === '--help') {
  help()
  process.exit(0)
}

if (cmd === 'run') {
  const jobPath = rest[0] || path.join('.marc', 'job.json')
  try {
    await runJob({ cwd: process.cwd(), jobPath })
  } catch (err) {
    console.error(err instanceof Error ? err.message : err)
    process.exit(1)
  }
} else if (cmd === 'stitch') {
  console.error('Stitch runs automatically after workers. Re-run: node bin/marc-workers.mjs run')
  process.exit(1)
} else {
  help()
  process.exit(1)
}
