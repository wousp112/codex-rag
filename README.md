# Codex + RAG 论文写作助手

这是一个专为学术写作设计的智能助手。它能帮你阅读成百上千页的文献，找出你需要的证据，并像法官一样检查你的论文是否有据可依。

---

## 🤖 For AI Agents (Codex / Claude / Gemini)

**You are equipped with a powerful RAG Toolset.** Do not hallucinate evidence. Use these tools as your **Skills** to deliver Distinction-level (70+) essays.

### 🧠 Your Skills & When to Use Them

1.  **Skill: Retrieve Evidence**
    *   **Command**: `rag query "topic"`
    *   **Use when**: Constructing arguments, creating outlines, or needing citations.
    *   **Behavior**: Search the vector database for citable evidence. Always base your writing on the returned `Evidence Pack`.

2.  **Skill: Self-Correction (Verify)**
    *   **Command**: `rag verify-citations draft.md`
    *   **Use when**: After drafting a section or completing the essay.
    *   **Behavior**: Check if your claims are actually supported by the cited docs. If status is `WEAK` or `MISSING`, rewrite the sentence or find better evidence.

3.  **Skill: Internalize Instructions**
    *   **Command**: `rag parse` (reads `raw/instruction/`)
    *   **Use when**: Starting a new project.
    *   **Behavior**: Read guidelines, rubrics, and feedback to understand constraints (tone, structure, formatting) before writing.

4.  **Skill: Quality Audit**
    *   **Command**: `rag audit draft.md`
    *   **Use when**: Checking flow and argument strength.
    *   **Behavior**: This now also generates a **Clean Copy** (no IDs) and calculates **Net Word Count**.

---

## 🤖 1. Agent 交互模式 (小白专用)

你不需要记忆任何指令，只需在终端启动你的 AI Agent，然后像对待真人助理一样指挥它。

### 常用“黑话”对照表

| 你对 AI 说... | AI 实际上帮你做的 (幕后工作) | 作用 |
| :--- | :--- | :--- |
| **"初始化一下项目"** | `rag init` | 创建文件夹结构，准备好放资料的地方 |
| **"我放好 PDF 了，帮我解析"** | `rag parse` | 把 PDF 变成电脑能读懂的文字 (调用 MinerU) |
| **"切分一下文档"** | `rag chunk` | 把长文章切成小段，方便查找 |
| **"生成向量库"** | `rag embed` | 让 AI 读懂所有内容并存入大脑 (LanceDB) |
| **"帮我找找关于 X 的证据"** | `rag query "X"` | 在所有文献里翻找，给你一个“证据包” |
| **"审计一下我的草稿"** | `rag audit draft.md` | 检查你的断言是否有证据，给出修改建议 |
| **"检查引用对不对"** | `rag verify-citations draft.md` | 核实你引用的文献是否真的支持你的观点 |

---

## 🛠️ 2. 环境与安装

在使用前，请确保你已经安装了本工具。

### 推荐安装方式 (一次性)

1.  **Python 3.10+**: 请确保电脑安装了 Python。
2.  **安装本工具**:
    在解压后的本工具文件夹内，打开终端运行：
    ```bash
    pip install -e .
    ```
3.  **配置密钥 (.env)**:
    在文件夹里新建一个 `.env` 文件，填入你的密钥（MinerU 和 GCP）。我们已经为你准备好了模板，填空即可。

    > **⚠️ 特别注意 (GCP 配置)**：
    > `.env` 中的 `GOOGLE_APPLICATION_CREDENTIALS` 必须填入 **JSON 密钥文件的路径** (例如 `./gcp_credentials.json`)，而不是一串字符！请确保该文件已下载并放在项目根目录下。

---

## 📚 3. 多任务/多论文管理指南

**黄金法则：一篇论文 = 一个新文件夹**

为了避免不同课程或论文的资料混在一起，我们建议每写一篇新论文，就新建一个文件夹。

### 📁 资料怎么放？(核心规则)

这套系统把资料分为两类，请务必放对位置：

1.  **学术文献** (`raw/evidence/pdfs/`)
    *   **放什么**：期刊论文、书籍、正式报告。
    *   **作用**：**可引用 (Citable=True)**。只有这里的资料会被当作证据检索出来，并允许出现在最终的参考文献里。

2.  **指令与背景** (`raw/instruction/`)
    *   **放什么**：课件(Slides)、作业要求(Guidance)、评分标准(Rubric)、范文。
    *   **作用**：**不可引用 (Citable=False)**。AI 会阅读它们来学习“该怎么写”、“老师喜欢什么风格”，但绝不会把课件当作学术证据引用到论文里（这是为了防止学术不端）。

### 如何开始一篇新论文？

1.  **新建文件夹**: 比如叫 `My_Thesis_Final`。
2.  **进入文件夹**: 在终端里 `cd My_Thesis_Final`。
3.  **呼唤 Agent**: 启动 Codex/Gemini。
4.  **下令**: "帮我初始化这个新项目" (AI 会运行 `rag init`)。
5.  **放资料**: 按照 AI 的提示，把这门课的资料放入对应文件夹：
    *   **学术文献 (Citable)** -> `raw/evidence/pdfs/`
        *   放期刊论文、书籍、报告。**只有这里的资料会被当作证据引用**。
    *   **课件与要求 (Non-citable)** -> `raw/instruction/`
        *   放 Slides、Guidance、Rubric。**这些资料仅供 AI 学习风格和规则，不会被当作引用来源**。
6.  **开始工作**: "解析资料" -> "开始写作"。

---

## 📝 4. 进阶：如何使用生成的证据？

当你问 AI "帮我找找关于气候变化的证据" 后，它会在 `outputs/` 目录下生成一个 Markdown 文件（例如 `evidence_pack_v001.md`）。

你可以直接对 AI 说：
> "读取 `outputs/evidence_pack_v001.md`，根据里面的证据，帮我写一段关于气候变化对农业影响的分析，要求学术风格。"

---

## 📂 目录结构 (AI 会自动维护)

- `raw/`: 你只需要把原始 PDF 扔进这里。
- `outputs/`: 所有的产出（草稿、证据包、审计报告）都在这里。
- `meta/`: 系统日志和配置，不用管。
- `config.yaml`: 项目配置，AI 会帮你看着办。
