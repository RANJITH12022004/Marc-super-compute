const BASE = 'https://api.meta.ai/v1'

export function userMessage(text) {
  return {
    type: 'message',
    role: 'user',
    content: [{ type: 'input_text', text }],
  }
}

function parseSse(buffer, onEvent) {
  const parts = buffer.split(/\r?\n\r?\n/)
  const rest = parts.pop() ?? ''
  for (const part of parts) {
    const data = part
      .split(/\r?\n/)
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.slice(5).trim())
      .join('')
    if (!data || data === '[DONE]') continue
    let parsed
    try {
      parsed = JSON.parse(data)
    } catch {
      continue
    }
    onEvent(parsed)
  }
  return rest
}

function textFromDelta(delta) {
  if (typeof delta === 'string') return delta
  if (delta && typeof delta === 'object' && typeof delta.text === 'string') return delta.text
  return ''
}

function errorMessage(payload, fallback) {
  if (!payload) return fallback
  try {
    const json = JSON.parse(payload)
    return json.error?.message || json.message || payload || fallback
  } catch {
    return payload || fallback
  }
}

function isExpiredRef(err) {
  const msg = err instanceof Error ? err.message : String(err)
  return /referenced response not found|expired/i.test(msg)
}

async function completeOnce({
  key,
  model,
  instructions,
  input,
  tools,
  effort = 'high',
  previousResponseId,
  onText,
}) {
  const body = {
    model,
    instructions,
    input,
    reasoning: { effort },
    store: true,
    stream: true,
  }
  if (tools?.length) body.tools = tools
  if (previousResponseId) body.previous_response_id = previousResponseId

  const res = await fetch(`${BASE}/responses`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${key}`,
      'content-type': 'application/json',
      accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const errText = await res.text()
    throw new Error(errorMessage(errText, `Meta API ${res.status}`))
  }

  const acc = { tools: new Map() }
  let text = ''
  let responseId
  let buffer = ''
  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  const handle = (json) => {
    const type = String(json.type || '')
    if (typeof json.response?.id === 'string') responseId = json.response.id
    if (json.error?.message) throw new Error(String(json.error.message))
    if (type === 'response.failed') {
      throw new Error(json.response?.error?.message || 'Meta response failed')
    }

    if (type === 'response.output_text.delta' || type.endsWith('.output_text.delta')) {
      const chunk = textFromDelta(json.delta) || (typeof json.text === 'string' ? json.text : '')
      if (chunk) {
        text += chunk
        onText?.(chunk)
      }
      return
    }

    if (type === 'response.output_item.added' || type === 'response.output_item.done') {
      const item = json.item || {}
      if (item.type === 'function_call' || item.type === 'tool_call') {
        const id = item.call_id || item.id
        if (!id) return
        const prev = acc.tools.get(id) || { name: '', arguments: '' }
        prev.name = item.name || prev.name
        if (item.arguments) prev.arguments = item.arguments
        acc.tools.set(id, prev)
      }
      return
    }

    if (type.includes('function_call_arguments.delta')) {
      const id = String(json.item_id || json.call_id || '')
      if (!id) return
      const prev = acc.tools.get(id) || { name: String(json.name || ''), arguments: '' }
      prev.arguments += textFromDelta(json.delta) || json.delta?.arguments || ''
      if (json.name) prev.name = String(json.name)
      acc.tools.set(id, prev)
    }

    if (type === 'response.completed' && Array.isArray(json.response?.output)) {
      for (const item of json.response.output) {
        if (item.type === 'function_call') {
          const id = item.call_id || item.id
          if (!id) continue
          acc.tools.set(id, {
            name: item.name || '',
            arguments: item.arguments || acc.tools.get(id)?.arguments || '',
          })
        }
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = parseSse(buffer, handle)
  }
  if (buffer.trim()) parseSse(`${buffer}\n\n`, handle)

  const toolCalls = [...acc.tools.entries()]
    .filter(([, v]) => v.name)
    .map(([callId, v]) => ({ callId, name: v.name, arguments: v.arguments || '{}' }))

  return { text, toolCalls, responseId }
}

export async function complete(opts) {
  try {
    return await completeOnce(opts)
  } catch (err) {
    if (opts.previousResponseId && opts.fallbackInput && isExpiredRef(err)) {
      return completeOnce({ ...opts, previousResponseId: undefined, input: opts.fallbackInput })
    }
    throw err
  }
}
