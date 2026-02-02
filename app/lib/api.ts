/**
 * Aura Backend API Client
 *
 * Utilities for interacting with the FastAPI backend.
 */

// =============================================================================
// Types
// =============================================================================

export interface OutlineSection {
  name: string;
  level: number;
  line: number;
  label: string | null;
  children: OutlineSection[];
}

export interface CompileResult {
  success: boolean;
  pdf_path: string | null;
  error_summary: string;
  log_output: string;
  tex_not_available?: boolean;  // True if no LaTeX compiler (MacTeX or Docker) is available
}

export interface ProjectFile {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
}

export interface Project {
  name: string;
  path: string;
  has_overleaf: boolean;
  last_modified: string;
}

export interface SyncStatus {
  status: 'not_initialized' | 'clean' | 'local_changes' | 'ahead' | 'behind' | 'diverged' | 'conflict' | 'error';
  is_git_repo: boolean;
  has_remote: boolean;
  remote_url: string | null;
  branch: string;
  commits_ahead: number;
  commits_behind: number;
  uncommitted_files: string[];
  last_sync: string | null;
  error_message: string | null;
}

export interface SyncResult {
  success: boolean;
  operation: 'pull' | 'push' | 'sync' | 'setup' | 'resolve' | 'abort';
  message: string;
  files_changed: string[];
  conflicts: string[];
}

// =============================================================================
// Memory Types
// =============================================================================

export interface PaperEntry {
  id: string;
  title: string;
  authors: string[];
  arxiv_id: string;
  summary: string;
  tags: string[];
  created_at: string;
}

export interface CitationEntry {
  id: string;
  bibtex_key: string;
  paper_id: string | null;
  reason: string;
  created_at: string;
}

export interface ConventionEntry {
  id: string;
  rule: string;
  example: string;
  created_at: string;
}

export interface TodoEntry {
  id: string;
  task: string;
  priority: 'low' | 'medium' | 'high';
  status: 'pending' | 'in_progress' | 'completed';
  created_at: string;
}

export interface NoteEntry {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
}

export interface MemoryStats {
  token_count: number;
  warning: boolean;
  threshold: number;
}

export interface MemoryData {
  entries: {
    papers: PaperEntry[];
    citations: CitationEntry[];
    conventions: ConventionEntry[];
    todos: TodoEntry[];
    notes: NoteEntry[];
  };
  stats: MemoryStats;
}

export type MemoryEntryType = 'papers' | 'citations' | 'conventions' | 'todos' | 'notes';

// =============================================================================
// Vibe Research Types
// =============================================================================

export type VibeResearchPhase =
  | 'scoping'
  | 'discovery'
  | 'synthesis'
  | 'ideation'
  | 'evaluation'
  | 'complete';

export interface VibeSession {
  session_id: string;
  topic: string;
  phase: VibeResearchPhase;
  created_at: string;
  config: {
    max_papers: number;
    max_papers_to_read: number;
    target_hypotheses: number;
  };
}

export interface VibeSessionSummary {
  session_id: string;
  topic: string;
  current_phase: VibeResearchPhase;
  is_complete: boolean;
  created_at: string;
  papers_count: number;
  hypotheses_count: number;
}

export interface VibeSessionList {
  count: number;
  sessions: VibeSessionSummary[];
}

export interface VibeStatus {
  session_id: string;
  topic: string;
  phase: VibeResearchPhase;
  progress: number;
  is_complete: boolean;
  stall_count: number;
  papers_found: number;
  papers_read: number;
  themes_count: number;
  gaps_count: number;
  hypotheses_count: number;
}

export interface VibePaper {
  paper_id: string;
  title: string;
  authors: string[];
  year?: number;
  abstract: string;
  citation_count: number;
  url: string;
  source: string;
}

export interface VibeTheme {
  theme_id: string;
  name: string;
  description: string;
  paper_ids: string[];
}

export interface VibeGap {
  gap_id: string;
  title: string;
  evidence: string;
  confidence: 'low' | 'medium' | 'high';
}

