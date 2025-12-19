from __future__ import annotations

import argparse
import json
import sys
import os
import hashlib
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# 立即加载 .env 环境变量
load_dotenv()

from . import __version__
from .config import load_config, save_default_config, config_hash, DEFAULT_CONFIG
from .errors import RagError, ErrorCode
from .logger import get_logger
from .utils import (
    ensure_dir,
    write_json,
    read_json,
    next_version_path,
    now_ts,
    append_version_log,
    load_version_log,
    human_warn,
)
from .versioning import generate_build_id, generate_query_id, latest_build_manifest

logger = get_logger()


def project_root() -> Path:
    return Path('.').resolve()


def meta_dir(cfg: dict) -> Path:
    return project_root() / cfg['paths']['meta']


def outputs_dir(cfg: dict) -> Path:
    return project_root() / cfg['paths']['outputs']


def _fail(msg: str, code: ErrorCode = ErrorCode.GENERAL):
    raise RagError(msg, code)


def _write_version_log(cfg: dict, file_path: Path, action: str, note: str = ''):
    log_path = meta_dir(cfg) / 'version_log.jsonl'
    append_version_log(
        log_path,
        {'timestamp': now_ts(), 'file': str(file_path), 'action': action, 'note': note},
    )


def _require_init():
    if not Path('config.yaml').exists():
        _fail('项目未初始化，请先运行 `rag init`。', ErrorCode.CONFIG_MISSING)


