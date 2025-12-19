# Dry Run 指南（dry_run_v001）

## 准备
1) 将 10 篇代表性 PDF 放入 `raw/evidence/`（保持原文件名，禁止移动已有 raw/ 文件）。
2) 若有 guidance/feedback/slides/exemplars，放入 `raw/instruction/` 对应子目录（默认 citable=false）。
3) 确保 Python 3.10+ 可用；在当前目录运行命令无需安装依赖（使用 `python -m rag.cli ...`）。

## 一次跑通的命令（复制即用）
```
python -m rag.cli init
python -m rag.cli parse
python -m rag.cli chunk
python -m rag.cli embed
python -m rag.cli build-bm25   # 可选，占位
python -m rag.cli query "<你的问题>" --mode evidence
python -m rag.cli verify-citations <draft.md>
python -m rag.cli audit <draft.md>
python -m rag.cli export-used-sources outputs/evidence_pack_v001.md
```

## 预期产物路径
- 解析质量报告：`meta/parse_quality_report.md`
- 切块：`chunks/parents.jsonl`, `chunks/chunks.jsonl`, `chunks/chunk_manifest.json`
- 向量构建 manifest：`meta/builds/<build_id>/build_manifest.json`
- Evidence Pack：`outputs/evidence_pack_vNNN.md`
- Query 运行记录：`meta/query_runs/<query_id>.json`
- 审计（claims）：`outputs/audits/<draft>_claims_vNNN.md`
- 引文核查：`outputs/audits/<draft>_citations_vNNN.md`
- 已用来源清单：`outputs/used_sources_vNNN.md`

## 失败场景与指引
- 无 MINERU_API_KEY：`rag parse` 以 stub 结束，写入提示；配置后重跑。
- 无 chunks：`rag query` 会提示先执行 chunk/embed。
- evidence 检索出现 citable=false：命令将直接失败并报错。
