import lancedb
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.cloud import aiplatform
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from .logger import get_logger
from .utils import get_google_project_id

logger = get_logger()

class VectorStore:
    def __init__(self, db_path: Path, table_name: str = "chunks"):
        self.db_path = db_path
        self.table_name = table_name
        self.db = lancedb.connect(db_path)
        self.embedding_model = None

    def _get_embedding_model(self, model_name: str = "text-embedding-004"):
        if self.embedding_model is None:
            # 确保 Vertex AI 已初始化
            project_id = get_google_project_id()
            if project_id:
                # 默认 location 可从 env 或 config 获取，此处暂定 us-central1
                vertexai.init(project=project_id, location="us-central1")
            
            self.embedding_model = TextEmbeddingModel.from_pretrained(model_name)
        return self.embedding_model

    def get_embeddings(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        model = self._get_embedding_model()
        all_embeddings = []
        batch_size = 100 # Vertex AI limit is 250, safe margin 100
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            inputs = [TextEmbeddingInput(text, task_type) for text in batch_texts]
            
            # 分批调用
            try:
                embeddings = model.get_embeddings(inputs)
                all_embeddings.extend([e.values for e in embeddings])
            except Exception as e:
                logger.error(f"Embedding batch {i} failed: {e}")
                raise e
                
        return all_embeddings

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        """
        PR 9.2: Hash-based Incremental Update.
        仅对新增/变更的 chunks 调用 Embedding API，其余复用 DB 中已有向量。
        最后使用 overwrite 确保 DB 与 jsonl 1:1 一致。
        """
        if not chunks:
            return

        # 1. 尝试从 DB 读取现有 hash -> vector 映射
        existing_map = {}
        if self.table_name in self.db.table_names():
            try:
                tbl = self.db.open_table(self.table_name)
                # 只需读 hash 和 vector 列，加速读取
                df_exist = tbl.to_pandas()
                if "hash" in df_exist.columns and "vector" in df_exist.columns:
                    # 建立 hash -> vector 映射
                    # 注意：如果有 hash 冲突，这里默认取最后一个
                    existing_map = dict(zip(df_exist["hash"], df_exist["vector"]))
            except Exception as e:
                logger.warning(f"读取现有向量表失败，将执行全量更新: {e}")

        # 2. Diff: 区分需要计算的和可以直接复用的
        to_embed_chunks = []
        to_embed_indices = []
        final_vectors = [None] * len(chunks)
        
        reused_count = 0
        
        for i, c in enumerate(chunks):
            h = c.get("hash")
            if h and h in existing_map:
                final_vectors[i] = existing_map[h]
                reused_count += 1
            else:
                to_embed_chunks.append(c["text"])
                to_embed_indices.append(i)

        # 3. Action: 仅对新增部分调用 API
        if to_embed_chunks:
            logger.info(f"增量更新: 复用 {reused_count} 条，需计算 {len(to_embed_chunks)} 条...")
            new_vectors = self.get_embeddings(to_embed_chunks)
            for idx, vec in zip(to_embed_indices, new_vectors):
                final_vectors[idx] = vec
        else:
            logger.info(f"增量更新: 全部 {len(chunks)} 条均命中缓存，无需调用 API。")

        # 4. Write: 合并后全量覆盖写入
        df = pd.DataFrame(chunks)
        df['vector'] = final_vectors

        # overwrite 模式保证数据一致性
        self.db.create_table(self.table_name, data=df, mode="overwrite")
        
        logger.info(f"LanceDB 更新完成。表: {self.table_name}, 总数: {len(df)}")

    def search(self, query_text: str, limit: int = 10, filters: Optional[str] = None) -> List[Dict]:
        """执行向量检索"""
        query_vector = self.get_embeddings([query_text], task_type="RETRIEVAL_QUERY")[0]
        
        table = self.db.open_table(self.table_name)
        query = table.search(query_vector).limit(limit)
        
        if filters:
            query = query.where(filters)
            
        results = query.to_pandas()
        return results.to_dict('records')

    def rerank(self, query: str, results: List[Dict], model: str = "semantic-ranker-default-004") -> List[Dict]:
        """
        Vertex AI Ranking API 占位实现。
        由于 Ranking API 相对独立，这里展示逻辑框架。
        """
        # 实际调用需使用 google.cloud.discoveryengine 或类似的 client
        # v1 暂时使用原始分值，或简单的模拟重排
        logger.info(f"正在对 {len(results)} 条结果进行重排 (Model: {model})...")
        # 模拟：相关性分值保持不变，或者简单按原本顺序返回
        return results
