# Releasing ai-detect 2.0.0

A checklist for PowerShell on Windows. Nothing below has been published: no push, no npm, no PyPI, no registry write was made while preparing it. **[dry-run OK]** means the step, or everything it does short of uploading, was run on 24 Nov 2026. **[not verified]** means it was not.

## Before you start

**Logins needed**
- npm: an account that can publish to the `@houtini` scope (`npm whoami`).
- GitHub: push rights on `houtini-ai/ai-detect`; `gh auth status`.
- MCP registry: the same GitHub account (device login; no separate account).
- PyPI (optional, step 6): an account and an API token for a new project named `ai-detect`.

**Tools needed on this machine:** Python 3.11+, Node 18+, `uv`, `gh`, and for step 5 `mcp-publisher`. The pre-flight uses whichever `python` is first on PATH, and your system Python has no pytest, so run this once first:
```powershell
python -m pip install pytest pyflakes
```
(While preparing this, the pre-flight was run with the virtual environment in `C:\MCP\ai-detect-rebuild\.venv`, which has both.)

**Blockers and decisions**
- None found by the harness: tests pass, no secrets in the branch history, the tarball holds only whitelisted files.
- The README is still the 1.0.0 text with factual corrections only. It ships inside the npm tarball. Publish after the rewrite, or accept that.
- The code is on a local branch in a second working folder, `C:\MCP\ai-detect-rebuild` (a git worktree of `C:\MCP\ai-detect`). Your installed `ai-detect` still runs the old code in `C:\MCP\ai-detect`.
- The npm package does **not** need a PyPI release: it carries the Python source and runs it with `uv`. PyPI is optional and comes last.
- The default model is unchanged (`desklib`). Changing it is a separate decision and a separate release.

**Pre-flight (runs everything, publishes nothing)** [dry-run OK]
```powershell
cd C:\MCP\ai-detect-rebuild
python scripts\release_check.py
```
Success: the last line is `RELEASE CHECK PASSED (nothing was published)`. Takes about three minutes.

## Steps, in order

**1. Review and merge the branch** [not verified: no push was made]
```powershell
cd C:\MCP\ai-detect-rebuild
git log --oneline main..rebuild-2026-11
git push -u origin rebuild-2026-11
gh pr create --base main --head rebuild-2026-11 --title "ai-detect 2.0.0" --body "See CHANGELOG.md"
```
Merge the PR on GitHub when reviewed. Success: `gh pr view --json state` shows `MERGED`.
Undo: before merging, `git push origin --delete rebuild-2026-11`. After merging, revert the merge commit.

**2. Tag** [not verified]
```powershell
cd C:\MCP\ai-detect
git checkout main; git pull
git tag v2.0.0; git push origin v2.0.0
```
Verify: `git ls-remote --tags origin v2.0.0` prints one line.
Undo: `git push origin :refs/tags/v2.0.0; git tag -d v2.0.0`.

**3. Publish to npm** [dry-run OK: `npm pack --dry-run`, install of the packed tarball, MCP handshake and a scan, on Windows and in a clean Docker container]
```powershell
cd C:\MCP\ai-detect
npm whoami
npm publish --access public
```
`prepublishOnly` runs the pre-flight again and stops the publish if anything fails. Success: a line `+ @houtini/ai-detect@2.0.0`.
Verify: `npm view @houtini/ai-detect version` prints `2.0.0`.
Undo: `npm unpublish @houtini/ai-detect@2.0.0` works within 72 hours of publishing; that version number can never be reused, so the fix is 2.0.1. After 72 hours: `npm deprecate @houtini/ai-detect@2.0.0 "use 2.0.1"`.

