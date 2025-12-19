# Codex + RAG 论文写作系统 PR（面向非技术读者的超细版）

> 这份 PR 说明的是：我们要把你现有的论文资料（100+ 篇 PDF、课件、范文、老师 feedback、guidance、reading list）做成一个“可反复使用的证据检索系统”。
>
> 目标：写论文时，你问一个问题，它能把最相关的原文证据（带出处信息）找出来，给 Codex / ChatGPT / Gemini 用来写段落，减少瞎编、减少翻找时间。

---

## 1. 一句话总结（90 岁老奶奶版）

你可以把它想象成：

- 你家里有 **100 多本书（PDF 文献）**，
- 以前要找一句话要翻很久。

现在我们做一个“聪明的目录 + 小贴纸系统”：

1. 先把每本书拆成很多小段落（chunks），每段贴上标签（比如“这段来自哪本书、哪一章、哪一年、属于哪门课”）；
2. 你问问题时，系统会先把“像你问题的段落”找出来；
3. 找到之后，把这几段“原文证据包”交给 AI 写作；
4. AI 写出来后，我们还会检查：哪些句子没有证据支撑，需要补引用。

---

## 2. 你现在手里有什么（输入资产清单）

我们明确把所有资料分成 6 类：

1. **Guidance / Rubric**：老师对结构、评分标准、格式的要求。
2. **历史范文**：高分/低分例子，用来学写法。
3. **老师 feedback**：老师指出你哪里弱、该怎么改。
4. **这学期课件**：概念框架、课程重点。
5. **Reading list（可选）**：有些课程会提供老师认可的参考文献清单；**也可能完全没有**。
6. **本地 PDFs（100+）**：你实际下载/收集到的论文、书章、报告等（不要求必须来自 reading list）。

额外：写作过程中，可能需要补新文献，由 AI 标注为 `EVIDENCE_NEEDED`，你再决定是否去找。

---

## 3. 我们最终要做出的东西（输出与功能）

### 3.1 最终用户体验（你使用时）

你只做 3 件事：

1. **导入资料**（把所有材料按类型放到指定文件夹：文献 PDF / 课件 / guidance / feedback / 范文 / reading list 等）
2. **建索引**（跑一条命令，自动解析、分块、生成向量、建索引；每个分块都会带上 `source_type` 标签）
3. **写论文时检索**（输入问题/段落目标，得到 Evidence Pack；默认只从“可引用文献”里取证据）

**非常重要的规则：不是所有文件都可以当“论文引用”。**

- **可引用（Citable）**：你放在 `raw/evidence/` 里的学术来源（论文/书章/报告/网页快照等）。这些会产生 `citation_key`，并允许出现在引用里。**不要求一定来自 reading list**。
- **不可当学术引用（Non‑citable）但非常有用**：guidance、老师 feedback、课件、历史范文。
  - 它们会进入索引，但被打上 `source_type=guidance/feedback/slides/exemplar`。
  - 默认检索证据时会 **排除** 它们，避免“引用了不该引用的东西”。
  - 它们主要用于：**约束写作结构与评分点（rubric）**、**按老师意见改稿**、**对齐课程框架与术语**、**学习写作风格**。

系统输出一个“证据包（Evidence Pack）”，里面包含：

- Top-K 最相关原文段落（英文原文 + 可选中文摘要）
- 每段来自哪篇文献（citation\_key）
- 章节标题（section）
- 可能的页码信息（如果解析能映射到页）
- 你可以让 AI 只基于这个证据包写段落

### 3.2 写作质量控制（自动标红）

系统还能做一个很关键的事情：

- 扫描你的 draft，找出“强断言句”（比如因果、比较、数据、结论很硬的句子）
- 如果没有对应证据块支持，标为：`EVIDENCE_NEEDED`
- 输出一个待办清单，告诉你需要补什么证据、用什么检索关键词。

---

## 4. 我们讨论过的每一个核心决策（Decision Log）

### 决策 1：这是完整 RAG 吗？

是。

- 解析（Parse）→ 分块（Chunk）→ 向量化（Embed）→ 索引（Index）→ 检索（Retrieve）→ 注入（Augment）→ 生成（Generate）→ 评估/审计（Evaluate）

### 决策 2：解析用什么？

**用 MinerU。**

原因（很朴素）：

- 学术 PDF 结构复杂（标题层级、表格、脚注、图注）
- 解析差会导致“检索出来的内容碎、乱、缺”，后面再强的 embedding 都救不回来
- MinerU 的定位就是把 PDF 解析成更“机器可读”的结构化结果（MD/JSON 等）

#### 2.1 MinerU 官方 API 的工程现实（你刚贴的文档最关键的点）

我们把“怎么调用 MinerU”说成一句话：

- **如果文件在你本地：用「批量文件上传解析」接口（先申请上传 URL，再 PUT 上传；上传后 MinerU 自动提交解析任务）。**
- **如果文件本来就在公网可访问的 URL：可以用「创建解析任务（URL）」接口或「URL 批量上传解析」。**

为什么要强调这一点：

- MinerU 的「单文件解析（URL）」接口**不支持文件直接上传**；对于你这种“100+ 本地 PDF”场景，主路径必须走批量上传接口。

#### 2.2 我们在 `rag parse` 里采用的默认策略（不需要你思考）

- 扫描 `raw/` 下的所有原始文件（pdf/docx/pptx/图片等）。
- 以 **最多 200 个文件/批次** 向 MinerU 申请上传链接（官方限制）。
- 逐个 `PUT` 上传文件（上传时不需要设置 Content-Type）。
- 轮询批量结果接口，直到每个文件进入 `done/failed`。
- 对 `done` 的文件：下载 `full_zip_url`，解压到 `parsed/`（一文献一个文件夹），拿到默认导出的 `markdown + json`。

#### 2.3 MinerU API 的硬限制（必须写进程序做预检）

- 单文件 **≤ 200MB**；**页数 ≤ 600**（超过则由脚本自动处理：
  1. **预检（preflight）**：先读取页数/体积，判定触发原因（pages\_limit 或 size\_limit）。
  2. **拆分计划（split plan）**：先按页数切成 ≤500 页的段（留余量），每段生成子 PDF；对子 PDF 再做大小校验。
  3. **递归细分（bisection）**：若某段仍 >200MB，则按页码二分递归，直到同时满足页数与体积限制。
  4. **可恢复与追溯（manifest）**：为每个子文件写入 `split_manifest`（记录原文件、页码范围、子文件路径/哈希），上传解析时用稳定 `data_id/doc_uid` 绑定，解析结果可精确映射回原文献与页码。
  5. **可选轻度压缩**：仅在“扫描件/大图 PDF”导致拆分过细时启用，避免任务数爆炸。 **为什么靠谱**：它是确定性规则（按页范围/二分），每次运行结果一致；有 manifest 主键映射，任何中断都能续跑；不会产生页码错位。 **为什么高效**：优先按页段切（一次生成大块），只对超限段做递归细分（最小化拆分次数）；并且拆分在本地完成，减少 MinerU 失败重试与无效上传）。
- 每个账号每天有 **2000 页最高优先级额度**，超过会降优先级（意味着“同样能跑，但可能更慢”）。
- 单次申请上传链接 **≤ 200 个文件**；上传链接有效期 **24 小时**。

#### 2.4 `model_version` 怎么选（我们默认给你一个可用的选择）

- MinerU API 的 `model_version` 有两个选项：`pipeline` / `vlm`。
- **默认：\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\***``（通常对复杂版式更稳，且你当前需求主要是“把文献变成可检索的结构化文本”）。
- **当你明确遇到“扫描件/需要 OCR / 需要指定语言 / 强依赖表格和公式开关”时：切到 \*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\***``（因为这些细粒度开关仅对 pipeline 有效）。

> 结论：`rag parse` 做成一个“自动化的 MinerU 任务编排器”，你只管放文件，其他都由脚本完成。

- 学术 PDF 结构复杂（标题层级、表格、脚注、图注）
- 解析差会导致“检索出来的内容碎、乱、缺”，后面再强的 embedding 都救不回来
- MinerU 的定位就是把 PDF 解析成更“机器可读”的结构化结果（MD/JSON 等）

### 决策 2.5：Chunking（分块）怎么做？——我们选“先小后大”的稳健默认

你贴的那段“大佬结论”整体方向是对的：**不存在对所有语料/所有问题类型都最优的单一 chunk 方案**；chunk 的最优点会随“问题类型 + 文档结构 + embedding 模型特性”迁移。NVIDIA 的系统评测也明确指出：不同数据集/不同查询类型在不同 chunk 尺度上表现最佳，而 **page-level chunking 在平均准确率和稳定性（**[**方差）上最好**](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/?utm_source=chatgpt.com)[。(](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/?utm_source=chatgpt.com)[developer.nvidia.com](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/?utm_source=chatgpt.com)) 同时，Chroma 的评测也显示：**更小的 chunk（如 max 200 tokens）往往带来更高的精度/IoU**，但 recall 可[能不一定最高。(](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com)[research.trychroma.com](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com))

因此，我们为“写论文找可引用证据”选一个**最稳健、最可辩护**的工程默认：

