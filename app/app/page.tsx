'use client';

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import Toolbar from '@/components/Toolbar';
import FileTree from '@/components/FileTree';
import FileOutline from '@/components/FileOutline';
import Editor, { PendingEdit, SendToAgentContext } from '@/components/Editor';
import PDFViewer from '@/components/PDFViewer';
import MarkdownPreview from '@/components/MarkdownPreview';
import AgentPanel from '@/components/AgentPanel';
import NewProjectModal from '@/components/NewProjectModal';
import SettingsModal from '@/components/SettingsModal';
import MemoryModal from '@/components/MemoryModal';
import DockerGuide from '@/components/DockerGuide';
import DockerSetupWizard from '@/components/DockerSetupWizard';
import DockerStartModal from '@/components/DockerStartModal';
import DockerInstallModal from '@/components/DockerInstallModal';
import DockerBuildModal from '@/components/DockerBuildModal';
import FallbackNoticeModal from '@/components/FallbackNoticeModal';
import RenameModal from '@/components/RenameModal';
import ResizeHandle from '@/components/ResizeHandle';
import { api, SyncStatus } from '@/lib/api';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface ProjectState {
  path: string | null;
  name: string;
  currentFile: string | null;
  files: string[];
}

// =============================================================================
// Main Page
// =============================================================================