**4. GitHub release with the bundle** [dry-run OK for building the `.mcpb` and running its command; the upload was not made]
```powershell
cd C:\MCP\ai-detect
npx --yes @anthropic-ai/mcpb pack . dist\ai-detect-2.0.0.mcpb
gh release create v2.0.0 dist\ai-detect-2.0.0.mcpb --title "ai-detect 2.0.0" --notes-file CHANGELOG.md
```
Success: `gh` prints the release URL. Verify: open it; the `.mcpb` is listed under Assets.
Undo: `gh release delete v2.0.0 --yes` (the tag stays; step 2's undo removes it).

**5. MCP registry** [not verified: `server.json` follows the 2025-12-11 schema used by your other servers, but `mcp-publisher` was not run]
```powershell
cd C:\MCP\ai-detect
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
```
Needs step 3 first: the registry checks that the npm package exists and that its `mcpName` equals `io.github.houtini-ai/ai-detect`. Success: a published confirmation.
Verify: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.houtini-ai/ai-detect"` returns the server.
Undo: the registry's quickstart does not describe deleting a version; it lists `mcp-publisher status` for changing a version's status. Treat a registry publish as permanent.

**6. PyPI (optional)** [dry-run OK: `python -m build` and `twine check` both passed; no upload]
```powershell
cd C:\MCP\ai-detect
python -m pip install build twine
Remove-Item -Recurse -Force dist\*.whl, dist\*.tar.gz -ErrorAction SilentlyContinue
python -m build
python -m twine check dist\ai_detect-2.0.0*
python -m twine upload dist\ai_detect-2.0.0*
```
Success: `View at: https://pypi.org/project/ai-detect/2.0.0/`. Verify: `pip index versions ai-detect`.
Undo: a PyPI file can be yanked or deleted in the project's web settings, but the file name can never be uploaded again; the fix is 2.0.1.
If you publish to PyPI and want it in the registry listing, add a `pypi` entry to `server.json` and a line `mcp-name: io.github.houtini-ai/ai-detect` to the README, then repeat step 5 with a new version.

## After publishing

Run these on a machine (or user account) that has never had ai-detect. All [not verified against the real registries; the same commands were run against a locally packed tarball].

1. `npx -y --package @houtini/ai-detect ai-detect --version` prints `ai-detect 2.0.0`. The first run takes a minute or more while `uv` installs PyTorch.
2. `npx -y --package @houtini/ai-detect ai-detect --model light --text "Furthermore, the platform provides a seamless experience for modern teams."` downloads 126 MB once and prints a report.
3. MCP handshake and one scan: `node scripts\smoke_mcp.mjs npx -y --package @houtini/ai-detect ai-detect-mcp` ends with `SMOKE PASS`.
4. Double-click `ai-detect-2.0.0.mcpb` from the GitHub release; Claude Desktop offers to install it; ask Claude to "list ai-detect models".
5. The registry `curl` from step 5 lists version 2.0.0.

## Appendix

**What the pre-flight checks.** `scripts/release_check.py`, in order: (1) the version is identical in `ai_detect/_version.py`, `package.json`, `manifest.json`, `server.json` and the newest `CHANGELOG.md` entry; (2) `compileall`, `pyflakes`, `node --check`; (3) the Python tests, browser tests excluded; (4) a scan of every commit on the branch and the working tree for credential-shaped strings (Hugging Face, OpenAI-style, GitHub, npm, AWS, PyPI, Slack tokens, private keys, quoted password assignments); (5) `npm pack --dry-run`: every file must match the whitelist, none may match the forbidden list (tests, docs, scripts, examples, caches, weights, images, `.env`, logs), none may contain a local user path or a credential-shaped string; (6) pack, `npm install` the tarball into an empty temp folder, start the MCP server from it, complete `initialize` and `tools/list`, and run one scan with the smallest model.

**Recorded output, 24 Nov 2026, Windows host**
```
== versions
  2.0.0      ai_detect/_version.py
  2.0.0      package.json
  2.0.0      manifest.json
  2.0.0      server.json
  2.0.0      server.json packages[0]
  2.0.0      CHANGELOG.md (latest entry)
== lint
  compileall: ok
  pyflakes: ok
  node --check bin/launch.js: ok
== tests
  125 passed
== secrets (every commit reachable from HEAD, plus the working tree)
  no credential-shaped strings found
== tarball (npm pack --dry-run)
  @houtini/ai-detect@2.0.0: 40 files, 104 kB packed, 325 kB unpacked
  only whitelisted files; no local paths or credential-shaped strings
== smoke (pack, install into an empty folder, MCP handshake, one scan)
  initialize ok: ai-detect , protocol 2025-06-18, instructions 1039 chars
  tools/list ok: 9 tools: compare_texts, detect_ai_file, detect_ai_text, detect_ai_url, get_model_status, list_models, open_dashboard, prefetch, scan_batch
  scan ok: model light, sentence score 96.6%, document 97.9%, sentences 2
  SMOKE PASS
RELEASE CHECK PASSED (nothing was published)
```
The 40 files: `CHANGELOG.md`, `LICENSE`, `README.md`, `THIRD-PARTY-MODELS.md`, `package.json`, `pyproject.toml`, three files in `bin/`, and `ai_detect/` (24 Python files, `calibration.json`, `assets/extract.js`, three static web files, `_vendor/LICENSE-conpara`).

**Clean container** (`scripts/docker-smoke/Dockerfile`: `python:3.12-slim` plus Node, npm and uv; build context holds only the tarball and the smoke script; no host mounts)
```
v20.19.2
Python 3.12.14
uv 0.13.10 (x86_64-unknown-linux-gnu)
initialize ok: ai-detect , protocol 2025-06-18, instructions 1039 chars
tools/list ok: 9 tools: compare_texts, detect_ai_file, detect_ai_text, detect_ai_url, get_model_status, list_models, open_dashboard, prefetch, scan_batch
  Downloading light (126.0 MB): 0%. Watch progress at http://127.0.0.1:8765/#/models. Ask me again in a minute.
scan ok: model light, sentence score 96.6%, document 97.9%, sentences 2
SMOKE PASS
```
In that container `uv` resolved MCP SDK 2.x, so this run also covers the newer SDK. The container sets `UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu` to get CPU-only PyTorch; without it the default Linux wheel pulls several GB of CUDA libraries (not tested). The image was removed afterwards. To repeat:
```powershell
cd C:\MCP\ai-detect-rebuild
$ctx = "$env:TEMP\aid-ctx"; New-Item -ItemType Directory -Force $ctx | Out-Null
npm pack --ignore-scripts --pack-destination $ctx; Copy-Item scripts\smoke_mcp.mjs $ctx
docker build -t ai-detect-smoke -f scripts\docker-smoke\Dockerfile $ctx; docker run --rm ai-detect-smoke
```

**The npm launcher.** `bin/launch.js` runs `uv tool run --from <package folder>[light] ai-detect-mcp` (or `ai-detect`). It needs `uv` on PATH and nothing else: `uv` supplies Python and installs the dependencies into its own cache. Without `uv` it prints install instructions and exits 1. First start: about a minute on Windows (measured 67 s; 2 s once cached). Names checked on 24 Nov 2026: `@houtini/ai-detect` and `ai-detect` on npm and `ai-detect` on PyPI all returned 404, so all are free.

**The MCPB bundle.** Manifest version 0.4, server type `uv`: the host runs `uv run --directory <bundle> --extra light mcpb_entry.py` and uv installs the dependencies from `pyproject.toml`. A bundle with PyTorch packed inside is not practical (per-platform, over a gigabyte), which is why the `uv` type is used. `mcpb validate` and `mcpb pack` passed (250 kB, 40 files); the packed file was unzipped and that exact command completed the MCP smoke test. It was **not** installed in Claude Desktop, and whether a given Claude Desktop build supports the `uv` server type was not checked. A copy is in `dist/` (git-ignored).

**Version.** 1.0.0 to 2.0.0. `tests/test_versions.py` fails if the five places disagree.
