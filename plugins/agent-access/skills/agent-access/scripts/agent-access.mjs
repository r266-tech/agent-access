#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PACKAGE_ROOT = path.resolve(ROOT, '../../../..');
const PACKAGED_REGISTRY_PATH = path.join(ROOT, 'registry.json');
const REGISTRY_PATH = process.env.AGENT_ACCESS_REGISTRY || PACKAGED_REGISTRY_PATH;
const MANIFEST_PATH = process.env.AGENT_ACCESS_MANIFEST || path.join(ROOT, 'cli-manifest.json');
const STATE_DIR = process.env.AGENT_ACCESS_STATE_DIR || path.join(os.homedir(), '.agent-access');
const AUTH_STATE_PATH = path.join(STATE_DIR, 'auth-state.json');
const CONTRIBUTIONS_DIR = path.join(STATE_DIR, 'contributions');

const NOW = () => new Date().toISOString();

function parseArgv(argv) {
  const opts = {};
  const pos = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--') {
      pos.push(...argv.slice(i + 1));
      break;
    }
    if (arg === '-h') {
      opts.help = true;
      continue;
    }
    if (!arg.startsWith('--')) {
      pos.push(arg);
      continue;
    }
    const raw = arg.slice(2);
    const eq = raw.indexOf('=');
    if (eq >= 0) {
      opts[raw.slice(0, eq)] = raw.slice(eq + 1);
      continue;
    }
    const key = raw;
    if (['help', 'human', 'json', 'run', 'secret-stdin', 'force', 'write', 'allow-removals', 'strict', 'reveal-local'].includes(key)) {
      opts[key] = true;
      continue;
    }
    const next = argv[i + 1];
    if (next && !next.startsWith('-')) {
      opts[key] = next;
      i += 1;
    } else {
      opts[key] = true;
    }
  }
  return { opts, pos };
}

const { opts, pos } = parseArgv(process.argv.slice(2));

function write(payload) {
  if (opts.human) {
    if (typeof payload === 'string') {
      console.log(payload);
      return;
    }
    console.log(JSON.stringify(payload, null, 2));
    return;
  }
  console.log(JSON.stringify(payload, null, 2));
}

function fail(code, message, nextAction = null, details = {}, exitCode = 1) {
  write({
    ok: false,
    error: {
      code,
      message,
      ...(nextAction ? { next_action: nextAction } : {}),
      ...details,
    },
  });
  process.exit(exitCode);
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (err) {
    if (err && err.code === 'ENOENT') return fallback;
    throw err;
  }
}

function writeJson(filePath, value) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(tmp, filePath);
}

function writePublicJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o644 });
  fs.renameSync(tmp, filePath);
}

function loadRegistryFrom(filePath) {
  const registry = readJson(filePath, null);
  if (!registry || !Array.isArray(registry.entries)) {
    fail('registry_invalid', `Registry is missing or invalid: ${redactedPath(filePath)}`);
  }
  return registry;
}

function loadRegistry() {
  return loadRegistryFrom(REGISTRY_PATH);
}

function manifestRegistryPath() {
  return opts.registry ? path.resolve(opts.registry) : PACKAGED_REGISTRY_PATH;
}

function loadManifestRegistry() {
  return loadRegistryFrom(manifestRegistryPath());
}

function normalize(value) {
  return String(value || '').trim().toLowerCase();
}

function findEntry(registry, name) {
  const needle = normalize(name);
  if (!needle) return null;
  return registry.entries.find((entry) => {
    const fields = [
      entry.name,
      entry.command,
      ...(entry.aliases || []),
      ...(entry.targets || []),
    ];
    return fields.some((field) => normalize(field) === needle);
  }) || registry.entries.find((entry) => {
    const fields = [
      entry.name,
      entry.command,
      ...(entry.aliases || []),
      ...(entry.targets || []),
    ];
    return fields.some((field) => normalize(field).includes(needle));
  }) || null;
}

function executableCandidates(entry) {
  const values = [entry.command, ...(entry.command_aliases || [])]
    .filter(Boolean)
    .filter((value) => /^[A-Za-z0-9._-]+$/.test(value));
  return [...new Set(values)];
}

function which(command) {
  if (!command) return null;
  const dirs = String(process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const candidates = command.includes(path.sep) ? [command] : dirs.map((dir) => path.join(dir, command));
  for (const candidate of candidates) {
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {}
  }
  return null;
}

function commandAvailability(entry) {
  return executableCandidates(entry).map((command) => ({
    command,
    path: redactedPath(which(command)),
    available: Boolean(which(command)),
  }));
}

function authCommand(entry, key) {
  const command = entry.auth?.commands?.[key];
  return Array.isArray(command) && command.length ? command : null;
}

function runnableCommand(command) {
  if (!Array.isArray(command) || command.length === 0) return null;
  const executable = which(command[0]);
  if (!executable) return null;
  return [executable, ...command.slice(1)];
}

function relPath(filePath) {
  const rel = path.relative(ROOT, filePath);
  if (!rel || rel === '') return '.';
  if (!rel.startsWith('..') && !path.isAbsolute(rel)) return rel;
  return '[outside-skill-dir]';
}

function redactedPath(filePath) {
  if (!filePath) return filePath;
  const text = String(filePath);
  if (text.startsWith(ROOT)) return relPath(text);
  const cwd = process.cwd();
  if (text === cwd) return '.';
  if (text.startsWith(`${cwd}${path.sep}`)) {
    const rel = path.relative(cwd, text);
    return rel || '.';
  }
  if (text.startsWith(STATE_DIR)) return text.replace(STATE_DIR, '$AGENT_ACCESS_STATE_DIR');
  if (text.startsWith(os.homedir())) {
    const rel = path.relative(os.homedir(), text);
    const parts = rel.split(path.sep).filter(Boolean);
    const privateHomeRoots = new Set(['cc-' + 'workspace', 'br' + 'ain', '.' + 'codex', '.' + 'claude']);
    if (parts[0] && privateHomeRoots.has(parts[0])) {
      return ['~', '[private-home-root]', ...parts.slice(1)].join('/');
    }
    return text.replace(os.homedir(), '~');
  }
  return text;
}

function commandWithDisplayArgs(command, extraArgs = [], displayArgs = extraArgs) {
  return [command[0], ...command.slice(1), ...displayArgs];
}

function runCommand(command, extraArgs = [], options = {}) {
  const displayCommand = options.displayCommand || commandWithDisplayArgs(command, extraArgs);
  const runnable = runnableCommand(command);
  if (!runnable) {
    return {
      ran: false,
      ok: false,
      reason: 'command_missing',
      command: displayCommand,
    };
  }
  const [executable, ...args] = runnable;
  const result = spawnSync(executable, [...args, ...extraArgs], {
    encoding: 'utf8',
    timeout: Number(opts.timeout || 120000),
    maxBuffer: 1024 * 1024 * 4,
    stdio: ['inherit', 'pipe', 'pipe'],
  });
  return {
    ran: true,
    command: displayCommand,
    status: result.status,
    signal: result.signal,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
    ok: result.status === 0,
  };
}

function redactAuthObject(value) {
  if (Array.isArray(value)) return value.map(redactAuthObject);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => {
      if (/^(id|uid|user_id|username|red_id|nickname|name|account|account_id|email|phone|mobile|avatar|image|url)$/i.test(key)) {
        return [key, (typeof item === 'boolean' || typeof item === 'number' || item == null) ? item : '[REDACTED]'];
      }
      if (/path|file|dir|folder|database|db|profile/i.test(key)) {
        return [key, (typeof item === 'boolean' || typeof item === 'number' || item == null) ? item : redactedPath(String(item))];
      }
      if (/password|secret|cookie|token|session|authorization|verification|qrcode|qr|payload|otp|pin/i.test(key) || /^code$/i.test(key)) {
        return [key, (typeof item === 'boolean' || typeof item === 'number' || item == null) ? item : '[REDACTED]'];
      }
      return [key, redactAuthObject(item)];
    }));
  }
  if (typeof value === 'string') return redactString(value);
  return value;
}

function sanitizeAuthDelegated(result) {
  if (!result || !result.ran) return result;
  const sanitized = { ...result };
  sanitized.command = Array.isArray(sanitized.command) ? sanitized.command.map((arg) => redactString(arg)) : sanitized.command;
  for (const stream of ['stdout', 'stderr']) {
    const text = sanitized[stream];
    if (!text) continue;
    sanitized[stream] = sanitizeOutputText(text);
  }
  return sanitized;
}

function sanitizeOutputText(text) {
  try {
    return `${JSON.stringify(redactAuthObject(JSON.parse(text)), null, 2)}\n`;
  } catch {
    return redactString(text);
  }
}

function sanitizeCommandResult(result) {
  if (!result || !result.ran) return result;
  const sanitized = { ...result };
  sanitized.command = Array.isArray(sanitized.command) ? sanitized.command.map((arg) => redactString(arg)) : sanitized.command;
  for (const stream of ['stdout', 'stderr']) {
    const text = sanitized[stream];
    if (typeof text !== 'string' || !text) continue;
    sanitized[stream] = sanitizeOutputText(text);
  }
  return sanitized;
}

function delegatedLooksAuthenticated(result) {
  if (!result?.ok) return false;
  const text = result.stdout || '';
  try {
    const parsed = JSON.parse(text);
    const flags = [
      parsed?.data?.authenticated,
      parsed?.authenticated,
      parsed?.data?.logged_in,
      parsed?.logged_in,
      parsed?.data?.credential_available,
      parsed?.credential_available,
    ];
    for (const flag of flags) {
      if (flag === true) return true;
      if (flag === false) return false;
    }
    const status = normalize(parsed?.data?.status || parsed?.status);
    if (['authenticated', 'logged_in', 'credential_available', 'credential_stored'].includes(status)) return true;
    if (['anonymous', 'unauthenticated', 'not_authenticated', 'logged_out', 'expired'].includes(status)) return false;
  } catch {
    if (/(authenticated|logged.?in)\s*[:=]\s*true|credential.*available/i.test(text)) return true;
  }
  return false;
}

function localStateLooksAuthenticated(state) {
  if (!state || typeof state !== 'object') return false;
  if (state.expires_at) {
    const expiresAt = Date.parse(state.expires_at);
    if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) return false;
  }
  if (state.authenticated === true) return true;
  if (state.authenticated === false) return false;
  const status = normalize(state.status);
  return ['authenticated', 'logged_in', 'credential_available', 'credential_stored'].includes(status);
}

