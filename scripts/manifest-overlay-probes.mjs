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

  const list = run(['list']);
  const listJson = parseStdout(list);
  assert(list.status === 0, 'list should include install contracts', {
    stdout: list.stdout,
    stderr: list.stderr,
  });
  const listEntries = new Map((listJson.entries || []).map((entry) => [entry.name, entry]));
  assert(
    listEntries.get('wechat-cli')?.install?.state === 'installable',
    'promoted wechat-cli route should be listed as installable',
    { stdout: list.stdout },
  );
  assert(
    listEntries.get('pmkt')?.install?.state === 'installable' && listEntries.get('pmkt')?.install?.bundled === true,
    'bundled pmkt route should be listed as installable',
    { stdout: list.stdout },
  );

  const info = run(['info', 'pmkt']);
  const infoJson = parseStdout(info);
  assert(info.status === 0, 'info should include install contract', {
    stdout: info.stdout,
    stderr: info.stderr,
  });
  assert(
    infoJson.entry?.install?.state === 'installable' && infoJson.entry?.install?.bundled === true,
    'info output should expose entry.install.state for bundled routes',
    { stdout: info.stdout },
  );

  const bundledRun = run(['run', 'pmkt', '--', '--help']);
  assert(bundledRun.status === 0, 'bundled pmkt route should run without PATH shim install', {
    stdout: bundledRun.stdout,
    stderr: bundledRun.stderr,
  });

  const bundledClobHelp = run(['run', 'pmkt', '--', 'clob', '--help']);
  assert(bundledClobHelp.status === 0, 'bundled pmkt subcommand help should run', {
    stdout: bundledClobHelp.stdout,
    stderr: bundledClobHelp.stderr,
  });
  assert(
    bundledClobHelp.stdout.includes('order book for a token') && !bundledClobHelp.stdout.includes('[REDACTED]'),
    'agent-access run should preserve normal bundled CLI stdout',
    { stdout: bundledClobHelp.stdout },
  );

  const bundledInstall = run(['install', 'pmkt']);
  const bundledInstallJson = parseStdout(bundledInstall);
  assert(bundledInstall.status === 0 && bundledInstallJson.dry_run === true, 'bundled pmkt install should dry-run', {
    stdout: bundledInstall.stdout,
    stderr: bundledInstall.stderr,
  });

  const bundledBinDir = path.join(tmp, 'bin');
  const bundledInstallRun = run(['install', 'pmkt', '--run', '--bin-dir', bundledBinDir]);
  const bundledInstallRunJson = parseStdout(bundledInstallRun);
  assert(bundledInstallRun.status === 0, 'bundled pmkt install --run should create a shim', {
    stdout: bundledInstallRun.stdout,
    stderr: bundledInstallRun.stderr,
  });
  assert(
    fs.existsSync(path.join(bundledBinDir, 'pmkt')) && (bundledInstallRunJson.shims || []).length === 1,
    'bundled pmkt shim was not created',
    { stdout: bundledInstallRun.stdout },
  );

  const bundledPathEnv = {
    ...process.env,
    PATH: '/usr/bin:/bin',
  };
  const bundledAuth = run(['auth', 'status', 'dp', '--run'], { env: bundledPathEnv });
  const bundledAuthJson = parseStdout(bundledAuth);
  assert(bundledAuth.status === 0, 'bundled auth status should not require PATH shims', {
    stdout: bundledAuth.stdout,
    stderr: bundledAuth.stderr,
  });
  assert(
    bundledAuthJson.delegated?.reason !== 'command_missing',
    'bundled auth status fell back to PATH and missed bundled CLI',
    { stdout: bundledAuth.stdout },
  );

  const dpAuthStatus = run(['run', 'dp', '--', 'auth', 'status']);
  assert(dpAuthStatus.status === 0, 'bundled dp auth status should run', {
    stdout: dpAuthStatus.stdout,
    stderr: dpAuthStatus.stderr,
  });
  assert(
    !`${dpAuthStatus.stdout}\n${dpAuthStatus.stderr}`.includes(os.homedir()),
    'bundled dp auth status leaked the home directory',
    { stdout: dpAuthStatus.stdout, stderr: dpAuthStatus.stderr },
  );

  const bundledUpdateRun = run(['update', 'pmkt', '--run']);
  assert(bundledUpdateRun.status !== 0, 'bundled update --run should not claim to update the plugin', {
    stdout: bundledUpdateRun.stdout,
    stderr: bundledUpdateRun.stderr,
  });
  assert(
    parseStdout(bundledUpdateRun).error?.code === 'plugin_upgrade_required',
    'bundled update --run did not report plugin_upgrade_required',
    { stdout: bundledUpdateRun.stdout },
  );

  const brokenPromotedRegistryPath = path.join(tmp, 'broken-promoted-registry.json');
  fs.writeFileSync(brokenPromotedRegistryPath, `${JSON.stringify({
    ...registry,
    entries: registry.entries.map((entry) => (entry.name === 'pmkt'
      ? {
        ...entry,
        source_status: 'public-source',
        install: { type: 'source-pending', hint: 'synthetic invalid promoted route' },
        bundle: undefined,
      }
      : entry)),
  }, null, 2)}\n`);
  const brokenPromoted = run(['validate-contracts'], {
    env: {
      ...process.env,
      AGENT_ACCESS_REGISTRY: brokenPromotedRegistryPath,
    },
  });
  const brokenPromotedJson = parseStdout(brokenPromoted);
  assert(brokenPromoted.status !== 0, 'promoted route without installer should fail validate-contracts', {
    stdout: brokenPromoted.stdout,
    stderr: brokenPromoted.stderr,
  });
  assert(
    (brokenPromotedJson.findings || []).some((finding) => finding.code === 'promoted_install_source_pending' && finding.target === 'pmkt'),
    'promoted route without installer did not report promoted_install_source_pending',
    { stdout: brokenPromoted.stdout },
  );

  const doctorlessRegistryPath = path.join(tmp, 'doctorless-registry.json');
  fs.writeFileSync(doctorlessRegistryPath, `${JSON.stringify({
    ...registry,
    entries: registry.entries.map((entry) => (entry.name === 'wechat-cli'
      ? { ...entry, doctor: [] }
      : entry)),
  }, null, 2)}\n`);
  const doctorlessList = run(['list', '--target', 'wechat-cli'], {
    env: {
      ...process.env,
      AGENT_ACCESS_REGISTRY: doctorlessRegistryPath,
    },
  });
  const doctorlessListJson = parseStdout(doctorlessList);
  assert(doctorlessList.status === 0, 'doctorless promoted route list should still render', {
    stdout: doctorlessList.stdout,
    stderr: doctorlessList.stderr,
  });
  assert(
    doctorlessListJson.entries?.[0]?.install?.state === 'manual-or-unknown',
    'promoted route without doctor must not be exposed as installable',
    { stdout: doctorlessList.stdout },
  );

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
