# MinerU API v4 接口文档 (本地存档)

## 1. 简介
MinerU API 提供基于深度学习的文档解析服务，支持 PDF 转换为 Markdown/JSON。

## 2. 核心流程 (本地文件)
1.  **申请上传链接** (`POST /file-urls/batch`) -> 获取 `batch_id` 和 `upload_url`。
2.  **上传文件** (`PUT upload_url`) -> 系统自动检测并开始解析。
3.  **轮询结果** (`GET /extract-results/batch/{batch_id}`) -> 获取解析状态与下载链接。

## 3. 接口详情

### 3.1 批量申请上传链接
- **Endpoint**: `POST https://mineru.net/api/v4/file-urls/batch`
- **Request**:
  ```json
  {
    "files": [
      {"name": "demo.pdf", "data_id": "unique_id_1"}
    ],
    "model_version": "vlm"
  }
  ```
- **Response**:
  ```json
  {
    "code": 0,
    "data": {
      "batch_id": "...",
      "file_urls": ["https://..."]
    }
  }
  ```

### 3.2 批量查询结果
- **Endpoint**: `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}`
- **Response**:
  ```json
  {
    "code": 0,
    "data": {
      "extract_result": [
        {
          "state": "done",
          "full_zip_url": "https://...",
          "data_id": "unique_id_1"
        }
      ]
    }
  }
  ```

## 4. 注意事项
- 上传后无需手动提交任务接口。
- 轮询时关注 `state` 字段 (`running`, `done`, `failed`)。