export interface VibeHypothesis {
  hypothesis_id: string;
  gap_id: string;
  title: string;
  description: string;
  rationale: string;
  building_blocks: string;
  suggested_experiments: string;
  novelty_score: number;
  feasibility_score: number;
  impact_score: number;
  similar_work: string;
  differentiation: string;
}

export interface VibeState {
  session_id: string;
  created_at: string;
  topic: string;
  scope: Record<string, unknown>;
  papers: VibePaper[];
  papers_read: string[];
  themes: VibeTheme[];
  gaps: VibeGap[];
  hypotheses: VibeHypothesis[];
  current_phase: VibeResearchPhase;
  phase_progress: Record<string, number>;
  last_action: string;
  current_activity: string;
  updated_at: string;
  stall_count: number;
  action_history: string[];
  is_complete: boolean;
  report: string;
  max_papers: number;
  max_papers_to_read: number;
  target_hypotheses: number;
}

export interface VibeReport {
  session_id: string;
  is_complete: boolean;
  topic?: string;
  phase?: VibeResearchPhase;
  message?: string;
  report: string;
  report_path?: string | null;
  report_filename?: string;
  hypotheses: VibeHypothesis[];
  papers_count?: number;
  themes_count?: number;
  gaps_count?: number;
}

export interface VibeIterationResult {
  session_id: string;
  is_complete: boolean;
  phase: VibeResearchPhase;
  progress: number;
  last_action: string;
  output: string;
  papers_found: number;
  hypotheses_count: number;
}

// =============================================================================
// Chat Session Types
// =============================================================================

export interface ChatSession {
  session_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSessionList {
  count: number;
  sessions: ChatSession[];
}

export interface ChatSessionMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatSessionMessage[];
}

// =============================================================================
// Literature Verifier Types
// =============================================================================

export interface CitationUsage {
  cite_key: string;
  line_number: number;
  surrounding_text: string;
  claim: string;
}

export interface VerificationResult {
  cite_key: string;
  status: 'verified' | 'warning' | 'error' | 'pending';
  exists: boolean;
  matched_paper: {
    paper_id: string;
    title: string;
    authors: string[];
    year?: number;
    abstract: string;
    citation_count: number;
    url: string;
  } | null;
  metadata_issues: string[];
  context_score: number;
  context_explanation: string;
  checked_via: 'abstract' | 'pdf' | 'skipped' | 'failed';
  bib_entry: {
    key: string;
    fields: Record<string, string>;
  } | null;
  usages: CitationUsage[];
}

export interface VerifierState {
  approved_citations: string[];
}

// =============================================================================
// API Client
// =============================================================================

class ApiClient {
  private baseUrl: string = 'http://127.0.0.1:8001';
  private initialized: boolean = false;
  private initPromise: Promise<void> | null = null;

  /**
   * Initialize the API client with the backend URL
   */
  async init(): Promise<void> {
    if (this.initialized) return;

    if (this.initPromise) {
      return this.initPromise;
    }

    this.initPromise = (async () => {
      if (typeof window !== 'undefined' && window.aura) {
        try {
          this.baseUrl = await window.aura.getBackendUrl();
          console.log('[API] Initialized with URL:', this.baseUrl);
        } catch (e) {
          console.error('[API] Failed to get backend URL:', e);
        }
      } else {
        console.log('[API] Using default URL:', this.baseUrl);
      }
      this.initialized = true;
    })();

    return this.initPromise;
  }

  /**
   * Ensure API is initialized before making a request
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.initialized) {
      await this.init();
    }
  }

  /**
   * Get the current backend URL
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }

  // ===========================================================================
  // File Operations
  // ===========================================================================

  /**
   * Read a file from a project
   */
  async readFile(projectPath: string, filename: string): Promise<string> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/read`;
    console.log('[API] readFile:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.content;
  }

  /**
   * Write a file to a project
   */
  async writeFile(projectPath: string, filename: string, content: string): Promise<void> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/write`;
    console.log('[API] writeFile:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
        content: content,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }

