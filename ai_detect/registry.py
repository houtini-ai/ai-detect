"""
The model registry: one frozen record per detector.

Everything that needs to know about a model (the CLI's ``--model`` choices, the
MCP ``list_models`` tool, the web UI's picker, the cache probe, the prefetch
file list, the backend loader) reads it from here. Adding a model is one
``ModelSpec`` in ``models.py`` plus, only if it needs a new way of loading, one
backend class in ``backends.py``.

Every external claim on a spec (licence, size, RAID rank) carries its source
URL and the date it was read. Nothing here is taken from memory.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

RAID_LEADERBOARD = "https://raid-bench.xyz/leaderboard"
RAID_REPO = "https://github.com/liamdugan/raid"
RAID_METRIC = "TPR at 5% FPR, all attacks"
RAID_READ = "2026-11-24"

MAX_ENSEMBLE = 5


@dataclass(frozen=True)
class RaidResult:
    """A model's standing on the RAID leaderboard on the date it was read."""

    rank: int
    of: int
    score: float
    submission: str  # folder under leaderboard/submissions in the RAID repo
    metric: str = RAID_METRIC
    read: str = RAID_READ
    note: str = ""

    @property
    def source(self):
        return f"{RAID_REPO}/tree/main/leaderboard/submissions/{self.submission}"

    def as_dict(self):
        return {
            "rank": self.rank, "of": self.of, "score": self.score,
            "metric": self.metric, "read": self.read, "source": self.source,
            "note": self.note,
        }


_LEGACY_KEYS = {"backend": "loader", "onnx_file": "cache_probe"}


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    loader: str                 # key into backends.LOADERS
    repo: str                   # Hugging Face repo id the weights come from
    files: Tuple[str, ...]      # exact files or glob patterns to download
    cache_probe: str            # one large file whose presence means "fetched"
    approx_mb: int
    params_m: Optional[float]   # millions of parameters, None when unpublished
    licence: str                # licence of the WEIGHTS
    licence_source: str
    runtime: str                # 'torch' | 'onnx'
    extra: Optional[str] = None  # pip extra that provides the runtime, if optional
    normalizer: str = "none"    # key into normalize.NORMALIZERS
    tokenizer_file: Optional[str] = None  # for loaders using `tokenizers` directly
    subfolder: Optional[str] = None
    extra_repos: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()  # (repo, files) also needed
    raid: Optional[RaidResult] = None
    summary: str = ""           # one plain line for pickers
    caveats: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()
    read: str = RAID_READ       # date the licence/size facts were read

    @property
    def card(self):
        return f"https://huggingface.co/{self.repo}"

    # The old registry was a dict of dicts (`MODELS["desklib"]["label"]`).
    # Keep that spelling working for anyone importing ai_detect.MODELS.
    def __getitem__(self, key):
        key = _LEGACY_KEYS.get(key, key)
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def public(self):
        """The JSON-safe description shown by list_models and the web UI."""
        return {
            "id": self.id,
            "label": self.label,
            "summary": self.summary,
            "repo": self.repo,
            "card": self.card,
            "approx_mb": self.approx_mb,
            "params_m": self.params_m,
            "licence": self.licence,
            "licence_source": self.licence_source,
            "runtime": self.runtime,
            "extra": self.extra,
            "raid": self.raid.as_dict() if self.raid else None,
            "caveats": list(self.caveats),
            "aliases": list(self.aliases),
        }


class UnknownModelError(ValueError):
    """Raised for a model id that is not in the registry."""


class Registry:
    """An ordered id -> ModelSpec mapping with alias lookup."""

    def __init__(self, specs=()):
        self.models = {}
        self.aliases = {}
        for spec in specs:
            self.add(spec)

    def add(self, spec):
        for name in (spec.id, *spec.aliases):
            if name in self.models or name in self.aliases:
                raise ValueError(f"duplicate model name {name!r}")
        self.models[spec.id] = spec
        for alias in spec.aliases:
            self.aliases[alias] = spec.id
        return spec

    def resolve(self, name):
        """Return the ModelSpec for an id or alias, or raise UnknownModelError."""
        key = (name or "").strip().lower()
        key = self.aliases.get(key, key)
        spec = self.models.get(key)
        if spec is None:
            raise UnknownModelError(
                f"Unknown model '{name}'. Choose from: {', '.join(self.models)}"
            )
        return spec

    def parse(self, value, default):
        """Turn a ``--model`` value into a list of model ids.

        Accepts one id, a comma-separated string (``a,b,c``), a list, or
        ``all``. Order is kept; duplicates (including an alias of an id already
        given) are dropped; more than MAX_ENSEMBLE is refused, not trimmed.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return [default]
        parts = value if isinstance(value, (list, tuple)) else str(value).split(",")
        parts = [p.strip() for p in parts if p and p.strip()]
        if [p.lower() for p in parts] == ["all"]:
            parts = list(self.models)[:MAX_ENSEMBLE]
        ids = []
        for part in parts:
            spec = self.resolve(part)
            if spec.id not in ids:
                ids.append(spec.id)
        if not ids:
            return [default]
        if len(ids) > MAX_ENSEMBLE:
            raise ValueError(
                f"An ensemble takes at most {MAX_ENSEMBLE} models; got {len(ids)}."
            )
        return ids
