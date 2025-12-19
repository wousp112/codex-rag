import json
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from .logger import get_logger
from .utils import ensure_dir, write_json, now_ts

logger = get_logger()

class ParentChildChunker:
    def __init__(self, child_size: int = 400, overlap: int = 50):
        # 字符数估算：中文/英文混合，400 char 约等于 200 tokens
        self.child_size = child_size
        self.overlap = overlap

    def _sha(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _find_json_content(self, doc_dir: Path) -> List[Dict]:
        """尝试找到并读取 MinerU 的 content_list.json"""
        # 常见命名模式
        candidates = list(doc_dir.glob("*_content_list.json")) + \
                     list(doc_dir.glob("model.json")) + \
                     list(doc_dir.glob("*.json"))
        
        for json_path in candidates:
            if "manifest" in json_path.name: continue # 跳过 manifest
            try:
                data = json.loads(json_path.read_text(encoding='utf-8'))
                # 检查是否是列表且包含 page_idx (MinerU 标准格式)
                if isinstance(data, list) and len(data) > 0 and "page_idx" in data[0]:
                    return data
                # 某些版本可能包裹在 data 字段里
                if isinstance(data, dict) and "pdf_info" in data:
                     # 或者是 doc_layout_result
                     return data.get("pdf_info", [])
            except Exception:
                continue
        return []

    def process_document(self, doc_dir: Path, doc_meta: Dict[str, Any]) -> tuple[List[Dict], List[Dict]]:
        """
        PR 2.5: 按页聚合 Parent，再切分 Child
        """
        doc_uid = doc_meta["doc_uid"]
        
        # 1. 尝试读取结构化 JSON
        content_list = self._find_json_content(doc_dir)
        
        parents = []
        childs = []
        
        if content_list:
            logger.info(f"[{doc_uid}] 发现结构化 JSON，执行按页分块...")
            parents, childs = self._chunk_by_page_json(doc_uid, content_list, doc_meta)
        else:
            logger.info(f"[{doc_uid}] 未找到结构化 JSON，退化为 Markdown 全文分块...")
            # 兜底：读 MD 文件
            md_files = list(doc_dir.glob("*.md"))
            if md_files:
                text = md_files[0].read_text(encoding='utf-8')
                parents, childs = self._chunk_fallback_text(doc_uid, text, doc_meta)

        return parents, childs

    def _chunk_by_page_json(self, doc_uid: str, content_list: List[Dict], doc_meta: Dict) -> tuple[List[Dict], List[Dict]]:
        """基于 MinerU JSON 的按页聚合逻辑"""
        # Group by page_idx
        pages = {}
        for item in content_list:
            # 过滤掉图片/表格的非文本占位 (可选，视需求而定)
            if item.get("type") in ["image", "table_caption"]: 
                pass 
            
            text = item.get("text", "")
            if not text.strip():
                continue
                
            pidx = item.get("page_idx", 0)
            if pidx not in pages:
                pages[pidx] = []
            pages[pidx].append(text)

        parents = []
        childs = []
        
        sorted_pidxs = sorted(pages.keys())
        for pidx in sorted_pidxs:
            # 聚合一页的文本作为 Parent
            page_text = "\n".join(pages[pidx])
            parent_id = f"{doc_uid}:p{pidx:04d}"
            
            parent_record = {
                "doc_uid": doc_uid,
                "parent_id": parent_id,
                "page_index": pidx, # 0-based from MinerU
                "parent_text": page_text,
                "citable": doc_meta.get("citable", True),
                "source_type": doc_meta.get("source_type", "evidence"),
                "hash": self._sha(page_text)
            }
            parents.append(parent_record)
            
            # 切分 Child
            page_childs = self._split_text_smart(page_text, parent_id, doc_uid, doc_meta, pidx)
            childs.extend(page_childs)
            
        return parents, childs

    def _chunk_fallback_text(self, doc_uid: str, text: str, doc_meta: Dict) -> tuple[List[Dict], List[Dict]]:
        """兜底：无页码信息的纯文本分块"""
        # 简单将全文切分为固定大小的 Parent (例如 2000 chars)
        parent_size = 2000
        parents = []
        childs = []
        
        start = 0
        p_idx = 0
        while start < len(text):
            end = start + parent_size
            # 尝试在换行符处截断
            if end < len(text):
                next_newline = text.find('\n', end)
                if next_newline != -1 and next_newline - end < 200:
                    end = next_newline
            
            p_text = text[start:end]
            parent_id = f"{doc_uid}:p_fallback_{p_idx:03d}"
            
            parents.append({
                "doc_uid": doc_uid,
                "parent_id": parent_id,
                "page_index": None, # 缺失
                "parent_text": p_text,
                "citable": doc_meta.get("citable", True),
                "source_type": doc_meta.get("source_type", "evidence"),
                "hash": self._sha(p_text)
            })
            
            p_childs = self._split_text_smart(p_text, parent_id, doc_uid, doc_meta, None)
            childs.extend(p_childs)
            
            start = end
            p_idx += 1
            
        return parents, childs

    def _split_text_smart(self, text: str, parent_id: str, doc_uid: str, doc_meta: Dict, page_index: Optional[int]) -> List[Dict]:
        """
        智能切分 Child: 优先按段落(\n\n) -> 句子(。！？.) -> 强制字符截断
        """
        chunks = []
        
        start = 0
        text_len = len(text)
        c_idx = 0
        
        while start < text_len:
            end = start + self.child_size
            
            # 寻找最佳截断点 (Lookback)
            cut_point = end
            if cut_point < text_len:
                # 优先级 1: 双换行 (段落)
                last_para = text.rfind('\n\n', start, end)
                # 优先级 2: 单换行
                last_line = text.rfind('\n', start, end)
                # 优先级 3: 句末标点
                last_punct = -1
                for p in ['. ', '。', '！', '!', '?', '？']:
                    idx = text.rfind(p, start, end)
                    if idx > last_punct:
                        last_punct = idx + len(p)
                
                if last_para != -1 and (end - last_para) < self.child_size * 0.4:
                    cut_point = last_para + 2
                elif last_punct != -1 and (end - last_punct) < self.child_size * 0.4:
                    cut_point = last_punct
                elif last_line != -1 and (end - last_line) < self.child_size * 0.2:
                    cut_point = last_line + 1
            
            # 修正边界
            cut_point = min(cut_point, text_len)
            
            # 提取
            chunk_text = text[start:cut_point].strip()
            
            if len(chunk_text) > 20: # 忽略太短的碎片
                chunks.append({
                    "chunk_id": f"{parent_id}:c{c_idx:02d}", # ID 包含 parent_id
                    "parent_id": parent_id,
                    "doc_uid": doc_uid,
                    "text": chunk_text,
                    "char_start": start,
                    "char_end": start + len(chunk_text), # 近似，因为 strip 可能会变
                    "page_index": page_index,
                    "citable": doc_meta.get("citable", True),
                    "source_type": doc_meta.get("source_type", "evidence"),
                    "hash": self._sha(chunk_text)
                })
                c_idx += 1
            
            # 滑动 (如果刚才没有完美截断，强制步进)
            if cut_point == start: # 防止死循环
                start += self.child_size
            else:
                # Overlap 处理：回退一部分
                start = max(cut_point - self.overlap, start + 1)
                
        return chunks

def run_chunking(parsed_dir: Path, chunks_dir: Path, meta_dir: Path):
    chunker = ParentChildChunker()
    ensure_dir(chunks_dir)
    
    all_parents = []
    all_childs = []
    
    for doc_dir in parsed_dir.iterdir():
        if not doc_dir.is_dir():
            continue
            
        doc_uid = doc_dir.name
        
        # 读取文档元数据
        doc_meta_file = meta_dir / f"{doc_uid}.json"
        if doc_meta_file.exists():
            with open(doc_meta_file, 'r', encoding='utf-8') as f:
                doc_meta = json.load(f)
        else:
            # 兜底
            doc_meta = {
                "doc_uid": doc_uid, 
                "citable": True, 
                "source_type": "evidence"
            }

        parents, childs = chunker.process_document(doc_dir, doc_meta)
        all_parents.extend(parents)
        all_childs.extend(childs)

    # 写入结果
    parents_path = chunks_dir / "parents.jsonl"
    chunks_path = chunks_dir / "chunks.jsonl"
    
    with open(parents_path, 'w', encoding='utf-8') as f:
        for p in all_parents:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
            
    with open(chunks_path, 'w', encoding='utf-8') as f:
        for c in all_childs:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            
    # 更新清单
    manifest = {
        "documents": len(all_parents),
        "chunks": len(all_childs),
        "generated_at": now_ts()
    }
    write_json(chunks_dir / "chunk_manifest.json", manifest)
    
    return len(all_childs)