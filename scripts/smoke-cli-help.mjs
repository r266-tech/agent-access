#!/usr/bin/env node

import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'plugins/agent-access/skills/agent-access/scripts/agent-access.mjs');

const result = spawnSync(process.execPath, [cli, '--help'], {
  cwd: root,
  encoding: 'utf8',
  stdio: ['ignore', 'ignore', 'pipe'],
  timeout: 30000,
});

if (result.status !== 0) {
  console.error(JSON.stringify({
    ok: false,
    command: 'smoke-cli-help',
    status: result.status,
    signal: result.signal,
    stderr: result.stderr || '',
  }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, command: 'smoke-cli-help' }, null, 2));
