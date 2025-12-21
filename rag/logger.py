import logging
import os
from pathlib import Path
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name or "rag")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    # Optional file logging for long-running commands (e.g., embed)
    log_file = os.environ.get("RAG_LOG_FILE")
    if log_file:
        try:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            already = False
            for h in logger.handlers:
                if isinstance(h, logging.FileHandler):
                    try:
                        if os.path.abspath(h.baseFilename) == os.path.abspath(str(path)):
                            already = True
                            break
                    except Exception:
                        continue
            if not already:
                fh = logging.FileHandler(path, encoding="utf-8")
                fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
                logger.addHandler(fh)
        except Exception:
            # If file handler setup fails, fall back to stream only.
            pass
    return logger
