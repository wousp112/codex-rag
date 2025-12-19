# Codex + RAG 论文写作系统 v1 设计说明（spec_v001）

> 规格唯一来源：`codex_rag_论文写作系统_pr（面向非技术读者的超细版）.md`（15.x Non-negotiables + v3-1/2/3/4/5/6 优先级最高）。本文件仅做工程落地设计，不改变原规格。

## 1. 范围与目标
- 目标：在当前目录提供可运行的 Python CLI `rag`，覆盖黄金路径 parse → chunk → embed → query → evidence_pack → audit → verify-citations，确保可复现、可审计、可引用。
- 非目标：GraphRAG、UI、复杂聚类、自动参考文献生成；仅提供 BM25 命令骨架（可选实现）。

## 2. 目录与元数据（init 后）
```
raw/                       # 原始文件（严禁移动/改名）
  evidence/                # 可引用文献源（必为 citable=true）
  instruction/guidance/    # rubric 等（citable=false）
  instruction/feedback/    # 老师反馈（citable=false）
  instruction/slides/      # 课件（citable=false）
  instruction/exemplars/   # 范文（citable=false）
parsed/                    # MinerU 解析结果（每文献一文件夹，含 markdown+json）
chunks/                    # 切块产物：parents.jsonl, chunks.jsonl, chunk_manifest.json
index/                     # 向量索引、可选 bm25
meta/
  project.json             # project_id（默认从当前目录推断），创建时间、tool_version、config_hash
  builds/<build_id>/build_manifest.json
  query_runs/<query_id>.json
  parse_quality_report.md
  instruction_brief.md
  style_brief.md
  version_log.jsonl
  health_report.md (按需)
outputs/                   # 所有对外可读 md（版本化，v001 起）
```

## 3. 核心字段（遵循 PR）
- 文献级：`doc_uid`（唯一）、`source_type`、`source_subtype`、`citable`、`citation_key`、`publisher/organisation`、`url`、`captured_at`、`accessed_at`、`published_date`。
- Parent：`parent_id`(如 doc_uid:p003)、`page_index/page_start/page_end`、`section_path`、`parent_text`、`hash`。
- Child：`chunk_id`、`parent_id`、`doc_uid`、`char_start/char_end`、`text`、`hash`。
- Evidence：`doc_uid`、`citation_key`、`source_type`、`citable`、`retrieval_score`、`parent_id`、`page_index/page_start/page_end` 或 `char_start/char_end + anchor_begin/anchor_end (+ section_path)`、`locator_quality`、`snippet`、`exact_quote(≤60 words 推荐)`。
- 运行元数据：`build_id=timestamp+config_hash+tool_version`、`query_id`、`q_zh/q_en`、`filters`、`top_k`、`fusion/rerank params`、`returned doc_uids/scores`。

## 4. 数据流与命令接口
### 4.1 init
- 生成目录骨架：raw/ parsed/ chunks/ index/ meta/ outputs/。
- 生成：`config.yaml`（默认值写死：verify_citations_k=10、T=0.55、rerank_on、embedding/rerank/provider 配置、counterevidence_mode=off）、`meta/project.json`、`AGENT.md`。
- 约束：只在空目录或首次运行写入 config；后续策略调整需写入决策文件而非直接改 config（除非用户明确同意）。

### 4.2 parse（MinerU 编排）
- 扫描 raw/ 全部原始文件；按批（≤200 文件）申请上传；PUT 上传；轮询任务；下载 `full_zip_url` 解压到 parsed/。
- 预检：页数>600 或 >200MB → 本地按页切分（≤500 页，递归二分）并写 `split_manifest`；保持稳定 doc_uid 绑定。
- 清洗：轻量 Text Normalization（断词连字符合并、空白规范、页眉页脚重复行去重阈值≥0.6 记录模板、References 标记 source_subtype=references）。
- 输出：parsed/ 每文献目录 + `meta/parse_quality_report.md`。
- 错误：外部 API key 缺失或 MinerU 失败需清晰报错与配置指引。

### 4.3 chunk
- 输入 parsed/ markdown+json。
- Parent：优先页级（parent_id=doc_uid:pXXX）；缺页信息时按页提示退化；保留 page_index。
- Child：句子切分 + 组块目标 ~200 tokens（80–300），overlap 0–10%；记录 char_start/end。
- 产物：`chunks/parents.jsonl`、`chunks/chunks.jsonl`、`chunks/chunk_manifest.json`（含 hash/增量信息）。

### 4.4 embed
- 读取 chunks.jsonl 未变更 child；调用可插拔 embedding provider（默认 Vertex `gemini-embedding-001`，可 batch/concurrency/backoff）；向量存储到 `index/`（本地向量文件或轻量 faiss/npz）。
- 写 build_id → meta/builds/<build_id>/build_manifest.json（记录输入 hash、模型、并发、重试、provider、config_hash）。

### 4.5 build-bm25（stub 必有命令）
- 占位实现：提示如何启用（如安装 `rank-bm25` 或 `whoosh`），若未启用则写明“未构建 bm25 索引”。

