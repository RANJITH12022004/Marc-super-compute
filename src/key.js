import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { spawn } from 'node:child_process'

const secretsFile = path.join(os.homedir(), 'AppData', 'Roaming', 'Marc', 'secrets.dpapi.json')

function runPs(script) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      'powershell.exe',
      ['-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { windowsHide: true },
    )
    let out = ''
    let err = ''
    child.stdout.on('data', (d) => (out += d.toString()))
    child.stderr.on('data', (d) => (err += d.toString()))
    child.on('close', (code) => {
      if (code !== 0) reject(new Error(err || `powershell exited ${code}`))
      else resolve(out.trim())
    })
  })
}

async function dpapiUnprotect(b64) {
  const script = `
    Add-Type -AssemblyName System.Security
    $prot = [Convert]::FromBase64String('${b64}')
    $plain = [System.Security.Cryptography.ProtectedData]::Unprotect($prot, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Text.Encoding]::UTF8.GetString($plain)
  `
  return runPs(script)
}

export async function loadMetaKey() {
  const env = process.env.MODEL_API_KEY || process.env.META_API_KEY
  if (env && env.trim()) return env.trim()
  try {
    const raw = JSON.parse(await fs.readFile(secretsFile, 'utf8'))
    if (raw.meta) return (await dpapiUnprotect(raw.meta)).trim()
  } catch {
    /* none saved */
  }
  throw new Error(
    'No Meta API key. Set MODEL_API_KEY or save a key in %AppData%\\Marc\\secrets.dpapi.json',
  )
}
