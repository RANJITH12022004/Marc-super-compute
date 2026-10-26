import fs from 'node:fs/promises'
import path from 'node:path'
import { complete, userMessage } from './meta.js'
import { AGENT_TOOLS, executeTool, normalizeRel } from './tools.js'

const MAX_TURNS = 14
const WORKER_PROMPT = `You are a Meta Muse coding worker. You implement ONE assigned task.
Only edit files on your allowlist. Do not touch other files.
Use tools. Prefer write_file for whole-file edits. Prefer apply_patch for tiny surgical edits.
Do not use run_command to edit files.
When done, summarize what you changed in a few bullets. Do not greet.`

export async function runWorker({ key, root, task, constraints, taskDir, log }) {
  const allowlist = (task.files || []).map(normalizeRel)
  const changed = new Set()
  const instructions = `${WORKER_PROMPT}

Task id: ${task.id}
Title: ${task.title}
Allowlist:\n${allowlist.map((f) => `- ${f}`).join('\n') || '(none — read only)'}
Do not touch:\n${(constraints || []).map((f) => `- ${f}`).join('\n') || '- (none)'}

Instructions:
${task.instructions}`

  const conversation = [userMessage(`Start task ${task.id}: ${task.title}`)]
  let input = conversation
  let previousResponseId
  let lastText = ''
  const toolLog = []

  for (let turn = 0; turn < MAX_TURNS; turn += 1) {
    const step = await complete({
      key,
      model: 'muse-spark-1.3',
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
      log(`\n[tool ${call.name}] ${call.arguments.slice(0, 200)}\n`)
      const result = await executeTool(root, call.name, call.arguments, {
        allowlist,
        constraints,
        changed,
      })
      toolLog.push({ name: call.name, arguments: call.arguments, result: result.slice(0, 4000) })
      log(`[tool ${call.name} done] ${result.slice(0, 180)}\n`)
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

  const files = [...changed]
  await fs.mkdir(taskDir, { recursive: true })
  await fs.writeFile(
    path.join(taskDir, 'result.json'),
    JSON.stringify({ id: task.id, title: task.title, files, summary: lastText, toolLog }, null, 2),
    'utf8',
  )
  return { id: task.id, title: task.title, files, summary: lastText, ok: true }
}
