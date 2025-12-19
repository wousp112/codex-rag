# Dry Run 指南（dry_run_v002）

## 准备
1) 放 10 篇代表性 PDF 到 `raw/evidence/`（保持文件名，勿动 raw/ 既有文件）。
2) 若有 guidance/feedback/slides/exemplars，放入 `raw/instruction/` 对应子目录；系统会生成 `meta/instruction_brief.md` 与 `meta/style_brief.md`（citable=false，默认不入 Evidence）。
3) 确保 Python 3.10+，无需额外安装依赖：全部命令使用 `python -m rag.cli ...`。

## 一次跑通命令
```
python -m rag.cli init
python -m rag.cli parse
python -m rag.cli chunk
python -m rag.cli embed
python -m rag.cli build-bm25        # 可选，占位
python -m rag.cli query "<你的问题>" --mode evidence
python -m rag.cli audit <draft.md>
python -m rag.cli verify-citations <draft.md>
python -m rag.cli export-used-sources outputs/evidence_pack_vXXX.md
```

## 预期产物
- Instruction briefs：`meta/instruction_brief.md`, `meta/style_brief.md`
- 解析质量报告：`meta/parse_quality_report.md`
- 切块：`chunks/parents.jsonl`, `chunks/chunks.jsonl`, `chunks/chunk_manifest.json`
- 构建信息：`meta/builds/<build_id>/build_manifest.json`
- Evidence Pack：`outputs/evidence_pack_vNNN.md`（含 build_id/query_id/LOCATOR_QUALITY）
- Query 记录：`meta/query_runs/<query_id>.json`
- 审计：`outputs/audits/<draft>_claims_vNNN.md`（含 Sources used）
- 引文核查：`outputs/audits/<draft>_citations_vNNN.md`（头部展示 k=10, T=0.55，含 Sources used）
- 已用来源：`outputs/used_sources_vNNN.md`

## 常见失败与处理
- 缺 MINERU_API_KEY：parse 以 stub 结束并提示；配置后重跑。
- chunks 为空：query/embed/verify 会提示先 chunk。
- 检索命中含 citable=false 或缺 doc_uid/parent_id：打印 Applied filters + Returned sources summary 后硬失败。
- 页码缺失但有 char_anchor：query 会 WARNING 并将 locator_quality=char_anchor。