  /**
   * Delete a file from a project
   */
  async deleteFile(projectPath: string, filename: string): Promise<void> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/delete`;
    console.log('[API] deleteFile:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }

  /**
   * Rename a file in a project
   */
  async renameFile(projectPath: string, oldFilename: string, newFilename: string): Promise<string> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/rename`;
    console.log('[API] renameFile:', url, { projectPath, oldFilename, newFilename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        old_filename: oldFilename,
        new_filename: newFilename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const result = await response.json();
    return result.new_path;
  }

  /**
   * Copy a file or directory in a project
   */
  async copyFile(projectPath: string, sourceFilename: string, destFilename: string): Promise<string> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/copy`;
    console.log('[API] copyFile:', url, { projectPath, sourceFilename, destFilename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        source_filename: sourceFilename,
        dest_filename: destFilename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const result = await response.json();
    return result.new_path;
  }

  /**
   * Move a file or directory in a project (rename to different location)
   */
  async moveFile(projectPath: string, sourceFilename: string, destFilename: string): Promise<string> {
    // Move is just a rename to a different path
    return this.renameFile(projectPath, sourceFilename, destFilename);
  }

  /**
   * Get file list for a project by name (only works for ~/aura-projects/)
   * @deprecated Use listFiles() instead for arbitrary paths
   */
  async getProjectFiles(projectName: string): Promise<ProjectFile[]> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/projects/${encodeURIComponent(projectName)}/files`;
    console.log('[API] getProjectFiles:', url, { projectName });

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('[API] getProjectFiles error:', error);
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get document outline (section structure) for a LaTeX file
   */
  async getOutline(projectPath: string, filepath: string = 'main.tex'): Promise<OutlineSection[]> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/outline`;
    console.log('[API] getOutline:', url, { projectPath, filepath });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filepath,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.outline;
  }

  /**
   * List files in any directory (works with any path)
   */
  async listFiles(projectPath: string): Promise<ProjectFile[]> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/files/list`;
    console.log('[API] listFiles:', url, { projectPath });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('[API] listFiles error:', error);
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Project Operations
  // ===========================================================================

  /**
   * List all projects
   */
  async listProjects(): Promise<Project[]> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/projects`;
    console.log('[API] listProjects:', url);

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Create a new project
   * @param name Project name
   * @param path Optional custom path. If not provided, creates in ~/aura-projects/
   * @param template Optional template ('article', 'minimal'). If not provided, creates empty project
   */
  async createProject(name: string, path?: string, template?: string): Promise<Project> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/projects`;
    console.log('[API] createProject:', url, { name, path, template });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, path, template }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Compilation
  // ===========================================================================

  /**
   * Compile a LaTeX project
   */
  async compile(projectPath: string, filename: string = 'main.tex'): Promise<CompileResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/compile`;
    console.log('[API] compile:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get PDF URL for a project in ~/aura-projects/ (legacy)
   * @deprecated Use getPdfUrlForPath() for projects outside ~/aura-projects/
   */
  getPdfUrl(projectName: string, filename: string = 'main.pdf'): string {
    return `${this.baseUrl}/api/pdf/${encodeURIComponent(projectName)}?filename=${encodeURIComponent(filename)}`;
  }

  /**
   * Get PDF URL for any project path
   * Note: This returns a URL that requires POST, so we need to handle it differently
   */
  async fetchPdfBlob(projectPath: string, filename: string = 'main.pdf'): Promise<Blob> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/pdf/serve`;
    console.log('[API] fetchPdfBlob:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.blob();
  }

  /**
   * Check LaTeX syntax without full compilation
   */
  async checkSyntax(projectPath: string, filename: string = 'main.tex'): Promise<CompileResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/check-syntax`;
    console.log('[API] checkSyntax:', url, { projectPath, filename });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Git/Overleaf Sync
  // ===========================================================================

  /**
   * Get sync status for a project
   */
  async getSyncStatus(projectPath: string): Promise<SyncStatus> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/sync/status`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Set up Overleaf sync for a project
   */
  async setupSync(
    projectPath: string,
    overleafUrl: string,
    username?: string,
    password?: string,
  ): Promise<SyncResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/sync/setup`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        overleaf_url: overleafUrl,
        username,
        password,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Sync project with Overleaf (pull then push)
   */
  async syncProject(projectPath: string, commitMessage?: string, filepath?: string): Promise<SyncResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/sync`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        commit_message: commitMessage,
        filepath: filepath,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Pull changes from Overleaf
   */
  async pullFromOverleaf(projectPath: string): Promise<SyncResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/sync/pull`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Push changes to Overleaf
   */
  async pushToOverleaf(projectPath: string, commitMessage?: string): Promise<SyncResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/sync/push`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        commit_message: commitMessage,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Memory Operations
  // ===========================================================================

