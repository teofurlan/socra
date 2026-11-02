import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const jitiPath = process.env.PI_JITI_PATH;
assert.ok(jitiPath, 'Set PI_JITI_PATH to jiti/lib/jiti.mjs inside your Pi install');
const { createJiti } = await import(pathToFileURL(jitiPath).href);

const extensionPath = fileURLToPath(new URL('./extension.mjs', import.meta.url));
const jiti = createJiti(import.meta.url, { moduleCache: false, interopDefault: true });
const extension = await jiti.import(extensionPath, { default: true });

assert.equal(typeof extension, 'function', 'Default export must be an extension factory function');

const commands = new Map();
const events = new Map();
const pi = {
  registerCommand: (name, command) => commands.set(name, command),
  on: (name, handler) => events.set(name, handler),
};

await extension(pi);

assert.equal(commands.has('voice'), true, 'Command /voice must be registered');
assert.equal(events.has('session_start'), true, 'Handler session_start must be registered');
assert.equal(events.has('agent_settled'), true, 'Handler agent_settled must be registered');
assert.equal(events.has('message_end'), true, 'Handler message_end must be registered');
assert.equal(events.has('agent_start'), true, 'Handler agent_start must be registered');
assert.equal(events.has('session_shutdown'), true, 'Handler session_shutdown must be registered');
assert.equal(typeof commands.get('voice').handler, 'function', '/voice handler must be a function');

console.log('PASS: Pi-installed jiti loader imported extension and registered /voice without starting a session or child.');