def handle_exception(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RagError as e:
            logger.error(f"{e.code}: {e}")
            sys.exit(1)

    return wrapper


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _print_filters_and_summary(records: List[dict]):
    # Applied filters fixed为 citable=true
    print("Applied filters: citable=true")
    summary = {}
    for r in records:
        st = r.get("source_type", "unknown")
        summary[st] = summary.get(st, 0) + 1
    total = sum(summary.values())
    parts = [f"{k}:{v}" for k, v in summary.items()]
    print(f"Returned sources summary: total={total}; " + ", ".join(parts))


# Command implementations --------------------------------------------------


@handle_exception
def cmd_init(args):
    root = project_root()
    # 基础目录
    base_paths = ['raw', 'parsed', 'chunks', 'index', 'meta', 'outputs']
    for p in base_paths:
        ensure_dir(root / p)
    
    # outputs 子目录 (PR 9.1)
    outputs_path = root / 'outputs'
    ensure_dir(outputs_path / 'drafts')
    ensure_dir(outputs_path / 'evidence')
    ensure_dir(outputs_path / 'audits')

    # raw 子目录：evidence + instruction 各类
    raw = root / 'raw'
    ensure_dir(raw / 'evidence')
    ensure_dir(raw / 'instruction' / 'guidance')
    ensure_dir(raw / 'instruction' / 'feedback')
    ensure_dir(raw / 'instruction' / 'slides')
    ensure_dir(raw / 'instruction' / 'exemplars')

    cfg_path = root / 'config.yaml'
    if cfg_path.exists():
        logger.info('config.yaml 已存在，跳过写入（如需变更请按决策流程修改）。')
    else:
        save_default_config(cfg_path)
        logger.info('已生成 config.yaml 默认配置。')

    meta_path = root / 'meta'
    ensure_dir(meta_path / 'builds')
    ensure_dir(meta_path / 'query_runs')
    load_version_log(meta_path / 'version_log.jsonl')

    project_json = meta_path / 'project.json'
    if not project_json.exists():
        proj = {
            'project_id': root.name,
            'created_at': now_ts(),
            'tool_version': __version__,
            'config_hash': config_hash(DEFAULT_CONFIG),
        }
        write_json(project_json, proj)
        logger.info('已写入 meta/project.json。')
    else:
        logger.info('meta/project.json 已存在，未覆盖。')

    agent_md = root / 'AGENT.md'
    if not agent_md.exists():
        agent_md.write_text(_agent_md_template(), encoding='utf-8')
        logger.info('已生成 AGENT.md。')
    else:
        logger.info('AGENT.md 已存在，未覆盖。')

    print('init 完成。')
    _write_version_log(DEFAULT_CONFIG, root / 'config.yaml', 'create', 'init')
    _write_version_log(DEFAULT_CONFIG, root / 'AGENT.md', 'create', 'init')


def _agent_md_template() -> str:
    return """# AGENT 边界与操作手册
- 工作边界：仅在当前目录及子目录读写；禁止改动 raw/ 内已有原始文件；不得上传密钥。
- 命令白名单：rag init/parse/chunk/embed/build-bm25/query/audit/verify-citations/meta set/export-used-sources。
- 自然语言→命令映射：初始化→rag init；解析→rag parse；分块→rag chunk；嵌入→rag embed；检索→rag query；审计→rag audit；引文核查→rag verify-citations。
- Evidence Pack 仅消费 citable=true 数据；出现 citable=false 必须报错终止。
- 失败兜底：外部 API 缺失或调用失败时给出清晰报错与配置指引，不静默降级。
- 输出版本化：所有 md 输出按 vNNN 递增，不覆盖旧版；记录 meta/version_log.jsonl。
- Instruction Assimilation：如 raw/instruction/** 存在，需生成 meta/instruction_brief.md 与 meta/style_brief.md，并在索引中标记 citable=false，禁止进入 Evidence Pack。
"""


@handle_exception
def cmd_parse(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    root = project_root()
    raw_dir = root / cfg['paths']['raw']
    parsed_dir = root / cfg['paths']['parsed']
    meta_path = meta_dir(cfg)
    ensure_dir(parsed_dir)

    # 1. 扫描所有原始文件
    all_files = [f for f in raw_dir.rglob('*.*') if f.is_file() and f.suffix.lower() in ['.pdf', '.docx', '.pptx', '.png', '.jpg']]

    if not all_files:
        print(human_warn('未找到原始文件（pdf/docx/pptx/png/jpg），请放入 raw/ 对应子目录。'))
        _instruction_assimilation(cfg, raw_dir)
        return

    api_key = os.environ.get('MINERU_API_KEY') or cfg.get('api_keys', {}).get('mineru')
    if not api_key or api_key == "REPLACE_WITH_MINERU_API_KEY":
        _fail("缺少 MINERU_API_KEY，请在环境变量或 config.yaml 中配置。", ErrorCode.CONFIG_INVALID)

    # 2. 预处理：PDF 拆分
    from .parser import MinerUParser
    parser = MinerUParser(api_key)
    
    files_to_parse = []
    temp_split_dir = root / "meta" / "tmp_splits"
    ensure_dir(temp_split_dir)

    logger.info("正在执行预检与拆分计划...")
    for f in all_files:
        if f.suffix.lower() == '.pdf':
            parts = parser.split_pdf(f, temp_split_dir)
            files_to_parse.extend(parts)
        else:
            files_to_parse.append(f)

    # 3. 提交 MinerU 解析
    logger.info(f"计划解析 {len(files_to_parse)} 个文件单元...")
    parser.parse_files(files_to_parse, parsed_dir)

    # 4. 生成质量报告与指令吸收
    report = meta_path / 'parse_quality_report.md'
    report.write_text(
        f"## Parse Quality Report\n- 状态：完成\n- 原始文件数：{len(all_files)}\n- 解析单元数：{len(files_to_parse)}\n- 时间：{now_ts()}\n",
        encoding='utf-8',
    )
    _instruction_assimilation(cfg, raw_dir)
    print("parse 流程执行完毕。")


def _instruction_assimilation(cfg: dict, raw_dir: Path):
    instr_root = raw_dir / "instruction"
    meta_path = meta_dir(cfg)
    brief = meta_path / "instruction_brief.md"
    style = meta_path / "style_brief.md"
    ensure_dir(meta_path)
    if not instr_root.exists():
        brief.write_text("## Instruction Brief\n- 未检测到 instruction 文件，保持空 brief（citable=false）。\n", encoding="utf-8")
        style.write_text("## Style Brief\n- 未检测到 style/instruction 文件。\n", encoding="utf-8")
        _write_version_log(cfg, brief, "create", "instruction_brief")
        _write_version_log(cfg, style, "create", "style_brief")
        return
    files = [p for p in instr_root.rglob("*") if p.is_file()]
    if not files:
        brief.write_text("## Instruction Brief\n- instruction 目录为空。\n", encoding="utf-8")
        style.write_text("## Style Brief\n- instruction 目录为空。\n", encoding="utf-8")
        _write_version_log(cfg, brief, "create", "instruction_brief")
        _write_version_log(cfg, style, "create", "style_brief")
        return
    brief_lines = ["## Instruction Brief", "- citable=false", "- 文件列表："]
    for f in files:
        brief_lines.append(f"- {f.relative_to(raw_dir)}")
    brief.write_text("\n".join(brief_lines), encoding="utf-8")
    style.write_text("## Style Brief\n- instruction 资料需人工查看（citable=false）。\n", encoding="utf-8")
    _write_version_log(cfg, brief, "create", "instruction_brief")
    _write_version_log(cfg, style, "create", "style_brief")


def _write_empty_chunk_outputs(chunks_dir: Path, cfg: dict):
    parents = chunks_dir / 'parents.jsonl'
    chunks = chunks_dir / 'chunks.jsonl'
    manifest = chunks_dir / 'chunk_manifest.json'
    parents.write_text('', encoding='utf-8')
    chunks.write_text('', encoding='utf-8')
    write_json(
        manifest,
        {'documents': 0, 'chunks': 0, 'generated_at': now_ts(), 'parent_hashes': [], 'child_hashes': []},
    )
    _write_version_log(cfg, parents, 'create', 'chunks')
    _write_version_log(cfg, chunks, 'create', 'chunks')
    _write_version_log(cfg, manifest, 'create', 'chunk_manifest')


@handle_exception
def cmd_chunk(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    root = project_root()
    parsed_dir = root / cfg['paths']['parsed']
    chunks_dir = root / cfg['paths']['chunks']
    meta_path = meta_dir(cfg)
    
    from .chunker import run_chunking
    logger.info("正在执行分块 (Parent-Child 策略)...")
    count = run_chunking(parsed_dir, chunks_dir, meta_path)
    
    if count == 0:
        print(human_warn('未发现可分块的解析内容，请先执行 rag parse。'))
    else:
        print(f'分块完成，共生成 {count} 条 child 记录。')


@handle_exception
def cmd_embed(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    root = project_root()
    chunks_path = Path(cfg['paths']['chunks']) / 'chunks.jsonl'
    if not chunks_path.exists():
        _fail('未找到 chunks/chunks.jsonl，请先运行 rag chunk。', ErrorCode.EMBED_NO_CHUNKS)

    import json
    chunks = []
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))

    if not chunks:
        print(human_warn('chunks.jsonl 为空，未生成向量。'))
        return

    from .vector_store import VectorStore
    db_dir = root / cfg['paths']['index'] / "lancedb"
    ensure_dir(db_dir)
    
    vs = VectorStore(db_dir)
    logger.info(f"正在为 {len(chunks)} 条 chunk 生成向量并存入 LanceDB...")
    vs.add_chunks(chunks)

    # 写入 build manifest
    cfg_hash = config_hash(cfg)
    build_id = generate_build_id(cfg_hash, __version__)
    manifest = {
        'build_id': build_id,
        'created_at': now_ts(),
        'config_hash': cfg_hash,
        'tool_version': __version__,
        'chunk_count': len(chunks),
        'provider': cfg['embedding']['provider'],
        'status': 'success',
    }
    build_dir = meta_dir(cfg) / 'builds' / build_id
    ensure_dir(build_dir)
    write_json(build_dir / 'build_manifest.json', manifest)
    _write_version_log(cfg, build_dir / 'build_manifest.json', 'create', 'build_manifest')
    print(f'Embed 完成，已写入 build manifest：{build_id}')


@handle_exception
def cmd_build_bm25(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    idx_dir = project_root() / cfg['paths']['index']
    ensure_dir(idx_dir)
    stub = idx_dir / 'bm25_stub.txt'
    stub.write_text(
        'BM25 索引占位：安装 rank-bm25 或 whoosh 后在此处生成实际索引。\n',
        encoding='utf-8',
    )
    print('已创建 bm25 占位说明文件。')


def _retrieve_candidates(query_text: str, vs, judge, cfg: dict, extra_filter: Optional[str] = None) -> tuple[List[dict], List[str]]:
    """
    公共检索逻辑: Expand -> Multi-Search -> Dedup -> Rerank
    返回: (final_results, variants_used)
    """
    # 1. Query Expansion
    logger.info(f"正在进行查询扩展: {query_text}")
    variants = judge.expand_query(query_text)
    queries = [query_text] + variants
    # logger.info(f"多路召回查询词: {queries}")

    # 构造过滤器
    base_filter = "citable = true"
    final_filter = f"{base_filter} AND {extra_filter}" if extra_filter else base_filter

    # 2. Retrieve & Dedup
    candidate_map = {} 
    for q in queries:
        # 每路召回 candidate_k 条
        res = vs.search(q, limit=cfg['rerank']['candidate_k'], filters=final_filter)
        for r in res:
            cid = r.get("chunk_id")
            if cid and cid not in candidate_map:
                candidate_map[cid] = r
    
    candidates = list(candidate_map.values())
    # logger.info(f"多路召回合并后共 {len(candidates)} 条候选。")

    if not candidates:
        return [], variants

    # 3. Rerank
    final_results = candidates
    if cfg['rerank']['enabled']:
        final_results = vs.rerank(query_text, candidates, model=cfg['rerank']['model'])
        
    # Cut Top N
    return final_results[:cfg['rerank']['top_n']], variants


@handle_exception
def cmd_query(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    root = project_root()
    meta_path = meta_dir(cfg)
    
    build_manifest_path = latest_build_manifest(meta_path)
    if not build_manifest_path:
        _fail('未找到任何 build，请先运行 rag embed。', ErrorCode.QUERY_NO_BUILD)

    from .vector_store import VectorStore
    from .judge import RagJudge
    
    db_dir = root / cfg['paths']['index'] / "lancedb"
    vs = VectorStore(db_dir)
    judge = RagJudge()

    # 调用公共检索逻辑
    final_results, variants = _retrieve_candidates(args.question, vs, judge, cfg)

    if not final_results:
        print(human_warn("未找到相关证据。"))
        return

    # 回填 Parent 上下文
    parents_file = Path(cfg['paths']['chunks']) / 'parents.jsonl'
    parents_map = {}
    if parents_file.exists():
        with open(parents_file, 'r', encoding='utf-8') as f:
            for line in f:
                p = json.loads(line)
                parents_map[p['parent_id']] = p

    # 生成 Evidence Pack
    query_id = generate_query_id()
    out_dir = outputs_dir(cfg)
    ep_path = next_version_path(out_dir, 'evidence_pack')
    
    _print_filters_and_summary(final_results)
    
    lines_out = [
        f"# Evidence Pack",
        f"- build_id: {read_json(build_manifest_path)['build_id']}",
        f"- query_id: {query_id}",
        f"- LOCATOR_QUALITY: page",
        f"- Applied filters: citable=true",
        f"- Returned sources summary: count={len(final_results)}",
        f"- Query variants used: {json.dumps(variants, ensure_ascii=False)}",
        "",
    ]

    for idx, r in enumerate(final_results, 1):
        parent = parents_map.get(r['parent_id'], {})
        lines_out.append(f"## Evidence {idx}")
        lines_out.append(f"- doc_uid: {r['doc_uid']}")
        lines_out.append(f"- citation_key: {r['doc_uid']}")
        lines_out.append(f"- source_type: {r['source_type']}")
        lines_out.append(f"- parent_id: {r['parent_id']}")
        lines_out.append(f"- page_index: {parent.get('page_index', 'unknown')}")
        lines_out.append(f"- snippet: {r['text'].strip()}")
        if parent.get('parent_text'):
            lines_out.append(f"- context: {parent['parent_text'][:500]}...")
        lines_out.append('')

    ep_path.write_text('\n'.join(lines_out), encoding='utf-8')
    
    run_record = {
        'query_id': query_id,
        'q_raw': args.question,
        'variants': variants,
        'returned': len(final_results),
        'timestamp': now_ts(),
    }
    write_json(meta_path / 'query_runs' / f'{query_id}.json', run_record)
    
    print(f'Evidence Pack 已生成：{ep_path}')


def _extract_claims(text: str) -> List[dict]:
    keywords = {
        '因果': ['cause', 'causes', 'lead to', 'results in', '因为', '导致'],
        '比较': ['more than', 'less than', 'higher', 'lower', '更高', '更低'],
        '定量': ['%', 'percent', '显著', 'p<', '样本'],
        '普遍化': ['always', 'never', 'most', 'widely', '总是', '从不'],
        '建议': ['should', 'must', 'recommend', '建议', '必须'],
        '最高级': ['first', 'most', '最佳', '最重要'],
    }
    claims = []
    for line in text.splitlines():
        for typ, kws in keywords.items():
            if any(kw.lower() in line.lower() for kw in kws):
                claims.append({'text': line.strip()[:200], 'type': typ})
                break
    return claims


@handle_exception
def cmd_audit(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    draft = Path(args.draft_path)
    text = draft.read_text(encoding='utf-8')
    
    # --- Feature: Clean Copy & Word Count ---
    import re
    # 移除 {#doc_uid} 格式的锚点
    clean_text = re.sub(r"{#[\w\-:.]+}", "", text)
    # 简单估算单词数 (按空格切分)
    word_count = len(clean_text.split())
    
    # 生成 clean copy 文件
    clean_path = draft.with_name(f"{draft.stem}_clean{draft.suffix}")
    clean_path.write_text(clean_text, encoding='utf-8')
    logger.info(f"Generated Clean Copy: {clean_path} (Net Words: {word_count})")
    # ----------------------------------------

    from .judge import RagJudge
    logger.info("正在调用 Gemini 执行语义审计 (法官模式)...")
    judge = RagJudge()
    claims = judge.audit_claims(text)
    
    outputs = outputs_dir(cfg) / 'audits'
    ensure_dir(outputs)
    base = f"{draft.stem}_claims"
    out_path = next_version_path(outputs, base)
    
    # 构建符合 PR 15.4.2 规范的表格
    # 在头部增加字数统计信息
    lines = [
        f"# Audit Report: {draft.name}",
        f"- **Net Word Count**: {word_count} words (excluding citation anchors)",
        f"- **Clean Copy**: `{clean_path.name}`",
        "",
        '| claim_id | claim_text | claim_type | status | suggested_action |',
        '|---|---|---|---|---|'
    ]
    for i, c in enumerate(claims, 1):
        lines.append(f"| c{i:03d} | {c['claim_text']} | {c['claim_type']} | NEED | {c['reason']} |")
    
    lines.append("\n## 自然语言待办清单 (PR 15.4.2)")
    for i, c in enumerate(claims, 1):
        lines.append(f"{i}. **{c['claim_type']}**: {c['claim_text']} \n   - 建议：{c['reason']}")
    
    lines.append("\n## Sources used")
    srcs = _sources_used_from_chunks()
    if srcs:
        lines.extend([f"- {s}" for s in srcs])
    else:
        lines.append("None")
        
    out_path.write_text('\n'.join(lines), encoding='utf-8')
    _write_version_log(cfg, out_path, 'create', 'audit_claims_api')
    print(f'API 审计完成，报告已生成：{out_path}')


def _extract_doc_ids(text: str) -> List[tuple]:
    import re

    pattern = re.compile(r"{#([\w\-:.]+)}")
    results = []
    for line in text.splitlines():
        for m in pattern.finditer(line):
            results.append((line.strip(), m.group(1)))
    return results


def _doc_citable(chunks_file: Path, docid: str) -> bool:
    for ln in chunks_file.read_text(encoding='utf-8').splitlines():
        if not ln.strip():
            continue
        obj = json.loads(ln)
        if obj.get('doc_uid') == docid:
            return obj.get('citable', False)
    return False


def _sources_used_from_chunks() -> List[str]:
    chunks_file = Path('chunks') / 'chunks.jsonl'
    if not chunks_file.exists():
        return []
    ids = []
    for ln in chunks_file.read_text(encoding='utf-8').splitlines():
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
            if obj.get('doc_uid') and obj.get('doc_uid') not in ids:
                ids.append(obj['doc_uid'])
        except Exception:
            continue
    return ids


def _load_chunks(chunks_file: Path) -> List[dict]:
    if not chunks_file.exists():
        return []
    data = []
    for ln in chunks_file.read_text(encoding='utf-8').splitlines():
        if ln.strip():
            try:
                data.append(json.loads(ln))
            except Exception:
                continue
    return data


@handle_exception
def cmd_verify_citations(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    draft = Path(args.draft_path)
    text = draft.read_text(encoding='utf-8')
    
    doc_ids = _extract_doc_ids(text) # 提取 {#doc_uid}
    if not doc_ids:
        print(human_warn("未在草稿中发现任何引用标记 {#doc_uid}。"))
        return

    from .vector_store import VectorStore
    from .judge import RagJudge
    
    db_dir = project_root() / cfg['paths']['index'] / "lancedb"
    vs = VectorStore(db_dir)
    judge = RagJudge()

    logger.info(f"正在核查 {len(doc_ids)} 处引用的支撑度 (Query Expansion + Multi-Search)...")

    outputs = outputs_dir(cfg) / 'audits'
    ensure_dir(outputs)
    base = f"{draft.stem}_citations"
    out_path = next_version_path(outputs, base)
    
    header = '| sentence_id | sentence_text | cited_doc | score | status | critique |\n|---|---|---|---|---|---|'
    rows = [header]
    
    for i, (sent, docid) in enumerate(doc_ids, 1):
        # 使用多路召回在目标文档中搜索证据
        # 限制范围：只在该 doc_uid 内搜索
        candidates, _ = _retrieve_candidates(sent, vs, judge, cfg, extra_filter=f"doc_uid = '{docid}'")
        
        if not candidates:
            # 如果连关键词都搜不到，那肯定是 MISSING
            rows.append(f"| s{i:03d} | {sent[:100]}... | {docid} | 0.00 | MISSING | 未在文档中检索到相关片段 |")
            continue
            
        evidence_texts = [c['text'] for c in candidates]
        
        # 调用 Gemini 进行语义比对
        result = judge.verify_support(sent, evidence_texts)
        
        rows.append(f"| s{i:03d} | {sent[:100]}... | {docid} | {result['support_score']:.2f} | {result['status']} | {result['critique']} |")

    out_path.write_text('\n'.join(rows), encoding='utf-8')
    _write_version_log(cfg, out_path, 'create', 'verify_citations_api')
    print(f'引文核查完成，报告已生成：{out_path}')


@handle_exception
def cmd_meta_set(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    meta_path = meta_dir(cfg)
    doc_meta_file = meta_path / f"{args.doc_uid}.json"
    if not doc_meta_file.exists():
        _fail('未找到该 doc_uid 的元数据文件。', ErrorCode.META_DOC_NOT_FOUND)
    data = read_json(doc_meta_file)
    if args.accessed_at:
        data['accessed_at'] = args.accessed_at
    write_json(doc_meta_file, data)
    _write_version_log(cfg, doc_meta_file, 'update', 'meta set')
    print(f'已更新元数据：{args.doc_uid}')


@handle_exception
def cmd_export_used_sources(args):
    _require_init()
    cfg = load_config(Path('config.yaml'))
    ep_path = Path(args.evidence_pack_path)
    doc_ids = []
    for line in ep_path.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('- doc_uid:'):
            doc_ids.append(line.split(':')[1].strip())
    # 加载 chunk 元数据以输出 source_type/citable
    chunk_records = _load_chunks(Path(cfg['paths']['chunks']) / 'chunks.jsonl')
    doc_meta = {}
    for r in chunk_records:
        uid = r.get('doc_uid')
        if uid and uid not in doc_meta:
            doc_meta[uid] = {'source_type': r.get('source_type', 'unknown'), 'citable': r.get('citable')}

    out_path = next_version_path(outputs_dir(cfg), 'used_sources')
    out_lines = ['# Sources used']
    if doc_ids:
        out_lines += ['', '| doc_uid | source_type | citable |', '|---|---|---|']
        for d in doc_ids:
            meta = doc_meta.get(d, {'source_type': 'unknown', 'citable': None})
            out_lines.append(f"| {d} | {meta['source_type']} | {meta['citable']} |")
    else:
        out_lines.append("None")
    out_path.write_text('\n'.join(out_lines), encoding='utf-8')
    _write_version_log(cfg, out_path, 'create', 'export_used_sources')
    print(f'已导出 sources：{out_path}')


# CLI dispatcher ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='rag', description='Codex + RAG 论文写作系统 CLI')
    parser.add_argument('--version', action='version', version=f'rag {__version__}')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('init', help='初始化目录与默认配置')

    parse_p = sub.add_parser('parse', help='解析 raw/ 到 parsed/')
    parse_p.add_argument('--project', help='覆盖 project_id', required=False)

    sub.add_parser('chunk', help='生成 parent/child chunks')
    sub.add_parser('embed', help='生成向量并写 build manifest')
    sub.add_parser('build-bm25', help='BM25 占位实现')

    query_p = sub.add_parser('query', help='检索并生成 Evidence Pack')
    query_p.add_argument('question')
    query_p.add_argument('--mode', choices=['evidence', 'papers'], default='evidence')

    audit_p = sub.add_parser('audit', help='审计草稿中的强断言')
    audit_p.add_argument('draft_path')

    verify_p = sub.add_parser('verify-citations', help='核查 draft 引用支撑度')
    verify_p.add_argument('draft_path')

    meta_p = sub.add_parser('meta', help='元数据操作')
    meta_sub = meta_p.add_subparsers(dest='meta_cmd')
    meta_set = meta_sub.add_parser('set', help='设置文档元数据')
    meta_set.add_argument('--doc_uid', required=True)
    meta_set.add_argument('--accessed_at', required=False)

    export_p = sub.add_parser('export-used-sources', help='导出 Evidence Pack 使用的 doc_uid')
    export_p.add_argument('evidence_pack_path')

    return parser


def main(argv: Optional[List[str]] = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == 'init':
        cmd_init(args)
    elif args.command == 'parse':
        cmd_parse(args)
    elif args.command == 'chunk':
        cmd_chunk(args)
    elif args.command == 'embed':
        cmd_embed(args)
    elif args.command == 'build-bm25':
        cmd_build_bm25(args)
    elif args.command == 'query':
        cmd_query(args)
    elif args.command == 'audit':
        cmd_audit(args)
    elif args.command == 'verify-citations':
        cmd_verify_citations(args)
    elif args.command == 'meta':
        if getattr(args, 'meta_cmd', None) == 'set':
            cmd_meta_set(args)
        else:
            parser.print_help()
    elif args.command == 'export-used-sources':
        cmd_export_used_sources(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