function methodCommandKey(method) {
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

function preferredLoginMethod(entry) {
  if (entry.auth?.broker === 'planned') return null;
  for (const method of entry.auth?.methods || []) {
    if (authCommand(entry, methodCommandKey(method))) return method;
  }
  return (entry.auth?.methods || [])[0] || null;
}

function displaySensitiveArgs(extraArgs) {
  return extraArgs.map((arg) => {
    if (opts.phone && arg === opts.phone) return '[PHONE]';
    if (opts.code && arg === opts.code) return '[CODE]';
    return arg;
  });
}

function sitePatternRefs(entry) {
  const dir = path.join(ROOT, 'references', 'site-patterns');
  const refs = [];
  for (const target of entry.targets || []) {
    const value = normalize(target);
    if (!value.includes('.')) continue;
    const host = value.replace(/^https?:\/\//, '').split('/')[0];
    const parts = host.split('.').filter(Boolean);
    for (let i = 0; i < Math.max(1, parts.length - 1); i += 1) {
      const candidate = parts.slice(i).join('.');
      const filePath = path.join(dir, `${candidate}.md`);
      if (!refs.includes(filePath) && fs.existsSync(filePath)) refs.push(filePath);
    }
  }
  return refs;
}

function publicEntry(entry) {
  const availability = commandAvailability(entry);
  return {
    name: entry.name,
    aliases: entry.aliases || [],
    kind: entry.kind,
    targets: entry.targets || [],
    command: entry.command,
    command_available: availability.some((item) => item.available),
    read_write: entry.read_write,
    ...(entry.write_policy ? { write_policy: entry.write_policy } : {}),
    source_status: entry.source_status || 'unknown',
    auth_methods: entry.auth?.methods || [],
    planned_auth_methods: entry.auth?.planned_methods || [],
    auth_broker: entry.auth?.broker || 'unknown',
    auth_command_keys: Object.keys(entry.auth?.commands || {}),
    quality: entry.quality || {},
    description: entry.description,
  };
}

function manifestIdentity(entry) {
  return String(entry.name || entry.command || '').trim();
}

function manifestAliases(entry) {
  return [...new Set([
    entry.name,
    entry.command,
    ...(entry.aliases || []),
    ...(entry.command_aliases || []),
    ...(entry.targets || []),
  ].filter(Boolean).map((value) => String(value).trim()).filter(Boolean))];
}

function entryManifest(entry) {
  const probes = (entry.quality?.probes || entry.verify?.probes || [])
    .map(normalizeProbe)
    .filter(Boolean);
  return {
    name: entry.name,
    command: entry.command,
    aliases: entry.aliases || [],
    command_aliases: entry.command_aliases || [],
    kind: entry.kind || null,
    targets: entry.targets || [],
    description: entry.description || null,
    repository: entry.repository || null,
    read_write: entry.read_write || null,
    source_status: entry.source_status || 'unknown',
    source_strategy: entry.source_strategy || null,
    source_contract: entry.source_contract || null,
    auth_methods: entry.auth?.methods || [],
    planned_auth_methods: entry.auth?.planned_methods || [],
    auth_broker: entry.auth?.broker || 'unknown',
    install_type: entry.install?.type || null,
    update_type: entry.update?.type || null,
    verify_flow: entry.verify?.required_flow || [],
    fixture_policy: entry.verify?.fixture_policy || null,
    probe_count: probes.length,
    safe_probe_count: probes.filter((probe) => probe.safe).length,
    error_exit_codes: entry.error_contract?.exit_codes || [],
    aliases_for_discovery: manifestAliases(entry),
  };
}

function buildManifest(registry) {
  const entries = (registry.entries || [])
    .map(entryManifest)
    .sort((a, b) => a.name.localeCompare(b.name));
  return {
    version: registry.version || null,
    generated_from: 'registry.json',
    generated_at: registry.updated_at || null,
    entry_count: entries.length,
    entries,
  };
}

function stableJson(value) {
  return JSON.stringify(value, null, 2);
}

function validateManifestShape(manifest, findings) {
  const names = new Map();
  const aliases = new Map();
  for (const entry of manifest.entries || []) {
    const name = manifestIdentity(entry);
    if (!name) {
      addContractFinding(findings, 'P0', 'manifest_entry_name_missing', 'Manifest entry missing name', { entry });
      continue;
    }
    if (names.has(normalize(name))) {
      addContractFinding(findings, 'P0', 'manifest_duplicate_name', `Manifest has duplicate name: ${name}`, { target: name });
    }
    names.set(normalize(name), entry);
    for (const alias of entry.aliases_for_discovery || []) {
      const key = normalize(alias);
      if (!key) continue;
      const owner = aliases.get(key);
      if (owner && owner !== name) {
        addContractFinding(findings, 'P1', 'manifest_alias_collision', `Discovery alias ${alias} is shared by ${owner} and ${name}`, {
          alias,
          first_target: owner,
          second_target: name,
        });
      } else {
        aliases.set(key, name);
      }
    }
  }
}

function compareManifestAgainstExisting(nextManifest, existingManifest, findings) {
  if (!existingManifest) return;
  if (existingManifest.version && nextManifest.version && existingManifest.version !== nextManifest.version) {
    addContractFinding(findings, 'P1', 'manifest_version_changed', `Manifest version changed from ${existingManifest.version} to ${nextManifest.version}`, {
      previous: existingManifest.version,
      next: nextManifest.version,
    });
  }
  const previousNames = new Set((existingManifest.entries || []).map((entry) => entry.name).filter(Boolean));
  const nextNames = new Set((nextManifest.entries || []).map((entry) => entry.name).filter(Boolean));
  for (const name of previousNames) {
    if (!nextNames.has(name)) {
      addContractFinding(findings, opts['allow-removals'] ? 'P1' : 'P0', 'manifest_entry_removed', `Manifest entry removed: ${name}`, {
        target: name,
        next_action: 'Pass --allow-removals only when this deletion is intentional and reviewed.',
      });
    }
  }
}

function baselineManifestFromGit() {
  if (opts.baseline === 'none') return null;
  if (opts.baseline) return readJson(path.resolve(opts.baseline), null);
  const manifestResult = spawnSync('git', [
    '-C',
    PACKAGE_ROOT,
    'show',
    `HEAD:${path.relative(PACKAGE_ROOT, MANIFEST_PATH)}`,
  ], {
    encoding: 'utf8',
    timeout: 10000,
    maxBuffer: 1024 * 1024,
  });
  if (manifestResult.status === 0 && manifestResult.stdout) {
    try {
      return JSON.parse(manifestResult.stdout);
    } catch {
      return null;
    }
  }
  const registryResult = spawnSync('git', [
    '-C',
    PACKAGE_ROOT,
    'show',
    `HEAD:${path.relative(PACKAGE_ROOT, PACKAGED_REGISTRY_PATH)}`,
  ], {
    encoding: 'utf8',
    timeout: 10000,
    maxBuffer: 1024 * 1024,
  });
  if (registryResult.status !== 0 || !registryResult.stdout) return null;
  try {
    return buildManifest(JSON.parse(registryResult.stdout));
  } catch {
    return null;
  }
}

function compareManifestAgainstBaseline(nextManifest, baselineManifest, findings) {
  if (!baselineManifest) return;
  const baselineNames = new Set((baselineManifest.entries || []).map((entry) => entry.name).filter(Boolean));
  const nextNames = new Set((nextManifest.entries || []).map((entry) => entry.name).filter(Boolean));
  for (const name of baselineNames) {
    if (!nextNames.has(name)) {
      addContractFinding(findings, opts['allow-removals'] ? 'P1' : 'P0', 'manifest_baseline_entry_removed', `Manifest baseline entry removed: ${name}`, {
        target: name,
        next_action: 'Pass --allow-removals only when this route deletion is intentional and reviewed.',
      });
    }
  }
}

function cmdBuildManifest() {
  if (opts.registry && !opts.output) {
    fail(
      'manifest_output_required',
      'build-manifest with --registry requires an explicit --output so private or experimental registries cannot overwrite the packaged manifest.',
      'agent-access build-manifest --registry PRIVATE_REGISTRY --output /tmp/cli-manifest.json',
    );
  }
  const registry = loadManifestRegistry();
  const manifestPath = path.resolve(opts.output || MANIFEST_PATH);
  const manifest = buildManifest(registry);
  const findings = [];
  validateManifestShape(manifest, findings);
  const existing = readJson(manifestPath, null);
  compareManifestAgainstExisting(manifest, existing, findings);
  compareManifestAgainstBaseline(manifest, baselineManifestFromGit(), findings);
  const changed = !existing || stableJson(existing) !== stableJson(manifest);
  const hardFailures = findings.filter((finding) => finding.severity === 'P0');
  if (opts.write && hardFailures.length === 0) {
    writePublicJson(manifestPath, manifest);
  }
  write({
    ok: hardFailures.length === 0 && (!changed || opts.write),
    command: 'build-manifest',
    manifest_path: redactedPath(manifestPath),
    registry_path: redactedPath(manifestRegistryPath()),
    entry_count: manifest.entry_count,
    changed,
    written: Boolean(opts.write && hardFailures.length === 0),
    dry_run: !opts.write,
    findings,
    next_action: changed && !opts.write
      ? 'Review manifest changes, then rerun with --write. Use --allow-removals only for intentional reviewed deletions.'
      : null,
  });
  process.exit(hardFailures.length === 0 && (!changed || opts.write) ? 0 : 1);
}

function cmdCheckManifest() {
  const registry = loadManifestRegistry();
  const manifestPath = path.resolve(opts.file || opts.manifest || MANIFEST_PATH);
  const manifest = readJson(manifestPath, null);
  const expected = buildManifest(registry);
  const findings = [];
  if (!manifest) {
    addContractFinding(findings, 'P0', 'manifest_missing', `CLI manifest is missing: ${redactedPath(manifestPath)}`, {
      next_action: 'agent-access build-manifest --write',
    });
  } else {
    validateManifestShape(manifest, findings);
    compareManifestAgainstExisting(expected, manifest, findings);
    compareManifestAgainstBaseline(expected, baselineManifestFromGit(), findings);
    if (stableJson(manifest) !== stableJson(expected)) {
      addContractFinding(findings, 'P0', 'manifest_stale', 'CLI manifest is not the deterministic output of registry.json', {
        next_action: 'agent-access build-manifest --write',
      });
    }
  }
  write({
    ok: findings.filter((finding) => finding.severity === 'P0').length === 0,
    command: 'check-manifest',
    manifest_path: redactedPath(manifestPath),
    registry_path: redactedPath(manifestRegistryPath()),
    expected_entry_count: expected.entry_count,
    findings,
  });
  process.exit(findings.filter((finding) => finding.severity === 'P0').length === 0 ? 0 : 1);
}

function sameFilePath(a, b) {
  if (!a || !b) return false;
  try {
    return fs.realpathSync(a) === fs.realpathSync(b);
  } catch {
    return path.resolve(a) === path.resolve(b);
  }
}

function overlayRegistryCandidates() {
  const candidates = [];
  const add = (filePath, source, explicit = false) => {
    if (!filePath) return;
    const resolved = path.resolve(filePath);
    if (sameFilePath(resolved, PACKAGED_REGISTRY_PATH)) return;
    if (candidates.some((item) => sameFilePath(item.path, resolved))) return;
    candidates.push({ path: resolved, source, explicit });
  };
  add(opts.registry, '--registry', Boolean(opts.registry));
  add(process.env.AGENT_ACCESS_REGISTRY, 'AGENT_ACCESS_REGISTRY', Boolean(process.env.AGENT_ACCESS_REGISTRY));
  add(path.join(STATE_DIR, 'registry.json'), 'default-state-registry');
  add(path.join(STATE_DIR, 'registry.local.json'), 'default-state-registry');
  add(path.join(STATE_DIR, 'overlays', 'registry.json'), 'default-state-registry');
  return candidates;
}

function discoveryKeySet(entry) {
  return new Set(manifestAliases(entry).map(normalize).filter(Boolean));
}

function matchingPackagedEntries(packagedEntries, overlayEntry) {
  const overlayKeys = discoveryKeySet(overlayEntry);
  return packagedEntries.filter((packagedEntry) => {
    if (normalize(packagedEntry.name) && normalize(packagedEntry.name) === normalize(overlayEntry.name)) return true;
    const packagedKeys = discoveryKeySet(packagedEntry);
    return [...overlayKeys].some((key) => packagedKeys.has(key));
  });
}

function localOverlayLabel(entry) {
  if (opts['reveal-local']) return entry.name || entry.command || '[unknown]';
  const name = normalize(entry.name || entry.command || '');
  return name ? '[LOCAL_OVERLAY_ENTRY]' : '[unknown]';
}

function collectOverlayAudit() {
  const findings = [];
  const packaged = readJson(PACKAGED_REGISTRY_PATH, null);
  if (!packaged || !Array.isArray(packaged.entries)) {
    addContractFinding(findings, 'P0', 'packaged_registry_invalid', `Packaged registry is invalid: ${redactedPath(PACKAGED_REGISTRY_PATH)}`, {
      path: redactedPath(PACKAGED_REGISTRY_PATH),
    });
    return { candidates: [], overlays_checked: [], findings };
  }
  const packagedEntries = packaged.entries || [];
  const candidates = overlayRegistryCandidates();
  const overlaysChecked = [];
  for (const candidate of candidates) {
    const displayPath = redactedPath(candidate.path);
    if (!fs.existsSync(candidate.path)) {
      if (candidate.explicit) {
        addContractFinding(findings, 'P0', 'overlay_registry_missing', `Overlay registry is missing: ${displayPath}`, {
          path: displayPath,
          source: candidate.source,
        });
      }
      continue;
    }
    let overlay;
    try {
      overlay = readJson(candidate.path, null);
    } catch (err) {
      addContractFinding(findings, 'P0', 'overlay_registry_invalid_json', `Overlay registry is not valid JSON: ${displayPath}`, {
        path: displayPath,
        source: candidate.source,
        error: String(err?.message || err),
      });
      continue;
    }
    if (!overlay || !Array.isArray(overlay.entries)) {
      addContractFinding(findings, 'P0', 'overlay_registry_invalid', `Overlay registry is missing entries[]: ${displayPath}`, {
        path: displayPath,
        source: candidate.source,
      });
      continue;
    }
    overlaysChecked.push({
      path: redactedPath(candidate.path),
      source: candidate.source,
      version: overlay.version || null,
      entries: overlay.entries.length,
    });
    for (const overlayEntry of overlay.entries) {
      const matches = matchingPackagedEntries(packagedEntries, overlayEntry);
      if (matches.length === 0) {
        addContractFinding(findings, 'P2', 'overlay_local_entry', `Overlay entry is local-only: ${localOverlayLabel(overlayEntry)}`, {
          target: opts['reveal-local'] ? (overlayEntry.name || overlayEntry.command || null) : '[LOCAL_OVERLAY_ENTRY]',
          path: redactedPath(candidate.path),
          source: candidate.source,
          next_action: 'Keep local-only entries private unless the user explicitly asks to contribute them.',
        });
        continue;
      }
      for (const packagedEntry of matches) {
        const sameManifest = stableJson(entryManifest(packagedEntry)) === stableJson(entryManifest(overlayEntry));
        addContractFinding(findings, 'P1', 'overlay_shadows_packaged_entry', `Overlay entry shadows packaged entry ${packagedEntry.name}`, {
          target: opts['reveal-local'] ? (overlayEntry.name || overlayEntry.command || null) : '[LOCAL_OVERLAY_ENTRY]',
          packaged_target: packagedEntry.name,
          path: redactedPath(candidate.path),
          source: candidate.source,
          same_manifest: sameManifest,
          next_action: sameManifest
            ? 'Remove the overlay copy unless you intentionally pin this route.'
            : 'Inspect the overlay before trusting agent-access list/info; it overrides the packaged route.',
        });
      }
    }
  }
  return { candidates, overlays_checked: overlaysChecked, findings };
}

function cmdAuditOverlay() {
  const audit = collectOverlayAudit();
  const hardFindings = audit.findings.filter((finding) => finding.severity === 'P0' || (opts.strict && finding.severity === 'P1'));
  write({
    ok: hardFindings.length === 0,
    command: 'audit-overlay',
    packaged_registry_path: redactedPath(PACKAGED_REGISTRY_PATH),
    active_registry_path: redactedPath(REGISTRY_PATH),
    state_dir: redactedPath(STATE_DIR),
    candidates: audit.candidates.map((candidate) => ({
      path: redactedPath(candidate.path),
      source: candidate.source,
      explicit: candidate.explicit,
      exists: fs.existsSync(candidate.path),
    })),
    overlays_checked: audit.overlays_checked,
    findings: audit.findings,
  });
  process.exit(hardFindings.length === 0 ? 0 : 1);
}

function readAuthState() {
  return readJson(AUTH_STATE_PATH, { version: '0.1.0', updated_at: null, targets: {} });
}

function writeAuthState(state) {
  state.updated_at = NOW();
  writeJson(AUTH_STATE_PATH, state);
}

function profileName() {
  return String(opts.profile || 'default');
}

function targetState(state, target, profile = profileName()) {
  return state.targets?.[target]?.profiles?.[profile] || null;
}

function setTargetState(state, target, profile, value) {
  state.targets[target] ||= { profiles: {} };
  state.targets[target].profiles[profile] = value;
}

function deleteTargetState(state, target, profile = profileName()) {
  if (state.targets?.[target]?.profiles) {
    delete state.targets[target].profiles[profile];
    if (Object.keys(state.targets[target].profiles).length === 0) delete state.targets[target];
  }
}

function maskValue(value) {
  const text = String(value || '');
  if (!text) return null;
  if (text.length <= 4) return '*'.repeat(text.length);
  return `${text.slice(0, 2)}***${text.slice(-2)}`;
}

function serviceName(target, profile = profileName()) {
  return `agent-access:${target}:${profile}`;
}

function keychainAvailable() {
  return os.platform() === 'darwin' && Boolean(which('security'));
}

function storeSecretInKeychain(target, profile, account, secret) {
  void target;
  void profile;
  void account;
  void secret;
  return {
    ok: false,
    error: 'secret_store_adapter_missing',
    next_action: 'Use a target-specific auth adapter or a user-approved secret store. Agent Access core does not write secrets directly.',
  };
}

function deleteSecretFromKeychain(target, profile = profileName()) {
  if (!keychainAvailable()) {
    return { ok: false, error: 'macos_security_command_unavailable' };
  }
  const result = spawnSync('security', [
    'delete-generic-password',
    '-s', serviceName(target, profile),
  ], { encoding: 'utf8', timeout: 10000 });
  if (result.status !== 0) {
    const text = (result.stderr || result.stdout || '').trim();
    if (/could not be found|not be found/i.test(text)) return { ok: true, deleted: false };
    return { ok: false, error: text || 'keychain_delete_failed' };
  }
  return { ok: true, deleted: true };
}

async function readSecretInput() {
  if (opts.secret) {
    fail(
      'unsafe_secret_argument',
      'Do not pass secrets on argv. Use --secret-stdin or AGENT_ACCESS_SECRET.',
      'agent-access auth login TARGET --method password --account ACCOUNT --secret-stdin',
    );
  }
  if (process.env.AGENT_ACCESS_SECRET) return process.env.AGENT_ACCESS_SECRET;
  if (!opts['secret-stdin']) return null;
  return await new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data.replace(/\r?\n$/, '')));
  });
}

