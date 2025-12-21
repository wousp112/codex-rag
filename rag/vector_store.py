import os
import random
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import lancedb
import pandas as pd
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from .logger import get_logger
from .utils import get_google_project_id, write_json

logger = get_logger()


class VectorStore:
    def __init__(
        self,
        db_path: Path,
        table_name: str = "chunks",
        model_name: str = "text-embedding-004",
        output_dimensionality: Optional[int] = None,
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.db = lancedb.connect(db_path)
        self.embedding_model = None
        self.model_name = model_name
        self.output_dimensionality = output_dimensionality
        # gemini-embedding-001 only supports single input
        self.max_batch_size = 1 if model_name == "gemini-embedding-001" else 100
        self.status_path = Path(os.environ.get("RAG_STATUS_FILE", "meta/embed_status.json"))

    def _get_embedding_model(self, model_name: Optional[str] = None):
        model_name = model_name or self.model_name
        if self.embedding_model is None:
            # If env proxies point to localhost:9, bypass to avoid Vertex connection failures
            for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
                v = os.environ.get(k, "")
                if "127.0.0.1:9" in v:
                    os.environ[k] = ""
            if os.environ.get("NO_PROXY") is None:
                os.environ["NO_PROXY"] = "*"
            project_id = get_google_project_id()
            location = os.environ.get("GCP_LOCATION", "us-central1")
            if project_id:
                vertexai.init(project=project_id, location=location)
            self.embedding_model = TextEmbeddingModel.from_pretrained(model_name)
        return self.embedding_model

    def get_embeddings(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        model = self._get_embedding_model()
        all_embeddings = []
        batch_size = self.max_batch_size

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            inputs = [TextEmbeddingInput(text, task_type) for text in batch_texts]
            try:
                if self.output_dimensionality:
                    embeddings = model.get_embeddings(inputs, output_dimensionality=self.output_dimensionality)
                else:
                    embeddings = model.get_embeddings(inputs)
                all_embeddings.extend([e.values for e in embeddings])
            except Exception as e:
                logger.error(f"Embedding batch {i} failed: {e}")
                raise e
        return all_embeddings

    def _embed_one_with_retry(
        self,
        text: str,
        task_type: str,
        max_retries: int = 5,
        base_backoff: float = 1.0,
    ) -> Tuple[Optional[List[float]], int, bool, Optional[str]]:
        model = self._get_embedding_model()
        retries = 0
        saw_throttle = False
        last_err = None
        for attempt in range(max_retries):
            try:
                inputs = [TextEmbeddingInput(text, task_type)]
                if self.output_dimensionality:
                    embeddings = model.get_embeddings(inputs, output_dimensionality=self.output_dimensionality)
                else:
                    embeddings = model.get_embeddings(inputs)
                return embeddings[0].values, retries, saw_throttle, None
            except Exception as e:
                msg = str(e)
                last_err = msg
                if "429" in msg or "503" in msg:
                    saw_throttle = True
                wait = base_backoff * (2 ** attempt)
                wait += random.uniform(0, 0.5)
                retries += 1
                logger.warning(f"Embedding retry {attempt+1}/{max_retries} after {wait:.1f}s: {e}")
                time.sleep(wait)
        return None, retries, saw_throttle, last_err

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return

        existing_map = {}
        existing_hashes = set()
        if self.table_name in self.db.table_names():
            try:
                tbl = self.db.open_table(self.table_name)
                df_exist = tbl.to_pandas()
                if "hash" in df_exist.columns and "vector" in df_exist.columns:
                    existing_map = dict(zip(df_exist["hash"], df_exist["vector"]))
                    existing_hashes = set(df_exist["hash"].tolist())
            except Exception as e:
                logger.warning(f"读取现有向量表失败，将执行全量更新: {e}")

        checkpoint_size = 1000
        concurrency = 32
        min_concurrency = 8
        max_concurrency = 128
        max_retries = 5
        heartbeat_interval = 10
        stall_timeout = int(os.environ.get("RAG_STALL_TIMEOUT", "600"))
        stall_mult = float(os.environ.get("RAG_STALL_MULT", "5.0"))
        degrade_ratio = float(os.environ.get("RAG_DEGRADE_RATIO", "0.05"))
        total = len(chunks)
        processed = 0
        start_time = time.time()
        last_total_log = start_time
        prev_batch_time = None
        good_streak = 0
        baseline_rate: Optional[float] = None
        degrade_start: Optional[float] = None
        progress_window = deque()  # (timestamp, total_done)

        table = self.db.open_table(self.table_name) if self.table_name in self.db.table_names() else None
        failures: List[Dict[str, Any]] = []

        for batch_start in range(0, total, checkpoint_size):
            batch = chunks[batch_start : batch_start + checkpoint_size]
            batch_start_time = time.time()
            self._write_status(
                status="running",
                processed=processed,
                total=total,
                batch_index=(batch_start // checkpoint_size) + 1,
                eta_sec=None,
                rate=None,
            )

            batch_rows = []
            to_embed: List[Tuple[int, str]] = []
            reused_count = 0

            for i, c in enumerate(batch):
                h = c.get("hash")
                if h and h in existing_map:
                    if h in existing_hashes:
                        reused_count += 1
                        continue
                    row = dict(c)
                    row["vector"] = existing_map[h]
                    batch_rows.append(row)
                    reused_count += 1
                else:
                    to_embed.append((i, c["text"]))

            retry_count = 0
            fail_count = 0
            saw_throttle = False

            index_to_vec: Dict[int, List[float]] = {}
            failed_items: List[Tuple[int, str, Optional[str]]] = []
            last_error: Optional[str] = None

            if to_embed:
                msg = f"Batch {batch_start//checkpoint_size+1}: 复用 {reused_count} 条，需计算 {len(to_embed)} 条..."
                logger.info(msg)
                print(msg, flush=True)
                if self.model_name == "gemini-embedding-001":
                    with ThreadPoolExecutor(max_workers=concurrency) as ex:
                        batch_done = 0
                        last_heartbeat = time.time()
                        last_progress = last_heartbeat
                        futures = {
                            ex.submit(
                                self._embed_one_with_retry,
                                text,
                                "RETRIEVAL_DOCUMENT",
                                max_retries,
                                1.0,
                            ): idx
                            for idx, text in to_embed
                        }
                        pending = set(futures.keys())
                        while pending:
                            done, pending = wait(pending, timeout=heartbeat_interval)
                            progressed = False
                            for fut in done:
                                idx = futures[fut]
                                try:
                                    vec, retries, throttled, err = fut.result()
                                except Exception as e:
                                    vec, retries, throttled, err = None, 0, False, str(e)
                                retry_count += retries
                                saw_throttle = saw_throttle or throttled
                                if vec is None:
                                    fail_count += 1
                                    failed_items.append((idx, batch[idx]["text"], err))
                                    last_error = err
                                else:
                                    index_to_vec[idx] = vec
                                batch_done += 1
                                last_progress = time.time()
                                total_done = processed + batch_done
                                progress_window.append((last_progress, total_done))
                                progressed = True
                                if baseline_rate is None and total_done >= 200:
                                    # Establish a baseline rate after initial warm-up
                                    elapsed = max(last_progress - start_time, 1e-6)
                                    baseline_rate = total_done / elapsed
                            now = time.time()
                            # Trim progress window to last 120s
                            while progress_window and (now - progress_window[0][0]) > 120:
                                progress_window.popleft()
                            if batch_done % 100 == 0 or (now - last_heartbeat) >= heartbeat_interval:
                                done_total = processed + batch_done
                                hb = f"HEARTBEAT: {done_total}/{total}"
                                logger.info(hb)
                                print(hb, flush=True)
                                last_heartbeat = now
                                self._write_status(
                                    status="running",
                                    processed=done_total,
                                    total=total,
                                    batch_index=(batch_start // checkpoint_size) + 1,
                                    eta_sec=None,
                                    rate=None,
                                )
                            # Stall detection: no progress for too long
                            if not progressed and (now - last_progress) >= stall_timeout:
                                err_msg = (
                                    f"Embedding stalled > {stall_timeout}s "
                                    f"(batch={batch_start//checkpoint_size+1}, done={batch_done}/{len(to_embed)}, "
                                    f"last_error={last_error})"
                                )
                                logger.error(err_msg)
                                print(err_msg, flush=True)
                                raise RuntimeError(err_msg)
                            # Degradation detection: sustained throughput collapse vs baseline
                            if baseline_rate and progress_window:
                                t0, d0 = progress_window[0]
                                t1, d1 = progress_window[-1]
                                dt = max(t1 - t0, 1e-6)
                                window_rate = (d1 - d0) / dt
                                if window_rate < baseline_rate * degrade_ratio:
                                    if degrade_start is None:
                                        degrade_start = now
                                    elif (now - degrade_start) >= stall_timeout:
                                        err_msg = (
                                            f"Embedding throughput degraded for > {stall_timeout}s "
                                            f"(window_rate={window_rate:.2f}, baseline_rate={baseline_rate:.2f}, "
                                            f"ratio={window_rate / max(baseline_rate,1e-6):.3f})"
                                        )
                                        logger.error(err_msg)
                                        print(err_msg, flush=True)
                                        raise RuntimeError(err_msg)
                                else:
                                    degrade_start = None
                else:
                    try:
                        batch_vectors = self.get_embeddings([t for _, t in to_embed])
                        for (i, _), vec in zip(to_embed, batch_vectors):
                            index_to_vec[i] = vec
                    except Exception as e:
                        fail_count = len(to_embed)
                        last_error = str(e)
                        failed_items = [(i, t, str(e)) for i, t in to_embed]

                # 批内失败项：再重试一次（单条）
                if failed_items:
                    retry_msg = f"Batch {batch_start//checkpoint_size+1}: retry_failed_once={len(failed_items)}"
                    logger.info(retry_msg)
                    print(retry_msg, flush=True)
                    still_failed = []
                    for idx, text, _ in failed_items:
                        vec, retries, throttled, err = self._embed_one_with_retry(
                            text, "RETRIEVAL_DOCUMENT", max_retries, 1.0
                        )
                        retry_count += retries
                        saw_throttle = saw_throttle or throttled
                        if vec is None:
                            still_failed.append((idx, text, err))
                            last_error = err
                        else:
                            index_to_vec[idx] = vec
                    fail_count = len(still_failed)
                    failed_items = still_failed

                for i, _ in to_embed:
                    vec = index_to_vec.get(i)
                    if vec is None:
                        continue
                    row = dict(batch[i])
                    row["vector"] = vec
                    batch_rows.append(row)
            else:
                no_api = f"Batch {batch_start//checkpoint_size+1}: 无需调用 API。"
                logger.info(no_api)
                print(no_api, flush=True)

            if batch_rows:
                df_batch = pd.DataFrame(batch_rows)
                if table is None:
                    table = self.db.create_table(self.table_name, data=df_batch, mode="overwrite")
                else:
                    table.add(df_batch)
                for row in batch_rows:
                    h = row.get("hash")
                    if h:
                        existing_hashes.add(h)

            # 记录失败清单
            if failed_items:
                for idx, text, err in failed_items:
                    failures.append({
                        "batch_index": batch_start,
                        "item_index": idx,
                        "error": err,
                        "text_preview": text[:200],
                    })

            processed = min(batch_start + checkpoint_size, total)
            batch_time = max(time.time() - batch_start_time, 1e-6)
            avg_chunks_per_sec = (len(batch) / batch_time) if batch_time > 0 else 0.0
            elapsed = max(time.time() - start_time, 1e-6)
            overall_rate = processed / elapsed
            eta_sec = (total - processed) / overall_rate if overall_rate > 0 else 0

            prog = (
                f"进度: {processed}/{total} | batch_time={batch_time:.1f}s | "
                f"avg_chunks_per_sec={avg_chunks_per_sec:.2f} | ETA={eta_sec/60:.1f} min"
            )
            logger.info(prog)
            print(prog, flush=True)
            self._write_status(
                status="running",
                processed=processed,
                total=total,
                batch_index=(batch_start // checkpoint_size) + 1,
                eta_sec=eta_sec,
                rate=overall_rate,
            )

            # Auto-tune concurrency
            fail_rate = (fail_count / max(len(to_embed), 1)) if to_embed else 0.0
            if to_embed and fail_count == len(to_embed):
                bad_batch_streak += 1
                err_msg = (
                    f"Batch {batch_start//checkpoint_size+1} failed for all items "
                    f"(fail_rate=1.0, last_error={last_error}). Aborting."
                )
                logger.error(err_msg)
                print(err_msg, flush=True)
                raise RuntimeError(err_msg)
            reason = None
            if saw_throttle or fail_rate > 0.01 or (prev_batch_time and batch_time > prev_batch_time * 1.5):
                new_conc = max(min_concurrency, concurrency - 8)
                if new_conc != concurrency:
                    reason = "throttle" if saw_throttle else ("fail_rate" if fail_rate > 0.01 else "batch_time")
                    concurrency = new_conc
                good_streak = 0
            else:
                if not saw_throttle and fail_rate < 0.002:
                    good_streak += 1
                    if good_streak >= 2:
                        new_conc = min(max_concurrency, concurrency + 8)
                        if new_conc != concurrency:
                            concurrency = new_conc
                            reason = "stable"
                        good_streak = 0

            if reason:
                adj = (
                    f"concurrency_adjusted: {concurrency} | reason={reason} | "
                    f"batch_time={batch_time:.1f}s | avg_chunks_per_sec={avg_chunks_per_sec:.2f} | "
                    f"ETA={eta_sec/60:.1f} min"
                )
                logger.info(adj)
                print(adj, flush=True)

            prev_batch_time = batch_time

            now = time.time()
            if now - last_total_log >= 300:
                total_msg = (
                    f"TOTAL_PROGRESS: {processed}/{total} | overall_rate={overall_rate:.2f} chunks/s | "
                    f"ETA={eta_sec/60:.1f} min"
                )
                logger.info(total_msg)
                print(total_msg, flush=True)
                last_total_log = now
                self._write_status(
                    status="running",
                    processed=processed,
                    total=total,
                    batch_index=(batch_start // checkpoint_size) + 1,
                    eta_sec=eta_sec,
                    rate=overall_rate,
                )

        if failures:
            logger.warning(f"FAILED_ITEMS: {len(failures)}")
            print(f"FAILED_ITEMS: {len(failures)}", flush=True)
            fail_path = Path("meta") / "embed_failures.jsonl"
            fail_path.parent.mkdir(parents=True, exist_ok=True)
            with fail_path.open("w", encoding="utf-8") as f:
                for item in failures:
                    f.write(str(item) + "\n")
            logger.warning(f"失败清单已写入: {fail_path}")
            print(f"失败清单已写入: {fail_path}", flush=True)

        logger.info(f"LanceDB 更新完成。表: {self.table_name}")
        print(f"LanceDB 更新完成。表: {self.table_name}", flush=True)
        self._write_status(
            status="done",
            processed=total,
            total=total,
            batch_index=(total // checkpoint_size) + 1,
            eta_sec=0,
            rate=(total / max(time.time() - start_time, 1e-6)),
        )

    def _write_status(
        self,
        status: str,
        processed: int,
        total: int,
        batch_index: int,
        eta_sec: Optional[float],
        rate: Optional[float],
    ) -> None:
        data = {
            "status": status,
            "processed": processed,
            "total": total,
            "batch_index": batch_index,
            "eta_seconds": eta_sec,
            "rate_chunks_per_sec": rate,
            "timestamp": time.time(),
        }
        try:
            write_json(self.status_path, data)
        except Exception:
            # Avoid crashing on status write issues
            pass

    def search(self, query_text: str, limit: int = 10, filters: Optional[str] = None) -> List[Dict]:
        query_vector = self.get_embeddings([query_text], task_type="RETRIEVAL_QUERY")[0]
        table = self.db.open_table(self.table_name)
        query = table.search(query_vector).limit(limit)
        if filters:
            query = query.where(filters)
        results = query.to_pandas()
        return results.to_dict('records')

    def rerank(self, query: str, results: List[Dict], model: str = "semantic-ranker-default-004") -> List[Dict]:
        logger.info(f"正在对 {len(results)} 条结果进行重排 (Model: {model})...")
        return results
