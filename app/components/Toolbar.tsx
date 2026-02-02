'use client';

import {
  FolderOpen,
  FilePlus,
  Save,
  Play,
  RefreshCw,
  Settings,
  Loader2,
  Check,
  X,
  AlertCircle,
  Cloud,
  CloudOff,
  Brain,
} from 'lucide-react';

type SyncStatusType = 'not_initialized' | 'clean' | 'local_changes' | 'ahead' | 'behind' | 'diverged' | 'conflict' | 'error';
type DockerBuildPhase = 'idle' | 'starting' | 'pulling' | 'building' | 'complete' | 'error';

interface ToolbarProps {
  projectName: string;
  projectPath: string | null;
  isDirty: boolean;
  isCompiling: boolean;
  compileStatus: 'idle' | 'success' | 'error';
  isSyncing: boolean;
  syncStatus: SyncStatusType | null;
  showCompile?: boolean;
  // Docker build progress
  dockerBuildPhase?: DockerBuildPhase;
  dockerBuildProgress?: number;
  onDockerBuildClick?: () => void;
  onOpenProject: () => void;
  onNewProject: () => void;
  onSave: () => void;
  onCompile: () => void;
  onSync: () => void;
  onSettings: () => void;
  onMemory: () => void;
}

export default function Toolbar({
  projectName,
  projectPath,
  isDirty,
  isCompiling,
  compileStatus,
  isSyncing,
  syncStatus,
  showCompile = true,
  dockerBuildPhase = 'idle',
  dockerBuildProgress = 0,
  onDockerBuildClick,
  onOpenProject,
  onNewProject,
  onSave,
  onCompile,
  onSync,
  onSettings,
  onMemory,
}: ToolbarProps) {
  // Determine sync button state
  const canSync = projectPath && syncStatus && syncStatus !== 'not_initialized';
  const hasSyncIssue = syncStatus === 'conflict' || syncStatus === 'diverged' || syncStatus === 'error';

  // Get sync icon
  const getSyncIcon = () => {
    if (isSyncing) {
      return <Loader2 size={14} className="animate-spin" />;
    }
    if (!syncStatus || syncStatus === 'not_initialized') {
      return <CloudOff size={14} />;
    }
    if (hasSyncIssue) {
      return <AlertCircle size={14} />;
    }
    if (syncStatus === 'clean') {
      return <Cloud size={14} />;
    }
    return <RefreshCw size={14} />;
  };

  // Get sync button style
  const getSyncButtonClass = () => {
    const base = 'btn-ghost';
    if (!canSync) return `${base} opacity-40 cursor-not-allowed`;
    if (hasSyncIssue) return `${base} text-warn`;
    if (syncStatus === 'clean') return `${base} text-success`;
    return base;
  };

  // Get sync tooltip
  const getSyncTooltip = () => {
    if (isSyncing) return 'Syncing...';
    if (!syncStatus || syncStatus === 'not_initialized') return 'Not connected to Overleaf. Open Settings to configure.';
    if (syncStatus === 'clean') return 'Synced with Overleaf';
    if (syncStatus === 'local_changes') return 'Local changes to sync';
    if (syncStatus === 'ahead') return 'Changes to push';
    if (syncStatus === 'behind') return 'Changes to pull';
    if (syncStatus === 'diverged') return 'Local and remote have diverged';
    if (syncStatus === 'conflict') return 'Merge conflicts detected';
    if (syncStatus === 'error') return 'Sync error';
    return 'Sync with Overleaf';
  };

  return (
    <div className="h-11 bg-white border-b border-black/6 flex items-center px-3 gap-2 titlebar-no-drag">
      {/* Project name */}
      <div className="flex items-center gap-2 min-w-[140px]">
        <span className="typo-body-strong truncate">
          {projectName}
        </span>
        {isDirty && (
          <span className="w-2 h-2 rounded-full bg-warn" title="Unsaved changes" />
        )}
      </div>

      {/* Separator */}
      <div className="w-px h-5 bg-black/10 mx-1" />

      {/* File operations */}
      <button
        onClick={onOpenProject}
        className="btn-ghost"
        title="Open Project"
      >
        <FolderOpen size={16} className="text-secondary" />
        <span className="hidden sm:inline text-secondary">Open</span>
      </button>

      <button
        onClick={onNewProject}
        className="btn-ghost"
        title="New Project"
      >
        <FilePlus size={16} className="text-secondary" />
        <span className="hidden sm:inline text-secondary">New</span>
      </button>

      <button
        onClick={onSave}
        className={`btn-ghost ${!isDirty ? 'opacity-40 cursor-not-allowed' : ''}`}
        title="Save (⌘S)"
        disabled={!isDirty}
      >
        <Save size={16} className="text-secondary" />
        <span className="hidden sm:inline text-secondary">Save</span>
      </button>

      {/* Separator */}
      <div className="w-px h-5 bg-black/10 mx-1" />

      {/* Compile - Primary action (hidden for non-tex files) */}
      {showCompile && (
        <button
          onClick={onCompile}
          className={`flex h-7 items-center gap-1.5 rounded-full bg-green1 px-3 text-white typo-small-strong hover:opacity-90 transition-opacity ${isCompiling ? 'opacity-80' : ''}`}
          title="Compile (⌘B)"
          disabled={isCompiling}
        >
          {isCompiling ? (
            <Loader2 size={14} className="animate-spin" />
          ) : compileStatus === 'success' ? (
            <Check size={14} />
          ) : compileStatus === 'error' ? (
            <X size={14} />
          ) : (
            <Play size={14} />
          )}
          <span>Compile</span>
        </button>
      )}

      {/* Sync */}
      <button
        onClick={canSync ? onSync : onSettings}
        className={getSyncButtonClass()}
        title={getSyncTooltip()}
        disabled={isSyncing}
      >
        {getSyncIcon()}
        <span className="hidden sm:inline">
          {canSync ? 'Sync' : 'Sync'}
        </span>
      </button>

      {/* Docker Build Progress Indicator */}
      {dockerBuildPhase !== 'idle' && dockerBuildPhase !== 'complete' && (
        <button
          onClick={onDockerBuildClick}
          className="flex items-center gap-2 px-2 py-1 rounded-yw-md hover:bg-black/3 transition-colors"
          title="Click to see download progress"
        >
          <div className="flex items-center gap-1.5">
            {dockerBuildPhase === 'error' ? (
              <AlertCircle size={14} className="text-error" />
            ) : (
              <Loader2 size={14} className="text-green2 animate-spin" />
            )}
            <span className="typo-ex-small text-secondary hidden sm:inline">
              {dockerBuildPhase === 'error' ? 'Setup failed' : 'Setting up...'}
            </span>
          </div>
          {/* Mini progress bar */}
          <div className="w-16 h-1.5 bg-black/5 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                dockerBuildPhase === 'error' ? 'bg-error' : 'bg-green2'
              }`}
              style={{ width: `${dockerBuildProgress}%` }}
            />
          </div>
          <span className="typo-ex-small text-tertiary w-8">
            {Math.round(dockerBuildProgress)}%
          </span>
        </button>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Memory */}
      <button
        onClick={onMemory}
        className="btn-icon"
        title="Project Memory"
      >
        <Brain size={16} className="text-secondary" />
      </button>

      {/* Settings */}
      <button
        onClick={onSettings}
        className="btn-icon"
        title="Settings"
      >
        <Settings size={16} className="text-secondary" />
      </button>
    </div>
  );
}
