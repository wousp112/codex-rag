# Codex + RAG 论文写作系统（CLI）

## 快速开始（克隆后两步）
```bash
python -m pip install -e . --no-build-isolation --no-cache-dir --user
rag init
```
如果 `rag` 未在 PATH，可用 `python -m rag init`，或把 `%APPDATA%\\Python\\Python313\\Scripts` 加入 PATH 后重开终端。

## 放置数据
- `rag init` 已自动创建：
  - `raw/evidence/`
  - `raw/instruction/guidance/`, `raw/instruction/feedback/`, `raw/instruction/slides/`, `raw/instruction/exemplars/`
- 可引用文献：放到 `raw/evidence/`
- 指令/风格文件：放到 `raw/instruction/...`（会生成 instruction/style brief，citable=false）

## 配置 API Key（可写进 config.yaml）
- MinerU 解析：在 `config.yaml` 添加
  ```json
  "api_keys": { "mineru": "你的MINERU_API_KEY" }
  ```
  或在终端设置环境变量 `MINERU_API_KEY`。parse 会优先读环境，缺失时读 config。
- 其他外部服务同理，可扩展 `api_keys` 字段；本仓库默认 embedding/rerank 仍为 stub。

## 黄金路径命令
```bash
rag parse
rag chunk
rag embed
rag query "你的问题"
rag audit draft_tmp.md
rag verify-citations draft_tmp.md
rag export-used-sources outputs/evidence_pack_v001.md   # 用最新 evidence_pack 版本号替换
python tests/smoke_test.py                               # 可选自检
```

## 目录结构（init 后）
```
raw/      parsed/    chunks/    index/    meta/    outputs/
```

## 配置与可复现
- 默认参数写在 `config.yaml`（init 时生成），含 verify-citations k=10, T=0.55。
- build/query 元数据落盘：`meta/builds/*`、`meta/query_runs/*`、`meta/version_log.jsonl`。
- 所有对外输出 Markdown 带版本号 v001、v002…，不覆盖旧版。

## 常见问题
- 缺 MINERU_API_KEY：`rag parse` 会 stub 并提示，配置后重跑。
- 命中 citable=false：`rag query/verify-citations` 会打印 filters+summary 后硬失败。
- 页码缺失但有 char_anchor：`rag query` 会 WARNING 且 locator_quality=char_anchor。
