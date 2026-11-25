"""Build docs/FEATURES.md from a template plus real command output.

    python scripts/build_features_doc.py

Every `{{run: ...}}` in docs/features.template.md is replaced by that command
and the output it actually printed on this machine; `{{tools}}`, `{{models}}`
and `{{screenshots}}` are filled from the live MCP server, the registry and the
screenshots folder, and the test counts from pytest's collection. So the examples in FEATURES.md cannot drift from the code:
re-run this after a change. Commands run on CPU with the small 'light' model.
"""

import asyncio
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ENV = {**os.environ, "AI_DETECT_DEVICE": "cpu", "CUDA_VISIBLE_DEVICES": "", "PYTHONIOENCODING": "utf-8",
       "PYTHONPATH": ROOT, "AI_DETECT_HOME": os.path.join(ROOT, "eval_cache", "features-home"),
       "AI_DETECT_PORT": "18795", "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
NOISE = re.compile(r"warn|symlink|^Loading|loaded (on|via)|^\s*$", re.IGNORECASE)


def run(command, limit=60):
    argv = command.replace("ai-detect ", f'"{sys.executable}" -m ai_detect.cli ', 1)
    r = subprocess.run(argv, cwd=ROOT, env=ENV, capture_output=True, text=True, shell=True,
                       encoding="utf-8", errors="replace")
    lines = [ln.rstrip() for ln in (r.stdout + r.stderr).split("\n")]
    lines = [ln for ln in lines if ln.strip() == "" or not NOISE.search(ln)]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    if len(lines) > limit:
        lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
    body = "\n".join(lines).replace(ROOT + os.sep, "").replace(ROOT, ".")
    return f"```\n$ {command}\n{body}\n```\nExit code {r.returncode}."


async def mcp_facts():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=["-m", "ai_detect.server"], env=ENV)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            tools = (await s.list_tools()).tools

            async def call(name, args):
                res = await s.call_tool(name, args)
                sc = getattr(res, "structuredContent", None)
                return (sc.get("result", sc) if sc else json.loads(res.content[0].text))

            detect = await call("detect_ai_text", {
                "model": "light", "device": "cpu",
                "text": "Furthermore, the platform provides a seamless experience for modern "
                        "teams. I don't love the price, though, and my brother agrees."})
            status = await call("get_model_status", {"model": "light"})
            dash = await call("open_dashboard", {})
            return init, tools, detect, status, dash


def shape(value, depth=0):
    """A compact description of a JSON value's shape."""
    if isinstance(value, dict):
        if depth >= 2:
            return "{" + ", ".join(value) + "}"
        return {k: shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0], depth + 1)] if value else []
    return type(value).__name__ if not isinstance(value, str) or len(value) > 40 else value


def tools_section():
    init, tools, detect, status, dash = asyncio.run(mcp_facts())
    out = ["Server name `ai-detect`. Transport: stdio. The table is read from the running "
           "server's `tools/list` answer.", "",
           "| Tool | Parameters (default) | Read-only | May start a download |", "|---|---|---|---|"]
    for t in sorted(tools, key=lambda t: t.name):
        props = t.inputSchema.get("properties", {})
        required = set(t.inputSchema.get("required", []))
        params = ", ".join(
            f"`{name}`" + ("" if name in required else f" (`{json.dumps(p.get('default'))}`)")
            for name, p in props.items()) or "none"
        ro = getattr(t.annotations, "readOnlyHint", None) if t.annotations else None
        description = " ".join((t.description or "").split())  # a docstring wraps anywhere
        dl = "yes" if "download" in description.lower() and "Never triggers" not in description else "no"
        if t.name == "prefetch":
            dl = "yes (that is its job)"
        out.append(f"| `{t.name}` | {params} | {'yes' if ro else 'no'} | {dl} |")
    out += ["", "### Tool descriptions (as sent to the client)", ""]
    for t in sorted(tools, key=lambda t: t.name):
        out += [f"**`{t.name}`**", "", "```", (t.description or "").strip(), "```", ""]
    out += ["### Server instructions (sent at initialize)", "", "```", init.instructions or "", "```", "",
            "### Return shape: `detect_ai_text` (real call, model `light`)", "", "```json",
            json.dumps(shape(detect), indent=1), "```", "",
            "`detect_ai_file` adds `file`; `detect_ai_url` adds `url`. With several models the "
            "result also has `per_model` and `ensemble`, and each flagged sentence has `agreement` "
            "and `scores`. With `include_all_sentences=true` it adds `all_sentences`. With "
            "`perplexity=true` it adds `perplexity`.", "",
            "When a needed model is not on disk the same tools return, at once:", "", "```json",
            json.dumps({"status": "downloading", "ready": False, "models": ["<one status object per model>"],
                        "dashboard_url": "http://127.0.0.1:8765/#/models",
                        "message": "Downloading light (126.0 MB): 34%, about 1 min left. Watch progress at "
                                   "http://127.0.0.1:8765/#/models. Ask me again in a minute."}, indent=1),
            "```", "", "### Return shape: `get_model_status` (real call)", "", "```json",
            json.dumps(status, indent=1), "```", "",
            "### Return shape: `open_dashboard` (real call; the port was set to 18795 for this run)", "",
            "```json", json.dumps(dash, indent=1), "```"]
    return "\n".join(out)


