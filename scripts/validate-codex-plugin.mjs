#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

function readJson(rel) {
  return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const plugin = readJson('plugins/agent-access/.codex-plugin/plugin.json');
assert(plugin.name === 'agent-access', 'plugin name must be agent-access');
assert(plugin.skills === './skills/', 'plugin skills path must be ./skills/');
assert(fs.existsSync(path.join(root, 'plugins/agent-access/skills/agent-access/SKILL.md')), 'missing skill SKILL.md');
assert(fs.existsSync(path.join(root, 'plugins/agent-access/skills/agent-access/scripts/agent-access.mjs')), 'missing agent-access CLI helper');
const retiredShim = ['web', 'access'].join('-') + '.mjs';
assert(!fs.existsSync(path.join(root, 'plugins/agent-access/skills/agent-access/scripts', retiredShim)), 'retired compatibility shim must not exist');

const marketplace = readJson('.agents/plugins/marketplace.json');
assert(marketplace.name === 'agent-access', 'marketplace name must be agent-access');
assert(Array.isArray(marketplace.plugins) && marketplace.plugins.length === 1, 'marketplace must expose one plugin');
assert(marketplace.plugins[0].source.path === './plugins/agent-access', 'marketplace path must point to plugin');
assert(marketplace.plugins[0].policy.installation === 'AVAILABLE', 'marketplace installation must be AVAILABLE');

const registry = readJson('plugins/agent-access/skills/agent-access/registry.json');
const registryExample = readJson('plugins/agent-access/skills/agent-access/registry.example.json');
const manifest = readJson('plugins/agent-access/skills/agent-access/cli-manifest.json');
assert(JSON.stringify(registry) === JSON.stringify(registryExample), 'registry and registry.example must match');
assert(Array.isArray(registry.entries) && registry.entries.length > 0, 'registry must include entries');
assert(manifest.generated_from === 'registry.json', 'manifest must be generated from registry.json');
assert(manifest.version === registry.version, 'manifest version must match registry version');
assert(manifest.entry_count === registry.entries.length, 'manifest entry_count must match registry entries');
assert(
  JSON.stringify((manifest.entries || []).map((entry) => entry.name).sort()) === JSON.stringify(registry.entries.map((entry) => entry.name).sort()),
  'manifest entries must match registry entry names',
);

function authCommandKey(method) {
  if (method === 'qr') return 'login_qr';
  if (method === 'sms') return 'login_sms';
  if (method === 'cookie-import') return 'login_cookie_import';
  if (method === 'browser-session') return 'login_browser_session';
  if (method === 'oauth') return 'login_oauth';
  if (method === 'device-code') return 'login_device_code';
  if (method === 'api-key') return 'login_api_key';
  if (method === 'password') return 'login_password';
  return `login_${String(method).replace(/[^A-Za-z0-9]+/g, '_')}`;
}

for (const entry of registry.entries) {
  assert(entry.name, 'registry entry missing name');
  assert(entry.command, `registry entry ${entry.name} missing command`);
  assert(entry.source_status, `registry entry ${entry.name} missing source_status`);
  assert(entry.source_strategy, `registry entry ${entry.name} missing source_strategy`);
  assert(entry.source_contract, `registry entry ${entry.name} missing source_contract`);
  assert(entry.source_note, `registry entry ${entry.name} missing source_note`);
  assert(entry.verify && Array.isArray(entry.verify.required_flow) && entry.verify.required_flow.length > 0, `registry entry ${entry.name} missing verify.required_flow`);
  assert(entry.verify.fixture_policy, `registry entry ${entry.name} missing verify.fixture_policy`);
  assert(Array.isArray(entry.quality?.probes) && entry.quality.probes.length > 0, `registry entry ${entry.name} missing quality.probes`);
  assert(entry.error_contract?.json_error_envelope === true, `registry entry ${entry.name} missing JSON error contract`);
  assert(entry.error_contract?.next_action === true, `registry entry ${entry.name} missing error next_action contract`);
  assert(entry.error_contract?.no_sentinel_rows === true, `registry entry ${entry.name} missing no sentinel rows contract`);
  const commands = entry.auth?.commands || {};
  const sessionSourceMethods = new Set(['local-app-session']);
  for (const method of entry.auth?.methods || []) {
    if (sessionSourceMethods.has(method)) continue;
    assert(commands[authCommandKey(method)], `active auth method ${entry.name}:${method} must register ${authCommandKey(method)} or move to planned_methods`);
  }
}

console.log(JSON.stringify({ ok: true, command: 'validate-codex-plugin' }, null, 2));
