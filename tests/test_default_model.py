"""The default model is gpttrace-150m, which runs on ONNX Runtime."""

import os
import re
import tomllib

import pytest

from ai_detect import backends
from ai_detect.models import DEFAULT_MODEL, MODELS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pyproject():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)["project"]


def _names(requirements):
    return {re.split(r"[<>=!~ \[;]", r, maxsplit=1)[0].lower() for r in requirements}


class FakeOrt:
    def __init__(self, providers):
        self._providers = providers

    def get_available_providers(self):
        return list(self._providers)


def test_default_is_gpttrace_150m_and_desklib_stays_selectable():
    assert DEFAULT_MODEL == "gpttrace-150m"
    assert MODELS[DEFAULT_MODEL].runtime == "onnx"
    assert MODELS[DEFAULT_MODEL].approx_mb == 151
    assert "desklib" in MODELS


def test_default_model_needs_no_extra():
    assert MODELS[DEFAULT_MODEL].extra in (None, "")
    assert MODELS["light"].extra in (None, "")
    assert MODELS["gpttrace-1b"].extra in (None, "")


def test_onnxruntime_is_a_core_dependency():
    project = _pyproject()
    assert "onnxruntime" in _names(project["dependencies"])


def test_light_extra_still_installs():
    extras = _pyproject()["optional-dependencies"]
    assert "light" in extras and "onnx" in extras
    # An alias only: it must not pull a second onnxruntime distribution.
    assert _names(extras["light"]) <= {"onnxruntime"}


def test_no_extra_adds_a_second_onnxruntime_distribution():
    """onnxruntime, onnxruntime-directml and onnxruntime-gpu all install the same
    `onnxruntime` package folder. Two of them in one environment overwrite each
    other, so no extra may name a GPU build while the CPU build is a core
    dependency."""
    extras = _pyproject()["optional-dependencies"]
    for name, requirements in extras.items():
        assert not _names(requirements) & {"onnxruntime-directml", "onnxruntime-gpu"}, name


@pytest.mark.parametrize("pref", [None, "auto", "cpu", "cuda", "gpu"])
def test_onnx_providers_fall_back_to_cpu_when_no_gpu_provider(monkeypatch, pref):
    monkeypatch.delenv("AI_DETECT_DEVICE", raising=False)
    ort = FakeOrt(["AzureExecutionProvider", "CPUExecutionProvider"])
    assert backends.onnx_providers(ort, pref) == ["CPUExecutionProvider"]


@pytest.mark.parametrize("gpu", ["DmlExecutionProvider", "CUDAExecutionProvider",
                                 "CoreMLExecutionProvider"])
def test_onnx_providers_use_an_installed_gpu_provider_with_cpu_behind_it(monkeypatch, gpu):
    monkeypatch.delenv("AI_DETECT_DEVICE", raising=False)
    ort = FakeOrt([gpu, "CPUExecutionProvider"])
    if gpu == "CoreMLExecutionProvider":
        # CoreML ships in the macOS wheel but is not selected: untested, and it
        # does not support every operator of the quantised models.
        assert backends.onnx_providers(ort, "auto") == ["CPUExecutionProvider"]
    else:
        assert backends.onnx_providers(ort, "auto") == [gpu, "CPUExecutionProvider"]
    assert backends.onnx_providers(ort, "cpu") == ["CPUExecutionProvider"]


def test_onnx_gpu_request_without_a_provider_says_how_to_get_one(monkeypatch, capsys):
    monkeypatch.delenv("AI_DETECT_DEVICE", raising=False)
    backends.onnx_providers(FakeOrt(["CPUExecutionProvider"]), "cuda")
    err = capsys.readouterr().err
    assert "using CPU" in err and "onnxruntime-directml" in err and "onnxruntime-gpu" in err


def test_cli_help_and_models_name_the_default(capsys):
    from ai_detect import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "default: gpttrace-150m" in capsys.readouterr().out
    cli.main(["models"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("gpttrace-150m"))
    assert "(default)" in line and "151 MB" in line
    assert "(default)" not in next(ln for ln in out.splitlines() if ln.startswith("desklib"))


def test_mcp_server_text_names_the_default():
    pytest.importorskip("mcp")
    from ai_detect import server
    assert "The default is gpttrace-150m" in server.INSTRUCTIONS
    for tool in (server.detect_ai_text, server.detect_ai_file, server.detect_ai_url):
        doc = getattr(tool, "__doc__", None) or getattr(getattr(tool, "fn", None), "__doc__", "")
        assert "Default 'gpttrace-150m'" in doc and "Default 'desklib'" not in doc


def test_manifest_size_range_matches_the_registry():
    import json
    with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
        text = json.load(f)["long_description"]
    assert "gpttrace-150m" in text and "151 MB" in text
