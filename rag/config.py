from __future__ import annotations

import yaml
import json
from pathlib import Path
from typing import Any, Dict

from .errors import RagError, ErrorCode
from .utils import sha256_str


DEFAULT_CONFIG = {
    "project": {"infer_from_meta": True},
    "paths": {
        "raw": "raw",
        "parsed": "parsed",
        "chunks": "chunks",
        "index": "index",
        "meta": "meta",
        "outputs": "outputs",
    },
    "embedding": {
        "provider": "vertex",
        "model": "gemini-embedding-001",
        "output_dim": 1536,
        "task_type_document": "RETRIEVAL_DOCUMENT",
        "task_type_query": "RETRIEVAL_QUERY",
        "concurrency": 4,
        "timeout_seconds": 30,
        "retry": {"max_attempts": 3, "backoff_seconds": 2},
    },
    "rerank": {
        "enabled": True,
        "model": "semantic-ranker-default-004",
        "candidate_k": 50,
        "top_n": 10,
    },
    "verify_citations": {"k": 10, "threshold_T": 0.55},
    "counterevidence_mode": "off",
    "locator": {"header_footer_repeat_threshold": 0.6},
}


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RagError(f"config.yaml not found at {path}", ErrorCode.CONFIG_MISSING)
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except Exception as exc:  # pragma: no cover - defensive
        raise RagError(f"Failed to parse config.yaml: {exc}", ErrorCode.CONFIG_INVALID) from exc
    return data


def save_default_config(path: Path) -> None:
    path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")


def config_hash(cfg: Dict[str, Any]) -> str:
    return sha256_str(json.dumps(cfg, sort_keys=True, ensure_ascii=False))
