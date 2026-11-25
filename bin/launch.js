'use strict';
// Launcher shared by the two bin scripts. ai-detect is a Python program; this
// npm package carries its source and runs it through uv, which provides the
// Python interpreter and installs the dependencies into its own cache.
//
// It depends on one thing being installed: uv (https://docs.astral.sh/uv/).
// It does NOT depend on a PyPI release: the Python source is in this package.
const { spawn, spawnSync } = require('node:child_process');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

function fail(lines) {
  process.stderr.write(lines.join('\n') + '\n');
  process.exit(1);
}

function hasUv() {
  return spawnSync('uv', ['--version'], { stdio: 'ignore', shell: false }).status === 0;
}

module.exports = function launch(command) {
  if (!hasUv()) {
    fail([
      'ai-detect needs "uv" to run its Python code, and uv was not found on PATH.',
      'Install it, then run this command again:',
      process.platform === 'win32'
        ? '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        : '  curl -LsSf https://astral.sh/uv/install.sh | sh',
      'More ways to install: https://docs.astral.sh/uv/getting-started/installation/',
      'Or skip npm: git clone https://github.com/houtini-ai/ai-detect && pip install ./ai-detect',
    ]);
  }
  // No extra is needed for the default model (ONNX Runtime is a core dependency).
  // AI_DETECT_EXTRAS adds some: "web" for URL input, "conpara" for that model.
  const extras = (process.env.AI_DETECT_EXTRAS || '').replace(/[^a-z,-]/g, '');
  const source = extras ? `${ROOT}[${extras}]` : ROOT;
  // No shell: the arguments are passed to uv as an array, never as a command line.
  const args = ['tool', 'run', '--quiet', '--from', source, command, ...process.argv.slice(2)];
  const child = spawn('uv', args, { stdio: 'inherit', shell: false, windowsHide: true });
  child.on('error', (e) => fail([`ai-detect: could not start uv: ${e.message}`]));
  child.on('exit', (code, signal) => process.exit(signal ? 1 : code ?? 0));
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));
};