  /**
   * Get all memory entries for a project
   */
  async getMemory(projectPath: string): Promise<MemoryData> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/memory?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getMemory:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get memory stats (token count)
   */
  async getMemoryStats(projectPath: string): Promise<MemoryStats> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/memory/stats?project_path=${encodeURIComponent(projectPath)}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Add a paper entry
   */
  async addPaper(
    projectPath: string,
    paper: { title: string; authors: string[]; arxiv_id?: string; summary?: string; tags?: string[] }
  ): Promise<PaperEntry> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/papers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, ...paper }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Add a citation entry
   */
  async addCitation(
    projectPath: string,
    citation: { bibtex_key: string; reason: string; paper_id?: string }
  ): Promise<CitationEntry> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/citations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, ...citation }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Add a convention entry
   */
  async addConvention(
    projectPath: string,
    convention: { rule: string; example?: string }
  ): Promise<ConventionEntry> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/conventions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, ...convention }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Add a todo entry
   */
  async addTodo(
    projectPath: string,
    todo: { task: string; priority?: string; status?: string }
  ): Promise<TodoEntry> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/todos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, ...todo }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Add a note entry
   */
  async addNote(
    projectPath: string,
    note: { content: string; tags?: string[] }
  ): Promise<NoteEntry> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, ...note }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Update a memory entry
   */
  async updateMemoryEntry(
    projectPath: string,
    entryType: MemoryEntryType,
    entryId: string,
    data: Record<string, unknown>
  ): Promise<unknown> {
    await this.ensureInitialized();

    const response = await fetch(`${this.baseUrl}/api/memory/${entryType}/${entryId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath, data }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Delete a memory entry
   */
  async deleteMemoryEntry(
    projectPath: string,
    entryType: MemoryEntryType,
    entryId: string
  ): Promise<void> {
    await this.ensureInitialized();

    const response = await fetch(
      `${this.baseUrl}/api/memory/${entryType}/${entryId}?project_path=${encodeURIComponent(projectPath)}`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }

  /**
   * Clear all memory entries for a project
   */
  async clearMemory(projectPath: string): Promise<void> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/memory/clear`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }

  // ===========================================================================
  // Vibe Research Operations
  // ===========================================================================

  /**
   * Start a new vibe research session
   */
  async startVibeResearch(
    projectPath: string,
    topic: string,
    config?: {
      maxPapers?: number;
      maxPapersToRead?: number;
      targetHypotheses?: number;
    }
  ): Promise<VibeSession> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/start`;
    console.log('[API] startVibeResearch:', url, { projectPath, topic });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        topic,
        max_papers: config?.maxPapers ?? 100,
        max_papers_to_read: config?.maxPapersToRead ?? 30,
        target_hypotheses: config?.targetHypotheses ?? 5,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * List all vibe research sessions for a project
   */
  async listVibeSessions(projectPath: string): Promise<VibeSessionList> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/sessions?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] listVibeSessions:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get status summary for a vibe research session
   */
  async getVibeStatus(projectPath: string, sessionId: string): Promise<VibeStatus> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/status/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getVibeStatus:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get full state for a vibe research session
   */
  async getVibeState(projectPath: string, sessionId: string): Promise<VibeState> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/state/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getVibeState:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get the final report for a vibe research session
   */
  async getVibeReport(projectPath: string, sessionId: string): Promise<VibeReport> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/report/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getVibeReport:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Run one iteration of vibe research
   */
  async runVibeIteration(projectPath: string, sessionId: string): Promise<VibeIterationResult> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/run/${sessionId}`;
    console.log('[API] runVibeIteration:', url);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Stop a running vibe research session
   */
  async stopVibeResearch(sessionId: string): Promise<{ success: boolean; message: string }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/stop/${sessionId}`;
    console.log('[API] stopVibeResearch:', url);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Delete a vibe research session
   */
  async deleteVibeSession(projectPath: string, sessionId: string): Promise<{ success: boolean; message: string }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/vibe-research/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] deleteVibeSession:', url);

    const response = await fetch(url, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Venue Preferences HITL
  // ===========================================================================

  /**
   * Submit venue preferences for a research request
   */
  async submitDomainPreference(
    requestId: string,
    domain: string
  ): Promise<{ success: boolean; request_id: string; domain: string }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/domain-preferences/submit`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: requestId,
        domain,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to submit domain preference: ${response.statusText}`);
    }

    return response.json();
  }

  async submitVenuePreferences(
    requestId: string,
    venues: string[]
  ): Promise<{ success: boolean; request_id: string; venues: string[] }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/venue-preferences/submit`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: requestId,
        venues,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to submit venue preferences: ${response.statusText}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Chat Session Operations
  // ===========================================================================

  /**
   * Create a new chat session
   */
  async createChatSession(
    projectPath: string,
    name?: string
  ): Promise<ChatSession> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/chat/sessions/create`;
    console.log('[API] createChatSession:', url, { projectPath, name });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        name: name || null,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * List all chat sessions for a project
   */
  async listChatSessions(projectPath: string): Promise<ChatSessionList> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/chat/sessions?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] listChatSessions:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get a chat session with its messages
   */
  async getChatSession(projectPath: string, sessionId: string): Promise<ChatSessionDetail> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/chat/session/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getChatSession:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Delete a chat session
   */
  async deleteChatSession(
    projectPath: string,
    sessionId: string
  ): Promise<{ success: boolean; message: string }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/chat/session/${sessionId}?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] deleteChatSession:', url);

    const response = await fetch(url, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Rename a chat session
   */
  async renameChatSession(
    projectPath: string,
    sessionId: string,
    name: string
  ): Promise<ChatSession> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/chat/session/${sessionId}/rename`;
    console.log('[API] renameChatSession:', url, { name });

    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        name,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ===========================================================================
  // Literature Verifier Operations
  // ===========================================================================

  /**
   * Get verifier state (approved citations)
   */
  async getVerifierState(projectPath: string): Promise<VerifierState> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/verify-references/state?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getVerifierState:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get tex/bib file pairs in project
   */
  async getTexBibPairs(projectPath: string): Promise<{
    pairs: Array<{ tex_file: string | null; bib_file: string; display_name: string }>;
    total_tex: number;
    total_bib: number;
  }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/verify-references/pairs?project_path=${encodeURIComponent(projectPath)}`;
    console.log('[API] getTexBibPairs:', url);

    const response = await fetch(url);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Approve a citation manually
   */
  async approveCitation(projectPath: string, citeKey: string): Promise<{ success: boolean }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/verify-references/approve`;
    console.log('[API] approveCitation:', url, { citeKey });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        cite_key: citeKey,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Remove approval from a citation
   */
  async unapproveCitation(projectPath: string, citeKey: string): Promise<{ success: boolean }> {
    await this.ensureInitialized();

    const url = `${this.baseUrl}/api/verify-references/unapprove`;
    console.log('[API] unapproveCitation:', url, { citeKey });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        cite_key: citeKey,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Get base URL for SSE streaming
   */
  getVerifyReferencesUrl(): string {
    return `${this.baseUrl}/api/verify-references`;
  }

  // ===========================================================================
  // Health Check
  // ===========================================================================

  /**
   * Check if the backend is healthy
   */
  async healthCheck(): Promise<boolean> {
    await this.ensureInitialized();

    try {
      const response = await fetch(`${this.baseUrl}/api/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}

// Singleton instance
export const api = new ApiClient();

// Initialize on import (async) - but callers should await ensureInitialized
if (typeof window !== 'undefined') {
  api.init().catch(console.error);
}
