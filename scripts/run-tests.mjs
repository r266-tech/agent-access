#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = process.cwd();
const cli = path.join(root, 'plugins/agent-access/skills/agent-access/scripts/agent-access.mjs');
const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-access-test-state-'));

const env = { ...process.env };
delete env.AGENT_ACCESS_REGISTRY;
delete env.AGENT_ACCESS_MANIFEST;
env.AGENT_ACCESS_STATE_DIR = stateDir;

const steps = [
  [process.execPath, ['--check', cli]],
  [cli, ['--help'], { stdout: 'ignore' }],
  [process.execPath, [cli, 'check-manifest']],
  [process.execPath, [cli, 'validate-contracts']],
  [process.execPath, [cli, 'audit-site-patterns']],
  [process.execPath, [cli, 'audit-overlay']],
  [process.execPath, [cli, 'audit-public', '.']],
  [process.execPath, ['scripts/validate-codex-plugin.mjs']],
  [process.execPath, ['scripts/privacy-probes.mjs']],
  [process.execPath, ['scripts/manifest-overlay-probes.mjs']],
];

try {
  for (const [command, args, options = {}] of steps) {
    const result = spawnSync(command, args, {
      cwd: root,
      env,
      encoding: 'utf8',
      stdio: [
        'inherit',
        options.stdout === 'ignore' ? 'ignore' : 'pipe',
        'pipe',
      ],
      timeout: 120000,
      maxBuffer: 1024 * 1024 * 8,
    });
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    if (result.status !== 0) process.exit(result.status || 1);
  }
} finally {
  fs.rmSync(stateDir, { recursive: true, force: true });
}
