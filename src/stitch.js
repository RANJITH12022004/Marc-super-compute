import fs from 'node:fs/promises'
import path from 'node:path'
import { complete, userMessage } from './meta.js'
import { AGENT_TOOLS, executeTool } from './tools.js'

const STITCH_PROMPT = `You are the Meta Muse stitcher (Wonder).
Workers already edited exclusive files. Review their summaries and remaining issues.
If something is broken across files, fix it with tools. You may edit any workspace file except .marc/runs.
If everything looks consistent, say APPROVE and list changed files.
Do not greet.`

export async function stitch({ key, root, goal, results, runDir, log, constraints = [] }) {
  const changed = new Set()
  const brief = results
    .map((r) => `## ${r.id} ${r.ok ? 'ok' : 'FAIL'} — ${r.title}\nFiles: ${(r.files || []).join(', ') || '(none)'}\n${r.summary || r.error || ''}`)
    .join('\n\n')

  const instructions = `${STITCH_PROMPT}\n\nGoal: ${goal}`
  const conversation = [userMessage(`Worker results:\n\n${brief}\n\nReview and stitch. If a worker failed, finish its allowlisted file yourself.`)]
  let input = conversation
  let previousResponseId
  let lastText = ''
  const blocked = ['.marc/runs', ...constraints]

  for (let turn = 0; turn < 8; turn += 1) {
    const step = await complete({
      key,
      model: 'muse-wonder-1.0',
      instructions,
      input,
      tools: AGENT_TOOLS,
      effort: 'high',
      previousResponseId,
      fallbackInput: conversation,
      onText: (chunk) => log(chunk),
    })
    lastText = step.text
    previousResponseId = step.responseId
    if (!step.toolCalls.length) break
    const outputs = []
    for (const call of step.toolCalls) {
      log(`\n[stitch ${call.name}] ${call.arguments.slice(0, 200)}\n`)
      const result = await executeTool(root, call.name, call.arguments, {
        allowlist: ['*'],
        constraints: blocked,
        changed,
      })
      log(`[stitch ${call.name} done] ${result.slice(0, 180)}\n`)
      conversation.push({
        type: 'function_call',
        call_id: call.callId,
        name: call.name,
        arguments: call.arguments,
      })
      const output = {
        type: 'function_call_output',
        call_id: call.callId,
        output: result.slice(0, 24_000),
      }
      conversation.push(output)
      outputs.push(output)
    }
    input = previousResponseId ? outputs : conversation
  }

  const summary = `# Run stitch

Goal: ${goal}

## Workers
${results.map((r) => `- ${r.id}: ${r.ok ? 'ok' : 'FAIL'} ${r.title} → ${(r.files || []).join(', ') || 'no files'}`).join('\n')}

## Stitcher
${lastText}

## Files touched by stitcher
${[...changed].join('\n') || '(none)'}
`
  await fs.writeFile(path.join(runDir, 'summary.md'), summary, 'utf8')
  return { text: lastText, files: [...changed], summary }
}
