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

console.log(JSON.stringify({ ok: true, command: 'validate-codex-plugin' }, null, 2));
