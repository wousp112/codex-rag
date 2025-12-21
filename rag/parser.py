import os
import time
import zipfile
import requests
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from PyPDF2 import PdfReader, PdfWriter
from tqdm import tqdm
from .logger import get_logger
from .utils import ensure_dir, write_json, read_json, now_ts

logger = get_logger()

class MinerUParser:
    def __init__(self, api_key: str, base_url: str = "https://mineru.net/api/v4"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        # Bypass environment proxies (some setups point to localhost:9 and break MinerU)
        self.session = requests.Session()
        self.session.trust_env = False

    def _get_file_hash(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def split_pdf(self, file_path: Path, output_dir: Path, max_pages: int = 500) -> List[Path]:
        """按照页数限制拆分 PDF"""
        try:
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
        except Exception as e:
            logger.warning(f"读取 PDF {file_path.name} 失败，跳过拆分: {e}")
            return [file_path]
        
        if total_pages <= max_pages:
            return [file_path]

        logger.info(f"文件 {file_path.name} 共有 {total_pages} 页，超过限制 {max_pages}，正在拆分...")
        split_files = []
        for i in range(0, total_pages, max_pages):
            writer = PdfWriter()
            end_page = min(i + max_pages, total_pages)
            for page in range(i, end_page):
                writer.add_page(reader.pages[page])
            
            part_name = f"{file_path.stem}_part_{i//max_pages + 1}{file_path.suffix}"
            part_path = output_dir / part_name
            with open(part_path, "wb") as f:
                writer.write(f)
            split_files.append(part_path)
            
            # 写入拆分清单
            manifest_path = part_path.with_suffix(".split_manifest.json")
            write_json(manifest_path, {
                "original_file": str(file_path),
                "page_range": [i, end_page],
                "hash": self._get_file_hash(part_path)
            })
            
        return split_files

    def parse_files(self, files: List[Path], output_root: Path, model_version: str = "vlm"):
        """批量解析主流程 (修正版: Get URLs & BatchID -> Upload -> Poll Results)"""
        
        # 0. 准备文件信息
        files_map = {self._get_file_hash(f): f for f in files}
        files_payload = [{"name": f.name, "data_id": h} for h, f in files_map.items()]
        
        if not files_payload:
            logger.warning("没有需要解析的文件。")
            return

        # 1. 申请上传链接并获取 Batch ID (POST /file-urls/batch)
        logger.info("正在申请上传链接...")
        resp_urls = self.session.post(
            f"{self.base_url}/file-urls/batch", 
            json={"files": files_payload, "model_version": model_version}, 
            headers=self.headers
        )
        if resp_urls.status_code != 200:
            logger.error(f"获取上传链接失败 (HTTP {resp_urls.status_code}): {resp_urls.text}")
            return

        resp_json = resp_urls.json()
        if resp_json.get("code") != 0:
            logger.error(f"API 错误: {resp_json.get('msg')}")
            return

        batch_id = resp_json.get("data", {}).get("batch_id")
        file_urls = resp_json.get("data", {}).get("file_urls", [])

        if not batch_id or not file_urls:
            logger.error(f"未获取到有效的 Batch ID 或 URL。响应: {resp_json}")
            return

        logger.info(f"获取到 Batch ID: {batch_id}")

        # 映射逻辑：假设返回的 file_urls 顺序与请求的 files_payload 顺序一致
        url_data = []
        for meta, url in zip(files_payload, file_urls):
            url_data.append({
                "data_id": meta["data_id"],
                "name": meta["name"],
                "upload_url": url
            })

        # 2. 上传文件 (系统会自动检测上传完成并开始任务，无需手动提交)
        logger.info(f"正在上传 {len(url_data)} 个文件到 MinerU...")
        for f_info in tqdm(url_data):
            data_id = f_info["data_id"]
            upload_url = f_info["upload_url"]
            file_path = files_map.get(data_id)
            
            if file_path:
                with open(file_path, "rb") as f:
                    put_resp = self.session.put(upload_url, data=f)
                    if put_resp.status_code != 200:
                        logger.error(f"文件 {file_path.name} 上传失败: {put_resp.text}")

        # 3. 轮询状态 (直接使用 step 1 的 batch_id)
        logger.info("等待解析完成...")
        while True:
            status_resp = self.session.get(f"{self.base_url}/extract-results/batch/{batch_id}", headers=self.headers)
            if status_resp.status_code != 200:
                logger.warning(f"轮询状态失败: {status_resp.text}，稍后重试...")
                time.sleep(10)
                continue

            status_data = status_resp.json().get("data", {})
            # 根据文档，字段名为 extract_result (list)
            extract_list = status_data.get("extract_result", [])
            
            if not extract_list:
                logger.info("任务仍在队列中，暂无结果...")
                time.sleep(5)
                continue

            all_done = all(item["state"] in ["done", "failed"] for item in extract_list)
            done_count = sum(1 for item in extract_list if item["state"] == "done")
            
            if all_done:
                logger.info(f"解析结束。成功: {done_count}, 失败: {len(extract_list) - done_count}")
                break
            
            # 打印进度 (从 extract_progress 中提取)
            running_count = sum(1 for item in extract_list if item["state"] == "running")
            if running_count > 0:
                logger.info(f"正在解析 {running_count} 个文件...")
            
            time.sleep(10)

        # 4. 下载并解压
        for item in extract_list:
            if item["state"] == "done":
                # 优先使用 data_id (若有) 作为目录名，否则用 file_name
                out_name = item.get("data_id") or item.get("file_name")
                full_zip_url = item.get("full_zip_url")
                if full_zip_url:
                    self._download_and_extract(full_zip_url, output_root / out_name)

    def _download_and_extract(self, url: str, target_dir: Path):
        ensure_dir(target_dir)
        zip_path = target_dir / "result.zip"
        try:
            resp = self.session.get(url)
            with open(zip_path, "wb") as f:
                f.write(resp.content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            logger.info(f"已解压: {target_dir.name}")
        except Exception as e:
            logger.error(f"下载/解压失败 {url}: {e}")
        finally:
            if zip_path.exists():
                try:
                    os.remove(zip_path)
                except PermissionError:
                    logger.warning(f"无法删除临时文件（可能被占用）：{zip_path}")
