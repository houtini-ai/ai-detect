"""End-to-end MCP test: start the real server over stdio and call its tools.

Runs a real detection with the small 'light' model, so it is skipped unless
that model is already downloaded and onnxruntime is installed.
"""

import asyncio
import json
import os
import sys

import pytest

pytest.importorskip("onnxruntime")
from ai_detect.detector import is_model_cached  # noqa: E402

pytestmark = pytest.mark.model
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = ("Furthermore, the platform provides a seamless experience for modern teams. "
        "I don't love the price, though, and my brother thinks it's too slow.")


def _payload(result):
    if getattr(result, "structuredContent", None):
        data = result.structuredContent
        return data.get("result", data)
    return json.loads(result.content[0].text)


async def _session(tmp_path, body):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "AI_DETECT_DEVICE": "cpu", "AI_DETECT_PORT": "18791",
           "AI_DETECT_HOME": str(tmp_path), "AI_DETECT_NO_PREFETCH": "1", "PYTHONPATH": ROOT}
    params = StdioServerParameters(command=sys.executable, args=["-m", "ai_detect.server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            return await body(session, init)


def test_mcp_server_end_to_end(tmp_path):
    if not is_model_cached("light"):
        pytest.skip("the 'light' model is not downloaded")

    async def body(session, init):
        out = {"instructions": init.instructions or ""}
        out["tools"] = sorted(t.name for t in (await session.list_tools()).tools)
        out["models"] = _payload(await session.call_tool("list_models", {}))
        out["status"] = _payload(await session.call_tool("get_model_status", {"model": "light"}))
        out["unknown"] = _payload(await session.call_tool("get_model_status", {"model": "nope"}))
        out["dash"] = _payload(await session.call_tool("open_dashboard", {}))
        out["detect"] = _payload(await session.call_tool(
            "detect_ai_text", {"text": TEXT, "model": "light", "device": "cpu"}))
        bad = await session.call_tool("detect_ai_text", {"text": TEXT, "model": "nope"})
        out["bad_is_error"] = bool(bad.isError)
        out["compare"] = _payload(await session.call_tool(
            "compare_texts", {"text_a": TEXT, "text_b": "It's fine, I suppose, for the money.",
                              "model": "light", "device": "cpu"}))
        return out

    out = asyncio.run(_session(tmp_path, body))
    assert "never leave" in out["instructions"] and "8765" in out["instructions"]
    assert {"detect_ai_text", "detect_ai_file", "compare_texts", "get_model_status",
            "list_models"} <= set(out["tools"])                      # the original five
    assert {"detect_ai_url", "scan_batch", "prefetch", "open_dashboard"} <= set(out["tools"])
    assert out["models"]["default"] == "gpttrace-150m" and "light" in out["models"]["models"]
    assert out["status"]["status"] == "ready" and out["status"]["downloaded"] is True
    assert "error" in out["unknown"] and "desklib" in out["unknown"]["available"]
    assert out["dash"]["url"].startswith("http://127.0.0.1:")
    d = out["detect"]
    assert d["status"] == "ok" and d["model"] == "light"
    assert {"model_ai_pct", "verdict", "counts", "text_metrics", "pattern_totals",
            "flagged_sentences"} <= set(d)                           # the original keys
    assert d["counts"]["total"] == 2
    assert d["dashboard_url"].startswith(out["dash"]["url"] + "/#/scan/")
    assert out["bad_is_error"] is True
    assert {"a", "b", "delta_ai_pct"} <= set(out["compare"])
