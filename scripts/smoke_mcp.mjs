// MCP smoke test over stdio, no dependencies.
//
//   node scripts/smoke_mcp.mjs <command> [args...]
//
// Starts the given MCP server command, completes initialize + tools/list, then
// runs one tiny scan with the smallest model ("light"). If the model has to be
// downloaded first it polls until the download finishes. Exits 0 on success.
import { spawn } from 'node:child_process';

const [command, ...args] = process.argv.slice(2);
if (!command) { console.error('usage: node smoke_mcp.mjs <command> [args...]'); process.exit(2); }
const TIMEOUT_MS = Number(process.env.SMOKE_TIMEOUT_MS || 1200000);
const MODEL = process.env.SMOKE_MODEL || 'light';
const TEXT = 'Furthermore, the platform provides a seamless experience for modern teams. I do not love the price, though.';

const child = spawn(command, args, { stdio: ['pipe', 'pipe', 'inherit'], shell: process.platform === 'win32' && /\.cmd$/i.test(command) });
const pending = new Map();
let buffer = '', nextId = 1;
child.stdout.on('data', (chunk) => {
  buffer += chunk.toString('utf8');
  let nl;
  while ((nl = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, nl).trim(); buffer = buffer.slice(nl + 1);
    if (!line) continue;
    let msg; try { msg = JSON.parse(line); } catch { fail('non-JSON on stdout: ' + line.slice(0, 200)); }
    if (msg.id != null && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  }
});
child.on('exit', (code) => { if (code !== null && code !== 0) fail('server exited with code ' + code); });
const timer = setTimeout(() => fail('timed out after ' + TIMEOUT_MS + ' ms'), TIMEOUT_MS);

function fail(reason) { console.error('SMOKE FAIL: ' + reason); child.kill(); process.exit(1); }
function send(method, params, notify) {
  const msg = { jsonrpc: '2.0', method, params };
  if (notify) { child.stdin.write(JSON.stringify(msg) + '\n'); return Promise.resolve(); }
  msg.id = nextId++;
  return new Promise((resolve) => { pending.set(msg.id, resolve); child.stdin.write(JSON.stringify(msg) + '\n'); });
}
async function tool(name, argumentsObj) {
  const res = await send('tools/call', { name, arguments: argumentsObj });
  if (res.error) fail(`${name}: ${JSON.stringify(res.error)}`);
  if (res.result.isError) fail(`${name}: ${res.result.content?.[0]?.text}`);
  const sc = res.result.structuredContent;
  return sc ? (sc.result ?? sc) : JSON.parse(res.result.content[0].text);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const init = await send('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'ai-detect-smoke', version: '1' } });
if (init.error) fail('initialize: ' + JSON.stringify(init.error));
console.log(`initialize ok: ${init.result.serverInfo.name} ${init.result.serverInfo.version}, protocol ${init.result.protocolVersion}, instructions ${String(init.result.instructions || '').length} chars`);
await send('notifications/initialized', {}, true);
const tools = (await send('tools/list', {})).result.tools.map((t) => t.name).sort();
console.log(`tools/list ok: ${tools.length} tools: ${tools.join(', ')}`);
for (const required of ['detect_ai_text', 'detect_ai_file', 'compare_texts', 'get_model_status', 'list_models']) {
  if (!tools.includes(required)) fail('missing tool ' + required);
}
let result;
for (;;) {
  result = await tool('detect_ai_text', { text: TEXT, model: MODEL, device: 'cpu' });
  if (result.status === 'ok') break;
  if (result.status === 'failed') fail('model download failed: ' + result.message);
  console.log('  ' + result.message);
  await sleep(10000);
}
console.log(`scan ok: model ${result.model}, sentence score ${result.model_ai_pct}%, document ${result.document_ai_pct}%, sentences ${result.counts.total}, dashboard ${result.dashboard_url}`);
clearTimeout(timer);
child.stdin.end();
child.kill();
console.log('SMOKE PASS');
process.exit(0);
