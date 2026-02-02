# OpenResearch

> **OpenResearch** is the open-source version of [YouResearch](https://youresearch.ai). Self-host, customize, and contribute freely.

**Local-First LaTeX IDE with Autonomous AI Research Agent**

OpenResearch is a macOS desktop application that combines an Overleaf-style LaTeX editor with an embedded AI agent capable of autonomous literature research, paper synthesis, and hypothesis generation. Think "Overleaf + Claude Code" as a native app.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Chat Mode](#chat-mode)
  - [Vibe Research Mode](#vibe-research-mode)
  - [Writing Tools](#writing-tools)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Development](#development)
- [Configuration](#configuration)

---

## Features

### Editor
- **Monaco Editor** with LaTeX syntax highlighting and IntelliSense
- **Live PDF Preview** with SyncTeX support
- **File Tree** navigation for multi-file projects
- **Git Integration** with Overleaf push/pull sync

### AI Agent
- **Chat Mode**: Quick research assistance, paper searches, writing help
- **Vibe Research Mode**: Autonomous deep literature exploration with hypothesis generation
- **Slash Commands**: Quick access to common actions (`/research`, `/polish`, `/compile`, etc.)
- **Context Menu AI**: Right-click selected text to polish or ask AI about it
- **Writing Intelligence**: Automated document analysis, citation management, and LaTeX generation
- **22 Built-in Tools**: File operations, LaTeX compilation, research, planning, writing
- **Subagent System**: Specialized agents for research, compilation, planning, and writing
- **Human-in-the-Loop (HITL)**: Approval system for sensitive operations
- **Streaming Responses**: Real-time SSE streaming with tool call visibility

### Writing Intelligence
- **Document Analysis**: Parse LaTeX structure (sections, figures, tables, citations)
- **Citation Management**: Auto-generate BibTeX entries and insert `\cite{}` commands
- **Table Generation**: Create booktabs tables from CSV or markdown data
- **Figure Generation**: Generate TikZ diagrams or pgfplots visualizations
- **Algorithm Generation**: Create algorithm2e pseudocode blocks
- **Consistency Checking**: Find terminology and notation inconsistencies
- **Bibliography Cleanup**: Identify unused BibTeX entries

### Research Capabilities
- **Research Preferences Modal**: Two-step HITL for domain and venue selection
  - LLM-suggested domain based on your query
  - Dynamically generated venue suggestions (conferences/journals)
  - Custom domain and venue input support
- **Google Scholar Search**: Priority search for academic papers
- **Semantic Scholar**: Citation-aware search with impact metrics
- **arXiv Search**: Find papers by topic, author, or ID
- **PDF Reading**: Full-text extraction from arXiv and URLs
- **Citation Graph Traversal**: Explore papers that cite or are cited by a paper
- **Theme Identification**: Cluster papers by methodological approach
- **Gap Analysis**: Identify underexplored research areas
- **Hypothesis Generation**: Propose novel research directions with scoring

### LaTeX Compilation
- **Docker Sandbox**: Isolated TexLive environment
- **Error Fixing**: AI-powered compilation error resolution
- **Syntax Checking**: Pre-compilation validation
- **Docker Guide**: Friendly setup instructions if Docker is not installed

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Electron Application                          │
├─────────────────────────────────────────────────────────────────────┤
│  Next.js Frontend                                                    │
│  ├── Monaco Editor (LaTeX editing)                                  │
│  ├── PDF Viewer (react-pdf)                                         │
│  ├── Agent Panel (chat + vibe research)                             │
│  └── File Tree (project navigation)                                 │
├─────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Python)                                            │
│  ├── Main Agent (Pydantic AI + Claude via OpenRouter)               │
│  │   ├── File Tools (read, edit, write, list, find)                │
│  │   ├── LaTeX Tools (compile, syntax check, get log)              │
│  │   ├── Planning Tools (plan, execute, complete steps)            │
│  │   ├── Writing Tools (analyze, cite, table, figure, algorithm)   │
│  │   └── Delegation (handoff to subagents)                         │
│  │                                                                   │
│  ├── Subagents                                                       │
│  │   ├── Research Agent (Google Scholar, S2, arXiv, PDF, vibe)     │
│  │   ├── Compiler Agent (LaTeX error fixing)                       │
│  │   ├── Planner Agent (task decomposition)                        │
│  │   └── Writing Agent (document analysis, consistency checks)     │
│  │                                                                   │
│  └── Services                                                        │
│      ├── Docker Service (LaTeX compilation)                         │
│      ├── Project Service (file management)                          │
│      ├── Memory Service (persistent notes)                          │
│      └── Semantic Scholar Client (citation graph)                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Installation

### For End Users (DMG)

**Requirements:**
- **macOS 14+** (Apple Silicon recommended)
- **Docker Desktop** (for LaTeX compilation only)

**That's it!** The DMG includes everything else:
- Bundled Python backend (no Python installation needed)
- Bundled Node.js runtime (no Node.js installation needed)
- All dependencies pre-packaged

**Installation Steps:**
1. Download `YouResearch-x.x.x-arm64.dmg` from Releases
2. Open the DMG and drag YouResearch to Applications
3. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) if not already installed
4. Launch YouResearch from Applications
5. On first compile, YouResearch automatically builds the LaTeX Docker image

> **Note:** The app is not code-signed. On first launch, right-click → Open, or go to System Preferences → Security & Privacy → "Open Anyway"

### For Developers

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **macOS** | 14+ | Primary platform |
| **Python** | 3.11+ | Backend development |
| **Node.js** | 18+ | Frontend development |
| **uv** | Latest | Python package management (recommended) |
| **Docker Desktop** | Latest | LaTeX compilation sandbox |

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/ArcoCodes/OpenResearch.git
   cd OpenResearch
   ```

2. **Configure API Key**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env and add your OpenRouter API key
   ```

3. **Install Docker Desktop** (required for LaTeX compilation)

   Download from: https://www.docker.com/products/docker-desktop/

   > The TeX image (`texlive/texlive:latest-small`) is pulled automatically on first compile.

That's it! The start script handles dependency installation automatically.

---

## Quick Start

YouResearch provides a unified start script that handles everything:

```bash
# Make the script executable (first time only)
chmod +x scripts/start.sh
```

### Desktop App (Recommended)

```bash
./scripts/start.sh --electron
```

This starts:
- Backend server on `http://localhost:8001`
- Electron desktop app with embedded Next.js frontend

### Web Development Mode

```bash
./scripts/start.sh
```

This starts:
- Backend server on `http://localhost:8001`
- Web frontend on `http://localhost:3001`

Open http://localhost:3001 in your browser.

### Landing Page

```bash
./scripts/start.sh --landing
```

This starts the servers and opens the YouResearch landing page.

### Other Options

```bash
# Start only the backend (for API testing)
./scripts/start.sh --backend-only

# Start only the frontend (assumes backend is already running)
./scripts/start.sh --frontend-only

# Run API tests after starting
./scripts/start.sh --test

# Run API tests only (assumes backend is running)
./scripts/start.sh --test-only

# Show help
./scripts/start.sh --help
```

### What the Start Script Does

1. **Checks dependencies** - Verifies Python 3.11+, Node.js 18+, npm are installed
2. **Auto-installs packages** - Runs `pip install` and `npm install` if needed
3. **Kills conflicting ports** - Clears ports 8001 and 3001 if occupied
4. **Starts services** - Launches backend and frontend with proper health checks
5. **Cleanup on exit** - Gracefully stops all services on Ctrl+C

### Manual Setup (Alternative)

If you prefer manual control:

**Terminal 1 - Backend:**
```bash
cd backend

# Using uv (recommended)
uv sync
uv run uvicorn main:app --reload --port 8001

# Or using pip (fallback)
pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8001
```

**Terminal 2 - Frontend:**
```bash
cd app
npm install
npm run dev  # Electron + Next.js
# Or: npm run next:dev  # Web only
```

### Production Build (DMG)

Build a distributable DMG file with bundled Python backend:

```bash
cd app
npm run dist:mac
```

The build process:
1. Compiles Python backend into standalone executable (PyInstaller)
2. Builds Next.js frontend
3. Packages everything into Electron app
4. Creates DMG installer

**Output:** `app/dist/YouResearch-<version>-arm64.dmg` (~230MB)

**What's included in the DMG:**
- Electron app with bundled Next.js frontend
- Bundled Python backend (standalone executable, no Python required)
- Dockerfile for LaTeX sandbox

**User requirements after install:**
- Docker Desktop (for LaTeX compilation only)
- That's it! No Python, no Node.js

**Note:** The DMG is not code-signed by default. On first launch, users may need to:
1. Right-click the app → Open
2. Or: System Preferences → Security & Privacy → "Open Anyway"

**Building for distribution:**
```bash
# Build full DMG (includes backend compilation)
npm run dist:mac

# Build unpacked directory (for testing)
npm run pack

# Build frontend only (dev backend already running)
npm run build
```

---

## Usage Guide

### Slash Commands

Type `/` in the chat input to see available commands:

| Command | Description | Keyboard Shortcut |
|---------|-------------|-------------------|
| `/research [topic]` | Search for papers on a topic | - |
| `/vibe [topic]` | Start deep autonomous research | - |
| `/cite [ref]` | Add a citation to the document | - |
| `/polish` | Polish selected text (use with context menu) | ⌘⇧P |
| `/analyze` | Analyze document structure | - |
| `/fix` | Fix LaTeX compilation errors | - |
| `/clean-bib` | Remove unused bibliography entries | - |
| `/compile` | Compile the LaTeX document | - |
| `/sync` | Sync with Overleaf | - |

**Navigation:**
- Use ↑↓ arrow keys to navigate
- Press Tab or Enter to select
- Press Escape to close

### Context Menu AI

Select text in the editor and right-click to access AI actions:

- **✨ Polish with AI** (⌘⇧P): Improve clarity, conciseness, and academic tone
- **💬 Ask AI** (⌘⇧A): Ask questions about the selected text

The selected text appears in a quote box above the chat input, showing the first 10 words. Press Enter to send.

### Chat Mode

Chat mode provides quick, interactive research assistance:

#### Research Preferences

When you trigger a research query (e.g., `/research` or asking the agent to find papers), a two-step preference modal appears:

1. **Domain Selection**:
   - The AI suggests a domain based on your query (e.g., "Machine Learning", "Physiology")
   - You can accept the suggestion or select from common domains
   - Option to enter a custom domain

2. **Venue Selection**:
   - The AI dynamically suggests relevant conferences and journals for your domain + query
   - Select venues to focus your search (e.g., NeurIPS, ICML, ICLR)
   - Option to add custom venues
   - Skip to search all venues

This ensures research results are targeted to your specific academic context.

**Example prompts:**
- "Search Google Scholar for papers on efficient attention mechanisms"
- "Read the paper 2301.07041 and summarize the key findings"
- "Find highly-cited papers on vision transformers from Semantic Scholar"
- "Fix the compilation error in main.tex"
- "Write an introduction paragraph about transformer architectures"

The agent can:
- Search Google Scholar, Semantic Scholar, and arXiv
- Read full paper PDFs
- Edit your LaTeX files
- Compile and fix errors
- Create structured plans for complex tasks

### Vibe Research Mode

Vibe Research is an autonomous deep research workflow that discovers literature, identifies gaps, and generates novel hypotheses.

#### Starting a Vibe Research Session

1. Toggle to **Vibe Research** mode in the Agent Panel
2. Enter your research topic (e.g., "efficient attention for long sequences")
3. Click **Start Research**

#### Research Phases

The agent autonomously progresses through 5 phases:

| Phase | Description | Output |
|-------|-------------|--------|
| **SCOPING** | Clarify research parameters | Domain, constraints, goals |
| **DISCOVERY** | Search comprehensively | 50-100+ papers found |
| **SYNTHESIS** | Read and analyze papers | 5+ themes identified |
| **IDEATION** | Find gaps, propose hypotheses | Gaps + hypothesis proposals |
| **EVALUATION** | Score and rank hypotheses | Ranked hypotheses with scores |

#### Phase Requirements

The agent enforces minimum requirements before advancing:
- **DISCOVERY → SYNTHESIS**: At least 30 papers found
- **SYNTHESIS → IDEATION**: At least 10 papers read AND 3+ themes recorded

#### Output

After completion, Vibe Research generates:
- **LaTeX Report** (`report/vibe_research_<session_id>.tex`)
- **BibTeX File** (`report/vibe_research_<session_id>.bib`)
- **JSON State** (`.youresearch/vibe_research_<session_id>.json`)

The report includes:
- Executive summary
- Literature landscape with identified themes
- Research gaps with confidence levels
- Ranked hypothesis proposals with novelty/feasibility/impact scores

#### Monitoring Progress

The UI displays real-time updates:
- Current phase and progress percentage
- Papers found / read count
- Themes, gaps, and hypotheses discovered
- Current agent activity with timestamp
- Stall warnings if progress stagnates

### Writing Tools

Writing Intelligence provides AI-powered tools for LaTeX document creation and maintenance.

#### Document Analysis

Ask the agent to analyze your document structure:
- "Analyze the structure of main.tex"
- "Show me all figures and tables in my document"
- "List all citations in chapter2.tex"

The `analyze_structure` tool parses LaTeX files and returns:
- Section hierarchy (sections, subsections, etc.)
- Figures with labels and captions
- Tables with labels and captions
- All `\cite{}` references

#### Citation Management

Add citations from research papers:
- "Add citation for the paper 2301.07041 to the introduction"
- "Cite this Semantic Scholar paper in section 3"

The agent will:
1. Fetch paper metadata (title, authors, year, venue)
2. Generate a proper BibTeX entry
3. Add it to your `.bib` file
4. Insert `\cite{key}` at the specified location

#### Table and Figure Generation

Create LaTeX tables from data:
- "Create a table comparing model accuracies from this CSV"
- "Generate a booktabs table with these results: Model A 94.2%, Model B 92.1%"

Generate visualizations:
- "Create a bar chart comparing the F1 scores"
- "Generate a TikZ diagram showing the architecture"
- "Create a line plot of training loss over epochs"

#### Algorithm Pseudocode

Generate algorithm2e blocks:
- "Create an algorithm block for binary search"
- "Generate pseudocode for the attention mechanism"

The `create_algorithm` tool produces properly formatted `algorithm2e` blocks with:
- Inputs and outputs
- Numbered lines
- Control structures (if/else, for, while)

#### Consistency Checking

Delegate to the Writing Agent for document-wide analysis:
- "Check my document for terminology inconsistencies"
- "Find notation inconsistencies in the methods section"
- "Clean up unused bibliography entries"

The Writing Agent scans your document for:
- Inconsistent terminology (e.g., "dataset" vs "data set")
- Notation variations (e.g., "$x$" vs "$X$" for the same variable)
- Unused BibTeX entries that can be removed

---

## API Reference

### Chat Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/stream` | POST | SSE streaming agent responses |
| `/api/chat/history/{project_path}` | GET | Get conversation history |

### Project Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/projects` | GET | List all projects |
| `/api/projects` | POST | Create new project |
| `/api/projects/{path}` | GET | Get project details |
| `/api/projects/{path}/files` | GET | List project files |

### Compilation Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/compile` | POST | Compile LaTeX project |
| `/api/compile/status/{id}` | GET | Get compilation status |

### Vibe Research Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vibe-research/start` | POST | Start new research session |
| `/api/vibe-research/sessions` | GET | List sessions for a project |
| `/api/vibe-research/status/{id}` | GET | Get session status |
| `/api/vibe-research/state/{id}` | GET | Get full session state |
| `/api/vibe-research/run/{id}` | POST | Run one research iteration |
| `/api/vibe-research/report/{id}` | GET | Get generated report |
| `/api/vibe-research/stop/{id}` | POST | Stop running session |
| `/api/vibe-research/{id}` | DELETE | Delete session |

### Sync Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sync/overleaf/push` | POST | Push to Overleaf |
| `/api/sync/overleaf/pull` | POST | Pull from Overleaf |
| `/api/sync/git/status` | GET | Get git status |

### Writing Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze-structure` | POST | Parse LaTeX document structure |
| `/api/clean-bibliography` | POST | Find unused BibTeX entries |

### Research Preference Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/domain-preferences/submit` | POST | Submit domain preference |
| `/api/domain-preferences/pending` | GET | Get pending domain requests |
| `/api/venue-preferences/submit` | POST | Submit venue preferences |
| `/api/venue-preferences/pending` | GET | Get pending venue requests |

---

## Project Structure

```
YouResearch/
├── app/                          # Electron + Next.js frontend
│   ├── components/               # React components
│   │   ├── AgentPanel.tsx        # Chat/Vibe toggle and interface
│   │   ├── VibeResearchView.tsx  # Vibe research display
│   │   ├── DomainPreferenceModal.tsx  # Domain selection HITL modal
│   │   ├── VenuePreferenceModal.tsx   # Venue selection HITL modal
│   │   ├── Editor.tsx            # Monaco editor wrapper
│   │   └── PDFViewer.tsx         # PDF preview component
│   ├── lib/
│   │   └── api.ts                # API client
│   ├── app/                      # Next.js app router
│   │   └── YouResearch/          # Landing page with animations
│   └── electron/                 # Electron main process
│
├── backend/                      # FastAPI Python backend
│   ├── main.py                   # API endpoints
│   ├── agent/
│   │   ├── pydantic_agent.py     # Main agent (22 tools)
│   │   ├── streaming.py          # SSE streaming
│   │   ├── compression.py        # Message compression
│   │   ├── hitl.py               # Human-in-the-loop
│   │   ├── venue_hitl.py         # Research preference HITL (domain/venue)
│   │   ├── steering.py           # Mid-conversation steering
│   │   ├── planning.py           # Structured planning
│   │   ├── vibe_state.py         # Vibe research state
│   │   ├── providers/
│   │   │   ├── openrouter.py     # OpenRouter provider (default)
│   │   │   └── dashscope.py      # DashScope provider (Chinese models)
│   │   ├── subagents/
│   │   │   ├── base.py           # Subagent base class
│   │   │   ├── research.py       # Google Scholar/S2/arXiv + vibe mode
│   │   │   ├── compiler.py       # LaTeX error fixing
│   │   │   ├── planner.py        # Task planning
│   │   │   └── writing.py        # Document analysis + consistency
│   │   └── tools/
│   │       ├── pdf_reader.py     # PDF text extraction
│   │       └── citations.py      # BibTeX generation helper
│   └── services/
│       ├── docker.py             # LaTeX compilation
│       ├── project.py            # Project management
│       ├── memory.py             # Persistent notes
│       ├── latex_parser.py       # LaTeX document parsing
│       └── semantic_scholar.py   # S2 API client
│
├── sandbox/
│   └── Dockerfile                # TexLive image
│
├── docs/plans/                   # Design documents
│
└── projects/                     # User LaTeX projects (gitignored)
```

---

## Development

### Running Tests

```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests
cd app
npm test
```

### Adding New Tools

Tools are registered via decorators on the agent:

```python
from pydantic_ai import Agent, RunContext

@agent.tool
async def my_tool(ctx: RunContext[MyDeps], arg1: str) -> str:
    """
    Tool description shown to the LLM.

    Args:
        arg1: Description of arg1

    Returns:
        Result description
    """
    return f"Result for {arg1}"
```

### Creating a Subagent

```python
from agent.subagents.base import Subagent, SubagentConfig, register_subagent

@register_subagent("my_subagent")
class MySubagent(Subagent[MyDeps]):
    def __init__(self):
        config = SubagentConfig(
            name="my_subagent",
            description="What this subagent does",
            use_haiku=True,
        )
        super().__init__(config)

    @property
    def system_prompt(self) -> str:
        return "You are a specialized agent for..."

    def _create_agent(self) -> Agent:
        agent = Agent(model=self._get_model(), ...)
        # Register tools
        return agent
```

---

## Configuration

### API Access

YouResearch uses **OpenRouter** for LLM access. Get your API key at [openrouter.ai/keys](https://openrouter.ai/keys).

```bash
# Copy the example env file
cd backend
cp .env.example .env

# Edit .env and add your API key
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxx
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Required |
| `OPENROUTER_MODEL` | Default model to use | `anthropic/claude-sonnet-4` |

### Alternative Providers

YouResearch also supports **DashScope** (阿里云百炼) for users in China. Configure in Settings → Model Provider.

### Project Storage

By default, LaTeX projects are stored in:
- `~/youresearch-projects/` - User projects
- `<project>/.youresearch/` - Project metadata and vibe research state

---

## Troubleshooting

### Port Already in Use

```bash
# The start script handles this automatically, but if needed:
lsof -ti:8001 | xargs kill -9  # Kill backend
lsof -ti:3001 | xargs kill -9  # Kill frontend
```

### Docker Not Running

If LaTeX compilation fails, YouResearch will display a friendly Docker installation guide:

**Docker Not Installed:**
- Step-by-step installation instructions
- Direct download link for Docker Desktop
- Note that Docker Desktop is free for personal use

**Docker Not Running:**
- Instructions to start Docker Desktop
- Tip to enable auto-start on login

You can also manually ensure Docker is set up:
1. Ensure Docker Desktop is running (whale icon in menu bar)
2. The LaTeX image is pulled automatically on first compile

### Backend Won't Start

```bash
# Check Python version
python3 --version  # Should be 3.11+

# Reinstall dependencies
cd backend
pip install -r requirements.txt --force-reinstall
```

### Frontend Build Errors

```bash
# Clear cache and reinstall
cd app
rm -rf node_modules .next
npm install
```

### API Connection Failed

If the frontend can't reach the backend:
1. Ensure backend is running on port 8001
2. Check `http://localhost:8001/docs` in browser
3. Look for CORS errors in browser console

---

## License

MIT

---

## Acknowledgments

- [Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/) - Inspiration for dual-ledger state tracking
- [Auto-Deep-Research](https://github.com/HKUDS/Auto-Deep-Research) - Deep research workflow patterns
- [Pydantic AI](https://ai.pydantic.dev/) - Agent framework
- [OpenRouter](https://openrouter.ai/) - LLM API gateway
- [Google Scholar](https://scholar.google.com/) - Academic paper search
- [Semantic Scholar API](https://api.semanticscholar.org/) - Citation graph traversal
- [arXiv API](https://arxiv.org/help/api) - Paper search and retrieval
