from datetime import datetime
from pathlib import Path

from .utils import sha256_str


def generate_build_id(config_hash: str, tool_version: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"build-{ts}-{config_hash[:6]}-{tool_version}"


def generate_query_id() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"q-{ts}"


def latest_build_manifest(meta_dir: Path):
    builds_dir = meta_dir / "builds"
    if not builds_dir.exists():
        return None
    manifests = sorted(builds_dir.glob("*/build_manifest.json"))
    return manifests[-1] if manifests else None