function help() {
  return `Agent Access

Usage:
  agent-access list [--target QUERY]
  agent-access info NAME
  agent-access install NAME [--run]
  agent-access update NAME [--run]
  agent-access doctor [NAME] [--run]
  agent-access contract --target NAME_OR_URL --task TASK
  agent-access verify NAME [--run]
  agent-access build-manifest [--write] [--registry FILE --output FILE] [--allow-removals]
  agent-access check-manifest [--registry FILE] [--baseline FILE|none]
  agent-access audit-overlay [--registry FILE] [--strict] [--reveal-local]
  agent-access validate-contracts
  agent-access audit-site-patterns
  agent-access audit-public [DIR]
  agent-access auth status [NAME] [--profile PROFILE]
  agent-access auth send-code NAME --phone PHONE [--run]
  agent-access auth login NAME --method qr|sms|browser-session|cookie-import|password|api-key [--run]
  agent-access auth refresh NAME
  agent-access auth forget NAME
  agent-access auth doctor NAME
  agent-access contributions list
  agent-access contributions new --type TYPE --target TARGET --summary SUMMARY
  agent-access contributions show DRAFT_ID
  agent-access contributions scrub DRAFT_ID
  agent-access contributions submit DRAFT_ID

JSON is the default output contract. Use --human only for ad hoc reading.`;
}

function cmdList(registry) {
  const query = opts.target || opts.query;
  const entries = registry.entries
    .filter((entry) => {
      if (!query) return true;
      const fields = [entry.name, entry.command, ...(entry.aliases || []), ...(entry.targets || [])];
      return fields.some((field) => normalize(field).includes(normalize(query)));
    })
    .map(publicEntry);
  write({
    ok: true,
    command: 'list',
    registry: {
      version: registry.version,
      updated_at: registry.updated_at,
      path: redactedPath(REGISTRY_PATH),
    },
    entries,
  });
}