- **检索定位用小 chunk（child）**：提高“命中是否干净”的概率（prec[ision）。(](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com)[research.trychroma.com](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com))
- **返回阅读与引用用大上下文（parent）**：避免断章取义，便于你核验与写作。LangChain 的 ParentDocumentRetriever 与 LlamaIndex 的 Sentence Window 都是同一类思想：**retrieve small, retu**[**rn big**](https://v02.api.js.langchain.com/classes/langchain.retrievers_parent_document.ParentDocumentRetriever.html?utm_source=chatgpt.com)[。(](https://v02.api.js.langchain.com/classes/langchain.retrievers_parent_document.ParentDocumentRetriever.html?utm_source=chatgpt.com)[v02.api.js.langchain.com](https://v02.api.js.langchain.com/classes/langchain.retrievers_parent_document.ParentDocumentRetriever.html?utm_source=chatgpt.com))

> 这不是“数学全局最优”，但它是对你场景（精确找证据 + 需要足够上下文）最稳健的默认解。

#### 默认参数（可以写进 config.yaml）

- **Parent（大块）边界**：优先 **page**（页级），因为对 PDF 最稳定且在 NVIDIA 测试中平均表现最[好、波动最小。(](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/?utm_source=chatgpt.com)[developer.nvidia.com](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/?utm_source=chatgpt.com))
  - 可选：如果 MinerU 能稳定给出章节结构（section\_path），也允许改为 section-level parent。
- **Child（小块，用于向量召回）**：`200 tokens` 起步（范围 15[0–300）。(](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com)[research.trychroma.com](https://research.trychroma.com/evaluating-chunking?utm_source=chatgpt.com))
- **Overlap**：默认 `0–10%`（先小后大； overlap 主要增加成本与冗余，除非你在评测中看到明显收益）。
- **检索策略**：先取 `top_k_child=20`，再按 `parent_id` 去重聚合，最终返回 `top_m_pa` `rent=3–5`个 /节）。



#### 为什么“大块有时 recall 更高”，但我们仍然不只用大块

一些多数据集分析显示：对需要更宽上下文的任务，chunk 变大确实会显著改善 Recall\@1（例如 TechQA 在 128→512 tokens 上[有大幅提升）。(](https://arxiv.org/html/2505.21700v2?utm_source=chatgpt.com)[arxiv.org](https://arxiv.org/html/2505.21700v2?utm_source=chatgpt.com)) 但对“精确定位可引用句子/段落”的论文写作场景，只用大块容易把无关文本一起嵌进去，导致命中漂移。

所以我们用“**小块定位 + 大块回填**”同时兼顾 precision 与 context。

#### `rag chunk` 的具体实现（工程可落地，不靠玄学）

**输入**：`parsed/`（MinerU 解压后的每文献文件夹，含 markdown + json + 图片等）

**输出**：`chunks/`（两类产物：parent 表 + child 表；child 表用于 embedding 与检索）

1. **构建 parent（大块，默认按页）**

- 优先从 MinerU 的结构化 JSON 中读取 page 信息，把同一页的文本聚合为一个 parent。
- 若 JSON 缺失/不可用：退化为“按 Markdown 中的页分隔符/版面提示”或“按长度阈值”做近似 page chunk（保证不会生成超长 parent）。
- 每个 parent 生成：
  - `parent_id`（例如 `doc_uid:p003`）
  - `doc_uid`、`source_type`、`citable`、`page_start/page_end`（若可得）
  - `section_path`（若能从标题层级推断）
  - `parent_text`（清洗后的正文）

2. **从 parent 切 child（小块，仅用于向量检索）**

- 先做轻度清洗：去页眉页脚噪声、合并断行、保留标题（标题对检索很有价值）。
- 句子级切分（优先按标点/换行，不强依赖语言模型）：把 parent\_text 切成句子序列。
- 以 token 预算组装 child：
  - 目标 `~200 tokens`；最小 `~80`；最大 `~300`（避免碎片过小或过大）。
  - overlap 默认 0–10%（例如 20 tokens），可在 config 调整。
- 每个 child 记录：
  - `chunk_id`（全局唯一）
  - `parent_id`（用于“retrieve small, return big”回填）
  - `char_start/char_end`（在 parent\_text 内的偏移，方便做窗口回填/高亮）
  - `text`、`hash`（用于增量更新：文本不变就不重算 embedding）

3. **写入 **``** 并做增量更新**

- `parents.jsonl`：parent 记录
- `chunks.jsonl`：child 记录（后续 `rag embed` 只读这一份）
- `chunk_manifest`：记录每个 doc 的 hash、chunk 数、生成时间，后续只处理新增/变更文档。

4. **检索时的“回填/聚合”规则（为写作服务）**

- 先检索 `top_k_child`（dense/hybrid + 可 rerank），得到命中的 child 列表。
- 按 `parent_id` 聚合去重，排序后返回 `top_m_parent`。
- Evidence Pack 里同时输出：
  - 命中 child（用于精确证据）
  - 对应 parent（用于上下文核验与写作）

> 这个实现与 LangChain/LlamaIndex 的 parent/window 思路一致：child 用于精确检索，parent 用[于阅读与引用。(](https://v02.api.js.langchain.com/classes/langchain.retrievers_parent_document.ParentDocumentRetriever.html?utm_source=chatgpt.com)[v02.api.js.langchain.com](https://v02.api.js.langchain.com/classes/langchain.retrievers_parent_document.ParentDocumentRetriever.html?utm_source=chatgpt.com))

### 决策 3：embedding（把文字变成向量）用什么？

**用 Google Cloud Vertex AI 的 **``**（Embeddings API）**，用你的 GCP credit 支付。

> 我们之所以默认选 `gemini-embedding-001`：Google 的官方模型表把它定位为“最高性能/统一英文+多语言+代码”的 embedding 模型；同时它支持用 `output_dimensionality` 把向量维度压缩（节省存储与计算，通常质量损失很小）。

**默认配置（建议写进 **``**）**

- `embedding_model`: `gemini-embedding-001`
- `task_type`:
  - 索引（文献 chunks）用：`RETRIEVAL_DOCUMENT`
  - 查询（你的问题）用：`RETRIEVAL_QUERY`
- `output_dimensionality`: `1536`（质量/体积的默认平衡点；追求极致质量可用 3072，追求更轻量可用 768）
- `autoTruncate`: `false`（让超长输入直接报错，避免“静默截断”导致引用位置丢失；但我们本身把 child 控到 200 tokens，理论上不会触发）

**性能/吞吐注意事项**

- `gemini-embedding-001` 的在线 API 每次请求只支持 1 条输入文本；因此我们会做并发与重试，必要时走 Batch Embeddings（更省钱、吞吐更高）。
- 如果你后面更在意“批量吞吐/更少 API 调用”而不是极致质量，可降级为 `text-embedding-005`（英文/代码）或 `text-multilingual-embedding-002`（多语言）。

原因：

- embedding 便宜（相比大模型生成便宜很多）
- 你不想额外花钱，而你已有 GCP credit
- 质量稳定，跨语言（中文问英文文献）也更可靠

### 决策 4：rerank（重排）用不用？

**默认用（开启）。**

原因：Ranking API 本来就是为“把已经召回的一批候选结果再排序”设计的；它是 stateless（不需要把文档再建一个索引），非常适合放在“向量/BM25 召回之后”，用来提升 Top-N 的相关性，从而提升“证据命中率”。（官方文档也把它列为 RAG 的典型流程：先切 chunk → embed → 向量召回 → rerank。）

---

### 决策 4.1：rerank 需要选模型吗？

**需要。为了追求稳定，我们固定模型版本，不使用 **``**。**

官方支持的模型（与你最相关的）：

- **稳定 + 质量优先（本方案固定使用）**：`semantic-ranker-default-004`（1024 tokens/record，25 种语言）
- 速度优先（备选，仅在你明确需要提速时启用）：`semantic-ranker-fast-004`（1024 tokens/record，25 种语言）
- 旧版本（不建议新项目默认）：`semantic-ranker-default-003`（512 tokens/record）

> 注意：每条 record（title+content）的 tokens 超过模型上限会被截断；每次请求最多可带 **200 条 records**。

---

### 决策 4.2：怎么配置才能“效果最好”？（我们给你一个可直接落地的默认）（我们给你一个可直接落地的默认）

我们把“效果最好”说得工程一点：**在可控成本和延迟下，让 Top-5 / Top-10 更可能包含“你能引用的那段证据”。**

因此我们推荐以下默认配置（写进 `config.yaml`）：

- `rerank_enabled: true`
- `rerank_model: semantic-ranker-default-004`（**固定版本，追求稳定与可复现**）
- `rerank_candidate_k: 50`  （先召回 50 条 child chunks 再 rerank）
- `rerank_topN: 10`  （最后只保留 10 条）
- `ignoreRecordDetailsInResponse: true`  （只返回 id+score；正文我们本地已有，减少响应体）

**record 的拼装（比“调模型”更重要）**

每条 record 你要给它一个“更可判别”的上下文：

- `id`: `chunk_id`
- `title`: `doc_title | section_path | year | page_range`（如果没有 page\_range 就省略）
- `content`: child chunk 的英文原文（约 150–300 tokens；我们默认 200 tokens）

为什么 title 要这么拼？因为论文检索里，“章节标题 + 年份”经常是强信号：它能帮助 ranker 在术语冲突时更稳。

---

### 决策 4.3：中文提问 + 英文文献时，rerank 用中文还是英文 query？

**默认：用英文 query（q\_en）做 rerank。**

原因很朴素：records 内容是英文，英文 query 在词面与语义上更对齐。

工程上我们采取的默认策略：

1. 你输入中文问题 `q_zh`
2. 生成英文 `q_en`（学术化改写 + 关键词扩展）
3. Dense 召回：`q_zh` 与 `q_en` 都跑一次（提升 recall）
4. BM25：只用 `q_en`（提升 precision）
5. Rerank：默认用 `q_en`

> 备注：Ranking 模型本身支持 25 种语言（包含中文），但它是否在“中文 query ↔ 英文 records”的跨语言 rerank 上稳定更强，官方并没有给出保证；所以我们用 `q_en` 作为稳健默认。

---

### 决策 4.4：什么时候需要调参？怎么用数据调？

你只需要围绕 3 个旋钮做小规模 ablation（20–50 条真实问题）即可：

1. `candidate_k`: 30 / 50 / 100
   - 召回质量一般时，**先增大 candidate\_k**（上限 200/请求）
2. `topN`: 5 / 10 / 20
   - 你写作时通常只看 top 5–10；太多反而拖慢核验
3. `model`: default-004 vs fast-004
   - default 更准；fast 更快（你可以用延迟与命中率做取舍）

评测指标（对论文写作最有意义）：

- Recall\@10（Top-10 是否含正确证据）
- MRR（正确证据排得多靠前）
- “可引用率”（你主观打分：能否直接支撑你的句子）

---

### 决策 4.5：稳定性与效率保障（并发控制 + 重试 + 自动提示）

你提出的要求非常正确：**固定模型版本只是“结果稳定”，还需要“请求稳定”。** 所以我们在程序里加三件事：

#### 4.5.1 并发控制（Concurrency Control）

- Ranking API 单次最多 200 records；我们会把 `candidate_k` 控制在 50（必要时 100），避免一次请求过大。
- 采用“有上限的并发队列”：例如默认 `rerank_max_concurrency=4`（可调）。
- 如果出现 429/503 等拥塞信号，会自动降低并发（自适应 backoff）。

#### 4.5.2 重试策略（Retry with exponential backoff + jitter）

- 只对“可恢复错误”重试：HTTP 429（限流）、5xx（服务端抖动）、网络超时。
- 默认 `rerank_max_retries=5`。
- backoff：指数退避 + 随机抖动（避免所有请求一起重试造成雪崩）。
- 每次请求设置超时（例如 `rerank_timeout_s=20`），避免卡死。

#### 4.5.3 低效率自动识别与“和你沟通”（Codex 提示机制）

我们在 `rag query`（新增：`--mode evidence|papers`，`--counterevidence off|soft|strict`） 的输出里增加一段“健康提示”，让 Codex 能明确告诉你当前效率是否低于预期，并给出可选动作：

- 记录本次查询的：
  - `rerank_latency_ms`（本次耗时）
  - `rerank_error`（是否发生重试/失败）
  - 滚动窗口的 `p50/p95 latency`（最近 N 次）

**触发提示的默认阈值（可配）：**

- 最近 20 次中 `p95 > 3000ms`，或
- 最近 20 次中错误率 `> 5%`（发生重试也算“错误事件”）

**一旦触发，Codex 必须向你输出清晰建议并征求是否调整：**

- 方案 1（最小改动）：把 `rerank_candidate_k` 从 50 降到 30（更快、通常仍够用）
- 方案 2（更快）：切到 `semantic-ranker-fast-004`
- 方案 3（临时降级）：暂时关闭 rerank（只用 hybrid 召回），并在 Evidence Pack 顶部标注“未 rerank，相关性可能略降”

> 关键点：我们不会“悄悄改配置”。任何降级或切换都必须先提示你并由你确认（你可以一句话回复：`switch to fast` / `reduce candidate_k` / `disable rerank`）。

---

### 决策 5：hybrid（关键词 + 向量）要不要？

**要。**

原因（论文检索的事实规律）：

- 论文经常有专有名词、作者名、年份、框架名
- 这些对关键词（BM25）非常友好
- 向量检索解决“同义改写/表达差异”
- 组合起来更稳：BM25 不漏掉“硬关键词”，向量补“语义近似”

---

### 决策 5.1：你用中文提问，但文献是英文，检索怎么做？

这不是问题，反而是一个很常见的真实场景。

我们把“检索”拆成两条路：

1. **Dense（向量）检索**：天然支持跨语言（中文问英文），因为我们选的是**多语言 embedding**；中文问题会被编码成和英文段落“同一向量空间里的点”，语义相近就能找出来。

2. **Sparse（BM25/关键词）检索**：**不支持跨语言**。因为 BM25 本质上是“词面匹配”，中文词不会出现在英文段落里，匹配会非常差。

因此，我们的默认策略是：

- **Dense：同时跑两次查询**
  - 用你的原始中文 query（保留你表达的细节）
  - 再生成一个英文 query（更贴近论文文本与术语）
- **Sparse/BM25：只用英文 query**（以及英文关键词/同义词扩展）
- **最后融合 + rerank**：把两路结果合并，再重排，输出 Evidence Pack

#### `rag query` 的具体步骤（工程路径）

当你输入中文问题：

1. **Query 翻译与扩展（很便宜，但收益很大）**

   - 生成 `q_en`：你的问题的“学术英文版本”
   - 生成 `q_terms`：10 个以内的英文关键词/同义词（用于 BM25）
   - 把 `q_zh/q_en/q_terms` 写进 `meta/query_cache.jsonl`（同样问题下次不重复花钱）

2. **Dense 检索（向量）**

   - 分别用 `q_zh` 与 `q_en` 做向量查询（各取 top\_k，例如各 30）
   - 对候选做去重（按 chunk\_id）

3. **Sparse 检索（BM25）**

   - 用 `q_en + q_terms` 做 BM25（取 top\_k，例如 30）

4. **融合（Hybrid Fuse）**

   - 用 RRF（Reciprocal Rank Fusion）或加权融合把 Dense + Sparse 的候选合成一个候选集（例如 50）

5. **Rerank（重排）**

   - 默认用 `q_en` 对候选 passages 做 rerank（因为 passages 是英文，英文 query 往往更对齐）
   - 输出 top\_n（例如 10），再按 parent 聚合输出 3–5 个 parent（页/节）作为最终 Evidence Pack

#### 关键点：你不需要“把所有英文文献翻译成中文”

- 你只需要在查询端做一次“中文→英文”的翻译/术语扩展即可。
- 这比“全文翻译索引”便宜几个数量级，也更不容易引入翻译噪声。

---

### 决策 6：向量数据库放云还是本地？

**本地。**

原因：

- 你明确担心云端数据库会贵（尤其是长期运行/托管向量服务）
- 你的规模（100+ 文献）通常是万级 chunks，单机完全够

### 决策 7：本地用哪种存储后端？（FAISS/SQLite vs LanceDB vs Qdrant）

我们最终形成了“按你需求画像”的选择：

- 你需要：**多个程序/多个 agent 访问同一个索引**（是）
- 你不需要：**必须常驻开着**（否）
- 你希望：**过滤检索（按课程、按年份）**（是）
- 你不强调：严格数据库治理能力（偏无所谓）

因此：

**默认推荐：LanceDB（本地文件型向量库）**

为什么：

- 不需要常驻服务：打开文件即可查询
- 多程序访问更自然（同一份库文件）
- 支持基于 metadata 的过滤
- 并发读通常没问题（写入我们设计成单 writer）

同时：

- 如果未来真的要跨机器/跨语言通过 HTTP 访问（像一个“个人知识库服务”）
- 再升级为：Qdrant（本地服务 + API）

我们明确：你现在不需要 Milvus / pgvector（过重）。

### 决策 8：你担心“每门课都要重建索引，所以服务化没意义”

我们确认你的偏好（并据此调整设计）：

- **不同课程/不同论文使用不同一批文献**：每门课一个独立索引与数据目录（`datasets/COURSE_ID/...`），**不跨课复用同一批文献**。
- 仍然保留“增量更新”，但范围限定在**同一门课内部**：
  - 新增/变更 PDF → 只对新增/变更 chunks 做 embedding → upsert
- 这样可复用的是“工具链/流程”（parse/chunk/embed/query/audit），而不是跨课程共享同一套文献库。

### 决策 9：多课程如何做到“彻底隔离”？（你问的“是不是新建项目/新建文件夹”）

我们采用**两层隔离**：

1. **文件层隔离（必须）**：每门课一个 `datasets/COURSE_ID/` 目录。任何解析产物、chunks、索引都只写入该目录。
2. **索引层隔离（建议）**：每门课一个独立的向量库位置（或独立 collection/table）。

- 如果用 **LanceDB（文件型）**：
  - 每门课的向量库就是一个独立目录，例如：`datasets/COURSE_ID/index/lancedb/`。
  - 在该目录下创建一张表（例如统一叫 `chunks`），不同课程不会混在一起。
- 如果未来用 **Qdrant（本地服务）**：
  - 仍然可以只跑一个 Qdrant 服务，但为每门课创建一个 **collection**（例如 `course_HUD_TERM1`）。
  - 检索命令必须显式指定 `--course`，从对应 collection 查询。

> 关键点（按你希望的“每篇论文独立管理、Codex 用自然语言接管”来解释）：
>
> **你有两种等价做法**，都能做到“每门课/每篇论文完全隔离”。区别只在于：工具代码是“共享一份”还是“每篇论文复制一份”。
>
> **做法 1（推荐，省维护）：共享一份工具代码 + 每篇论文一个数据目录**
>
> - 代码（CLI/脚本）只维护一份（例如放在仓库根目录 `rag/` 或 `tools/`）。
> - 每篇论文新建一个 `datasets/COURSE_ID/`（或更直观：`projects/ESSAY_X/`）目录，里面放该论文的 `raw/parsed/chunks/index/meta`。
> - Codex 使用时：**你会先在终端手动 **``**，再从这个目录启动 Codex 并 \*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\***``（这样 Codex 的上下文天然聚焦在这一篇论文）。工具的调用有两种安全做法：

1. **推荐**：把工具做成可执行命令（例如 `rag`），通过 `pip install -e` 或系统 PATH 安装；论文目录里只保存数据与配置，Codex 无需访问上一级源码。
2. **次选**：在论文目录里放一个很薄的包装脚本 `./rag`（内部调用 `../tools/rag`），但明确禁止工具扫描上一级的其他论文目录。

> **做法 2（符合你最初设想，隔离更“物理化”）：每篇论文一个独立文件夹 + 复制/快照一份工具代码**
>
> - 你新建 `projects/ESSAY_X/`，把工具脚本一起拷进去，然后 `codex /init` 在这个文件夹里。
> - 优点：每篇论文文件夹自包含，迁移/打包更直观。
> - 缺点：后续修 bug/加功能要在多份代码里同步；一不小心版本分叉，反而容易出问题。
>
> **折中（强烈建议）：每篇论文文件夹“看起来像拷贝了代码”，但其实是引用同一份**

这里的“挂载”是一个工程口语：意思是**让论文目录可以直接调用工具链**，但你不需要把工具代码复制进每一篇论文的文件夹。

在你这个场景里（每篇论文一个目录、你总是在论文目录里启动 Codex，且你最怕“串上下文/串项目”），我们**只保留并强制采用一种挂载方案**：

## 唯一方案：`pip install -e`（可编辑安装，把工具变成命令）

### 技术原理（为什么它是“挂载”）

- `pip install -e` 会把工具项目以“可编辑模式”安装到当前 Python 环境。
- **运行时不复制源码**：Python 仍从你工具源码所在的原路径加载模块。
- 同时会把命令入口（例如 `rag`）注册到环境的 PATH（准确说是 venv 的 `bin/` 目录）。

你看到的效果：

- 在任何论文目录里，都能直接运行 `rag ...`；论文目录里**不需要出现工具代码**。

实际发生的事：

- 论文目录只保存论文数据与配置；工具代码在统一位置维护一份，靠“可编辑安装”让命令可用。

### 为什么这对你最靠谱（核心理由）

1. **最不容易串上下文**：你在论文目录启动 Codex，Codex 的可见文件天然只包含当前论文；工具通过命令调用，Codex 不必读取上一级目录的源码或其他论文目录。
2. **零复制、零分叉**：工具链只维护一份；修 bug/加功能不会出现“这篇能跑那篇不能跑”。
3. **可恢复、可迁移**：论文目录是纯数据与配置，打包/备份/搬家简单；换机器时只需要重新 `pip install -e` 一次。
4. **对多 agent 更友好**：未来多个 agent 只要能执行同一条 `rag` 命令，就能共用同一套工具链；数据仍然按 `--course`（或当前目录配置）严格隔离。

### 实现路径（一步到位，可照抄执行）

#### Step 1：一次性创建工具目录（只做一次）

假设你把工具代码放在：

- `~/rag-tools/`（你也可以换成任何路径）

要求：这个目录里是一个标准 Python 项目，至少包含：

- `pyproject.toml`（或 `setup.py`，推荐 pyproject）
- 一个包目录，例如 `rag/`
- 一个命令入口 `rag`（通过 console\_scripts 或等价方式）

#### Step 2：一次性创建并激活 venv（只做一次）

在任意位置：

- `python -m venv ~/.venvs/rag`
- `source ~/.venvs/rag/bin/activate`  （macOS/Linux）

> 以后每次要用 `rag`，只要先激活这个 venv（或把 venv 固定到你的终端配置）。

#### Step 3：一次性安装工具（只做一次，后续自动跟随源码更新）

- `pip install -U pip`
- `pip install -e ~/rag-tools`

验证：

- `rag --help` 能输出帮助信息就说明成功。

#### Step 4：每篇论文的日常使用方式（你要的工作方式）

1. 你先手动进入该论文目录：
   - `cd projects/ESSAY_X`
2. 在该目录启动 Codex 并初始化：
   - `codex` → `codex /init`
3. 你用自然语言指挥 Codex：它只需要执行类似命令：
   - `rag parse --course ESSAY_X`
   - `rag chunk --course ESSAY_X`
   - `rag embed --course ESSAY_X`
   - `rag query --course ESSAY_X "..."`

> 关键点：你始终从论文目录启动 Codex；工具以命令方式调用；因此上下文不会被“其他论文目录”污染。

#### Step 5：升级/回滚（维护策略）

- 升级工具：直接在 `~/rag-tools/` 里 `git pull` 或修改代码即可；因为是 `-e` 安装，改完立刻生效。
- 回滚工具：用 git checkout 到某个 commit；立刻对所有论文生效。

> 结论：我们只保留 `pip install -e`，因为它在“隔离、稳定、可维护、最少混乱”这四个维度上同时最优。

---

## 5. 系统长什么样（架构图，超直观版）

```
你的文件夹(PDF/课件/feedback)
        |
        | 1) MinerU 解析
        v
结构化文本(MD/JSON)
        |
        | 2) 分块 + 打标签
        v
chunks + metadata(课程/年份/文献key/章节...)
        |
        | 3) Vertex Embeddings（云端，便宜）
        v
向量(embeddings)
        |
        | 4) 本地索引（LanceDB） + 关键词索引（可选 SQLite FTS5）
        v
检索服务（本地，无需常驻）
        |
        | 5) 查询 → Evidence Pack
        v
把证据包喂给 Codex/ChatGPT/Gemini 写作
        |
        | 6) Draft 审计：EVIDENCE_NEEDED 清单
        v
迭代补证据 → 提升质量
```

---

## 6. 数据怎么存（“标签”就是过滤的基础）

每个 chunk（小段落）至少存这些字段：

- `course_id`：属于哪门课/哪篇论文（例如 HUD-TERM1 / ESSAY-01）。**如果你每篇论文完全独立一个目录/索引，这个字段可以固定为同一个值（甚至可选），但建议保留用于防串库校验、日志追溯，以及同一论文内按模块/周次/子主题再细分。**
- `source_type`：evidence\_document / slides / feedback / guidance / exemplar / programme\_info / admin\_notice / personal\_notes / other（注意：这里表示“来源用途类型”，不是文件格式；PDF→MinerU→MD 只是解析管线的一部分；**允许新增自定义类型**，但是否可引用永远由 `citable=true/false` 决定）
- `citable`：是否允许作为**学术引用证据源**（`true/false`）。这是工程上最重要的“闸门”。
  - **它决定什么能进入 Evidence Pack（可引用证据包）**：
    - `citable=true`：允许被 Evidence Mode 检索、允许在草稿中生成引用占位（Author–Year + `{#doc_uid}`）。
    - `citable=false`：只能进入 Instruction Mode（写作约束/改稿/背景理解），**默认不会被当作论文引用**。
  - **它不等于文件格式**：slides 也可能是 PDF；是否可引用只看 `citable`。
  - **默认规则（可改）**：
    - `source_type=evidence_document` → `citable=true`
    - `source_type in {slides, feedback, guidance, exemplar, programme_info, admin_notice, personal_notes}` → `citable=false`
    - 如果你明确要把某份官方文件/灰色文献当作引用：把它放在 `raw/evidence/` 并将 `citable=true`，同时补齐 `publisher/year/url` 等元数据。
  - **安全校验**：查询命令在 Evidence Mode 下会强
- `citation_key`：文献引用键（例如 vojnovic2019...）
- `doc_type`：journal\_article / book / book\_chapter / report / website / slide / feedback / guidance / exemplar
- `title`：标题（可选）
- `year`：年份（用于“近几年”过滤）
- `authors`：作者（可选）
- `publisher`：出版社/机构（可选，书籍/报告常用）
- `doi`：DOI（如果有）
- `isbn`：ISBN（书籍如果有）
- `url`：网页链接（website 类型用）
- `section_path`：章节路径（例如 3.2 Methods → 3.2.1 Data）
- `chunk_id`：唯一 ID
- `text`：chunk 原文
- `page_start/page_end`：若可映射，用于定位
- `embedding`：向量
- `hash`：用于增量更新（内容变了才重新算）

> 过滤查询（按课程、按年份、只看近几年）就是靠这些字段实现的。

---

## 6.5 文献信息与 citation\_key（引用键）怎么来？（A+B 组合策略）

你提出的情况完全正确：

- 有些文献能找到 DOI（常见于期刊论文）；
- 有些没有 DOI（书籍、书章、政策报告、网页等）。

所以我们采用 **A+B 组合**：

### A) 先自动生成一个“能用但未必完美”的 citation\_key（覆盖所有类型）

系统会按这个顺序尽量自动抓（从可靠到兜底）：

1. **reading list（如果有）**：有就用，没有就跳过。老师给的清单通常包含作者/年份/标题，最可靠。
2. **PDF 自带 metadata**：很多 PDF 内部就写了 Title/Author/Year。
3. **MinerU 解析结果的第一页**：学术论文第一页常见 Title/Authors/Year。
4. **文件名规则**：如果你文件名里有 “AuthorYearTitle” 之类，也能做兜底。

当系统拿到 `authors + year + title` 的任意组合后，就生成一个候选 citation\_key，例如：

- 期刊论文：`marmot2015_health-inequalities`
- 机构报告：`who2021_urban-health`
- 网页：`ons2023_mortality-statistics`（机构名 + 年份 + 短标题）

如果撞名（同一作者同一年两篇）：自动加后缀 `a/b/c`。

### B) 如果能找到 DOI，就自动“补全并校正”元数据（更准）

对 **journal\_article** 这类文献：

- 系统会尝试从首页/参考信息里提取 DOI（例如 `10.xxxx/xxxxx`）
- 一旦有 DOI：
  - 用 DOI 去补齐/校正：作者列表、年份、标题、期刊、卷期页（可选）
  - 同时把 DOI 写入 `meta/library.csv`

> 注意：B 只对“有 DOI 的文献”生效；没有 DOI 的（书籍/网页等）仍然走 A。

---

## 6.6 你提到的“晚绑定引用”（不想早期人工校正 library）的做法

你提出的思路是可行的：

- AI 先用系统生成的“兜底 citekey”在草稿里占位；
- 最后再把这些 citekey 对应的 PDF 导入 Zotero，让 Zotero 自动抓元数据；
- 最终生成参考文献表。

为了让这个过程稳定、不怕你移动/改名文件，我们建议把“引用键”拆成两层：

### 6.6.1 内部唯一 ID（永远不变）：`doc_uid`

- 生成方式：用 **PDF 文件内容哈希**（例如 sha1/xxhash）做一个短 ID，如 `doc_8f3a2c1d`。
- 它和 `source_path`（文件相对路径）一起存入索引。
- 这样即使你改文件名/移动文件夹，只要文件内容没变，`doc_uid` 仍然能匹配。

### 6.6.2 草稿里用的 citekey（可以先用 `doc_uid` 当兜底）

- 草稿引用先统一写成：`[@doc_8f3a2c1d]`（机器可追溯）。
- Evidence Pack 必须同时输出：`doc_uid + source_path`，保证你能回到本地文件核验。

### 6.6.3 期末对齐 Zotero（把“兜底 citekey”变成真正可用的文献条目）

- 将“草稿里实际用到的 doc\_uid 列表”导出（命令可做：`rag export-used-sources --course ...`）。
- 把对应 PDF 拖入 Zotero：
  - Zotero 会（在多数情况下）自动为 PDF **检索元数据并创建父条目**；
  - 对检索失败的条目，再用 DOI/ISBN/URL 等方式补齐。
- 最关键的技巧：
  - **把 Zotero 里的 citation key 固定为我们的 \*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\***``（这样你草稿不用全局替换 citekey）。
  - 之后你导出的 bibliography 就能用“正确元数据”，而 citekey 本身不会出现在最终参考文献格式里。

> 这样你完全可以把“人工校正 library.csv”推迟到最后，甚至不做；只要 Zotero 抓到了元数据，你的参考文献表就能正确。

---

## 6.7 你提出的关键问题：Word 最终提交，但 Markdown 写作时需要 Author-Year（叙述式/括号式）怎么办？

现实约束：很多学校按 Harvard/APA 等格式要求 **叙述式引用**（Author (Year)）和 **括号式引用**（(Author, Year)）。最终提交在 Word 时，通常也会把这些算进字数。

我们推荐的做法是：**草稿阶段“显示 Author-Year”，但“绑定 doc\_uid”**。

### 6.7.1 推荐的占位语法（Markdown 中使用）

- **叙述式（in-text / narrative）**：
  - `Marmot (2015){#doc_8f3a2c1d}`
- **括号式（parenthetical）**：
  - `(Marmot, 2015){#doc_8f3a2c1d}`

说明：

- `Marmot (2015)` 负责满足写作格式与大致字数；
- `{#doc_8f3a2c1d}` 负责机器可追溯，方便你后期在 Word/Zotero 精确定位并替换。
- 最终提交前可一键移除 `{#...}` 标记（不影响正文）。

### 6.7.2 如果当时还不知道作者/年份怎么办？

用“长度相近”的通用占位符，避免字数偏差太大：

- 叙述式：`Author (Year){#doc_xxx}`
- 括号式：`(Author, Year){#doc_xxx}`

后期再由 Zotero 元数据补齐。

### 6.7.3 字数会不会被 doc\_uid 影响？要不要担心？

建议：

- 草稿阶段把 `{#doc_uid}` 当作“技术标记”，最终提交前统一删除；
- 为了不超字数：将草稿控制在目标字数的 **1–2%** 以内留出安全边际（尤其引用很多时）。

### 6.7.4 从 Markdown 到 Word 的两种落地方式

- **方式 A（最少依赖，手动插入 Zotero 引用）**：

  1. 把 Markdown 终稿复制到 Word。
  2. Word 里用搜索 `doc_` 快速定位每个引用。
  3. 用 Zotero 插件插入对应条目：
     - 叙述式引用：正文保留作者名，插入引用时用 Zotero 的“抑制作者（Suppress Author）”只显示年份（视你所用样式支持）。
  4. 删除 `{#doc_uid}` 标记。

- **方式 B（更自动，直接导出带 Zotero live citation fields 的 docx）**：

  - 利用 Better BibTeX + Pandoc filter，可把 Markdown 转成 Word 文档，并保留可与 Zotero 连接的引用字段（适合你后面多次迭代）。

---

## 7. 速度与规模（你电脑扛不扛得住）

你的电脑：3060 Laptop 6GB VRAM、16GB RAM。

我们关心的不是“能不能跑”，而是“会不会慢”。

对你目前 100+ 文献规模：

- 真正耗时通常是：PDF 解析（MinerU）与首次 embedding（云端）
- 向量索引与检索：万级 chunks 在单机通常非常轻松

结论：

- **你不需要 Milvus / pgvector 级别的方案**
- 本地 LanceDB/FAISS 级别完全够

---

## 8. 和 Gemini File Search 的关系（我们如何使用/替代）

Gemini File Search 是“官方托管 RAG”，开箱即用。

但我们选择自建方案 B 的原因是：

- 你更看重“论文证据可核验 + 可控 chunk + 可控混合检索策略”
- 同时你担心云端向量库/托管服务的持续成本

我们也保留一个 A/B 测试方法：

- 同一批问题（30–50 条）
- 比较 Recall\@10 / MRR / nDCG\@10 / 引用可核验率
- 用数据决定是否需要在某些模块用 File Search 做对照

---

## 9. PR 具体要做的代码/文件改动（工程清单）

> 这一段是给“写代码的人”看的，但我也会写得很容易懂。

### 9.1 新增目录结构

（补充：为了满足“输出只用 Markdown + 版本化迭代”的硬规则，我们在 `outputs/` 下增加子目录）

- `outputs/`
  - `drafts/`（Codex 写作产物，按 v001/v002… 迭代）
  - `evidence/`（每次 query 的 Evidence Pack，建议也版本化/时间戳化）
  - `audits/`（audit/style\_report 等质检报告，和 draft 版本绑定）

---

- `datasets/`

- `datasets/`

  - `COURSE_ID/`
    - `raw/`
      - `evidence/`（**可引用证据**：学术文献 PDF 等）
        - `pdfs/`
      - `instruction/`（**不可当学术引用，但用于写作约束**）
        - `guidance/`
        - `feedback/`
        - `slides/`
        - `exemplars/`
    - `parsed/`（MinerU 输出：**系统自动生成**，一篇文献一个文件夹，含 md + 图片等）
    - `chunks/`（分块结果：**系统自动生成**）
    - `index/`（本地向量库文件：**系统自动生成**）
    - `meta/`（文献清单、哈希、日志、配置：系统生成/维护）

> 重要：你只需要把“原始文件”放进 `raw/`。`parsed/chunks/index` 都是派生物，永远由程序生成，避免手工搬来搬去。

### 9.2 新增命令（CLI）（CLI）

0. `rag init`
   - 在**当前论文目录**生成最小可用项目骨架：目录结构 + `AGENT.md` + `config.yaml`
   - 写入 \`meta/project.json

- （新增）`meta/builds/<build_id>/build_manifest.json`
- （新增）\`meta/query\_runs/\<query\_id>.json\`\`（记录 project\_id、工具版本）

0.5 `rag new PROJECT_ID`（推荐）

- 在约定父目录创建 `PROJECT_ID/` 并自动执行 `rag init`

1. `rag parse --course COURSE_ID`

2. `rag parse --course COURSE_ID`

   - 扫描 `raw/`
   - 调 MinerU
   - 输出到 `parsed/`

3. `rag chunk --course COURSE_ID`

   - 读取 `parsed/`（MinerU 输出）
   - **先生成 parent（大块，默认按 page 聚合）**：一页/一节 = 一个 parent，保存 `parent_id + parent_text + page/section metadata`
   - **再从每个 parent 切 child（小块，仅用于向量召回）**：目标 \~200 tokens（范围 150–300），overlap 默认 0–10%
   - 写 `chunks/`：
     - `parents.jsonl`（parent 记录）

     - `chunks.jsonl`（child 记录，含 `parent_id`、`hash`、`citable/source_type/year/...`）

     - `chunk_manifest`（用于增量：文档没变就不重复切）


   > 检索时采用“retrieve small, return big”：先检索 child，最终返回 parent（用于上下文与引用核验）。

4. `rag embed --course COURSE_ID`

   - 对新增/变更 chunks 调 Vertex embeddings
   - 写入向量库（LanceDB）

5. `rag build-bm25 --course COURSE_ID`（可选）

   - 建 SQLite FTS5 索引

6. `rag query --course COURSE_ID --year>=2020 "你的问题"`

   - hybrid 召回（BM25 + Dense）
   - 可选 rerank
   - 输出 Evidence Pack（Markdown）

7. `rag audit draft.md --course COURSE_ID`

   - 扫描强断言 → 输出 `EVIDENCE_NEEDED`

   - 扫描结构与 rubric 覆盖 → 输出 `Rubric Compliance Audit`

   - 扫描语言与连贯性 → 输出 `Style Report`（或调用 `rag style-check`）

   - 给出“下一步改稿指令”（按优先级排序）

   - 扫描强断言

   - 输出 `EVIDENCE_NEEDED` 清单 + 推荐 query

### 9.3 配置文件

- `config.yaml`
  - GCP project / region
  - embedding model 名称
  - 是否开启 rerank
  - chunk 大小与 overlap
  - 默认 topK

### 9.4 安全与隐私

- 不在日志里打印任何 API key
- 允许离线解析（MinerU 本地）
- 云端只发送 chunk 文本做 embedding / ranking（可选脱敏策略）

---

## 10. Codex 优先的交互与自动化协议（你真正的使用方式）

这一节是专门为你“cd 到某一篇论文目录 → 打开 Codex → 全程自然语言指挥”的交互方式写的。

### 10.1 你的一致操作方式（强制）

**你每次只在当前论文目录里工作。**

- 你先手动：`cd` 到该论文目录（例如 `datasets/HUD-TERM1/` 或 `projects/ESSAY_X/`）。
- 你在该目录启动 Codex，并执行 `codex /init`。
- 你把资料放在该目录内部约定的位置（`raw/evidence/`、`raw/instruction/`）。

这样做的目的只有一个：**避免 Codex 把别的论文项目混进上下文**。

### 10.2 Codex 必须遵守的“工作边界”（写进 AGENT.md）

为了稳定与可控，我们要求 Codex 永远遵守这些边界（这不是建议，是硬规则）：

1. **只允许读写当前论文目录**（当前工作目录就是项目根目录）。
2. **只允许往派生目录写入**：`parsed/`、`chunks/`、`index/`、`meta/`。
3. **只允许从 **``** 读取原始文件**，不允许自动移动/改名/删除你放的原始文件。
4. **任何会改变检索行为的动作必须先告诉你**（例如：修改 chunk size、改 top\_k、切换 fast reranker、关掉 rerank）。
5. **永远不打印任何 Token/API Key**；日志只记录 trace\_id/错误码/耗时，不记录密钥。

### 10.3 Codex 的职责分工（产品层面的“人机协议”）

**新增一条最重要的职责：Instruction Assimilation（把评分标准“内化”）。**

- 只要 `raw/instruction/` 里有 guidance/rubric/feedback/exemplar 等文件，Codex 必须先完整阅读并提炼成“可执行规则”，写入 `AGENT.md`（以及 `meta/instruction_brief.md`），之后所有写作/审计都以这些规则为约束。
- 这些文件永远 `citable=false`（不能当学术引用），但它们是“怎么写才能得分”的来源，必须被优先吸收。

---

### 10.3 Codex 的职责分工（产品层面的“人机协议”）

你希望的体验是：你说一句话，Codex 自动完成“该做的技术工作”。

我们把 Codex 的职责拆成 3 类：

1. **资料管理与建库**（一次性 / 增量）

- 识别你新增了哪些文件
- 触发 `rag parse/chunk/embed` 的增量流水线
- 输出一个“本次更新摘要”（新增文献数、新增 chunks 数、是否有失败）

2. **写作时自动接入 RAG**

- 你提出写作需求（中文也可以）
- Codex 自动：生成 `q_en` + 关键词 → `rag query` → 拿到 Evidence Pack → 再写段落
- 产出内容必须“有证据驱动”：每个关键断言都要能回指到 Evidence Pack 的 chunk/parent

3. **Draft 审计与补证据闭环**

- 你让 Codex 执行 `rag audit`，得到 `EVIDENCE_NEEDED` 清单
- Codex 给你一个“补证据任务列表”（要找什么、建议检索词、优先级）
- 你补 PDF/报告/网页快照后，Codex 自动做增量更新并回填到 draft

### 10.4 Evidence Pack 如何“自然对接回 Codex 上下文”

我们把 Evidence Pack 设计成 Codex 可直接消费的格式：

- `outputs/evidence_pack.md`（默认输出路径）
- 内容结构固定：
  - `Query Summary`（你问了什么 + q\_en）
  - `Top Evidence (child chunks)`（可引用证据，带 doc\_uid/citation\_key/page/section）
  - `Context (parent pages/sections)`（回填的大上下文，用于核验与避免断章取义）
  - `Used Filters`（例如 `citable=true`, `year>=2020`）

**Codex 写作时必须遵守：**

- 写作前必须先读入最新的 `outputs/evidence_pack.md` 作为上下文
- 写作时只允许引用 `citable=true` 的证据（默认）
- 写作输出必须同时给出：
  - “本段使用了哪些 doc\_uid/citation\_key”清单
  - 对应的引用占位（`Author (Year){#doc_uid}` 或 `(Author, Year){#doc_uid}`）

### 10.5 输出文件格式与版本管理（强制：只用 Markdown，改版必出新文件）

你提出的要求必须写成硬规则，否则 Codex 很容易在迭代时“覆盖原稿”导致追溯困难。

**硬规则（Non‑negotiables）**

1. **Codex 的任何交付物一律落盘为 **``** 文件**（段落、小节、整篇 draft、Evidence Pack、Audit 报告都一样）。
2. **只要你提出“改版/修改/重写/优化/按反馈再来一版”，必须生成一个新的 **``** 文件**，不得覆盖旧版本。
3. 版本号必须体现在文件名里，并且严格递增（v001、v002…）。

**推荐目录与命名规范（默认，除非你另有指定）**

- 草稿（写作输出）：

  - `outputs/drafts/essay_v001.md`
  - `outputs/drafts/essay_v002.md`
  - 若是分章节：`outputs/drafts/section_2_methods_v003.md`

- Evidence Pack（查询证据包，允许多次）：

  - `outputs/evidence/evidence_pack_<YYYYMMDD_HHMM>_v001.md`（每次查询都新建）

- Audit（审计输出，和被审计的草稿版本绑定）：

  - `outputs/audits/essay_v002_audit_v001.md`

**版本号怎么自动递增（Codex 必须实现）**

- Codex 在写入前扫描对应目录下同名模式的文件，找到最大版本号 +1。
- 同时写一条版本日志：`meta/version_log.jsonl`，至少记录：
  - `timestamp`
  - `artifact_type`（draft/evidence/audit/style\_report…）
  - `from_version` → `to_version`
  - `change_request_summary`（你要求怎么改的 1–2 句话）

**交互约束（避免你读文件地狱）**

- Codex 每次输出后，在聊天里只需给：
  - 新文件路径（可点击）
  - 本次改动要点 3–7 条（bullet）
  - 下一步建议（例如：是否需要 `rag audit`）

> 这样你永远可以回到任意历史版本对比，也能把“老师反馈改稿”做成可追溯的迭代链。

---

### 10.6 你希望的“增量补证据”操作（SOP）

你描述的流程是对的，我们把它做成标准动作：

**当你新增一篇文献：**

1. 你把 PDF 放入：`raw/evidence/pdfs/`
2. 你对 Codex 说：
   - “我新增了一个文件：@raw/evidence/pdfs/XXX.pdf，请增量更新索引”
3. Codex 必须执行：
   - `rag parse --course <当前目录>`（增量：只处理新增/变更文件）
   - `rag chunk --course <当前目录>`（增量：只对新增/变更 doc 重切）
   - `rag embed --course <当前目录>`（增量：只对新增/变更 chunks 重新算 embedding 并 upsert）
4. Codex 必须输出一个摘要：
   - 新增文献数 / 失败文献数（含原因）
   - 新增 chunks 数（child）
   - 本次 embedding 花费估算（可选）

**注意：你不需要“手动再索引一次”。**

因为 `rag parse/chunk/embed` 都是 **幂等 + 增量**：同一个文件没变不会重复处理。

### 10.6 写作与审计：必须“边写边审计”，不是等到最后

你问的很关键：Draft audit 要不要等到全文写完？

**不建议等到最后才做。** 论文写作最常见的失败模式是：写了一堆强断言，最后发现证据缺口太大，返工成本爆炸。

我们采用“双层审计节奏”：

1. **段落级/小节级审计（写完就审）**

- 你写完一小节（例如 400–800 words），就跑一次：`rag audit section.md`
- 立刻修补 `EVIDENCE_NEEDED`，避免后面滚雪球

2. **全文终审（交稿前最后一轮）**

- 全文完成后再跑：`rag audit draft_full.md`
- 这一轮更像 QA：查漏补缺、统一引用风格、检查是否有“证据与表述不匹配”

### 10.7 性能/速率异常时的“先提示后变更”机制（你要求的沟通逻辑）

你要求“追求稳定、固定 default-004；若速率太慢，Codex 提醒并沟通是否改方案”。我们把它写成硬规则：

- 默认固定：`semantic-ranker-default-004`
- 程序记录 `p50/p95 latency`、错误率、重试次数
- 触发阈值时，Codex 必须明确提示并给出选项，但不得私自切换：
  - 降 `candidate_k`（50→30）
  - 切 `semantic-ranker-fast-004`
  - 临时关闭 rerank

### 10.8 需要新增一个 AGENT.md（让 Codex “按章办事”）

为了让 Codex 不靠记忆而靠规则工作，我们新增一个文件：`AGENT.md`（放在每个论文目录根部）。

它包含：

- 当前论文目录的边界规则（只能读写本目录）
- 你允许的命令白名单（`rag parse/chunk/embed/query/audit`）
- “自然语言 → 命令”的映射（你说什么，Codex 应该跑哪条命令）
- Evidence Pack 的消费规则（写作前先 query；引用只来自 citable=true）
- 失败处理（MinerU failed/timeout、embedding 失败、rerank 429 的重试策略）

---

### 10.8.1 Instruction Assimilation（把 guidance/feedback/rubric “深度内化”进 AGENT.md）

你提的要求非常关键：**instruction 文件（guidance、评分 rubrics、task brief、历史范文、老师 feedback）不应该只“能检索”，而是要变成 Codex 写作时的硬约束。**

因此我们规定一个强制流程：只要 `raw/instruction/` 里存在文件，Codex 必须先“读完—总结—写入 AGENT.md”，并且在写作过程中持续遵守。

#### A) 什么时候触发？（自动）

- **第一次进入论文目录并 **``** 后**：必须执行一次。
- **任何时候 instruction 文件发生变化**（新增/修改/删除）：必须重新生成。

我们用一个很简单且稳定的增量机制：

- 程序对 `raw/instruction/**` 里的每个文件计算 `sha256`，写到 `meta/instruction_digest.json`。
- 每次写作/审计前对比 digest：有变化才重建 instruction brief（没有变化不重复做）。

#### B) 生成什么产物？（两个文件，目的不同）

1. `meta/instruction_brief.md`（机器与人都能读）

- `Task constraints`：题目/任务是什么，必须回答什么
- `Marking rubric`：评分维度、得分点、扣分点
- `Structure requirements`：必须包含哪些章节/要素
- `Evidence & referencing rules`：需要多少证据、引用风格、是否允许灰色文献
- `Formatting constraints`：字数、图表、附录、提交格式
- `Teacher feedback`：老师明确指出你要改的 3–10 条要点（原句要摘出来）
- `Exemplar patterns`：范文共同特征（但不引用范文作为证据）
- `Do/Don't checklist`：10–20 条可执行检查清单

2. `AGENT.md`（“硬规则清单”，写作时必须遵守）

AGENT.md 里只保留“可执行规则”，不写长篇解释。建议结构：

- **Non‑negotiables（不可违反）**：字数范围、引用格式、必须覆盖的主题点
- **Rubric-to-action mapping**：每个评分维度 → 具体写作动作
- **Tone & style constraints**：比如“不要空话、要批判性分析、要结合课程概念”等
- **Feedback hotfixes**：老师最看重/你最容易失分的点（置顶）

#### C) Codex “读 instruction” 怎么做（工程上可落地）

- instruction 文件也可能是 PDF/Slides（PDF），因此同样走 MinerU 解析成可读文本（但 `citable=false`）。
- Codex 必须逐份检阅：guidance → rubric → task brief → feedback → exemplar → slides（按这个优先级）。
- 生成 brief 时必须引用来源文件路径（例如 `raw/instruction/guidance/...`），方便你核对。

#### D) 写作时怎么用（强制）

- 每次你要求写任何段落/小节/全文：Codex 必须先读取 `AGENT.md` + 最新 `meta/instruction_brief.md`。
- 任何输出都必须显式说明：本段在满足哪些 rubric 点（用 3–5 条 bullet 说清楚）。
- `rag audit` 除了 `EVIDENCE_NEEDED`，还要输出一个 **Rubric Compliance Audit**：
  - 哪些 rubric 点已覆盖
  - 哪些 rubric 点缺失（给出下一步行动建议）

> 这样 instruction 文件就不只是“资料库的一部分”，而是变成 Codex 的“写作操作系统”。

---

> 这样你每次新建论文目录，只要把 `AGENT.md + config.yaml` 放进去，Codex 就能稳定接管。

### 10.9 启动前检查清单（Codex 第一次搭建时最容易卡在这里）

为了让 Codex 一次性把环境跑通，我们在 PR 里明确要求它先做这 6 个检查（并把结果写入 `meta/setup_report.md`）：

1. **确认 **``** 可用**（说明 `pip install -e` 已完成，命令入口已注册）
2. **确认 Python 环境一致**：建议固定一个 venv，并在启动 Codex 前先激活（避免“用错环境导致依赖缺失”）
3. **MinerU Token 的存放方式**：放在 `.env` 或系统环境变量里；仓库只提供 `.env.example`，永远不提交真实 Token
4. **GCP/Vertex 凭证是否可用**：能调用一次最小 API（例如 embeddings 的一次空跑），否则后面会在 `rag embed` 卡死
5. **目录权限与磁盘空间**：`parsed/`、`chunks/`、`index/` 会增长，避免写到只读或空间不足的位置
6. **网络与限流**：对 MinerU/Vertex/Rerank 都必须内置 retry/backoff；并发有上限

### 10.10 关键问题：你开新论文目录/新对话后，Codex 怎么“仍然知道规则”？（用文件保证，不靠聊天记忆）

你这个担心是对的：**聊天窗口的上下文不是可靠的“系统记忆”。** 一旦你开了新对话，Codex 不一定知道根目录那份 PR 写了什么。

解决方案的核心原则：

- **所有规则必须落到“每个论文目录里可读的文件”**（最重要的是 `AGENT.md` + `config.yaml`）。
- Codex 的启动流程必须是：**先读本目录的 AGENT.md，再做任何事**。
- 如果本目录没有这些文件，Codex 必须先执行“脚手架初始化”，把它们生成出来。

为此我们在工具链里新增 2 个命令（强制实现）：

#### 10.10.1 `rag init`（在当前目录生成最小可用的“论文项目骨架”）

你只需要在新论文目录里跑一次：

- `rag init`

它必须完成：

- 创建标准目录结构：`raw/`、`parsed/`、`chunks/`、`index/`、`meta/`、`outputs/`
- 生成 `AGENT.md`（从工具内置模板渲染出来，包含本 PR 的硬规则）
- 生成 `config.yaml`（默认值 + 可改）
- 写入 `meta/project.json`（记录 project\_id、创建时间、工具版本/commit hash，方便复现）

> 这样就算你不开复制粘贴，**新论文目录里也会自动拥有“可执行规则”。**

#### 10.10.2 `rag new <PROJECT_ID>`（一条命令创建新论文项目目录并初始化）

推荐你以后每次开新论文，都用：

- `rag new ESSAY_X`

它会：

- 在约定的父目录（如 `projects/` 或 `datasets/`）创建 `ESSAY_X/`
- 自动执行 `rag init`
- 输出下一步提示：你应该把 PDF/guidance 放到哪里

> 这会把“创建目录 + 放模板文件”这件事彻底自动化。

#### 10.10.3 Codex 的硬规则：发现缺文件必须先初始化

把这条写进 AGENT 模板里（强制）：

- 如果当前目录不存在 `AGENT.md` 或 `config.yaml`：Codex 必须先执行 `rag init`，并向你解释它生成了哪些文件。
- 每次写作/审计前：Codex 必须先读 `AGENT.md` 与 `meta/instruction_brief.md`。

#### 10.10.4 为什么这套机制稳定？

- **跨对话稳定**：新聊天也能读到文件；文件就是系统状态。
- **跨目录稳定**：每篇论文目录自带规则，不会串项目。
- **可复现**：`meta/project.json` 记录工具版本；你回滚工具也能知道当时用的是什么。

---

### 10.12 写作语言质量如何“可控”？（Direct / Concise / Logical / Coherent / Cohesive 的工程化保证）

你要的不是“更漂亮的句子”，而是**读者不需要停下来解码，就能顺着你的推理自然前进**。这件事必须工程化，否则只能靠反复人工改。

我们把“语言质量”拆成两层控制：

- **输入侧（规则）**：从 guidance / rubric / exemplars / feedback 提取“写法约束”，写进 `AGENT.md`。
- **输出侧（质检）**：每次 Codex 产出文字前，必须跑一套“清晰度与连贯性门禁（Quality Gate）”，不通过就重写。

---

#### 10.12.1 Style Assimilation（从 guidance + 范文里抽“写作规则”，写进 AGENT.md）

在 10.8.1 的 Instruction Assimilation 基础上，新增一个固定产物：

- `meta/style_brief.md`

Codex 必须从以下来源提取“可执行写作规则”（按优先级）：

1. **Guidance/Rubric** 中明确写的语言要求（例如：critical analysis、coherence、signposting、clarity、avoid description 等）
2. **老师 feedback** 中对语言/逻辑的具体批评（例如：unclear argument、paragraph lacks focus、need clearer topic sentences）
3. **高分范文** 的可复用模式（结构、段落推进方式、过渡语、论证密度）

`meta/style_brief.md` 必须包含：

- `Non-negotiable language rules`（不可违反）
- `Paragraph template`（每段的标准骨架）
- `Transition bank`（你这门课常用的学术过渡句型）
- `Common failure patterns`（你最容易写糊的地方，如何修）

并且把其中“可执行规则”浓缩写入 `AGENT.md` 的 **Tone & style constraints** 区块（置顶，仅 15–25 条）。

---

#### 10.12.2 Codex 写作算法（强制流程，不是建议）

每次你让 Codex 写任意一段/一节，它必须按下面顺序执行（输出时可省略中间过程，但内部必须做）：

1. **Micro-outline（5 行以内）**

   - 本段要证明的结论（1 句）
   - 论证链条（2–3 个逻辑台阶）
   - 需要的证据点（1–3 条）

2. **Claim → Evidence → Interpretation（CEI）写段落**

   - 每个关键断言都要有证据支撑（来自 Evidence Pack）
   - 证据后必须解释“为什么这条证据支持你的结论”（避免堆引用）

3. **Flow pass（连贯性重写）**

   - 检查每句的“主语”是否清晰、是否突然换话题
   - 检查是否存在“读者必须回头找指代对象”的句子

4. **Clarity pass（清晰度压缩）**

   - 删除无信息密度句子（尤其是“宏大正确但没内容”的句子）
   - 拆长句：优先把一条句子控制在 20–28 个词的可读区间（学术文体允许略长，但避免 40+）

5. **Deliverable**

   - 输出段落
   - 附一行 `Logic chain:`（用 1→2→3 表示这段怎么推进）
   - 附一行 `Rubric coverage:`（本段满足哪些 rubric 点）

---

#### 10.12.3 “读起来顺滑”的具体硬指标（Codex 必须自检）

为了避免“段落看起来有道理，但读者要停下来想”，我们用一组简单但有效的门槛：

- **每段第一句必须是 Topic Sentence**：直接回答“这一段要论证什么”。
- **每段只推进 1 个核心主张**：不要在同一段里同时回答 2 个问题。
- **每句尽量只承载 1 个新信息点**：避免多重从句堆叠。
- **指代必须可回指**：this/these/it 指向的对象必须在上一句出现过且唯一。
- **过渡句必备**：每段末尾用 1 句把读者带到下一段（例如：This matters because… / This suggests… / However…）。

建议的量化阈值（作为 lint 指标，非绝对）：

- 平均句长：18–28 words
- 超长句比例（>35 words）：< 15%
- 每段字数：120–180 words（可随要求调整）

---

#### 10.12.4 新增“语言门禁”：Style Lint + Coherence Test（自动化，写进工具链）

我们把语言质量检查写进 `rag audit`（或新增一个 `rag style-check`，二选一，推荐合并进 audit）：

**Style Lint（可自动）**

- 标出 >35 words 的句子（建议拆分）
- 标出连续 3 句没有明确主语的地方（易糊）
- 标出“空话句”（无名词实体/无因果动词/无证据指向）
- 标出过度名词化（nominalization）密集段落（易读不动）

**Coherence Test（半自动，但 Codex 必须做）**

- 只看每段首句（topic sentences），能否串成一条完整论证线？
- 只看每段尾句（bridge sentences），是否自然引出下一段？

输出产物：

- `outputs/style_report.md`（列出“哪里卡读者、怎么改”）

Codex 规则：如果 style\_report 标红超过阈值（例如 >8 条），必须先重写再交付。

---

#### 10.12.5 70+ 的语言与论证“最低可辩护形态”（你目标导向的写法）

在英国 70+ 常见评语语汇里，语言清晰通常与这些一起出现：

- clear line of argument
- critical engagement with literature
- coherent structure and signposting
- synthesis (not description)

所以 Codex 的输出必须表现为：

- **先立论点，再给证据，再做评述/限制/含义**（不是“介绍了一堆文献”）
- **每节结尾有 mini‑conclusion**（收束并指向下一节）
- **对关键概念给操作性定义**（避免抽象词堆叠）

---

### 10.13 v1 版本“交付标准”（给 Codex 的 Definition of Done）

为了避免 Codex 做出一个“看起来像系统，其实不可用”的东西，我们定义 v1 必须满足：

- 你在论文目录放入 10 篇 PDF + guidance/feedback/slides
- 运行一条命令链（或一个 `rag pipeline`）：能完成 parse → chunk → embed → build-bm25（可选）
- 你用中文问 5 个问题：每个问题都能产出 Evidence Pack（且默认只来自 `citable=true`）
- 你要求写一个 300–500 字段落：Codex 会先 query，再写，并给出引用占位（含 `{#doc_uid}`）
- 你要求审计 draft：能输出 `EVIDENCE_NEEDED` 清单
- 你新增 1 篇 PDF（@文件）：能完成增量更新，并在下一次 query 中可检索到该文献内容

> 非目标（v1 不做）：图数据库/GraphRAG、复杂 UI、跨课程共享同一库、自动生成最终参考文献表（我们先用 doc\_uid 占位 + Zotero 晚绑定）。

---

## 11. 使用说明（从零到可用）

### 第一步：放文件（只放原始文件，按类型分开）

- **学术文献（可引用证据）PDF** 放到：
  - `datasets/HUD-TERM1/raw/evidence/pdfs/`
- **guidance / rubric** 放到：
  - `datasets/HUD-TERM1/raw/instruction/guidance/`
- **老师 feedback** 放到：
  - `datasets/HUD-TERM1/raw/instruction/feedback/`
- **课件 slides** 放到：
  - `datasets/HUD-TERM1/raw/instruction/slides/`
- **历史范文**（可选）放到：
  - `datasets/HUD-TERM1/raw/instruction/exemplars/`

> 规则：instruction 资料会被索引用于“写作约束/改稿”，但默认禁止作为学术引用；真正的引用只来自 `raw/evidence`。

### 0. 先初始化（每篇论文目录只做一次）

在你新建的论文目录里先跑：

- `rag init`

它会生成目录结构、`AGENT.md` 与 `config.yaml`，保证你开新聊天后 Codex 仍能读到规则。

---

### 第二步：解析

运行：

- `rag parse --course HUD-TERM1`

### 第三步：分块

运行：

- `rag chunk --course HUD-TERM1`

它会做两件事：

- 先把每篇文献按页（或按章节）聚合成较大的 parent（方便你阅读与引用核验）
- 再把 parent 切成 \~200 tokens 的小块 child（只用于向量检索定位）

这一步是为了解决“命中精度 vs 上下文完整”这个核心矛盾：检索时用小块更准，交付时用大块更不容易断章取义。

### 第四步：embedding + 建库

运行：

- `rag embed --course HUD-TERM1`

（可选）建 BM25：

- `rag build-bm25 --course HUD-TERM1`

### 第五步：查询证据

运行：

- `rag query --course HUD-TERM1 --year>=2020 "greenspace access and mental health Cape Town"`

你会得到一个 `evidence_pack.md`，直接喂给 Codex/ChatGPT/Gemini。

### 第六步：审计草稿

运行：

- `rag audit essay_draft.md --course HUD-TERM1`

得到 `evidence_needed.md`，逐条补证据。

---

## 12. 测试计划（确保不是“看起来能用”而是真能用）

我们用一个小而硬的基准：

- 选 30–50 条“必须引用证据”的问题
- 对每条标注 1–3 个正确证据来源（citation\_key + 章节/页）

对系统输出：

- Recall\@10：Top-10 里是否出现正确证据
- MRR：正确证据出现得有多靠前
- 引用可核验率：证据包能否回指到原文位置

---

## 13. 未来工作（不在本 PR 内，但预留接口）

1. 如果未来要多 agent/多机器访问：把后端替换为 Qdrant（API 服务）。
2. 如果未来要 UI：加一个本地 Web 界面展示 Evidence Pack 与引用。
3. 如果未来要更强排序：加入更强 reranker（仍走云端 API）。
4. 更强的页码映射：把 MinerU 的结构信息做更精确定位。

---

## 15. PR补丁 v2（产品级缺口 → 可验收标准 DoD）

> 这一节把“真实写论文会踩坑的点”写成 Codex **不可能误解**的硬规则与验收标准。目标不是更复杂，而是让产物**可引用、可复核、可复现、可审计**，从而支撑 70+。

### 15.1 Non-negotiables（硬性要求，违反即失败）

1. **Evidence Pack 必须 Quote-safe（精确可复核定位）**

- 每条 evidence 必须包含：

  - `doc_uid`, `citation_key`, `source_type`, `citable`, `retrieval_score`
  - `parent_locator`（至少一种可复核定位）：
    - 优先：`page_index` / `page_start` / `page_end`
    - 若页码不可得：`parent_id + section_path + char_start/char_end`
  - `snippet`（用于快速阅读）
  - `exact_quote`（可选但推荐）：句子级原文引用（带 locator），用于“逐字核对”

- 若任何 evidence 缺少 locator：**Evidence Pack 生成失败，直接报错**（避免你不敢引用）。

2. **防泄漏（instruction/exemplar 绝不进入 Evidence Pack）**

- Evidence 模式下强制 `citable=true`，并且输出里必须打印：
  - `Applied filters`
  - `Returned sources summary`（按 source\_type 统计数量）
- 若出现任意 `citable=false` 来源：**直接报错终止**。
- Draft 输出必须附：`Sources used (doc_uid list)`。
- `rag verify-citations` 必须检查：任何 `{#doc_uid}` 若对应 source 非 `citable=true` → **失败**。

3. **可复现（build\_id + query\_id 必须落盘）**

- 每次 build（parse/chunk/embed/bm25）必须写：`build_id = timestamp + config_hash + tool_version`。
- 每次 query 必须写：`query_id`，并保存：`q_zh/q_en/filters/top_k/fusion/rerank params/returned doc_uids/scores`。
- Evidence Pack 顶部必须打印：`build_id` 与 `query_id`。

4. **输出只用 Markdown + 版本化迭代**（沿用 10.5 的规则）

---

### 15.2 你提出的疑问逐条落地（并改进 PR）

#### 15.2.1 Paper-level 不是“再检索一遍”，而是“聚合展示”（可选）

你说得对：passage-level 每条都有 doc\_uid/citation\_key，理论上能定位文献。

paper-level 的价值在于**控制覆盖面与去重**：向量召回很容易让 Top-K 被同一篇论文的多个相近段落“吃掉”，你会误以为证据来源很多。

因此我们在 PR 里把它定义成：

- `rag query --mode evidence`（默认）：输出 Evidence Pack（段落级 + parent context）
- `rag query --mode papers`（可选）：对同一批召回 passages 按 `doc_uid` 聚合，输出 Top-N 文献卡片：
  - 标题/作者/年份
  - 命中段落数
  - 代表段落 1–3 条 + locator
  - “为什么相关”一句话

实现要求：**不允许引入新的检索内核**（只是聚合展示），否则复杂度会失控。

#### 15.2.2 反证/争议召回不能死板，改成“高风险断言触发 + 可选开关”

新增配置：

- `counterevidence_mode: off | soft | strict`

默认推荐：`off`（不强行增加负担）；你要更“70+风格”时用 `soft`。

- `soft`：只对“高风险断言（见 15.4）”尝试找限制/边界/争议
- `strict`：对每个核心 claim 都尝试找限制

找不到时的硬规则：

- 不允许编造反面证据
- 标记：`NO_COUNTEREVIDENCE_FOUND_IN_CORPUS`
- 若该 claim 属于高风险断言：再标记 `LIMITATION_NEEDED` 并给建议检索词（可选外部补证据）

#### 15.2.3 页眉页脚清洗不会破坏页码追踪：页码靠 page\_id，不靠页眉文字

硬规则：

- 必须先按页建立 parent：`parent_id = doc_uid:p003` 这类格式
- 清洗只删除“重复行”，不删除页边界与 page\_index
- 被识别为 header/footer 的文本模板要记录在 `meta/parse_quality_report.md`

---

### 15.3 Text Normalization Spec（不可省略，避免 PDF 垃圾文本拖垮检索）

**必须做（v1 must-have）**

- 断词连字符合并：`word- word → wordword`（保留段落边界）
- 统一空白：合并多余空格；保留段落换行
- 页眉页脚去重：按“行在多少页重复出现”识别并删除（保留 page\_index）
- References 区域标记：遇到 `References/Bibliography` 后的内容标记 `source_subtype=references`（默认降权或可过滤）

**质量报告（必须自动生成）**：`meta/parse_quality_report.md`

- 每篇文献重复行比例
- 非字母字符占比（OCR 噪声代理指标）
- 段落长度分布（异常短/异常碎要报警）
- header/footer 模板文本（便于你人工核对）

当质量报告触发阈值（可配）时，Codex 必须提示你：

- 建议重新用 MinerU 另一模型版本/开启 OCR
- 或把该文献标记为 `needs_manual_check=true`

---

### 15.4 Draft 审计闭环：不止 EVIDENCE\_NEEDED，还要 verify-citations（你明确要求的）

#### 15.4.1 “强断言”定义（触发优先审计）

强断言 = 读者会追问“证据在哪”的句子，常见触发：

- 因果：causes/leads to/results in
- 比较：higher/lower/more/less than
- 定量：数字/百分比/显著性/样本量
- 普遍化：always/never/most/widely
- 政策建议：should/must/recommend
- 最高级：first/most significant

#### 15.4.2 审计输出必须是“表格 + 自然语言待办”

你仍然可以自然语言说“帮我审计这一段”。

Codex 的行为是：跑工具 → 输出表格落盘 → 在聊天里给你 5–10 条待办。

表格规范（落盘文件）：

- `outputs/audits/<draft_version>_claims_v001.md`

字段：

- `claim_id | claim_text | claim_type | linked_evidence (0..n) | status (OK/NEED/WAIVED) | suggested_queries`

#### 15.4.3 新增/强化：`rag verify-citations draft.md`

目标：你提出的“检查每个观点是否真的来自文献、citation 是否支撑句子”。

最小可用规则：

- Draft 中所有 `{#doc_uid}` 必须能在库中找到 source
- source 必须 `citable=true`
- 对包含 `{#doc_uid}` 的句子：
  - 在该 doc 的 chunks 里检索 top-k（例如 10）必须命中相似证据，否则标记 `CITATION_WEAK`

输出：

- `outputs/audits/<draft_version>_citations_v001.md`

字段：

- `sentence_id | sentence_text | cited_doc_uids | support_score | status(OK/WEAK/MISSING) | suggested_query`

---

### 15.5 灰色文献（网页/报告/政策）元数据与 accessed date（减少你手工负担）

统一概念：

- `captured_at`：文件进入证据库的时间（系统自动：用文件 mtime）
- `accessed_at`：论文引用声明“访问于”的日期（系统默认：本次 query 运行日期；可覆盖）
- `published_date`：发布日（能识别就填，识别不了就空）

硬字段（source\_type=website/report/policy）：

- `publisher/organisation`
- `url`（若有）
- `captured_at`
- `accessed_at`
- `published_date`（可空）

新增命令（可选，但建议 v1 支持）：

- `rag meta set --doc_uid <...> --accessed_at YYYY-MM-DD`（让你用一句话覆盖默认）

---

### 15.6 v1 Must-have vs Nice-to-have（避免 Codex 偏航）

**v1 Must-have（必须实现）**

- parse/chunk/embed/hybrid query/rerank
- Evidence Pack quote-safe（locator 兜底）
- 防泄漏（citable 过滤 + 失败即终止）
- build\_id/query\_id 落盘
- audit + verify-citations（输出表格 + 自然语言待办）
- 解析质量报告（parse\_quality\_report）
- Markdown 版本化输出

**v1 Nice-to-have（可延后）**

- `--mode papers` 聚合视图（建议实现，低成本高收益）
- counterevidence soft/strict
- cluster/观点地图
- duplicates 指纹与去重报告

---

### 15.7 可测试验收（DoD 清单，Codex 必须逐条通过）

1. Evidence 模式下，Evidence Pack 只包含 `citable=true`，否则报错终止。
2. Evidence Pack 每条 evidence 都有可复核 locator（page 或 char\_range），缺失则失败。
3. 任意 draft 输出都附 `Sources used (doc_uid list)`。
4. `rag verify-citations` 能标出 `WEAK/MISSING` 并给 suggested\_query。
5. 每次 build 生成 `build_id` 并写入 `meta/builds/<build_id>/build_manifest.json`。
6. 每次 query 生成 `query_id` 并写入 `meta/query_runs/<query_id>.json`。
7. parse 后自动生成 `meta/parse_quality_report.md`。
8. 你新增 1 篇 PDF 并 @ 文件后，增量更新后下一次 query 能检到该文献。
9. 任意“改版”都生成新 md 文件（v 递增），且写入 `meta/version_log.jsonl`。

---

## 16. 你现在要我立刻推进的“第一步”（最小闭环）

请你选 **10 篇最代表性的 PDF**（排版复杂的也要包括 1 篇），放到一个课程目录（比如 `HUD-TERM1`）里。

我会基于这 10 篇，先把：

- chunk 数量
- 检索命中率（Recall\@10）
- 是否需要 rerank
- 过滤条件（course/year）的字段设计

全部跑出真实数据，然后把参数定死，进入大规模导入。



### v3-1 Quote-safe locator：从“缺 locator 直接失败”改为两级策略（必改 1）

**替换/覆盖你现有的 Quote-safe 规则为：**

**Locator 字段要求（每条 evidence）：**

- `doc_uid`（必填）
- `parent_id`（必填，用于回到源文档定位单元）
- `locator` 至少一种（按优先级）
  1. **page 级**：`page_index` / `page_start` / `page_end`
  2. **char\_anchor 级（页码缺失兜底）**：`char_start` / `char_end` + `anchor_begin` + `anchor_end` + `section_path(optional)`

**exact\_quote 规范：**

- `exact_quote` 可选但推荐
- 长度限制：每条最多 **40–60 words**

**判定策略：**

- **HARD FAIL（必须终止）**：`doc_uid` 缺失 或 `parent_id` 缺失（无法回源文档）
- **WARN（允许继续输出）**：页码字段缺失，但 char\_anchor 齐全

Evidence Pack 顶部必须输出：

- `LOCATOR_QUALITY: page | char_anchor | weak`

并且每条 evidence 写入：

- `locator_quality`

> 备注：若 locator\_quality=weak（既无页码也无 char\_anchor），Evidence Pack 仍可生成但必须对该条打醒目标记，并在 audit 里提示“需人工复核/需重解析”。

---

### v3-2 verify-citations：阈值与 k 写死到 config（必改 2）

在 PR 中把 `rag verify-citations` 的判定规则写成可复现版本：

**默认参数（写入 config.yaml，v1 固定默认值）：**

- `verify_citations_k: 10`
- `verify_citations_threshold_T: 0.55`

**算法（对每个包含 ****\`\`**** 的句子）：**

1. 仅在该 `doc_uid` 的 **child chunks** 内检索
2. 取 top-k=10
3. 取 `support_score = best_score`（建议用与主检索一致的 rerank 分数，解释性更强）
4. 判定：
   - 没检索到任何 chunk → `MISSING`
   - `support_score < T` → `WEAK`
   - 否则 → `OK`

输出表必须包含：

- `sentence_id | sentence_text | cited_doc_uids | support_score | status(OK/WEAK/MISSING) | suggested_query`

> 后续校准：用 20–50 条真实句子样本校准 T，但 v1 必须先有明确默认值，避免“玄学实现”。

---

### v3-3 CLI 项目推断：统一为 current-directory project（必改 3）

把 PR 里所有 `--course COURSE_ID` 统一成一个原则：

**统一原则：**

- 默认从当前目录的 `meta/project.json` 推断 project\_id
- `--project <ID>` 仅作为覆盖参数（可选）
- 文档里不再出现 `--course`（避免 Codex 乱用）

并在 `rag init` 明确生成：

- `meta/project.json`（project\_id、创建时间、工具版本、config\_hash）

---

### v3-4 papers mode 再收紧一条硬约束（建议改 4）

在 `--mode papers` 的定义后追加：

- `--mode papers` **只能对同一次召回结果聚合展示**（去重/覆盖面视图）
- **不得触发新的检索/新的 embedding/新的 rerank**
- 否则视为实现失败（结果不可比、调参困难、复杂度暴涨）

---

### v3-5 页眉页脚清洗阈值写死（建议改 5）

在“重复行识别 header/footer”处补默认阈值：

- 同一行在该文档中出现比例 **≥ 0.6 的页** → header/footer 候选
- 删除前把候选模板写入 `meta/parse_quality_report.md`（保留样例 3 条）
- 保留 `page_index/parent_id`，清洗不影响页码追踪

---

### v3-6 “不悄悄改配置”改为“建议→你确认→改 config 落盘”（建议改 7）

把“必须征求确认”的表述替换成工程可控版本：

- 性能异常时生成 `meta/health_report.md`（指标+原因+建议）
- 需要切 fast / 降 candidate\_k / 关 rerank：**由你修改 config.yaml**\
  或你一句话让 Codex 改 config，但必须：
  - 修改落盘
  - 记录到 `meta/version_log.jsonl`（from→to）

