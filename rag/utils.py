import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def now_ts() -> str:
    return datetime.utcnow().strftime(ISO_FMT)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def next_version_path(base_dir: Path, stem: str, suffix: str = ".md") -> Path:
    ensure_dir(base_dir)
    pattern = re.compile(rf"{re.escape(stem)}_v(\d{{3}}){re.escape(suffix)}$")
    max_v = 0
    for file in base_dir.glob(f"{stem}_v*{suffix}"):
        m = pattern.match(file.name)
        if m:
            max_v = max(max_v, int(m.group(1)))
    return base_dir / f"{stem}_v{max_v+1:03d}{suffix}"


def load_version_log(path: Path) -> None:
    ensure_dir(path.parent)
    if not path.exists():
        path.touch()


def append_version_log(path: Path, record: Dict[str, Any]) -> None:
    load_version_log(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_draft_version(draft_path: Path) -> str:
    name = draft_path.stem
    return name


def human_warn(msg: str) -> str:
    return f"WARNING: {msg}"


def get_google_project_id() -> Optional[str]:
    import os
    # 1. 优先读取显式环境变量
    pid = os.environ.get("GCP_PROJECT_ID")
    if pid:
        return pid
    
    # 2. 尝试从 GOOGLE_APPLICATION_CREDENTIALS 文件中读取
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        path = Path(cred_path)
        if path.exists() and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                found = data.get("project_id")
                if found:
                    return found
            except Exception:
                pass # 解析失败则静默跳过
    
    return None