function requireEntry(registry, name) {
  const entry = findEntry(registry, name);
  if (!entry) {
    fail('unknown_target', `No registry entry matched: ${name}`, 'agent-access list');
  }
  return entry;
}

function cmdInfo(registry, name) {
  const entry = requireEntry(registry, name);
  write({
    ok: true,
    command: 'info',
    entry,
    availability: commandAvailability(entry),
    auth_commands: entry.auth?.commands || {},
    references: {
      auth: relPath(path.join(ROOT, 'references', 'auth-sessions.md')),
      registry: relPath(path.join(ROOT, 'references', 'cli-registry.md')),
      site_patterns: sitePatternRefs(entry).map(relPath),
    },
  });
}

function commandEntries(section) {
  const raw = Array.isArray(section?.commands)
    ? section.commands
    : (Array.isArray(section?.command) ? [section.command] : []);
  return raw
    .map((item) => (Array.isArray(item) ? { command: item } : item))
    .filter((item) => item && Array.isArray(item.command) && item.command.length > 0);
}

function commandOsMatches(item) {
  if (!item.os) return true;
  const values = Array.isArray(item.os) ? item.os : [item.os];
  return values.includes(process.platform);
}

function publicCommandEntries(section) {
  return commandEntries(section).map((item) => ({
    command: item.command,
    ...(item.os ? { os: item.os } : {}),
    ...(item.description ? { description: item.description } : {}),
    active_on_this_platform: commandOsMatches(item),
  }));
}

function commandDisplay(command, extraArgs = []) {
  return [...command, ...extraArgs].map((arg) => String(arg));
}

function runCommandEntries(entries) {
  const results = [];
  for (const entry of entries) {
    const result = sanitizeCommandResult(runCommand(entry.command));
    results.push({
      ...(entry.description ? { description: entry.description } : {}),
      ...result,
    });
    if (!result.ok) break;
  }
  return results;
}

function cmdInstall(registry, name) {
  const entry = requireEntry(registry, name);
  const install = entry.install || null;
  const commands = commandEntries(install);
  const activeCommands = commands.filter(commandOsMatches);
  if (commands.length > 0 && !opts.run) {
    write({
      ok: true,
      command: 'install',
      dry_run: true,
      entry: publicEntry(entry),
      install: {
        ...install,
        commands: publicCommandEntries(install),
      },
      next_action: `agent-access install ${entry.name} --run`,
    });
    return;
  }
  if (commands.length > 0 && activeCommands.length === 0) {
    fail(
      'no_install_command_for_platform',
      `No install command is declared for ${entry.name} on ${process.platform}.`,
      install?.hint || `Install ${entry.command} and rerun agent-access doctor ${entry.name}`,
      { install: { ...install, commands: publicCommandEntries(install) } },
    );
  }
  if (activeCommands.length > 0) {
    const results = runCommandEntries(activeCommands);
    const ok = results.every((result) => result.ok);
    write({
      ok,
      command: 'install',
      target: entry.name,
      results,
      next_action: ok ? `agent-access doctor ${entry.name} --run` : (install?.hint || `Install ${entry.command} manually`),
    });
    process.exit(ok ? 0 : 1);
  }
  write({
    ok: false,
    command: 'install',
    error: {
      code: 'installer_not_configured',
      message: `No automatic installer is configured for ${entry.name}.`,
      next_action: entry.install?.hint || `Install ${entry.command} and rerun agent-access doctor ${entry.name}`,
    },
    entry: publicEntry(entry),
    install: entry.install || null,
  });
  process.exit(1);
}

function cmdUpdate(registry, name) {
  const entry = requireEntry(registry, name);
  const update = entry.update || null;
  const commands = commandEntries(update);
  const activeCommands = commands.filter(commandOsMatches);
  if (commands.length > 0 && !opts.run) {
    write({
      ok: true,
      command: 'update',
      dry_run: true,
      entry: publicEntry(entry),
      update: {
        ...update,
        commands: publicCommandEntries(update),
      },
      next_action: `agent-access update ${entry.name} --run`,
    });
    return;
  }
  if (commands.length > 0 && activeCommands.length === 0) {
    fail(
      'no_update_command_for_platform',
      `No update command is declared for ${entry.name} on ${process.platform}.`,
      update?.hint || `Update ${entry.command} using its upstream instructions.`,
      { update: { ...update, commands: publicCommandEntries(update) } },
    );
  }
  if (activeCommands.length > 0) {
    const results = runCommandEntries(activeCommands);
    const ok = results.every((result) => result.ok);
    write({
      ok,
      command: 'update',
      target: entry.name,
      results,
      next_action: ok ? `agent-access doctor ${entry.name} --run` : (update?.hint || `Update ${entry.command} manually`),
    });
    process.exit(ok ? 0 : 1);
  }
  write({
    ok: false,
    command: 'update',
    error: {
      code: 'updater_not_configured',
      message: `No updater is configured for ${entry.name}.`,
      next_action: update?.hint || `Update ${entry.command} using its upstream instructions.`,
    },
    entry: publicEntry(entry),
    update,
  });
  process.exit(1);
}

function runDoctor(entry) {
  const doctor = entry.doctor;
  if (!Array.isArray(doctor) || doctor.length === 0) {
    return { ran: false, reason: 'no_doctor_command' };
  }
  const executable = which(doctor[0]);
  if (!executable) {
    return { ran: false, reason: 'doctor_command_missing', command: doctor };
  }
  const result = spawnSync(executable, doctor.slice(1), {
    encoding: 'utf8',
    timeout: Number(opts.timeout || 10000),
    maxBuffer: 1024 * 1024,
  });
  return sanitizeCommandResult({
    ran: true,
    command: doctor,
    status: result.status,
    signal: result.signal,
    stdout: (result.stdout || '').slice(-8000),
    stderr: (result.stderr || '').slice(-8000),
    ok: result.status === 0,
  });
}

function cmdDoctor(registry, name) {
  const cdpHelperPath = path.join(ROOT, 'scripts', 'check-deps.mjs');
  if (!name) {
    const overlayAudit = collectOverlayAudit();
    write({
      ok: true,
      command: 'doctor',
      root: '.',
      registry_path: redactedPath(REGISTRY_PATH),
      manifest_path: redactedPath(MANIFEST_PATH),
      state_dir: redactedPath(STATE_DIR),
      node: process.version,
      entries: registry.entries.map(publicEntry),
      overlay_audit: {
        ok: overlayAudit.findings.filter((finding) => finding.severity === 'P0').length === 0,
        findings: overlayAudit.findings,
      },
      cdp_next_action: fs.existsSync(cdpHelperPath)
        ? `node ${relPath(cdpHelperPath)}`
        : 'No browser helper is bundled. Configure a browser adapter explicitly before using CDP fallback.',
    });
    return;
  }
  const entry = requireEntry(registry, name);
  const doctorRun = opts.run ? runDoctor(entry) : {
    ran: false,
    reason: 'pass --run to execute target doctor command',
    command: entry.doctor || null,
  };
  write({
    ok: true,
    command: 'doctor',
    entry: publicEntry(entry),
    availability: commandAvailability(entry),
    auth: {
      required_for: entry.auth?.required_for || [],
      methods: entry.auth?.methods || [],
      broker: entry.auth?.broker || 'unknown',
      state: redactAuthObject(targetState(readAuthState(), entry.name)),
    },
    doctor_run: doctorRun,
  });
  if (opts.run && !doctorRun.ok) process.exit(1);
}

function looksLikeUrl(value) {
  try {
    const url = new URL(value);
    return Boolean(url.hostname);
  } catch {
    return /^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:\/|$)/.test(String(value || ''));
  }
}

function hostnameFromTarget(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  try {
    return new URL(raw.includes('://') ? raw : `https://${raw}`).hostname.toLowerCase();
  } catch {
    return null;
  }
}

function scoreEntryForTarget(entry, target) {
  const needle = normalize(target);
  if (!needle) return 0;
  const host = hostnameFromTarget(target);
  const domainLikeTarget = Boolean(host && (host.includes('.') || String(target || '').includes('://')));
  const fields = [
    entry.name,
    entry.command,
    ...(entry.aliases || []),
    ...(entry.targets || []),
  ].filter(Boolean);
  let score = 0;
  for (const field of fields) {
    const text = normalize(field);
    if (!text) continue;
    if (text === needle) {
      score = Math.max(score, 100);
      continue;
    }
    if (domainLikeTarget) {
      const fieldHost = hostnameFromTarget(text) || text;
      if (fieldHost.includes('.') && (host === fieldHost || host.endsWith(`.${fieldHost}`) || fieldHost.endsWith(`.${host}`))) {
        score = Math.max(score, 90);
      }
      continue;
    }
    if (needle.length >= 3 && text.length >= 3 && (text.includes(needle) || needle.includes(text))) {
      score = Math.max(score, 50);
    }
  }
  return score;
}