### 4.6 query
- 输入：问题（中文/英文）、可选 `--project` 覆盖、`--mode evidence|papers`（默认 evidence）、filters（年份、source_type 等）。
- 处理：中文→英文改写 q_en；dense 检索 q_zh+q_en；可选 BM25（若索引存在）；rerank（semantic-ranker-default-004 固定）；child top_k→按 parent_id 聚合→parent 回填。
- 输出：`outputs/evidence_pack_v###.md`（版本递增），包含 build_id/query_id、Applied filters、Returned sources summary、LOCATOR_QUALITY；仅 citable=true；若出现 citable=false 直接报错终止；缺 doc_uid/parent_id 硬失败；无页码但有 char_anchor → WARN 继续。
- `--mode papers`：仅对同一批召回结果按 doc_uid 聚合，不触发新检索/embedding/rerank。
- 同步落盘：`meta/query_runs/<query_id>.json`。

### 4.7 audit
- 输入 draft md/ txt。
- 识别强断言（因果/比较/定量/普遍化/建议/最高级）；链接已用 Evidence；标记 `EVIDENCE_NEEDED`；可选 counterevidence (soft/strict) 逻辑。
- 输出表：`outputs/audits/<draft_version>_claims_v001.md`（claim_id | claim_text | claim_type | linked_evidence | status | suggested_queries）。

### 4.8 verify-citations
- 默认参数写死：k=10，threshold T=0.55（config 默认值）。
- 对含 `{#doc_uid}` 的句子，仅在该 doc 的 child chunks 内检索；support_score=best_score；判定 OK/WEAK/MISSING；source 需 citable=true，否则失败。
- 输出：`outputs/audits/<draft_version>_citations_v001.md`（或 json+md 摘要）。

### 4.9 meta set
- 用于覆盖元数据（如 accessed_at）：`rag meta set --doc_uid <id> --accessed_at YYYY-MM-DD`；落盘更新对应记录并写 version_log.jsonl。

### 4.10 export-used-sources
- 读取最近一次 Evidence Pack 或指定文件，导出使用的 doc_uid 列表/元数据到 `outputs/used_sources_v###.md`，便于 Zotero 处理。

## 5. 配置与提供者
- `config.yaml` 默认写死：
  - embedding: provider=vertex, model=gemini-embedding-001, output_dim=1536, task_type per document/query, concurrency/backoff/timeouts。
  - rerank: enabled=true, model=semantic-ranker-default-004, candidate_k=50, topN=10。
  - verify_citations_k=10, verify_citations_threshold_T=0.55。
  - counterevidence_mode=off（可 soft/strict）。
  - locator 优先级：page → char_anchor；页眉页脚重复行阈值 0.6。
- Provider keys 从环境变量/.env 读取；日志禁止打印 key；若缺失须明确报错 + 配置指引。

## 6. 版本化与可复现
- 所有对外输出为 Markdown，文件名带 vNNN 递增；禁止覆盖旧版。
- 变更记录写入 `meta/version_log.jsonl`（包含文件、from→to、timestamp、reason）。
- 每次 build/query 记录 build_id/query_id，并在 Evidence Pack 顶部打印。

## 7. 安全与防泄漏
- Evidence 模式强制过滤 `citable=true`；若结果含 citable=false → 立即报错并打印 Applied filters + Returned sources summary。
- Instruction/Style 文件（raw/instruction/**）读取生成 meta briefs，标记 citable=false，不得进入 Evidence Pack。

## 8. DoD 映射（对应 15.7 九条）
1) Evidence Pack 仅 citable=true → query 过滤 + 违规报错。
2) 每条 evidence 有 locator（page 或 char_anchor）；缺失 doc_uid/parent_id 硬失败，缺页但有 char_anchor 警告。
3) 所有 draft 输出附 `Sources used (doc_uid list)`（query/audit 写入）。
4) verify-citations 输出 OK/WEAK/MISSING + suggested_query，k=10,T=0.55 写死。
5) 每次 build 写 meta/builds/<build_id>/build_manifest.json。
6) 每次 query 写 meta/query_runs/<query_id>.json。
7) parse 后生成 meta/parse_quality_report.md。
8) chunk_manifest/hash 支持增量，新增 PDF 后增量更新并可检索。
9) 所有改版生成新 md（v 递增）并写 meta/version_log.jsonl。

## 9. 执行顺序（黄金路径命令草案）
1) `rag init`
2) 放置原始文件到 raw/...（不可移动 raw/ 内既有文件）
3) `rag parse`
4) `rag chunk`
5) `rag embed`
6) `rag build-bm25`（可选/stub）
7) `rag query \"<your question>\" --mode evidence`
8) `rag audit <draft>.md`
9) `rag verify-citations <draft>.md`
10) `rag export-used-sources <evidence_pack>.md`

## 10. 风险与待确认点
- MinerU/Vertex/Rerank API key 未配置时的回退路径：必须显式报错 + 配置指引（不静默降级）。
- 本地向量存储格式选择：初版采用 faiss/npz 轻量实现，可切换 provider 时在 config 中声明；BM25 仅 stub。
- papers 模式仅聚合同一召回结果，不再触发检索；需保存上次 child 命中列表以供聚合。