def models_section():
    from ai_detect.models import DEFAULT_MODEL, MODELS
    out = ["| Id (aliases) | Model | Size | Licence of weights | RAID rank | Needs | Select with |",
           "|---|---|---|---|---|---|---|"]
    for mid, s in MODELS.items():
        raid = f"{s.raid.rank} of {s.raid.of} ({s.raid.score:.4f})"
        alias = f" ({', '.join(s.aliases)})" if s.aliases else ""
        needs = "core install"
        if s.extra == "conpara":
            needs = "`[conpara]` extra (sentencepiece)"
        default = " **default**" if mid == DEFAULT_MODEL else ""
        out.append(f"| `{mid}`{alias}{default} | [{s.label}]({s.card}) | {s.approx_mb} MB | {s.licence} | "
                   f"{raid} | {needs} | `--model {mid}` |")
    out += ["", "RAID rank: TPR at 5% FPR with all attacks, the leaderboard's default view, computed "
            "from every `results.json` in https://github.com/liamdugan/raid at commit 84c2ea4 and "
            "matching https://raid-bench.xyz/leaderboard, read 24 Nov 2026. Per-model source links "
            "are in `ai-detect models --json` (`raid.source`). Notes on each rank:", ""]
    for mid, s in MODELS.items():
        if s.raid.note:
            out.append(f"- `{mid}`: {s.raid.note}")
    return "\n".join(out)


def screenshots_section():
    folder = os.path.join(ROOT, "docs", "screenshots")
    names = sorted(n for n in os.listdir(folder) if n.endswith(".png"))
    captions = {
        "scan-form": "The scan form with the URL tab and the model picker",
        "result-single-model": "Result of a single-model scan (the default, gpttrace-150m): verdict, highlighted text, sentence detail",
        "result-ensemble": "Result of a five-model ensemble scan of the same page: the verdict, the text shaded by the combined calibrated score, and five models' scores for one sentence",
        "ensemble-sentences-table": "Sentence table with one calibrated column per model, agreement dots and the combined score",
        "tells-panel": "Structure and style tells; the selected tell is highlighted in the text",
        "rewrite-panel": "Rewrite view: flagged sentences with their suggestions",
        "models-panel": "Models tab: each model's facts and its view of the document",
        "signals-perplexity": "Signals tab: sentence-length variation, GPT-2 perplexity and burstiness, passages",
        "page-view-annotated": "Page view: the fetched page's screenshot with the selected tell's region outlined",
        "compare": "Before/after compare (the two bundled example files)",
        "models": "Models page: size, licence, RAID rank with source, download state",
        "history": "History page",
        "export-html-report": "The exported HTML report",
    }
    out = ["| File | Shows |", "|---|---|"]
    for n in names:
        key = re.sub(r"-(dark|light)\.png$", "", n)
        theme = "dark" if n.endswith("-dark.png") else "light"
        out.append(f"| `docs/screenshots/{n}` | {captions.get(key, key)} ({theme} theme) |")
    return "\n".join(out)


def count_tests(selection):
    """How many tests pytest collects for a selection (nothing is run)."""
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", selection],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) tests? collected", r.stdout)
    if not m:
        raise SystemExit("could not count tests:\n" + r.stdout[-500:] + r.stderr[-500:])
    return int(m.group(1))


def main():
    with open(os.path.join(ROOT, "docs", "features.template.md"), encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\{\{run: (.+?)\}\}", lambda m: run(m.group(1)), text)
    text = text.replace("{{tools}}", tools_section()).replace("{{models}}", models_section())
    text = text.replace("{{screenshots}}", screenshots_section())
    unit, ui = count_tests("--ignore=tests/ui"), count_tests("tests/ui")
    text = (text.replace("{{unit_tests}}", str(unit)).replace("{{ui_tests}}", str(ui))
            .replace("{{all_tests}}", str(unit + ui)))
    with open(os.path.join(ROOT, "docs", "FEATURES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote docs/FEATURES.md", len(text), "characters")


if __name__ == "__main__":
    main()