function rankedEntries(registry, target) {
  return registry.entries
    .map((entry) => ({ entry, score: scoreEntryForTarget(entry, target) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.name.localeCompare(b.entry.name));
}

function sourceTierForEntry(entry) {
  return {
    strategy: entry.source_strategy || null,
    contract: entry.source_contract || null,
    note: entry.source_note || null,
  };
}

function cmdContract(registry) {
  const target = String(opts.target || pos[1] || '').trim();
  const task = String(opts.task || opts.goal || '').trim();
  if (!target) {
    fail('target_required', 'contract requires --target NAME_OR_URL.', 'agent-access contract --target xhs --task "read note comments"');
  }
  const ranked = rankedEntries(registry, target);
  const selected = ranked[0]?.entry || null;
  const targetHost = hostnameFromTarget(target);
  const targetLooksUrl = looksLikeUrl(target);
  const writeIntent = /\b(post|publish|send|delete|remove|upload|comment|reply|follow|unfollow|rate|mark|buy|order|pay|trade|control|turn\s+on|turn\s+off|apply)\b/i.test(task);
  const selectedSurface = selected
    ? {
      kind: 'registered-cli',
      entry: publicEntry(selected),
      availability: commandAvailability(selected),
      source: sourceTierForEntry(selected),
      verify: selected.verify || null,
    }
    : {
      kind: targetLooksUrl ? 'unregistered-url' : 'unregistered-target',
      source: null,
    };
  const rejectedSurfaces = [];
  if (!selected) {
    rejectedSurfaces.push({
      surface: 'registered-cli',
      reason: 'No registry entry matched target.',
    });
  }
  if (targetLooksUrl && !selected) {
    rejectedSurfaces.push({
      surface: 'browser-first',
      reason: 'Browser fallback is not first choice; inspect public/API/fetch route before CDP unless the page is session-bound or dynamic.',
    });
  }
  const nextProbe = selected
    ? `agent-access info ${selected.name} && agent-access doctor ${selected.name}${opts.run ? ' --run' : ''}`
    : (targetLooksUrl
      ? `Try primary source/API/fetch for ${targetHost || target}; enter Edge CDP only if CLI/API/fetch cannot cover the task.`
      : 'agent-access list --target QUERY');
  write({
    ok: true,
    command: 'contract',
    goal: task || null,
    target,
    target_host: targetHost,
    selected_surface: selectedSurface,
    rejected_surfaces: rejectedSurfaces,
    primary_sources_required: true,
    auth_boundary: selected
      ? {
        methods: selected.auth?.methods || [],
        planned_methods: selected.auth?.planned_methods || [],
        broker: selected.auth?.broker || 'unknown',
        local_state_only: Boolean(selected.auth?.local_state_only),
      }
      : {
        methods: [],
        broker: 'unknown',
        guidance: 'Do not ask for login until target data/action is actually blocked and login is likely to unblock it.',
      },
    write_boundary: selected
      ? {
        read_write: selected.read_write || null,
        write_intent_detected: writeIntent,
        write_policy: selected.write_policy || null,
        requires_user_approval: writeIntent || ['write-capable', 'external-action'].includes(selected.read_write),
      }
      : {
        write_intent_detected: writeIntent,
        requires_user_approval: writeIntent,
      },
    site_pattern_refs: selected ? sitePatternRefs(selected).map(relPath) : [],
    next_probe: nextProbe,
    references: [
      relPath(path.join(ROOT, 'references', 'tool-routing.md')),
      relPath(path.join(ROOT, 'references', 'source-contracts.md')),
      relPath(path.join(ROOT, 'references', 'cli-generation.md')),
    ],
  });
}

function localVerifySpecPath(target, commandName = null) {
  const safeTarget = safeSlug(target);
  const safeCommand = commandName ? safeSlug(commandName) : 'default';
  return path.join(STATE_DIR, 'sites', safeTarget, 'verify', `${safeCommand}.json`);
}

function successCriteriaMet(result, criteria = {}) {
  const checks = [];
  if (criteria.exit_code !== undefined) {
    checks.push({
      name: 'exit_code',
      ok: result.status === Number(criteria.exit_code),
      expected: Number(criteria.exit_code),
      actual: result.status,
    });
  }
  if (criteria.stdout_includes) {
    const values = Array.isArray(criteria.stdout_includes) ? criteria.stdout_includes : [criteria.stdout_includes];
    for (const value of values) {
      checks.push({
        name: 'stdout_includes',
        ok: String(result.stdout || '').includes(String(value)),
        expected: String(value),
      });
    }
  }
  if (criteria.stderr_includes) {
    const values = Array.isArray(criteria.stderr_includes) ? criteria.stderr_includes : [criteria.stderr_includes];
    for (const value of values) {
      checks.push({
        name: 'stderr_includes',
        ok: String(result.stderr || '').includes(String(value)),
        expected: String(value),
      });
    }
  }
  if (criteria.json_path) {
    const paths = Array.isArray(criteria.json_path) ? criteria.json_path : [criteria.json_path];
    let parsed;
    try {
      parsed = JSON.parse(result.stdout || '');
    } catch {
      parsed = null;
    }
    for (const rawPath of paths) {
      const parts = String(rawPath).replace(/^\$\./, '').split('.').filter(Boolean);
      let cursor = parsed;
      for (const part of parts) {
        if (cursor && typeof cursor === 'object' && part in cursor) cursor = cursor[part];
        else {
          cursor = undefined;
          break;
        }
      }
      checks.push({
        name: 'json_path',
        ok: cursor !== undefined,
        expected: rawPath,
      });
    }
  }
  if (checks.length === 0) {
    checks.push({ name: 'exit_zero', ok: result.status === 0, expected: 0, actual: result.status });
  }
  return { ok: checks.every((check) => check.ok), checks };
}

function normalizeProbe(probe, index = 0) {
  if (!probe || typeof probe !== 'object') return null;
  const command = Array.isArray(probe.command) ? probe.command : null;
  if (!command || command.length === 0) return null;
  return {
    name: probe.name || `probe-${index + 1}`,
    kind: probe.kind || 'command',
    command,
    safe: probe.safe !== false,
    requires_auth: probe.requires_auth === true,
    success_criteria: probe.success_criteria || {},
    last_verified_at: probe.last_verified_at || null,
  };
}

function runProbe(probe) {
  if (!probe.safe) {
    return {
      name: probe.name,
      ran: false,
      ok: false,
      reason: 'probe_not_marked_safe',
      command: probe.command,
    };
  }
  if (!opts.run) {
    return {
      name: probe.name,
      ran: false,
      ok: true,
      reason: 'pass --run to execute safe probe',
      command: probe.command,
      success_criteria: probe.success_criteria,
    };
  }
  const result = sanitizeCommandResult(runCommand(probe.command));
  const criteria = successCriteriaMet(result, probe.success_criteria);
  const explicitExitCode = probe.success_criteria && probe.success_criteria.exit_code !== undefined;
  return {
    name: probe.name,
    ran: result.ran,
    ok: explicitExitCode ? criteria.ok : (result.ok && criteria.ok),
    command: result.command,
    status: result.status,
    signal: result.signal,
    stdout: result.stdout,
    stderr: result.stderr,
    success_criteria: criteria,
  };
}

function localVerifySpec(targetName) {
  const commandName = opts.command || opts.probe || null;
  const specPath = opts.file
    ? path.resolve(opts.file)
    : localVerifySpecPath(targetName, commandName);
  if (!fs.existsSync(specPath)) return { specPath, spec: null };
  return { specPath, spec: readJson(specPath, null) };
}

function cmdVerify(registry, name) {
  const entry = requireEntry(registry, name);
  const registryProbes = (entry.quality?.probes || entry.verify?.probes || [])
    .map(normalizeProbe)
    .filter(Boolean);
  const { specPath, spec } = localVerifySpec(entry.name);
  const specProbes = (spec?.probes || [])
    .map(normalizeProbe)
    .filter(Boolean);
  const probes = [...registryProbes, ...specProbes];
  if (probes.length === 0) {
    write({
      ok: false,
      command: 'verify',
      target: entry.name,
      verify_contract: entry.verify || null,
      local_spec_path: redactedPath(specPath),
      results: [],
      next_action: `Create ${redactedPath(specPath)} with {"probes":[{"name":"help","command":["${entry.command || entry.name}","--help"],"safe":true}]}, or add quality.probes to registry.json.`,
    });
    process.exit(1);
  }
  const results = probes.map(runProbe);
  const ok = results.every((result) => result.ok);
  write({
    ok,
    command: 'verify',
    target: entry.name,
    dry_run: !opts.run,
    verify_contract: entry.verify || null,
    local_spec_path: redactedPath(specPath),
    probe_count: probes.length,
    results,
    next_action: opts.run ? null : `agent-access verify ${entry.name} --run`,
  });
  process.exit(ok ? 0 : 1);
}

function walkFiles(root, result = []) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (['.git', 'node_modules', '.DS_Store'].includes(entry.name)) continue;
    const filePath = path.join(root, entry.name);
    if (entry.isDirectory()) walkFiles(filePath, result);
    else if (entry.isFile()) result.push(filePath);
  }
  return result;
}

