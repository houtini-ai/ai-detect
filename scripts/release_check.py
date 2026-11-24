"""Pre-publish checks. Run by `npm publish` through prepublishOnly.

    python scripts/release_check.py            # everything
    python scripts/release_check.py --fast     # skip the tarball smoke test

It never publishes, uploads or writes to any registry. Steps, each of which
stops the publish on failure:

  1. versions   every file that states the version agrees
  2. lint       the package compiles and pyflakes (if installed) is clean
  3. tests      the Python test suite (browser tests excluded)
  4. secrets    no credential-shaped string in any commit on this branch
  5. tarball    `npm pack --dry-run`: only whitelisted files, nothing private
  6. smoke      pack, install the tarball into an empty temp folder, complete
                an MCP initialize + tools/list handshake and one tiny scan
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPM = shutil.which("npm") or "npm"

ALLOWED = re.compile(
    r"^(package\.json|README\.md|LICENSE|CHANGELOG\.md|THIRD-PARTY-MODELS\.md|pyproject\.toml|"
    r"bin/[\w.-]+\.js|ai_detect/[\w/.-]+\.(py|js|css|html|json)|ai_detect/_vendor/LICENSE-conpara)$")
FORBIDDEN = re.compile(
    r"(^|/)(tests?|docs|examples|eval_cache|scripts|node_modules|\.venv|\.git|__pycache__)/|"
    r"\.(env|pem|key|safetensors|onnx|bin|pt|pyc|png|jpe?g|tgz|mcpb|log)$|(^|/)\.env", re.IGNORECASE)
SECRETS = {
    "Hugging Face token": r"\bhf_[A-Za-z0-9]{30,}\b",
    "OpenAI-style key": r"\bsk-[A-Za-z0-9_-]{24,}\b",
    "GitHub token": r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{30,}\b",
    "npm token": r"\bnpm_[A-Za-z0-9]{30,}\b",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "PyPI token": r"\bpypi-[A-Za-z0-9_-]{40,}\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    "password assignment": r"(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']",
}
LOCAL_PATH = re.compile(r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z]|/Users/[a-z]+/|/home/[a-z]+/", re.IGNORECASE)


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=kw.pop("cwd", ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def step(name):
    print(f"\n== {name}", flush=True)


def die(message):
    print(f"RELEASE CHECK FAILED: {message}", flush=True)
    sys.exit(1)


def versions():
    """Every stated version, by file. All must be equal."""
    found = {}
    with open(os.path.join(ROOT, "ai_detect", "_version.py"), encoding="utf-8") as f:
        found["ai_detect/_version.py"] = re.search(r'"([^"]+)"', f.read()).group(1)
    for name in ("package.json", "manifest.json", "server.json"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            data = json.load(f)
        found[name] = data["version"]
        for i, pkg in enumerate(data.get("packages", [])):
            found[f"{name} packages[{i}]"] = pkg["version"]
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        m = re.search(r"^## \[?(\d+\.\d+\.\d+[^\]\s]*)", f.read(), re.MULTILINE)
    found["CHANGELOG.md (latest entry)"] = m.group(1) if m else "missing"
    return found


def check_versions():
    step("versions")
    found = versions()
    for where, v in found.items():
        print(f"  {v:10} {where}")
    if len(set(found.values())) != 1:
        die("version numbers disagree")


def _unmarked(report):
    """pyflakes findings on lines that do not carry a `noqa` marker."""
    keep = []
    for line in report.strip().splitlines():
        m = re.match(r"(.+?):(\d+):", line)
        if m:
            with open(os.path.join(ROOT, m.group(1)), encoding="utf-8") as f:
                source = f.read().split("\n")
            if "noqa" in source[int(m.group(2)) - 1]:
                continue
        keep.append(line)
    return keep


def check_lint():
    step("lint")
    r = run([sys.executable, "-m", "compileall", "-q", "ai_detect", "scripts", "tests"])
    if r.returncode:
        die("compileall:\n" + r.stdout + r.stderr)
    print("  compileall: ok")
    r = run([sys.executable, "-m", "pyflakes", "ai_detect"])
    if "No module named pyflakes" in r.stderr:
        print("  pyflakes: not installed, skipped (pip install pyflakes)")
    elif _unmarked(r.stdout):
        die("pyflakes:\n" + "\n".join(_unmarked(r.stdout)))
    else:
        print("  pyflakes: ok")
    r = run(["node", "--check", "bin/launch.js"])
    if r.returncode:
        die("node --check bin/launch.js:\n" + r.stderr)
    print("  node --check bin/launch.js: ok")


def check_tests():
    step("tests")
    r = run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
             "--ignore=tests/ui"])
    print("  " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
    if r.returncode:
        die("pytest failed:\n" + r.stdout[-3000:])


def check_secrets():
    step("secrets (every commit reachable from HEAD, plus the working tree)")
    log = run(["git", "log", "-p", "--all", "--no-color", "--unified=0", "HEAD"]).stdout
    tree = []
    for name in run(["git", "ls-files", "-co", "--exclude-standard"]).stdout.split("\n"):
        path = os.path.join(ROOT, name)
        if name and os.path.isfile(path) and os.path.getsize(path) < 2_000_000:
            try:
                with open(path, encoding="utf-8") as f:
                    tree.append(f.read())
            except (UnicodeDecodeError, OSError):
                pass
    hits = []
    for label, pattern in SECRETS.items():
        for text, where in ((log, "history"), ("\n".join(tree), "working tree")):
            for m in re.finditer(pattern, text):
                if "release_check.py" in text[max(0, m.start() - 300):m.start()] and where == "history":
                    continue
                hits.append(f"{label} in {where}: {m.group(0)[:12]}...")
    print(f"  scanned {len(log):,} characters of history and {len(tree)} files")
    if hits:
        die("possible secrets:\n  " + "\n  ".join(sorted(set(hits))[:20]))
    print("  no credential-shaped strings found")


def check_tarball():
    step("tarball (npm pack --dry-run)")
    r = run([NPM, "pack", "--dry-run", "--json", "--ignore-scripts"], shell=os.name == "nt")
    if r.returncode:
        die("npm pack --dry-run failed:\n" + r.stderr)
    info = json.loads(r.stdout)[0]
    files = sorted(f["path"].replace("\\", "/") for f in info["files"])
    print(f"  {info['name']}@{info['version']}: {len(files)} files, "
          f"{info['size'] / 1024:.0f} kB packed, {info['unpackedSize'] / 1024:.0f} kB unpacked")
    bad = [f for f in files if FORBIDDEN.search(f) or not ALLOWED.match(f)]
    if bad:
        die("files that must not ship:\n  " + "\n  ".join(bad))
    leaks = []
    for name in files:
        with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
            text = f.read()
        if LOCAL_PATH.search(text):
            leaks.append(name + ": local path")
        for label, pattern in SECRETS.items():
            if name != "ai_detect/web/app.py" and re.search(pattern, text):
                leaks.append(f"{name}: {label}")
    if leaks:
        die("private content in shipped files:\n  " + "\n  ".join(leaks))
    for name in files:
        print("    " + name)
    for needed in ("LICENSE", "THIRD-PARTY-MODELS.md", "pyproject.toml", "bin/launch.js",
                   "ai_detect/server.py", "ai_detect/web/static/index.html"):
        if needed not in files:
            die(f"{needed} is missing from the tarball")
    print("  only whitelisted files; no local paths or credential-shaped strings")


def check_smoke():
    step("smoke (pack, install into an empty folder, MCP handshake, one scan)")
    work = tempfile.mkdtemp(prefix="ai-detect-smoke-")
    try:
        r = run([NPM, "pack", "--ignore-scripts", "--pack-destination", work], shell=os.name == "nt")
        if r.returncode:
            die("npm pack failed:\n" + r.stderr)
        tarball = os.path.join(work, r.stdout.strip().splitlines()[-1])
        site = os.path.join(work, "site")
        os.makedirs(site)
        with open(os.path.join(site, "package.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "ai-detect-smoke", "private": true}\n')  # pin npm to this folder
        r = run([NPM, "install", "--no-audit", "--no-fund", "--ignore-scripts", tarball],
                cwd=site, shell=os.name == "nt")
        if r.returncode:
            die("npm install of the tarball failed:\n" + r.stderr[-2000:])
        entry = os.path.join(site, "node_modules", "@houtini", "ai-detect", "bin", "ai-detect-mcp.js")
        env = {**os.environ, "AI_DETECT_HOME": os.path.join(work, "home"), "AI_DETECT_PORT": "18799",
               "AI_DETECT_DEVICE": "cpu"}
        r = run(["node", os.path.join(ROOT, "scripts", "smoke_mcp.mjs"), "node", entry], env=env,
                cwd=site)
        print("  " + "\n  ".join(r.stdout.strip().splitlines()))
        if r.returncode or "SMOKE PASS" not in r.stdout:
            die("smoke test failed:\n" + r.stderr[-3000:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    check_versions()
    check_lint()
    check_tests()
    check_secrets()
    check_tarball()
    if "--fast" not in sys.argv:
        check_smoke()
    print("\nRELEASE CHECK PASSED (nothing was published)")


if __name__ == "__main__":
    main()
