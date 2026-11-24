import json
from ai_detect.registry import Registry, ModelSpec, RaidResult, UnknownModelError, MAX_ENSEMBLE
from ai_detect.models import MODELS, DEFAULT_MODEL

def _make_spec(id="test_model", label="Test", aliases=()):
    return ModelSpec(
        id=id, label=label, loader="onnx", repo="org/repo",
        files=("model.onnx",), cache_probe="model.onnx", approx_mb=100,
        params_m=10.0, licence="MIT", licence_source="https://example.com",
        runtime="onnx", aliases=aliases
    )

def test_registry_resolution():
    spec = _make_spec(aliases=["tm"])
    reg = Registry([spec])
    assert reg.resolve("test_model") is spec
    assert reg.resolve("tm") is spec
    assert reg.resolve("TEST_MODEL") is spec

def test_registry_unknown_model():
    reg = Registry([_make_spec()])
    try:
        reg.resolve("unknown")
        assert False
    except UnknownModelError:
        pass

def test_registry_duplicate_name():
    spec1 = _make_spec(aliases=["dup"])
    spec2 = _make_spec(id="other", aliases=())
    spec3 = _make_spec(id="conflict", aliases=["dup"])
    reg = Registry([spec1, spec2])
    try:
        reg.add(spec3)
        assert False
    except ValueError:
        pass

def test_parse_none_default():
    reg = Registry([_make_spec()])
    assert reg.parse(None, "test_model") == ["test_model"]

def test_parse_order_and_dedupe():
    reg = Registry([_make_spec(aliases=["alias"])])
    assert reg.parse("test_model,alias", "default") == ["test_model"]
    assert reg.parse("alias,test_model", "default") == ["test_model"]

def test_parse_all_and_limit():
    specs = [_make_spec(f"m{i}", aliases=[f"a{i}"]) for i in range(MAX_ENSEMBLE + 1)]
    reg = Registry(specs)
    all_ids = reg.parse("all", "default")
    assert len(all_ids) == MAX_ENSEMBLE
    try:
        reg.parse(", ".join([f"m{i}" for i in range(MAX_ENSEMBLE + 1)]), "default")
        assert False
    except ValueError:
        pass

def test_spec_legacy_keys():
    spec = _make_spec()
    assert spec["label"] == "Test"
    assert spec["backend"] == "onnx"
    try:
        _ = spec["nope"]
        assert False
    except KeyError:
        pass

def test_public_serializable():
    spec = _make_spec()
    data = spec.public()
    json.dumps(data)

def test_raid_result_source():
    raid = RaidResult(rank=1, of=10, score=0.9, submission="sub_name")
    assert "sub_name" in raid.source

def test_real_registry():
    assert DEFAULT_MODEL == "desklib"
    assert "light" in MODELS
    for spec in MODELS.values():
        if spec.raid:
            assert isinstance(spec.raid.read, str) and spec.raid.read
            assert spec.licence_source.startswith("https://")