function cmdAuditPublic(dir) {
  const auditRoot = path.resolve(dir || ROOT);
  if (!fs.existsSync(auditRoot)) {
    fail('audit_root_missing', `Audit root does not exist: ${auditRoot}`);
  }
  const privateMarkers = String(process.env.AGENT_ACCESS_PRIVATE_MARKERS || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const privateWorkspacePattern = ['cc-' + 'workspace', 'br' + 'ain', '\\.' + 'codex', '\\.' + 'claude'].join('|');
  const textPatterns = [
    { code: 'absolute_user_path', re: /\/Users\/[A-Za-z0-9._-]+/ },
    { code: 'private_workspace_path', re: new RegExp(`(?:^|[~/"'\\s])(?:${privateWorkspacePattern})(?:[/"'\\s]|$)`) },
    ...privateMarkers.map((marker) => ({ code: 'private_project_marker', re: new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') })),
    { code: 'credential_like_value', re: /\b(?:password|passwd|secret|token|cookie|authorization|api[-_]?key|ck)\b\s*[:=]\s*["']?[A-Za-z0-9._~+/=-]{8,}/i },
    { code: 'bearer_value', re: /Bearer\s+[A-Za-z0-9._~+/=-]{8,}/i },
    { code: 'phone_number', re: /(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d[\d\s-]{7,}\d(?!\d)/ },
  ];
  const blockedNames = new Set([]);
  const blockedNamePatterns = [
    /(?:run|usage|telemetry|session|conversation).*\.jsonl$/i,
    /login.*\.(png|jpg|jpeg|webp)$/i,
    /qr.*\.(png|jpg|jpeg|webp)$/i,
  ];
  const blockedPathParts = ['private', 'local-v-pack'];
  const findings = [];
  for (const filePath of walkFiles(auditRoot)) {
    const rel = path.relative(auditRoot, filePath);
    const base = path.basename(filePath);
    if (blockedNames.has(base) || blockedNamePatterns.some((pattern) => pattern.test(base))) {
      findings.push({ severity: 'P0', code: 'blocked_private_artifact', path: rel, line: null, match: base });
      continue;
    }
    if (blockedPathParts.some((part) => rel.split(path.sep).includes(part))) {
      findings.push({ severity: 'P0', code: 'blocked_private_path', path: rel, line: null, match: rel });
      continue;
    }
    let content;
    try {
      const buffer = fs.readFileSync(filePath);
      if (buffer.includes(0)) {
        findings.push({ severity: 'P1', code: 'binary_file', path: rel, line: null, match: 'binary content' });
        continue;
      }
      content = buffer.toString('utf8');
    } catch (err) {
      findings.push({ severity: 'P1', code: 'unreadable_file', path: rel, line: null, match: String(err?.message || err) });
      continue;
    }
    const lines = content.split(/\r?\n/);
    lines.forEach((line, index) => {
      for (const pattern of textPatterns) {
        if (pattern.re.test(line)) {
          findings.push({
            severity: ['credential_like_value', 'bearer_value', 'phone_number'].includes(pattern.code) ? 'P0' : 'P1',
            code: pattern.code,
            path: rel,
            line: index + 1,
            match: redactString(line).slice(0, 240),
          });
        }
      }
    });
  }
  write({
    ok: findings.length === 0,
    command: 'audit-public',
    root: redactedPath(auditRoot),
    file_count: walkFiles(auditRoot).length,
    findings,
  });
  process.exit(findings.length === 0 ? 0 : 1);
}

function parseFrontmatter(content) {
  const lines = content.split(/\r?\n/);
  if (lines[0] !== '---') return { ok: false, data: {}, body: content };
  const end = lines.findIndex((line, index) => index > 0 && line === '---');
  if (end < 0) return { ok: false, data: {}, body: content };
  const data = {};
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    const value = rawValue.trim();
    if (value === '[]') data[key] = [];
    else if (value.startsWith('[') && value.endsWith(']')) {
      data[key] = value.slice(1, -1).split(',').map((item) => item.trim()).filter(Boolean);
    } else data[key] = value.replace(/^["']|["']$/g, '');
  }
  return { ok: true, data, body: lines.slice(end + 1).join('\n') };
}

function cmdAuditSitePatterns() {
  const root = path.join(ROOT, 'references', 'site-patterns');
  const findings = [];
  if (!fs.existsSync(root)) {
    findings.push({ severity: 'P0', code: 'site_patterns_missing', path: relPath(root), line: null, match: 'missing directory' });
  }
  const files = fs.existsSync(root)
    ? walkFiles(root).filter((filePath) => filePath.endsWith('.md'))
    : [];
  const sensitivePatterns = [
    { code: 'credential_like_value', re: /\b(?:password|passwd|secret|token|cookie|authorization|api[-_]?key|ck)\b\s*[:=]\s*["']?[A-Za-z0-9._~+/=-]{8,}/i },
    { code: 'bearer_value', re: /Bearer\s+[A-Za-z0-9._~+/=-]{8,}/i },
    { code: 'phone_number', re: /(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d[\d\s-]{7,}\d(?!\d)/ },
  ];
  for (const filePath of files) {
    const rel = relPath(filePath);
    const content = fs.readFileSync(filePath, 'utf8');
    const parsed = parseFrontmatter(content);
    if (!parsed.ok) {
      findings.push({ severity: 'P1', code: 'frontmatter_missing', path: rel, line: 1, match: 'expected YAML frontmatter' });
    }
    const visibility = parsed.data.visibility || null;
    if (!['local-private', 'public-safe'].includes(visibility)) {
      findings.push({ severity: 'P1', code: 'visibility_missing', path: rel, line: 1, match: 'visibility must be local-private or public-safe' });
    }
    if (!parsed.data.verified_at) {
      findings.push({ severity: 'P1', code: 'verified_at_missing', path: rel, line: 1, match: 'verified_at is required' });
    }
    if (!parsed.data.redaction_status) {
      findings.push({ severity: 'P1', code: 'redaction_status_missing', path: rel, line: 1, match: 'redaction_status is required' });
    }
    content.split(/\r?\n/).forEach((line, index) => {
      for (const pattern of sensitivePatterns) {
        if (pattern.re.test(line)) {
          findings.push({
            severity: visibility === 'public-safe' ? 'P0' : 'P1',
            code: pattern.code,
            path: rel,
            line: index + 1,
            match: redactString(line).slice(0, 240),
          });
        }
      }
    });
  }
  const hardFailures = findings.filter((finding) => finding.severity === 'P0');
  write({
    ok: hardFailures.length === 0,
    command: 'audit-site-patterns',
    root: redactedPath(root),
    file_count: files.length,
    findings,
  });
  process.exit(hardFailures.length === 0 ? 0 : 1);
}

const SOURCE_STRATEGIES = new Set([
  'PUBLIC_API',
  'COOKIE_API',
  'DOM_STATE',
  'UI_SELECTOR',
  'PAGE_FETCH',
  'INTERCEPT',
  'LOCAL_APP_DB',
  'LOCAL_APP_SCRIPT',
  'DEVICE_API',
  'EXTERNAL_CLI',
]);

const SOURCE_CONTRACTS = new Set([
  'stable',
  'visible-ui',
  'internal-unstable',
  'local-data',
  'local-control',
]);

const FIXTURE_POLICIES = new Set([
  'redacted-fixture',
  'live-probe',
  'manual-only',
]);

const VERIFY_FLOW_STEPS = new Set([
  'help',
  'doctor',
  'auth-status',
  'list',
  'search',
  'detail',
  'follow-up',
  'pagination',
  'filter',
  'error-path',
  'dry-run',
  'apply',
  'read-back',
]);

const REQUIRED_ERROR_EXIT_CODES = new Set([1, 2, 66, 75, 77]);

function addContractFinding(findings, severity, code, message, details = {}) {
  findings.push({ severity, code, message, ...details });
}

function validateReferenceContracts(findings) {
  const required = [
    {
      file: 'references/source-contracts.md',
      headings: ['## Strategy Classes', '## Required Strategy Note', '## Registry Fields', '## Promotion Gate'],
    },
    {
      file: 'references/cli-generation.md',
      headings: ['## Source Strategy Gate', '## Verify And Fixtures', '## Site Memory'],
    },
    {
      file: 'references/cli-registry.md',
      headings: ['## Verify Contract'],
    },
    {
      file: 'references/cdp-api.md',
      headings: ['## Browser Task Envelope', '## Structured Browser Envelope', '## Site Memory After Browser Discovery'],
    },
    {
      file: 'references/cli-errors.md',
      headings: ['## Exit Codes', '## Error Envelope', '## Registry Requirements'],
    },
    {
      file: 'references/site-patterns/_template.md',
      headings: ['## Scope', '## CLI Promotion', '## Redaction Notes'],
    },
    {
      file: 'references/tool-routing.md',
      headings: ['## Routing Contract'],
    },
  ];
  for (const item of required) {
    const filePath = path.join(ROOT, item.file);
    let content = '';
    try {
      content = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      addContractFinding(findings, 'P0', 'reference_missing', `${item.file} is missing`, { path: item.file });
      continue;
    }
    for (const heading of item.headings) {
      if (!content.includes(heading)) {
        addContractFinding(findings, 'P1', 'reference_heading_missing', `${item.file} missing ${heading}`, { path: item.file, heading });
      }
    }
  }
}

function validateRegistryContracts(registry, findings) {
  for (const entry of registry.entries || []) {
    const target = entry.name || '[unknown]';
    if (!entry.source_strategy || !SOURCE_STRATEGIES.has(entry.source_strategy)) {
      addContractFinding(findings, 'P0', 'invalid_source_strategy', `${target} has invalid or missing source_strategy`, {
        target,
        value: entry.source_strategy || null,
        allowed: [...SOURCE_STRATEGIES],
      });
    }
    if (!entry.source_contract || !SOURCE_CONTRACTS.has(entry.source_contract)) {
      addContractFinding(findings, 'P0', 'invalid_source_contract', `${target} has invalid or missing source_contract`, {
        target,
        value: entry.source_contract || null,
        allowed: [...SOURCE_CONTRACTS],
      });
    }
    if (!entry.source_note || typeof entry.source_note !== 'string') {
      addContractFinding(findings, 'P1', 'source_note_missing', `${target} missing source_note`, { target });
    }
    const verify = entry.verify || null;
    if (!verify || typeof verify !== 'object') {
      addContractFinding(findings, 'P0', 'verify_missing', `${target} missing verify contract`, { target });
      continue;
    }
    if (!Array.isArray(verify.required_flow) || verify.required_flow.length === 0) {
      addContractFinding(findings, 'P0', 'verify_flow_missing', `${target} verify.required_flow must be a non-empty array`, { target });
    } else {
      for (const step of verify.required_flow) {
        if (!VERIFY_FLOW_STEPS.has(step)) {
          addContractFinding(findings, 'P1', 'verify_flow_invalid_step', `${target} has invalid verify step: ${step}`, {
            target,
            step,
            allowed: [...VERIFY_FLOW_STEPS],
          });
        }
      }
    }
    if (!FIXTURE_POLICIES.has(verify.fixture_policy)) {
      addContractFinding(findings, 'P0', 'fixture_policy_invalid', `${target} has invalid verify.fixture_policy`, {
        target,
        value: verify.fixture_policy || null,
        allowed: [...FIXTURE_POLICIES],
      });
    }
    const probes = entry.quality?.probes || verify.probes || [];
    if (!Array.isArray(probes) || probes.length === 0) {
      addContractFinding(findings, 'P0', 'quality_probe_missing', `${target} missing quality.probes or verify.probes`, { target });
    } else {
      probes.forEach((probe, index) => {
        if (!probe?.name) addContractFinding(findings, 'P1', 'probe_name_missing', `${target} probe ${index + 1} missing name`, { target });
        if (!Array.isArray(probe?.command) || probe.command.length === 0) {
          addContractFinding(findings, 'P0', 'probe_command_missing', `${target} probe ${probe?.name || index + 1} missing command array`, { target });
        }
        if (probe?.safe !== true) {
          addContractFinding(findings, 'P0', 'probe_not_safe', `${target} probe ${probe?.name || index + 1} must explicitly set safe: true`, { target });
        }
      });
    }
    const errorContract = entry.error_contract || null;
    if (!errorContract || typeof errorContract !== 'object') {
      addContractFinding(findings, 'P0', 'error_contract_missing', `${target} missing error_contract`, { target });
    } else {
      const exitCodes = new Set(errorContract.exit_codes || []);
      for (const code of REQUIRED_ERROR_EXIT_CODES) {
        if (!exitCodes.has(code)) {
          addContractFinding(findings, 'P1', 'error_exit_code_missing', `${target} error_contract missing exit code ${code}`, { target, code });
        }
      }
      for (const key of ['json_error_envelope', 'next_action', 'no_sentinel_rows']) {
        if (errorContract[key] !== true) {
          addContractFinding(findings, 'P0', 'error_contract_flag_missing', `${target} error_contract.${key} must be true`, { target, key });
        }
      }
    }
    if (['write-capable', 'external-action'].includes(entry.read_write)) {
      if (!entry.write_policy || typeof entry.write_policy !== 'string') {
        addContractFinding(findings, 'P0', 'write_policy_missing', `${target} is ${entry.read_write} but missing write_policy`, { target });
      }
      const flow = new Set(verify.required_flow || []);
      if (!flow.has('dry-run') && !flow.has('apply')) {
        addContractFinding(findings, 'P0', 'write_verify_gate_missing', `${target} write route must declare dry-run or apply verification`, { target });
      }
    }
  }
}

function cmdValidateContracts(registry) {
  const findings = [];
  validateReferenceContracts(findings);
  validateRegistryContracts(registry, findings);
  write({
    ok: findings.length === 0,
    command: 'validate-contracts',
    registry: {
      version: registry.version,
      updated_at: registry.updated_at,
      path: redactedPath(REGISTRY_PATH),
      entries: Array.isArray(registry.entries) ? registry.entries.length : 0,
    },
    references_checked: [
      'references/source-contracts.md',
      'references/cli-generation.md',
      'references/cli-registry.md',
      'references/cdp-api.md',
      'references/cli-errors.md',
      'references/site-patterns/_template.md',
      'references/tool-routing.md',
    ],
    findings,
  });
  process.exit(findings.length === 0 ? 0 : 1);
}

function authStatus(registry, name) {
  const state = readAuthState();
  if (!name) {
    write({
      ok: true,
      command: 'auth status',
      state_path: redactedPath(AUTH_STATE_PATH),
      targets: Object.fromEntries(Object.entries(state.targets || {}).map(([target, value]) => [
        target,
        { profiles: Object.keys(value.profiles || {}) },
      ])),
      registry_auth: registry.entries.map((entry) => ({
        name: entry.name,
        methods: entry.auth?.methods || [],
        broker: entry.auth?.broker || 'unknown',
      })),
    });
    return;
  }
  const entry = requireEntry(registry, name);
  const statusCommand = authCommand(entry, 'status');
  const rawDelegated = statusCommand && opts.run ? runCommand(statusCommand) : null;
  const delegated = statusCommand
    ? (opts.run ? sanitizeAuthDelegated(rawDelegated) : {
      ran: false,
      reason: 'pass --run to execute delegated auth status command',
      command: statusCommand,
    })
    : null;
  const localState = targetState(state, entry.name);
  const authenticated = localStateLooksAuthenticated(localState) || delegatedLooksAuthenticated(rawDelegated);
  const loginMethod = preferredLoginMethod(entry);
  write({
    ok: true,
    command: 'auth status',
    target: entry.name,
    profile: profileName(),
    supported_methods: entry.auth?.methods || [],
    broker: entry.auth?.broker || 'unknown',
    state: redactAuthObject(localState),
    authenticated,
    delegated,
    next_action: authenticated
      ? null
      : (loginMethod
        ? `agent-access auth login ${entry.name} --method ${loginMethod}`
        : `agent-access auth doctor ${entry.name}`),
  });
}

function authSendCode(registry, name) {
  const entry = requireEntry(registry, name);
  const sendCommand = authCommand(entry, 'send_sms');
  if (!sendCommand) {
    fail(
      'sms_adapter_missing',
      `No SMS send-code adapter is registered for ${entry.name}.`,
      `agent-access auth doctor ${entry.name}`,
      { supported_methods: entry.auth?.methods || [] },
    );
  }
  if (!opts.phone) {
    fail(
      'phone_required',
      'SMS send-code delegation requires --phone.',
      `agent-access auth send-code ${entry.name} --phone PHONE --run`,
    );
  }
  const extraArgs = [];
  if (opts['area-code']) extraArgs.push('--area-code', opts['area-code']);
  extraArgs.push(opts.phone);
  const displayArgs = displaySensitiveArgs(extraArgs);
  if (!opts.run) {
    write({
      ok: true,
      command: 'auth send-code',
      target: entry.name,
      profile: profileName(),
      delegated: {
        ran: false,
        reason: 'pass --run to send SMS code',
        command: commandWithDisplayArgs(sendCommand, extraArgs, displayArgs),
      },
      next_action: `agent-access auth send-code ${entry.name} --phone PHONE --run`,
    });
    return;
  }
  const delegated = sanitizeAuthDelegated(runCommand(sendCommand, extraArgs, {
    displayCommand: commandWithDisplayArgs(sendCommand, extraArgs, displayArgs),
  }));
  write({
    ok: delegated.ok,
    command: 'auth send-code',
    target: entry.name,
    profile: profileName(),
    delegated,
    next_action: delegated.ok
      ? `agent-access auth login ${entry.name} --method sms --phone PHONE --code CODE --run`
      : `agent-access auth doctor ${entry.name}`,
  });
  process.exit(delegated.ok ? 0 : 1);
}

async function authLogin(registry, name) {
  const entry = requireEntry(registry, name);
  const method = String(opts.method || '').trim();
  if (!method) {
    const loginMethod = preferredLoginMethod(entry);
    fail(
      'method_required',
      'Missing --method.',
      loginMethod ? `agent-access auth login ${entry.name} --method ${loginMethod}` : `agent-access auth doctor ${entry.name}`,
    );
  }
  const supported = entry.auth?.methods || [];
  if (supported.length && !supported.includes(method)) {
    fail('unsupported_auth_method', `${entry.name} does not declare auth method: ${method}`, `agent-access info ${entry.name}`, { supported_methods: supported });
  }

  const delegatedCommand = authCommand(entry, methodCommandKey(method));
  if (delegatedCommand) {
    if (method === 'cookie-import') {
      write({
        ok: true,
        command: 'auth login',
        target: entry.name,
        profile: profileName(),
        method,
        delegated: {
          ran: false,
          reason: 'cookie import requires secret stdin; Agent Access will not echo or collect cookies',
          command: [...delegatedCommand, '< cookies.json'],
        },
        next_action: `${delegatedCommand.join(' ')} < REDACTED_COOKIE_FILE`,
      });
      return;
    }
    const displayArgs = [];
    if (method === 'sms') {
      if (opts['area-code']) displayArgs.push('--area-code', opts['area-code']);
      displayArgs.push('[PHONE]', '[CODE]');
    }
    if (!opts.run) {
      write({
        ok: true,
        command: 'auth login',
        target: entry.name,
        profile: profileName(),
        method,
        delegated: {
          ran: false,
          reason: 'pass --run to execute delegated login command',
          command: [...delegatedCommand, ...displayArgs],
        },
        next_action: `agent-access auth login ${entry.name} --method ${method} --run`,
      });
      return;
    }
    const extraArgs = [];
    const runDisplayArgs = [];
    if (method === 'sms') {
      if (!opts.phone || !opts.code) {
        fail(
          'sms_phone_code_required',
          'SMS login delegation requires --phone and --code.',
          `agent-access auth login ${entry.name} --method sms --phone PHONE --code CODE --run`,
        );
      }
      if (opts['area-code']) extraArgs.push('--area-code', opts['area-code']);
      extraArgs.push(opts.phone, opts.code);
      runDisplayArgs.push(...displaySensitiveArgs(extraArgs));
    }
    const delegated = sanitizeAuthDelegated(runCommand(delegatedCommand, extraArgs, {
      displayCommand: commandWithDisplayArgs(delegatedCommand, extraArgs, runDisplayArgs),
    }));
    write({
      ok: delegated.ok,
      command: 'auth login',
      target: entry.name,
      profile: profileName(),
      method,
      delegated,
      next_action: delegated.ok ? `agent-access auth status ${entry.name} --run` : `agent-access auth doctor ${entry.name}`,
    });
    process.exit(delegated.ok ? 0 : 1);
  }

  if (['password', 'api-key'].includes(method)) {
    const account = String(opts.account || opts.profile || 'default');
    const secret = await readSecretInput();
    if (!secret) {
      fail(
        'secret_required',
        `${method} login requires a secret from stdin or AGENT_ACCESS_SECRET.`,
        `agent-access auth login ${entry.name} --method ${method} --account ACCOUNT --secret-stdin`,
      );
    }
    const stored = storeSecretInKeychain(entry.name, profileName(), account, secret);
    if (!stored.ok) {
      fail('secret_store_failed', 'Could not store secret in OS keychain.', null, stored);
    }
    const state = readAuthState();
    setTargetState(state, entry.name, profileName(), {
      target: entry.name,
      profile: profileName(),
      method,
      status: 'credential_stored',
      account_label: opts['account-label'] || maskValue(account),
      secret_ref: stored.ref,
      last_verified_at: null,
      updated_at: NOW(),
      expires_at: null,
      refresh_supported: false,
      next_action: `${entry.command || entry.name} auth doctor || agent-access auth doctor ${entry.name}`,
    });
    writeAuthState(state);
    write({
      ok: true,
      command: 'auth login',
      target: entry.name,
      profile: profileName(),
      method,
      status: 'credential_stored',
      secret_ref: stored.ref,
      next_action: `${entry.command || entry.name} auth doctor || agent-access auth doctor ${entry.name}`,
    });
    return;
  }

  fail(
    'auth_adapter_missing',
    `Agent Access core has no ${method} adapter for ${entry.name} yet. This should live in the companion CLI or a target-specific adapter.`,
    `${entry.command || entry.name} auth login --method ${method} || implement the adapter and register it in registry.json`,
    {
      target: entry.name,
      method,
      supported_methods: supported,
      reference: relPath(path.join(ROOT, 'references', 'auth-sessions.md')),
    },
  );
}

function authRefresh(registry, name) {
  const entry = requireEntry(registry, name);
  const state = readAuthState();
  const current = targetState(state, entry.name);
  if (!current) {
    const loginMethod = preferredLoginMethod(entry);
    fail(
      'auth_state_missing',
      `No auth state for ${entry.name}.`,
      loginMethod ? `agent-access auth login ${entry.name} --method ${loginMethod}` : `agent-access auth doctor ${entry.name}`,
    );
  }
  fail(
    'refresh_adapter_missing',
    `No refresh adapter is registered for ${entry.name}.`,
    `${entry.command || entry.name} auth refresh || add an Agent Access auth adapter`,
    { state: redactAuthObject(current) },
  );
}

function authForget(registry, name) {
  const entry = requireEntry(registry, name);
  const state = readAuthState();
  const current = targetState(state, entry.name);
  const keychain = deleteSecretFromKeychain(entry.name);
  deleteTargetState(state, entry.name);
  writeAuthState(state);
  write({
    ok: true,
    command: 'auth forget',
    target: entry.name,
    profile: profileName(),
    had_state: Boolean(current),
    keychain,
  });
}

function authDoctor(registry, name) {
  const entry = requireEntry(registry, name);
  const loginMethod = preferredLoginMethod(entry);
  const nextActions = [];
  if (loginMethod) nextActions.push(`agent-access auth login ${entry.name} --method ${loginMethod}`);
  if (entry.auth?.broker === 'planned') {
    nextActions.push('Auth broker is planned for this target; use the target CLI docs or implement/register an adapter before relying on Agent Access auth.');
  }
  if (entry.auth?.commands?.status) nextActions.push(entry.auth.commands.status.join(' '));
  if (entry.doctor && runnableCommand(entry.doctor)) nextActions.push(entry.doctor.join(' '));
  write({
    ok: true,
    command: 'auth doctor',
    target: entry.name,
    profile: profileName(),
    keychain_available: keychainAvailable(),
    supported_methods: entry.auth?.methods || [],
    broker: entry.auth?.broker || 'unknown',
    delegated_commands: entry.auth?.commands || {},
    state_path: redactedPath(AUTH_STATE_PATH),
    state: redactAuthObject(targetState(readAuthState(), entry.name)),
    next_actions: nextActions,
  });
}

function contributionFiles() {
  try {
    return fs.readdirSync(CONTRIBUTIONS_DIR)
      .filter((name) => name.endsWith('.json'))
      .map((name) => path.join(CONTRIBUTIONS_DIR, name))
      .sort();
  } catch (err) {
    if (err && err.code === 'ENOENT') return [];
    throw err;
  }
}

function draftId(filePath) {
  return path.basename(filePath).replace(/\.json$/, '');
}

function redactedSummary(value) {
  return value ? redactString(value) : null;
}

function findDraft(id) {
  const files = contributionFiles();
  return files.find((filePath) => draftId(filePath) === id)
    || files.find((filePath) => draftId(filePath).startsWith(id))
    || null;
}

function safeSlug(text) {
  return String(text || 'draft')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'draft';
}

function contributionsList() {
  const drafts = contributionFiles().map((filePath) => {
    const draft = readJson(filePath, {});
    return {
      id: draftId(filePath),
      path: redactedPath(filePath),
      type: draft.type || null,
      target: draft.target || null,
      created_at: draft.created_at || null,
      updated_at: draft.updated_at || null,
      summary: redactedSummary(draft.summary || draft.proposed_patch_summary),
      privacy_review: draft.privacy_review || null,
    };
  });
  write({ ok: true, command: 'contributions list', contributions_dir: redactedPath(CONTRIBUTIONS_DIR), drafts });
}

function contributionsNew() {
  const type = String(opts.type || '').trim();
  const target = String(opts.target || '').trim();
  const summary = String(opts.summary || '').trim();
  if (!type || !target || !summary) {
    fail('draft_fields_required', 'Need --type, --target, and --summary.', 'agent-access contributions new --type cli-friction --target xhs --summary "..."');
  }
  ensureDir(CONTRIBUTIONS_DIR);
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+$/, '').replace('T', '-');
  const filePath = path.join(CONTRIBUTIONS_DIR, `${stamp}-${safeSlug(type)}-${safeSlug(target)}.json`);
  const draft = {
    version: '0.1.0',
    id: draftId(filePath),
    type,
    target,
    summary,
    created_at: NOW(),
    updated_at: NOW(),
    task_goal: opts.goal || null,
    commands_run: [],
    files_changed: [],
    evidence: [],
    reproduction_steps: [],
    proposed_patch_summary: summary,
    privacy_review: {
      redacted: false,
      user_confirmed_for_submit: false,
      notes: 'Local draft only. Scrub and ask the user before any upload.',
    },
  };
  writeJson(filePath, draft);
  write({ ok: true, command: 'contributions new', draft: deepRedact(draft) });
}

function contributionsShow(id) {
  const filePath = findDraft(id);
  if (!filePath) fail('draft_not_found', `No contribution draft matched: ${id}`, 'agent-access contributions list');
  const draft = deepRedact(readJson(filePath, {}));
  const residual = residualPrivacyFindings(draft);
  write({
    ok: residual.length === 0,
    command: 'contributions show',
    path: redactedPath(filePath),
    redacted: true,
    residual_findings: residual,
    draft,
    next_action: residual.length === 0
      ? `agent-access contributions scrub ${draftId(filePath)}`
      : 'Manual review required before sharing this draft.',
  });
  if (residual.length > 0) process.exit(1);
}

function redactString(value) {
  return String(value)
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [REDACTED]')
    .replace(/(["']?(?:authorization|cookie|set-cookie|x-api-key|api[-_]?key|token|session|password|passwd|secret|verification|otp|pin|user[_-]?id|account[_-]?id|username|account|code)["']?\s*:\s*)["'][^"']+["']/gi, '$1"[REDACTED]"')
    .replace(/(["']?(?:authorization|cookie|set-cookie|x-api-key|api[-_]?key|token|session|password|passwd|secret|verification|otp|pin|user[_-]?id|account[_-]?id|username|account|code)["']?\s*:\s*)[A-Za-z0-9._~+/=-]{4,}/gi, '$1[REDACTED]')
    .replace(/(authorization|cookie|set-cookie|x-api-key|api[-_]?key|token|session|password|passwd|secret|verification|otp|pin|user[_-]?id|account[_-]?id|username|account|code)[=:]\s*[^&\s"']+/gi, '$1=[REDACTED]')
    .replace(/\b(authorization|cookie|set-cookie|x-api-key|api[-_]?key|token|session|password|passwd|secret|verification|otp|pin|user[_-]?id|account[_-]?id|username|account|code)\b\s+["']?[A-Za-z0-9._~+/=-]{8,}["']?/gi, '$1 [REDACTED]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[REDACTED_EMAIL]')
    .replace(/(?<!\d)1[3-9]\d{9}(?!\d)/g, '[REDACTED_PHONE]')
    .replace(/\b(phone|mobile|tel|telephone)\b\s*[:=]?\s*\+?\d[\d -]{7,}\d/gi, '$1 [REDACTED_PHONE]')
    .replace(/([?&](?:token|session|auth|code|key|user_id|account_id)=)[^&\s"']+/gi, '$1[REDACTED]')
    .replace(/\/Users\/[A-Za-z0-9._-]+\/(?:cc-workspace|brain|\.codex|\.claude)(?=\/|[\s"'`]|$)/g, '~/$PRIVATE_PATH')
    .replace(/\/Users\/\[REDACTED_USER\]\/(?:cc-workspace|brain|\.codex|\.claude)(?=\/|[\s"'`]|$)/g, '~/$PRIVATE_PATH')
    .replace(/\/Users\/[A-Za-z0-9._-]+/g, '/Users/[REDACTED_USER]')
    .replace(/(?:^|[\s"'`])~\/(?:\.codex|\.claude|cc-workspace|brain)(?=\/|[\s"'`]|$)/g, (match) => match[0] === '~' ? '~/$PRIVATE_PATH' : `${match[0]}~/$PRIVATE_PATH`);
}

function deepRedact(value) {
  if (Array.isArray(value)) return value.map(deepRedact);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => {
      if (/password|secret|cookie|token|session|authorization|verification|phone|email|qr|otp|pin/i.test(key) || /^(code|user_id|uid|account|account_id|username)$/i.test(key)) {
        return [key, '[REDACTED]'];
      }
      return [key, deepRedact(item)];
    }));
  }
  if (typeof value === 'string') return redactString(value);
  return value;
}

function residualPrivacyFindings(value) {
  const text = JSON.stringify(value);
  const checks = [
    ['absolute_user_path', /\/Users\/(?!\[REDACTED_USER\])[^/"'\s]+/],
    ['private_workspace_path', /(?:^|[~/"'\s])(?:cc-workspace|brain|\.codex|\.claude)(?:[/"'\s]|$)/],
    ['credential_like_value', /\b(?:password|passwd|secret|token|cookie|authorization|api[-_]?key|session|verification|otp|pin|code)\b\s*[:=]\s*["']?(?!\[REDACTED\])[A-Za-z0-9._~+/=-]{4,}/i],
    ['phone_number', /(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d[\d\s-]{7,}\d(?!\d)/],
    ['email', /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i],
  ];
  return checks
    .filter(([, re]) => re.test(text))
    .map(([code]) => code);
}

function contributionsScrub(id) {
  const filePath = findDraft(id);
  if (!filePath) fail('draft_not_found', `No contribution draft matched: ${id}`, 'agent-access contributions list');
  const draft = deepRedact(readJson(filePath, {}));
  const residual = residualPrivacyFindings(draft);
  draft.privacy_review ||= {};
  draft.privacy_review.redacted = residual.length === 0;
  draft.privacy_review.redaction_status = residual.length === 0 ? 'clean' : 'needs_manual_review';
  draft.privacy_review.residual_findings = residual;
  draft.privacy_review.scrubbed_at = NOW();
  draft.privacy_review.user_confirmed_for_submit = false;
  const outPath = filePath.replace(/\.json$/, '.scrubbed.json');
  writeJson(outPath, draft);
  write({
    ok: residual.length === 0,
    command: 'contributions scrub',
    source_path: redactedPath(filePath),
    scrubbed_path: redactedPath(outPath),
    draft,
  });
  if (residual.length > 0) process.exit(1);
}

function contributionsSubmit(id) {
  const filePath = findDraft(id);
  if (!filePath) fail('draft_not_found', `No contribution draft matched: ${id}`, 'agent-access contributions list');
  fail(
    'explicit_confirmation_required',
    'Agent Access never uploads contribution drafts automatically.',
    `Review and scrub ${redactedPath(filePath)}, then ask the user before opening a PR or producing a patch.`,
    { draft_path: redactedPath(filePath) },
  );
}

async function main() {
  if (opts.help || pos.length === 0 || pos[0] === 'help') {
    console.log(help());
    return;
  }

  const [command, subcommand, target] = pos;

  if (command === 'audit-overlay') return cmdAuditOverlay();
  if (command === 'audit-site-patterns') return cmdAuditSitePatterns();
  if (command === 'audit-public') return cmdAuditPublic(subcommand);
  if (command === 'build-manifest') return cmdBuildManifest();
  if (command === 'check-manifest') return cmdCheckManifest();

  const registry = loadRegistry();

  if (command === 'list') return cmdList(registry);
  if (command === 'info') return cmdInfo(registry, subcommand);
  if (command === 'install') return cmdInstall(registry, subcommand);
  if (command === 'update') return cmdUpdate(registry, subcommand);
  if (command === 'doctor') return cmdDoctor(registry, subcommand);
  if (command === 'contract') return cmdContract(registry);
  if (command === 'verify') return cmdVerify(registry, subcommand);
  if (command === 'validate-contracts') return cmdValidateContracts(registry);

  if (command === 'auth') {
    if (subcommand === 'status') return authStatus(registry, target);
    if (subcommand === 'send-code') return authSendCode(registry, target);
    if (subcommand === 'login') return await authLogin(registry, target);
    if (subcommand === 'refresh') return authRefresh(registry, target);
    if (subcommand === 'forget') return authForget(registry, target);
    if (subcommand === 'doctor') return authDoctor(registry, target);
    fail('unknown_auth_command', `Unknown auth command: ${subcommand || ''}`, 'agent-access auth status');
  }

  if (command === 'contributions') {
    if (subcommand === 'list') return contributionsList();
    if (subcommand === 'new') return contributionsNew();
    if (subcommand === 'show') return contributionsShow(target);
    if (subcommand === 'scrub') return contributionsScrub(target);
    if (subcommand === 'submit') return contributionsSubmit(target);
    fail('unknown_contributions_command', `Unknown contributions command: ${subcommand || ''}`, 'agent-access contributions list');
  }

  fail('unknown_command', `Unknown command: ${command}`, 'agent-access help');
}

await main();
