# Aura: An Agentic Academic IDE for Vibe-Driven Research Writing

## 1. 系统愿景 (Project Vision)
Aura 是一款专为科研人员设计的 Agent-Native 学术集成开发环境 (IDE)。它不仅是 LaTeX 编辑器，更是一个拥有自主执行权的“AI 副驾驶”。

*   **核心目标**：将科研人员从繁琐的文献检索、LaTeX 调参和文风润色中解放出来。
*   **核心哲学**：Vibe + Logic + Engineering。通过理解用户的写作基调（Vibe），通过自主研究补完逻辑（Logic），并通过自动化工具链实现可靠的输出（Engineering）。

## 2. 核心定义 (Core Definition)
Aura 建立在“闭环代理 (Closed-loop Agency)”的概念之上。与传统的聊天机器人不同，Aura 能够像人类研究员一样，在观察到编译错误或逻辑漏洞时，自主进行修正和深层研究。

## 3. 系统架构 (System Architecture)
系统由三个核心层级组成，通过 MCP (Model Context Protocol) 协议相互通信。

### 3.1 用户交互层 (Frontend - The Dashboard)
*   **IDE Interface**: 基于 Next.js 14 开发，集成 Monaco Editor。
*   **Live Plan**: 一个动态的 Plan.md 面板，显示 Agent 的当前任务、已完成任务和待处理逻辑。
*   **Vibe Console**: 用户输入指令、上传参考论文、定义写作风格的控制台。

### 3.2 Agent 调度层 (Logic Layer - Pydantic AI)
基于 Pydantic AI 框架构建，负责所有的高级决策：
*   **Orchestrator Agent**: 负责解析用户意图，维护任务 DAG（有向无环图）。
*   **Vibe Profiler**: 提取参考论文的“语言指纹”（词汇密度、数学表达惯例等）。
*   **Deep Researcher**: 控制文献搜索闭环，决定何时需要查阅 arXiv。
*   **Writer Agent**: 负责 LaTeX 代码的原子级生成。

### 3.3 沙盒执行层 (Execution Layer - Tools & MCP)
*   **LaTeX Kernel**: 在隔离的 Docker 环境中运行 pdflatex，返回编译 Log。
*   **Git Bridge**: 实现与 Overleaf 的双向同步（基于 Git-Sync）。
*   **Research Tools**: 接入 Semantic Scholar API 和 arXiv API，支持 PDF 到 Markdown 的精确解析。

## 4. 核心功能模块 (Functional Modules)

### 4.1 风格建模与迁移 (Vibe Matching)
Aura 不使用泛泛的“学术语气”，而是通过 RAG 检索用户提供的标杆论文（Reference Papers），并在生成时应用以下约束：
*   **数学范式**：例如，如果标杆论文使用 $$\mathcal{M} = (S, A, P, R, \gamma)$$ 定义 MDP，Aura 将绝不会使用其他符号系统。
*   **叙事张力**：复刻标杆论文在描述挑战（Challenges）和动机（Motivations）时的逻辑密度。

### 4.2 自主研究循环 (Autonomous Research Loop)
当用户要求“写一段 Related Work”时，Agent 将执行以下循环：
1.  **Query**: 生成搜索关键词。
2.  **Filter**: 筛选近 3-5 年的 Top 10 摘要。
3.  **Read**: 使用 OCR 工具（如 Marker）阅读 2-3 篇核心论文的正文。
4.  **Synthesis**: 将新发现与用户论文的逻辑进行对比，生成带有真实 \cite 的 LaTeX。

### 4.3 LaTeX 故障自愈 (Self-healing Compiler)
Agent 在每次完成章节写作后会自动运行编译任务。若编译失败，Agent 会解析 *.log 文件，定位到特定的 LaTeX 语法错误（如未闭合的括号、非法字符、宏包缺失）并自动修复。

## 4. 技术栈 (Tech Stack)

| 模块 | 技术选型 |
| :--- | :--- |
| **基础框架** | Python 3.11+, FastAPI, Pydantic AI |
| **Agent 模型** | Claude 3.5 Sonnet (主推), Gemini 1.5 Pro (备选) |
| **前端** | Next.js, Tailwind CSS, Monaco Editor (React-monaco) |
| **协议** | MCP (Model Context Protocol) |
| **PDF 解析** | Marker-pdf / Nougat |
| **环境** | Docker (LaTeX 编译环境), Git (Overleaf 同步) |

## 5. 成功指标 (Success Metrics)
*   **Zero-Error Compilation**: Agent 提交给用户的代码必须 100% 通过编译。
*   **Fact-Groundedness**: 所有引用的文献必须真实存在，拒绝任何幻觉。
*   **Vibe Accuracy**: 生成内容在词频分布和句法结构上与参考论文的余弦相似度需高于 0.85。

## 6. 开发路线图 (For Claude Code)

### 第一阶段：沙盒内核 (Week 1)
- [ ] 搭建具备 LaTeX 编译能力的 Docker 容器。
- [ ] 实现 MCP 工具：read_paper, run_latex_build, edit_tex_file。

### 第二阶段：Vibe 引擎 (Week 2)
- [ ] 实现 PDF 到 Markdown 的特征提取逻辑。
- [ ] 编写 Pydantic AI 系统提示词，支持风格约束下的文本生成。

### 第三阶段：全闭环集成 (Week 3)
- [ ] 集成 Git 同步功能，实现与 Overleaf 的连接。
- [ ] 开发前端 Plan.md 实时监控面板。
