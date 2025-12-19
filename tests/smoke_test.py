import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"command failed (rc={e.returncode}): {' '.join(cmd)}", file=sys.stderr)
        sys.exit(e.returncode)


def main():
    py = sys.executable
    run([py, "-m", "rag", "init"])
    run([py, "-m", "rag", "parse"])
    run([py, "-m", "rag", "chunk"])
    run([py, "-m", "rag", "embed"])
    run([py, "-m", "rag", "query", "test question"])

    tmp_draft = Path("draft_tmp.md")
    tmp_draft.write_text("No citations here.", encoding="utf-8")
    # audit 可选，这里保持最短链路
    run([py, "-m", "rag", "verify-citations", str(tmp_draft)])
    try:
        tmp_draft.unlink()
    except PermissionError:
        print("WARNING: failed to remove draft_tmp.md (PermissionError); please delete manually.")


if __name__ == "__main__":
    main()
