#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'plugins/agent-access/skills/agent-access/scripts/agent-access.mjs');
const registryPath = path.join(root, 'plugins/agent-access/skills/agent-access/registry.json');
const manifestPath = path.join(root, 'plugins/agent-access/skills/agent-access/cli-manifest.json');

function run(args, options = {}) {
  return spawnSync(process.execPath, [cli, ...args], {
    cwd: root,
    encoding: 'utf8',
    timeout: 30000,
    maxBuffer: 1024 * 1024,
    ...options,
  });
}

function assert(condition, message, details = {}) {
  if (!condition) {
    console.error(JSON.stringify({ ok: false, error: message, ...details }, null, 2));
    process.exit(1);
  }
}

function parseStdout(result) {
  try {
    return JSON.parse(result.stdout || '{}');
  } catch {
    return {};
  }
}

const check = run(['check-manifest']);
assert(check.status === 0, 'packaged manifest check failed', { stdout: check.stdout, stderr: check.stderr });

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-access-probes-'));
try {
  const existing = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  existing.entries.push({
    name: 'removed-route',
    command: 'removed-route',
    aliases: [],
    command_aliases: [],
    kind: 'site',
    targets: ['removed.example'],
    description: 'synthetic stale route',
    repository: null,
    read_write: 'read-only',
    source_status: 'test',
    source_strategy: 'PUBLIC_API',
    source_contract: 'stable',
    auth_methods: [],
    planned_auth_methods: [],
    auth_broker: 'none',
    install_type: null,
    update_type: null,
    verify_flow: ['help'],
    fixture_policy: 'live-probe',
    probe_count: 1,
    safe_probe_count: 1,
    error_exit_codes: [1, 2, 66, 75, 77],
    aliases_for_discovery: ['removed-route', 'removed.example'],
  });
  const staleManifestPath = path.join(tmp, 'cli-manifest.json');
  fs.writeFileSync(staleManifestPath, `${JSON.stringify(existing, null, 2)}\n`);
  const manifestGate = run(['build-manifest', '--registry', registryPath, '--output', staleManifestPath]);
  const manifestGateJson = parseStdout(manifestGate);
  assert(manifestGate.status !== 0, 'manifest deletion gate should fail on stale removed route', {
    stdout: manifestGate.stdout,
    stderr: manifestGate.stderr,
  });
  assert(
    (manifestGateJson.findings || []).some((finding) => finding.code === 'manifest_entry_removed'),
    'manifest deletion gate did not report manifest_entry_removed',
    { stdout: manifestGate.stdout },
  );

  const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  const privateRegistryPath = path.join(tmp, 'private-registry.json');
  fs.writeFileSync(privateRegistryPath, `${JSON.stringify({
    ...registry,
    entries: [{
      ...registry.entries[0],
      name: 'private-route-should-not-ship',
      command: 'private-route-should-not-ship',
      aliases: ['private-alias-should-not-ship'],
      targets: ['private.example'],
    }],
  }, null, 2)}\n`);
  const isolatedManifestPath = path.join(tmp, 'isolated-cli-manifest.json');
  const privateEnvGate = run(['build-manifest', '--output', isolatedManifestPath, '--write'], {
    env: {
      ...process.env,
      AGENT_ACCESS_REGISTRY: privateRegistryPath,
    },
  });
  assert(privateEnvGate.status === 0, 'default build-manifest should ignore AGENT_ACCESS_REGISTRY', {
    stdout: privateEnvGate.stdout,
    stderr: privateEnvGate.stderr,
  });
  const isolatedManifest = fs.readFileSync(isolatedManifestPath, 'utf8');
  assert(
    !isolatedManifest.includes('private-route-should-not-ship') && !isolatedManifest.includes('private.example'),
    'default manifest generation leaked AGENT_ACCESS_REGISTRY content',
    { manifest: isolatedManifest },
  );

  const removedRegistryPath = path.join(tmp, 'removed-registry.json');
  const removedRegistry = {
    ...registry,
    entries: registry.entries.filter((entry) => entry.name !== 'xyz'),
  };
  fs.writeFileSync(removedRegistryPath, `${JSON.stringify(removedRegistry, null, 2)}\n`);
  const removedManifestPath = path.join(tmp, 'removed-cli-manifest.json');
  const removedWrite = run(['build-manifest', '--registry', removedRegistryPath, '--output', removedManifestPath, '--write']);
  const removedWriteJson = parseStdout(removedWrite);
  assert(removedWrite.status !== 0, 'baseline deletion gate should fail when registry and manifest both remove a route', {
    stdout: removedWrite.stdout,
    stderr: removedWrite.stderr,
  });
  assert(
    (removedWriteJson.findings || []).some((finding) => finding.code === 'manifest_baseline_entry_removed' && finding.target === 'xyz'),
    'baseline deletion gate did not report xyz removal',
    { stdout: removedWrite.stdout },
  );

  const overlayRegistryPath = path.join(tmp, 'overlay-registry.json');
  const shadow = {
    ...registry,
    entries: [
      {
        ...registry.entries[0],
        command: 'local-wechat-cli',
        description: 'synthetic local override for shadow audit',
      },
    ],
  };
  fs.writeFileSync(overlayRegistryPath, `${JSON.stringify(shadow, null, 2)}\n`);
  const overlayGate = run(['audit-overlay', '--registry', overlayRegistryPath, '--strict']);
  const overlayGateJson = parseStdout(overlayGate);
  assert(overlayGate.status !== 0, 'strict overlay audit should fail on packaged shadow', {
    stdout: overlayGate.stdout,
    stderr: overlayGate.stderr,
  });
  assert(
    (overlayGateJson.findings || []).some((finding) => finding.code === 'overlay_shadows_packaged_entry'),
    'overlay audit did not report overlay_shadows_packaged_entry',
    { stdout: overlayGate.stdout },
  );
  assert(
    !`${overlayGate.stdout}\n${overlayGate.stderr}`.includes('local-wechat-cli'),
    'overlay shadow audit leaked the local command name without --reveal-local',
    { stdout: overlayGate.stdout, stderr: overlayGate.stderr },
  );

  const unsafeManifestWrite = run(['build-manifest', '--registry', privateRegistryPath, '--write']);
  assert(unsafeManifestWrite.status !== 0, 'build-manifest --registry --write should require --output', {
    stdout: unsafeManifestWrite.stdout,
    stderr: unsafeManifestWrite.stderr,
  });
  assert(
    parseStdout(unsafeManifestWrite).error?.code === 'manifest_output_required',
    'unsafe manifest write did not report manifest_output_required',
    { stdout: unsafeManifestWrite.stdout },
  );

  const missingPrivateOverlay = path.join(os.homedir(), '.agent-access', 'missing-private-registry.json');
  const missingPrivate = run(['audit-overlay', '--registry', missingPrivateOverlay]);
  assert(missingPrivate.status !== 0, 'missing private overlay should fail', {
    stdout: missingPrivate.stdout,
    stderr: missingPrivate.stderr,
  });
  assert(
    !`${missingPrivate.stdout}\n${missingPrivate.stderr}`.includes(os.homedir()),
    'missing private overlay output leaked the home directory',
    { stdout: missingPrivate.stdout, stderr: missingPrivate.stderr },
  );
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log(JSON.stringify({ ok: true, command: 'manifest-overlay-probes' }, null, 2));
