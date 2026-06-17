#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'plugins/agent-access/skills/agent-access/scripts/agent-access.mjs');
const privateToken = ['abcd', '1234', 'SECRET'].join('');
const privateUserId = ['u', '1234', '5678'].join('');
const privateEmail = ['private', '@', 'example.com'].join('');
const privatePath = ['/', 'Users', '/', 'admin', '/', '.cla', 'ude', '/', 'settings.json'].join('');
const privateWorkspace = ['cc-', 'workspace'].join('');
const tokenKey = ['tok', 'en'].join('');
const userIdKey = ['user', '_id'].join('');

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    timeout: 30000,
    maxBuffer: 1024 * 1024,
    ...options,
  });
  return result;
}

function assert(condition, message, details = {}) {
  if (!condition) {
    console.error(JSON.stringify({ ok: false, error: message, ...details }, null, 2));
    process.exit(1);
  }
}

function assertNoLeak(text, label) {
  const leaks = [
    privateToken,
    privateUserId,
    privateEmail,
    ['/', 'Users', '/', 'admin'].join(''),
    ['.cla', 'ude'].join(''),
    privateWorkspace,
  ].filter((needle) => text.includes(needle));
  assert(leaks.length === 0, `${label} leaked private markers`, { leaks, text });
}

const registry = {
  version: 'test',
  updated_at: '2026-06-17',
  entries: [
    {
      name: 'stub',
      kind: 'test',
      targets: ['stub.local'],
      command: process.execPath,
      description: 'privacy probe',
      doctor: [],
      auth: { methods: [], broker: 'none' },
      read_write: 'read-only',
      outputs: ['json'],
      source_status: 'test',
      quality: {},
    },
  ],
};
registry.entries[0].doctor = [
  process.execPath,
  '-e',
  `console.log(JSON.stringify({token:${JSON.stringify(privateToken)},user_id:${JSON.stringify(privateUserId)},path:${JSON.stringify(privatePath)}}))`,
];

const registryDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-access-registry-'));
try {
  const registryPath = path.join(registryDir, 'registry.json');
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2));
  const doctor = run(process.execPath, [cli, 'doctor', 'stub', '--run'], {
    env: {
      ...process.env,
      AGENT_ACCESS_REGISTRY: registryPath,
      AGENT_ACCESS_STATE_DIR: path.join(os.tmpdir(), 'agent-access-audit-nonexistent'),
    },
  });
  assert(doctor.status === 0, 'delegated doctor probe failed', { stdout: doctor.stdout, stderr: doctor.stderr });
  assertNoLeak(doctor.stdout + doctor.stderr, 'delegated doctor output');
} finally {
  fs.rmSync(registryDir, { recursive: true, force: true });
}

const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-access-privacy-'));
try {
  const contributionsDir = path.join(stateDir, 'contributions');
  fs.mkdirSync(contributionsDir, { recursive: true });
  fs.writeFileSync(path.join(contributionsDir, 'demo.json'), JSON.stringify({
    type: 'cli-friction',
    target: 'xhs',
    summary: `${tokenKey} ${privateToken}`,
    [tokenKey]: privateToken,
    [userIdKey]: privateUserId,
    email: privateEmail,
    path: privatePath,
  }, null, 2));
  const show = run(process.execPath, [cli, 'contributions', 'show', 'demo'], {
    env: { ...process.env, AGENT_ACCESS_STATE_DIR: stateDir },
  });
  assert(show.status === 0, 'contribution show probe failed', { stdout: show.stdout, stderr: show.stderr });
  assertNoLeak(show.stdout + show.stderr, 'contribution show output');
} finally {
  fs.rmSync(stateDir, { recursive: true, force: true });
}

console.log(JSON.stringify({ ok: true, command: 'privacy-probes' }, null, 2));