export default function Home() {
  // Project state
  const [project, setProject] = useState<ProjectState>({
    path: null,
    name: 'No Project Open',
    currentFile: null,
    files: [],
  });

  // Editor state
  const [editorContent, setEditorContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState(false);
  // Ref to store latest editor content synchronously (avoids race condition on compile)
  const editorContentRef = useRef<string>('');

  // PDF state
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [currentPdfFile, setCurrentPdfFile] = useState<string | null>(null);

  // SyncTeX state (PDF to source navigation)
  const [syncTexLine, setSyncTexLine] = useState<number | null>(null);
  const [syncTexColumn, setSyncTexColumn] = useState<number | null>(null);

  // Compilation state
  const [isCompiling, setIsCompiling] = useState(false);
  const [compileStatus, setCompileStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [compileLog, setCompileLog] = useState<string>('');

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [showMemory, setShowMemory] = useState(false);
  const [showDockerGuide, setShowDockerGuide] = useState(false);
  const [showDockerWizard, setShowDockerWizard] = useState(false);
  const [showDockerStartModal, setShowDockerStartModal] = useState(false);
  const [showDockerInstallModal, setShowDockerInstallModal] = useState(false);
  const [showDockerBuildModal, setShowDockerBuildModal] = useState(false);
  const [showFallbackNotice, setShowFallbackNotice] = useState(false);
  const [dockerBuildPhase, setDockerBuildPhase] = useState<'idle' | 'starting' | 'pulling' | 'building' | 'complete' | 'error'>('idle');
  const [dockerBuildProgress, setDockerBuildProgress] = useState(0);
  const [dockerBuildError, setDockerBuildError] = useState<string | null>(null);
  const [dockerStarting, setDockerStarting] = useState(false);
  const [dockerChecked, setDockerChecked] = useState(false);

  // Sync state
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus['status'] | null>(null);

  // Pending edit state (for HITL approval in Editor)
  const [pendingEdit, setPendingEdit] = useState<PendingEdit | null>(null);

  // File clipboard state (for cut/copy/paste)
  const [fileClipboard, setFileClipboard] = useState<{
    path: string;
    operation: 'cut' | 'copy';
  } | null>(null);

  // Rename modal state
  const [renameModal, setRenameModal] = useState<{
    isOpen: boolean;
    path: string;
    name: string;
  }>({ isOpen: false, path: '', name: '' });

  // Quoted text state (for sending selected text to agent)
  const [quotedContext, setQuotedContext] = useState<SendToAgentContext | null>(null);

  // Panel layout state
  const [fileTreeWidth, setFileTreeWidth] = useState(200);
  const [pdfViewerWidth, setPdfViewerWidth] = useState(400);
  const [agentPanelWidth, setAgentPanelWidth] = useState(350);
  const [outlineHeight, setOutlineHeight] = useState(200);
  const [isAgentPanelOpen, setIsAgentPanelOpen] = useState(true);
  const [isResizing, setIsResizing] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Panel resize constraints
  const MIN_FILE_TREE = 150;
  const MAX_FILE_TREE = 400;
  const MIN_PDF_VIEWER = 300;
  const MIN_AGENT_PANEL = 280;
  const MIN_OUTLINE_HEIGHT = 100;
  const MAX_OUTLINE_HEIGHT = 400;

  // File type detection
  const isMarkdownFile = useMemo(() => {
    return project.currentFile?.endsWith('.md') ?? false;
  }, [project.currentFile]);

  // Debounced content for Markdown preview (300ms)
  const [debouncedMarkdownContent, setDebouncedMarkdownContent] = useState<string>('');

  useEffect(() => {
    if (!isMarkdownFile) {
      setDebouncedMarkdownContent('');
      return;
    }
    const timer = setTimeout(() => {
      setDebouncedMarkdownContent(editorContent);
    }, 300);
    return () => clearTimeout(timer);
  }, [editorContent, isMarkdownFile]);

  // Initialize API client and settings on mount
  useEffect(() => {
    api.init().catch(console.error);
    // Load settings from Electron storage (for persistence across app restarts)
    import('@/lib/providerSettings').then(({ initializeSettings }) => {
      initializeSettings().catch(console.error);
    });
  }, []);

  // Track container width for panel layout calculations
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Set initial width
    setContainerWidth(container.clientWidth);

    // Use ResizeObserver to track width changes
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Check Docker status on app startup
  useEffect(() => {
    if (dockerChecked) return;

    let attempts = 0;
    const maxAttempts = 10;

    const checkDockerStatus = async () => {
      attempts++;
      try {
        const res = await fetch('http://localhost:8001/api/docker/status');
        if (!res.ok) {
          throw new Error('API not ready');
        }

        const status = await res.json();
        console.log('Docker status:', status);
        setDockerChecked(true);

        if (status.docker_installed && !status.docker_running) {
          // Docker is installed but not running - ask to start
          setShowDockerStartModal(true);
        } else if (!status.docker_installed) {
          // Docker not installed - show installation modal
          setShowDockerInstallModal(true);
        } else if (status.docker_running && !status.image_pulled) {
          // Docker is running but image doesn't exist - show fallback notice
          console.log('Docker running but image not found, showing fallback notice...');
          setShowFallbackNotice(true);
        }
        // If Docker is running with image, do nothing
      } catch (e) {
        console.log(`Docker status check attempt ${attempts}/${maxAttempts} failed`);
        // Retry if we haven't exceeded max attempts
        if (attempts < maxAttempts) {
          setTimeout(checkDockerStatus, 2000);
        }
      }
    };

    // Initial delay to let backend start
    const timer = setTimeout(checkDockerStatus, 2000);
    return () => clearTimeout(timer);
  }, [dockerChecked]);

  // Load sync status when project changes
  const loadSyncStatus = useCallback(async () => {
    if (!project.path) {
      setSyncStatus(null);
      return;
    }
    try {
      const status = await api.getSyncStatus(project.path);
      setSyncStatus(status.status);
    } catch (e) {
      console.error('Failed to load sync status:', e);
      setSyncStatus(null);
    }
  }, [project.path]);

  useEffect(() => {
    loadSyncStatus();
  }, [loadSyncStatus]);

  // Compile keyboard shortcut ref (to access handleCompile in useEffect)
  const handleCompileRef = useRef<() => void>(() => {});

  // =============================================================================
  // File List Fetching
  // =============================================================================

  const fetchFileList = useCallback(async (projectPath: string) => {
    try {
      console.log('[Page] Fetching files for path:', projectPath);
      const files = await api.listFiles(projectPath);

      // Extract paths from file objects (backend returns {name, path, type, size})
      const filePaths = files.map((f) => f.path);

      setProject((prev) => ({
        ...prev,
        files: filePaths,
      }));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch file list:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to load files: ${errorMsg}`);
    }
  }, []);

  // =============================================================================
  // Project Operations
  // =============================================================================

  const handleOpenProject = useCallback(async () => {
    if (typeof window !== 'undefined' && window.aura) {
      const projectPath = await window.aura.openProject();
      console.log('[Page] Open project path:', projectPath);

      if (projectPath) {
        // Extract project name - filter out empty strings to handle trailing slashes
        const pathParts = projectPath.split('/').filter((p: string) => p.length > 0);
        const name = pathParts[pathParts.length - 1] || 'Project';
        console.log('[Page] Extracted project name:', name);

        setProject({
          path: projectPath,
          name,
          currentFile: null,
          files: [],
        });
        setEditorContent('');
        editorContentRef.current = '';
        setIsDirty(false);
        setPdfUrl(null);
        setCompileStatus('idle');
        setError(null);
        setPendingEdit(null);

        // Fetch file list using full path
        await fetchFileList(projectPath);
      }
    }
  }, [fetchFileList]);

  const handleNewProject = useCallback(() => {
    setIsNewProjectModalOpen(true);
  }, []);

  const handleCreateProject = useCallback(async (name: string) => {
    try {
      // First, open folder picker to choose location
      if (!window.aura) {
        throw new Error('Electron API not available');
      }
      const selectedPath = await window.aura.newProject(name);

      if (!selectedPath) {
        // User cancelled the folder picker
        return;
      }

      // Create project at selected path (empty, no template)
      const newProject = await api.createProject(name, selectedPath);

      // Use the path from the response
      const projectPath = newProject.path;
      if (projectPath) {
        setProject({
          path: projectPath,
          name,
          currentFile: null,
          files: [],
        });
        setEditorContent('');
        editorContentRef.current = '';
        setIsDirty(false);
        setPdfUrl(null);
        setCompileStatus('idle');
        setError(null);
        setPendingEdit(null);

        // Fetch file list using full path
        await fetchFileList(projectPath);
      }
    } catch (err) {
      console.error('Failed to create project:', err);
      setError(`Failed to create project: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [fetchFileList]);

  // =============================================================================
  // File Operations
  // =============================================================================

  const handleFileSelect = useCallback(async (filePath: string) => {
    if (!project.path) return;

    setProject((prev) => ({ ...prev, currentFile: filePath }));
    setEditorContent('');
    editorContentRef.current = '';

    try {
      const content = await api.readFile(project.path, filePath);
      setEditorContent(content);
      editorContentRef.current = content;
      setIsDirty(false);
      setError(null);
    } catch (err) {
      console.error('Failed to read file:', err);
      const errorContent = `% Error loading ${filePath}\n% ${err instanceof Error ? err.message : 'Unknown error'}`;
      setEditorContent(errorContent);
      editorContentRef.current = errorContent;
      setError(`Failed to load file: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path]);

  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      // Update ref synchronously first (ensures compile always has latest content)
      editorContentRef.current = value;
      setEditorContent(value);
      setIsDirty(true);
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!project.path || !project.currentFile) return;

    try {
      // Use ref value to ensure we save the latest content (avoids race condition)
      await api.writeFile(project.path, project.currentFile, editorContentRef.current);
      setIsDirty(false);
      setError(null);
    } catch (err) {
      console.error('Failed to save file:', err);
      setError(`Failed to save: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, project.currentFile]);

  // =============================================================================
  // Docker Start Handler
  // =============================================================================

  // Start Docker image build in background
  const startDockerBuild = useCallback(async () => {
    if (dockerBuildPhase !== 'idle' && dockerBuildPhase !== 'error') {
      return; // Already building
    }

    setDockerBuildPhase('starting');
    setDockerBuildProgress(5);
    setDockerBuildError(null);

    try {
      // Trigger the build (don't await - it runs in background)
      fetch('http://localhost:8001/api/docker/pull-image', { method: 'POST' })
        .catch(err => console.error('Build request failed:', err));

      // Poll for status
      let pollCount = 0;
      const maxPolls = 1200; // 20 minutes max

      const pollStatus = async () => {
        if (pollCount >= maxPolls) {
          setDockerBuildPhase('error');
          setDockerBuildError('Build timed out');
          return;
        }

        pollCount++;

        try {
          const res = await fetch('http://localhost:8001/api/docker/status');
          const status = await res.json();

          if (status.image_pulled) {
            setDockerBuildPhase('complete');
            setDockerBuildProgress(100);
            return;
          }

          // Update progress simulation
          const progress = Math.min(95, 5 + (pollCount / 12)); // ~10 mins to 95%
          setDockerBuildProgress(progress);

          if (pollCount > 30) {
            setDockerBuildPhase('building');
          } else {
            setDockerBuildPhase('pulling');
          }

          // Continue polling
          setTimeout(pollStatus, 1000);
        } catch {
          // Continue polling even on error
          setTimeout(pollStatus, 2000);
        }
      };

      // Start polling
      setTimeout(pollStatus, 2000);
    } catch (e) {
      setDockerBuildPhase('error');
      setDockerBuildError(e instanceof Error ? e.message : 'Build failed');
    }
  }, [dockerBuildPhase]);

  const handleStartDocker = useCallback(async () => {
    setDockerStarting(true);
    try {
      await fetch('http://localhost:8001/api/docker/start', { method: 'POST' });
      // Poll until Docker is running
      const maxAttempts = 30;
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        try {
          const res = await fetch('http://localhost:8001/api/docker/status');
          const status = await res.json();
          if (status.docker_running) {
            setShowDockerStartModal(false);
            setDockerStarting(false);
            // Check if image exists, if not, show fallback notice
            if (!status.image_pulled) {
              console.log('Docker running but image not found, showing fallback notice...');
              setShowFallbackNotice(true);
            }
            return;
          }
        } catch {
          // Continue polling
        }
      }
      setDockerStarting(false);
    } catch (e) {
      console.error('Failed to start Docker:', e);
      setDockerStarting(false);
    }
  }, []);

  // =============================================================================
  // SyncTeX Handler (PDF to source navigation)
  // =============================================================================

  const handleSyncTexClick = useCallback(async (file: string, line: number, column?: number) => {
    console.log('[SyncTeX] Jump to:', file, 'line', line, 'column', column);

    // If the file is different from current, switch to it first
    if (file !== project.currentFile) {
      await handleFileSelect(file);
      // Small delay to let editor load, then scroll
      setTimeout(() => {
        setSyncTexLine(line);
        setSyncTexColumn(column ?? null);
      }, 150);
    } else {
      setSyncTexLine(line);
      setSyncTexColumn(column ?? null);
    }
  }, [project.currentFile, handleFileSelect]);

  const handleSyncTexScrollComplete = useCallback(() => {
    // Clear the syncTexLine and column after scroll is complete
    setSyncTexLine(null);
    setSyncTexColumn(null);
  }, []);

  // Handler for outline navigation (jump to line in editor)
  const handleOutlineNavigate = useCallback((line: number) => {
    setSyncTexLine(line);
    setSyncTexColumn(null);
  }, []);

  // =============================================================================
  // Compilation
  // =============================================================================

  const handleCompile = useCallback(async () => {
    if (!project.path) return;

    // Determine which file to compile
    let fileToCompile = project.currentFile;

    // If current file is not a .tex file, try to find main.tex or any .tex file
    if (!fileToCompile || !fileToCompile.endsWith('.tex')) {
      const texFiles = project.files.filter(f => f.endsWith('.tex'));
      if (texFiles.includes('main.tex')) {
        fileToCompile = 'main.tex';
      } else if (texFiles.length > 0) {
        fileToCompile = texFiles[0];
      } else {
        setError('No .tex file found to compile');
        return;
      }
    }

    // Save current file first if dirty
    if (isDirty && project.currentFile) {
      await handleSave();
    }

    setIsCompiling(true);
    setCompileStatus('idle');
    setCompileLog('');

    try {
      const result = await api.compile(project.path, fileToCompile);

      setCompileLog(result.log_output || '');

      if (result.success) {
        setCompileStatus('success');
        // Fetch PDF as blob and create object URL
        const pdfName = fileToCompile.replace(/\.tex$/, '.pdf');
        try {
          const pdfBlob = await api.fetchPdfBlob(project.path, pdfName);
          // Revoke old URL to prevent memory leaks
          if (pdfUrl) {
            URL.revokeObjectURL(pdfUrl);
          }
          const newPdfUrl = URL.createObjectURL(pdfBlob);
          setPdfUrl(newPdfUrl);
          setCurrentPdfFile(pdfName);
        } catch (pdfErr) {
          console.error('Failed to load PDF:', pdfErr);
          setError(`Compilation succeeded but failed to load PDF: ${pdfErr instanceof Error ? pdfErr.message : 'Unknown error'}`);
        }
      } else {
        setCompileStatus('error');
        // Check if no LaTeX compiler is available
        if (result.tex_not_available) {
          // Fetch Docker status to determine the best action
          try {
            const dockerStatus = await fetch('http://localhost:8001/api/docker/status');
            const status = await dockerStatus.json();

            if (status.docker_installed && !status.docker_running) {
              // Docker is installed but not running - show start modal
              setShowDockerStartModal(true);
            } else {
              // Docker not installed or needs setup - show install modal
              setShowDockerInstallModal(true);
            }
          } catch {
            // If we can't fetch status, show the wizard
            setShowDockerWizard(true);
          }
        } else {
          setError(result.error_summary || 'Compilation failed');
        }
      }
    } catch (err) {
      console.error('Compilation error:', err);
      setCompileStatus('error');
      setError(`Compilation error: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsCompiling(false);
    }
  }, [project.path, project.currentFile, project.files, isDirty, handleSave, pdfUrl]);

  // Keep handleCompileRef in sync and set up global keyboard shortcut
  useEffect(() => {
    handleCompileRef.current = handleCompile;
  }, [handleCompile]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // ⌘B or Ctrl+B to compile
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        handleCompileRef.current();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // =============================================================================
  // Refresh File List
  // =============================================================================

  const handleRefreshFiles = useCallback(async () => {
    if (project.path) {
      await fetchFileList(project.path);
    }
  }, [project.path, fetchFileList]);

  // =============================================================================
  // File Creation Handlers
  // =============================================================================

  // Get current directory based on the open file
  const getCurrentDirectory = useCallback(() => {
    if (!project.currentFile) return '';
    const lastSlash = project.currentFile.lastIndexOf('/');
    return lastSlash > 0 ? project.currentFile.substring(0, lastSlash) : '';
  }, [project.currentFile]);

  const handleCreateFile = useCallback(async (filename: string, targetDir?: string) => {
    if (!project.path) return;

    try {
      // Create empty file with appropriate template based on extension
      let content = '';
      if (filename.endsWith('.tex')) {
        content = '% ' + filename + '\n\n';
      } else if (filename.endsWith('.bib')) {
        content = '% Bibliography file\n\n';
      }

      // Use targetDir if provided, otherwise use current directory
      const dir = targetDir !== undefined ? targetDir : getCurrentDirectory();
      const fullPath = dir ? `${dir}/${filename}` : filename;

      await api.writeFile(project.path, fullPath, content);
      await fetchFileList(project.path);
      // Select the new file
      handleFileSelect(fullPath);
    } catch (err) {
      console.error('Failed to create file:', err);
      setError(`Failed to create file: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, fetchFileList, handleFileSelect, getCurrentDirectory]);

  const handleCreateFolder = useCallback(async (foldername: string, targetDir?: string) => {
    if (!project.path) return;

    try {
      // Use targetDir if provided, otherwise use current directory
      const dir = targetDir !== undefined ? targetDir : getCurrentDirectory();
      const fullPath = dir ? `${dir}/${foldername}/.gitkeep` : `${foldername}/.gitkeep`;

      await api.writeFile(project.path, fullPath, '');
      await fetchFileList(project.path);
    } catch (err) {
      console.error('Failed to create folder:', err);
      setError(`Failed to create folder: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, fetchFileList, getCurrentDirectory]);

  const handleUploadFiles = useCallback(async (files: FileList, targetDir?: string) => {
    if (!project.path) return;

    try {
      // Use targetDir if provided, otherwise use current directory
      const dir = targetDir !== undefined ? targetDir : getCurrentDirectory();

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const content = await file.text();
        const fullPath = dir ? `${dir}/${file.name}` : file.name;
        await api.writeFile(project.path, fullPath, content);
      }
      await fetchFileList(project.path);
    } catch (err) {
      console.error('Failed to upload files:', err);
      setError(`Failed to upload: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, fetchFileList, getCurrentDirectory]);

  // =============================================================================
  // Sync Handlers
  // =============================================================================

  const handleSync = useCallback(async () => {
    if (!project.path) return;

    setIsSyncing(true);
    setError(null);

    try {
      // Save any unsaved changes first
      if (isDirty && project.currentFile) {
        await handleSave();
      }

      // Sync all changes (not just current file)
      const result = await api.syncProject(project.path);

      if (result.success) {
        // Refresh file list after sync
        await fetchFileList(project.path);
        // Reload sync status
        await loadSyncStatus();
        // Show success message briefly
        setError(null);
      } else {
        setError(result.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setIsSyncing(false);
    }
  }, [project.path, project.currentFile, isDirty, handleSave, fetchFileList, loadSyncStatus]);

  const handleOpenSettings = useCallback(() => {
    setIsSettingsModalOpen(true);
  }, []);

  const handleCloseSettings = useCallback(() => {
    setIsSettingsModalOpen(false);
  }, []);

  const handleSyncSetup = useCallback(() => {
    // Refresh sync status after setup
    loadSyncStatus();
  }, [loadSyncStatus]);

  // =============================================================================
  // HITL Approval Handlers
  // =============================================================================

  const handleApprovalRequest = useCallback(async (edit: PendingEdit) => {
    console.log('[Page] Approval request received:', edit);
    console.log('[Page] Setting pendingEdit - old_string length:', edit.old_string?.length);
    console.log('[Page] Setting pendingEdit - new_string length:', edit.new_string?.length);

    // If the edit is for a different file, switch to it FIRST before setting pendingEdit
    // This ensures the file content is loaded before Editor tries to find old_string
    if (project.path && edit.filepath && edit.old_string) {
      const editFilename = edit.filepath.split('/').pop();
      const currentFilename = project.currentFile?.split('/').pop();

      if (editFilename !== currentFilename) {
        // Load the file being edited, then set pendingEdit
        await handleFileSelect(edit.filepath);
        // Small delay to ensure content is rendered
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }

    // Set pendingEdit AFTER file is loaded
    setPendingEdit(edit);
  }, [project.path, project.currentFile, handleFileSelect]);

  const handleApproveEdit = useCallback(async (requestId: string) => {
    console.log('[Page] Approving edit:', requestId);

    // Capture the pending edit info before clearing it
    const editInfo = pendingEdit;

    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId }),
      });

      setPendingEdit(null);

      // Refresh file list to show new/modified files
      if (project.path) {
        await fetchFileList(project.path);
      }

      // For new file creations (no old_string), select the new file
      if (editInfo && !editInfo.old_string && editInfo.filepath) {
        setTimeout(async () => {
          await handleFileSelect(editInfo.filepath);
        }, 300);
      } else if (project.path && project.currentFile) {
        // Reload the file to show the changes, then auto-compile
        setTimeout(async () => {
          await handleFileSelect(project.currentFile!);
          // Auto-compile after edit is applied
          setTimeout(() => {
            console.log('[Page] Auto-compiling after edit...');
            handleCompile();
          }, 300);
        }, 500);
      }
    } catch (error) {
      console.error('Failed to approve:', error);
      setError(`Failed to approve edit: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }, [project.path, project.currentFile, pendingEdit, handleFileSelect, handleCompile, fetchFileList]);

  const handleRejectEdit = useCallback(async (requestId: string) => {
    console.log('[Page] Rejecting edit:', requestId);

    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          reason: 'User rejected',
        }),
      });

      setPendingEdit(null);
    } catch (error) {
      console.error('Failed to reject:', error);
      setError(`Failed to reject edit: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }, []);

  const handleApprovalResolved = useCallback(() => {
    setPendingEdit(null);
  }, []);

  // =============================================================================
  // Send to Agent Handler (from Editor context menu)
  // =============================================================================

  const handleSendToAgent = useCallback((context: SendToAgentContext) => {
    setQuotedContext(context);
    // Open agent panel if closed
    if (!isAgentPanelOpen) {
      setIsAgentPanelOpen(true);
    }
  }, [isAgentPanelOpen]);

  const handleClearQuote = useCallback(() => {
    setQuotedContext(null);
  }, []);

  // =============================================================================
  // File Tree Context Menu Handlers
  // =============================================================================

  const handleRevealInFinder = useCallback(async (relativePath: string) => {
    if (!project.path || !window.aura) return;
    const fullPath = `${project.path}/${relativePath}`;
    await window.aura.revealInFinder(fullPath);
  }, [project.path]);

  const handleCopyPath = useCallback(async (relativePath: string) => {
    if (!project.path) return;
    const fullPath = `${project.path}/${relativePath}`;
    await navigator.clipboard.writeText(fullPath);
  }, [project.path]);

  const handleCopyRelativePath = useCallback(async (relativePath: string) => {
    await navigator.clipboard.writeText(relativePath);
  }, []);

  const handleAddFileToChat = useCallback((relativePath: string) => {
    // Send the file content to the agent chat
    setQuotedContext({
      text: relativePath,
      action: 'file',
      filePath: null,
      startLine: 0,
      endLine: 0,
    });
    if (!isAgentPanelOpen) {
      setIsAgentPanelOpen(true);
    }
  }, [isAgentPanelOpen]);

  const handleCompileFile = useCallback(async (relativePath: string) => {
    if (!project.path || !relativePath.endsWith('.tex')) return;

    // Save current file first if dirty
    if (isDirty && project.currentFile) {
      await handleSave();
    }

    setIsCompiling(true);
    setCompileStatus('idle');
    setCompileLog('');

    try {
      const result = await api.compile(project.path, relativePath);
      setCompileLog(result.log_output || '');

      if (result.success) {
        setCompileStatus('success');
        const pdfName = relativePath.replace(/\.tex$/, '.pdf');
        try {
          const pdfBlob = await api.fetchPdfBlob(project.path, pdfName);
          if (pdfUrl) {
            URL.revokeObjectURL(pdfUrl);
          }
          setPdfUrl(URL.createObjectURL(pdfBlob));
          setCurrentPdfFile(pdfName);
        } catch (pdfErr) {
          console.error('Failed to load PDF:', pdfErr);
        }
      } else {
        setCompileStatus('error');
        if (result.tex_not_available) {
          // Fetch Docker status to determine the best action
          try {
            const dockerStatus = await fetch('http://localhost:8001/api/docker/status');
            const status = await dockerStatus.json();

            if (status.docker_installed && !status.docker_running) {
              // Docker is installed but not running - show start modal
              setShowDockerStartModal(true);
            } else {
              // Docker not installed or needs setup - show install modal
              setShowDockerInstallModal(true);
            }
          } catch {
            // If we can't fetch status, show the wizard
            setShowDockerWizard(true);
          }
        } else {
          setError(result.error_summary || 'Compilation failed');
        }
      }
    } catch (err) {
      console.error('Compilation error:', err);
      setCompileStatus('error');
      setError(`Compilation error: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsCompiling(false);
    }
  }, [project.path, project.currentFile, isDirty, handleSave, pdfUrl]);

  const handleDeleteFile = useCallback(async (relativePath: string) => {
    if (!project.path) return;

    const confirmed = window.confirm(`Are you sure you want to delete "${relativePath}"?`);
    if (!confirmed) return;

    try {
      await api.deleteFile(project.path, relativePath);
      // Refresh file list
      await fetchFileList(project.path);
      // Clear editor if deleted file was open
      if (project.currentFile === relativePath) {
        setProject(prev => ({ ...prev, currentFile: null }));
        setEditorContent('');
        editorContentRef.current = '';
        setIsDirty(false);
      }
    } catch (err) {
      console.error('Failed to delete file:', err);
      setError(`Failed to delete: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, project.currentFile, fetchFileList]);

  const handleRenameFile = useCallback((relativePath: string) => {
    const currentName = relativePath.split('/').pop() || '';
    setRenameModal({
      isOpen: true,
      path: relativePath,
      name: currentName,
    });
  }, []);

  const handleRenameConfirm = useCallback(async (newName: string) => {
    if (!project.path || !renameModal.path) return;

    const relativePath = renameModal.path;
    const currentName = relativePath.split('/').pop() || '';

    if (newName === currentName) return;

    // Construct new path (same directory, new name)
    const directory = relativePath.includes('/')
      ? relativePath.substring(0, relativePath.lastIndexOf('/') + 1)
      : '';
    const newPath = directory + newName;

    try {
      await api.renameFile(project.path, relativePath, newPath);
      // Refresh file list
      await fetchFileList(project.path);
      // Update current file if it was renamed
      if (project.currentFile === relativePath) {
        setProject(prev => ({ ...prev, currentFile: newPath }));
      }
    } catch (err) {
      console.error('Failed to rename file:', err);
      setError(`Failed to rename: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, project.currentFile, renameModal.path, fetchFileList]);

  const handleCutFile = useCallback((relativePath: string) => {
    setFileClipboard({ path: relativePath, operation: 'cut' });
  }, []);

  const handleCopyFile = useCallback((relativePath: string) => {
    setFileClipboard({ path: relativePath, operation: 'copy' });
  }, []);

  const handlePasteFile = useCallback(async (targetPath: string, isDirectory: boolean) => {
    if (!project.path || !fileClipboard) return;

    // Get the filename from the clipboard path
    const filename = fileClipboard.path.split('/').pop() || '';
    // Construct destination path (paste into target directory or next to target file)
    let destPath: string;
    if (isDirectory) {
      destPath = `${targetPath}/${filename}`;
    } else {
      // Paste next to the file (in the same directory)
      const directory = targetPath.includes('/')
        ? targetPath.substring(0, targetPath.lastIndexOf('/'))
        : '';
      destPath = directory ? `${directory}/${filename}` : filename;
    }

    try {
      if (fileClipboard.operation === 'cut') {
        // Move file
        await api.moveFile(project.path, fileClipboard.path, destPath);
        // Update current file if it was moved
        if (project.currentFile === fileClipboard.path) {
          setProject(prev => ({ ...prev, currentFile: destPath }));
        }
      } else {
        // Copy file
        await api.copyFile(project.path, fileClipboard.path, destPath);
      }

      // Clear clipboard after cut (but not after copy)
      if (fileClipboard.operation === 'cut') {
        setFileClipboard(null);
      }

      // Refresh file list
      await fetchFileList(project.path);
    } catch (err) {
      console.error('Failed to paste file:', err);
      setError(`Failed to paste: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [project.path, project.currentFile, fileClipboard, fetchFileList]);

  const fileContextMenuHandlers = {
    onRevealInFinder: handleRevealInFinder,
    onCopyPath: handleCopyPath,
    onCopyRelativePath: handleCopyRelativePath,
    onAddToChat: handleAddFileToChat,
    onCut: handleCutFile,
    onCopy: handleCopyFile,
    onPaste: handlePasteFile,
    onCompile: handleCompileFile,
    onDelete: handleDeleteFile,
    onRename: handleRenameFile,
    onOpenToSide: handleFileSelect, // Open in editor
  };

  // =============================================================================
  // Panel Resize Handlers
  // =============================================================================

  // Panel resize constraints
  const MIN_EDITOR = 300;
  const RESIZE_HANDLE_WIDTH = 3;

  const handleFileTreeResize = useCallback((delta: number) => {
    const effectiveContainerWidth = containerWidth || 1200;
    const handleCount = isAgentPanelOpen ? 3 : 2;
    const totalHandleWidth = RESIZE_HANDLE_WIDTH * handleCount;
    const agentWidth = isAgentPanelOpen ? agentPanelWidth : 0;

    // Calculate maximum file tree width that still leaves MIN_EDITOR for editor
    const maxFileTree = effectiveContainerWidth - MIN_EDITOR - pdfViewerWidth - agentWidth - totalHandleWidth;

    setFileTreeWidth((prev) => Math.max(MIN_FILE_TREE, Math.min(Math.min(MAX_FILE_TREE, maxFileTree), prev + delta)));
  }, [containerWidth, pdfViewerWidth, agentPanelWidth, isAgentPanelOpen]);

  const handlePdfViewerResize = useCallback((delta: number) => {
    const effectiveContainerWidth = containerWidth || 1200;
    const handleCount = isAgentPanelOpen ? 3 : 2;
    const totalHandleWidth = RESIZE_HANDLE_WIDTH * handleCount;
    const agentWidth = isAgentPanelOpen ? agentPanelWidth : 0;

    // Calculate maximum PDF width that still leaves MIN_EDITOR for editor
    const maxPdfWidth = effectiveContainerWidth - fileTreeWidth - MIN_EDITOR - agentWidth - totalHandleWidth;

    // Negative delta because handle is on the left of PDF panel
    setPdfViewerWidth((prev) => Math.max(MIN_PDF_VIEWER, Math.min(maxPdfWidth, prev - delta)));
  }, [containerWidth, fileTreeWidth, agentPanelWidth, isAgentPanelOpen]);

  const handleAgentPanelResize = useCallback((delta: number) => {
    const effectiveContainerWidth = containerWidth || 1200;
    const totalHandleWidth = RESIZE_HANDLE_WIDTH * 3;

    // Calculate maximum agent panel width that still leaves MIN_EDITOR for editor
    const maxAgentWidth = effectiveContainerWidth - fileTreeWidth - MIN_EDITOR - pdfViewerWidth - totalHandleWidth;

    // Negative delta because handle is on the left of agent panel
    setAgentPanelWidth((prev) => Math.max(MIN_AGENT_PANEL, Math.min(maxAgentWidth, prev - delta)));
  }, [containerWidth, fileTreeWidth, pdfViewerWidth]);

  const handleOutlineResize = useCallback((delta: number) => {
    // Negative delta because handle is at the top of outline (dragging up increases height)
    setOutlineHeight((prev) => Math.max(MIN_OUTLINE_HEIGHT, Math.min(MAX_OUTLINE_HEIGHT, prev - delta)));
  }, []);

  const toggleAgentPanel = useCallback(() => {
    setIsAgentPanelOpen((prev) => !prev);
  }, []);

  // =============================================================================
  // Render
  // =============================================================================

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-fill-secondary">
      {/* Titlebar drag area for macOS */}
      <div className="h-7 bg-sidebar-bg titlebar-drag border-b border-black/6" />

      {/* Toolbar */}
      <Toolbar
        projectName={project.name}
        projectPath={project.path}
        isDirty={isDirty}
        isCompiling={isCompiling}
        compileStatus={compileStatus}
        isSyncing={isSyncing}
        syncStatus={syncStatus}
        showCompile={!isMarkdownFile}
        dockerBuildPhase={dockerBuildPhase}
        dockerBuildProgress={dockerBuildProgress}
        onDockerBuildClick={() => setShowDockerBuildModal(true)}
        onOpenProject={handleOpenProject}
        onNewProject={handleNewProject}
        onSave={handleSave}
        onCompile={handleCompile}
        onSync={handleSync}
        onSettings={handleOpenSettings}
        onMemory={() => setShowMemory(true)}
      />

      {/* Error Banner */}
      {error && (
        <div className="bg-error/10 border-b border-error/20 px-4 py-2.5 flex items-center justify-between animate-fade-in-down">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-error" />
            <span className="typo-small text-error">{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-error/10 transition-colors"
          >
            <span className="text-error text-lg leading-none">×</span>
          </button>
        </div>
      )}

      {/* Main Content - 4 Panel Layout */}
      <div ref={containerRef} className="flex-1 flex overflow-hidden relative">
        {/* File Tree */}
        <div
          style={{ width: fileTreeWidth }}
          className="flex-shrink-0 overflow-hidden bg-sidebar-bg flex flex-col"
        >
          <div className="flex-1 overflow-auto">
            <FileTree
              projectPath={project.path}
              files={project.files}
              currentFile={project.currentFile}
              onFileSelect={handleFileSelect}
              onRefresh={handleRefreshFiles}
              onCreateFile={handleCreateFile}
              onCreateFolder={handleCreateFolder}
              onUploadFiles={handleUploadFiles}
              contextMenuHandlers={fileContextMenuHandlers}
              clipboardHasContent={!!fileClipboard}
            />
          </div>
          <FileOutline
            projectPath={project.path}
            currentFile={project.currentFile}
            onNavigate={handleOutlineNavigate}
            height={outlineHeight}
            onResize={handleOutlineResize}
          />
        </div>

        {/* Resize Handle: File Tree | Editor */}
        <ResizeHandle onResize={handleFileTreeResize} />

        {/* Editor - flex-1 to fill remaining space, with min-width constraint */}
        <div
          className="flex-1 min-w-[300px] overflow-hidden"
        >
          <Editor
            content={editorContent}
            filePath={project.currentFile}
            onChange={handleEditorChange}
            onSave={handleSave}
            pendingEdit={pendingEdit}
            onApproveEdit={handleApproveEdit}
            onRejectEdit={handleRejectEdit}
            onSendToAgent={handleSendToAgent}
            scrollToLine={syncTexLine}
            scrollToColumn={syncTexColumn}
            onScrollComplete={handleSyncTexScrollComplete}
          />
        </div>

        {/* Resize Handle: Editor | Preview Panel */}
        <ResizeHandle onResize={handlePdfViewerResize} />

        {/* Preview Panel (PDF or Markdown) */}
        <div
          style={{ width: pdfViewerWidth }}
          className="flex-shrink-0 overflow-hidden"
        >
          {isMarkdownFile ? (
            <MarkdownPreview
              content={debouncedMarkdownContent}
              filename={project.currentFile ?? undefined}
            />
          ) : (
            <PDFViewer
              pdfUrl={pdfUrl}
              isCompiling={isCompiling}
              pdfFile={currentPdfFile ?? undefined}
              projectPath={project.path}
              onSyncTexClick={handleSyncTexClick}
            />
          )}
        </div>

        {/* Resize Handle: PDF Viewer | Agent Panel (only if open) */}
        {isAgentPanelOpen && (
          <ResizeHandle
            onResize={handleAgentPanelResize}
            onResizeStart={() => setIsResizing(true)}
            onResizeEnd={() => setIsResizing(false)}
          />
        )}

        {/* Agent Panel (Collapsible) */}
        <div
          style={{ width: isAgentPanelOpen ? agentPanelWidth : 0 }}
          className={`flex-shrink-0 overflow-hidden ${
            isResizing ? '' : 'transition-all duration-300'
          } ${
            isAgentPanelOpen ? 'opacity-100' : 'opacity-0 w-0'
          }`}
        >
          <AgentPanel
            projectPath={project.path}
            onApprovalRequest={handleApprovalRequest}
            onApprovalResolved={handleApprovalResolved}
            onOpenFile={handleFileSelect}
            quotedContext={quotedContext}
            onClearQuote={handleClearQuote}
          />
        </div>

        {/* Toggle Button for Agent Panel */}
        <button
          onClick={toggleAgentPanel}
          style={{ right: isAgentPanelOpen ? agentPanelWidth + 8 : 8 }}
          className={`absolute z-10 top-14 flex h-8 w-8 items-center justify-center rounded-yw-lg shadow-card transition-all duration-300 ${
            isAgentPanelOpen
              ? 'bg-white border border-black/6 hover:bg-black/3'
              : 'bg-green1 hover:opacity-90'
          }`}
          title={isAgentPanelOpen ? 'Close AI Panel' : 'Open AI Panel'}
        >
          {isAgentPanelOpen ? (
            <PanelRightClose size={16} className="text-secondary" />
          ) : (
            <PanelRightOpen size={16} className="text-white" />
          )}
        </button>
      </div>

      {/* Status Bar */}
      <div className="h-7 bg-white border-t border-black/6 flex items-center px-4 gap-4">
        <span className="flex-1 typo-small text-secondary truncate">
          {project.currentFile || 'No file selected'}
          {isDirty && <span className="text-warn ml-1">•</span>}
        </span>
        {pendingEdit && (
          <span className="badge badge-warning">
            Pending approval
          </span>
        )}
        <span className="typo-small">
          {compileStatus === 'success' && (
            <span className="text-success flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-success" />
              Compiled
            </span>
          )}
          {compileStatus === 'error' && (
            <span className="text-error flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-error" />
              Error
            </span>
          )}
          {isCompiling && (
            <span className="text-secondary flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
              Compiling...
            </span>
          )}
        </span>
        {compileLog && (
          <button
            onClick={() => console.log(compileLog)}
            className="typo-small text-link hover:underline"
            title="View compilation log"
          >
            View Log
          </button>
        )}
      </div>

      {/* New Project Modal */}
      <NewProjectModal
        isOpen={isNewProjectModalOpen}
        onClose={() => setIsNewProjectModalOpen(false)}
        onSubmit={handleCreateProject}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={handleCloseSettings}
        projectPath={project.path}
        onSyncSetup={handleSyncSetup}
      />

      {/* Memory Modal */}
      <MemoryModal
        isOpen={showMemory}
        onClose={() => setShowMemory(false)}
        projectPath={project.path}
      />

      {/* Docker Start Modal (Docker installed but not running) */}
      <DockerStartModal
        isOpen={showDockerStartModal}
        onClose={() => setShowDockerStartModal(false)}
        onStart={handleStartDocker}
        isStarting={dockerStarting}
      />

      {/* Docker Install Modal (Docker not installed) */}
      <DockerInstallModal
        isOpen={showDockerInstallModal}
        onClose={() => setShowDockerInstallModal(false)}
        onInstall={() => setShowDockerInstallModal(false)}
      />

      {/* Fallback Notice Modal */}
      <FallbackNoticeModal
        isOpen={showFallbackNotice}
        onClose={() => setShowFallbackNotice(false)}
        onContinue={() => {
          startDockerBuild();
        }}
      />

      {/* Docker Build Modal (shows progress) */}
      <DockerBuildModal
        isOpen={showDockerBuildModal}
        onClose={() => setShowDockerBuildModal(false)}
        progress={dockerBuildProgress}
        phase={dockerBuildPhase}
        error={dockerBuildError}
        onRetry={() => {
          setDockerBuildPhase('idle');
          startDockerBuild();
        }}
      />

      {/* Docker Guide (fallback) */}
      <DockerGuide
        isOpen={showDockerGuide}
        onClose={() => setShowDockerGuide(false)}
        onDockerStarted={() => {
          handleCompile();
        }}
      />

      {/* Docker Setup Wizard (fallback) */}
      <DockerSetupWizard
        isOpen={showDockerWizard}
        onClose={() => setShowDockerWizard(false)}
        onComplete={() => {
          handleCompile();
        }}
      />

      {/* Rename Modal */}
      <RenameModal
        isOpen={renameModal.isOpen}
        currentName={renameModal.name}
        onClose={() => setRenameModal({ isOpen: false, path: '', name: '' })}
        onRename={handleRenameConfirm}
      />
    </div>
  );
}
