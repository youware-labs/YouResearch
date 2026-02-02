'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Play,
  FileText,
  AlertTriangle,
  Lightbulb,
  BookOpen,
  Target,
  CheckCircle,
  RefreshCw,
  Square,
  Trash2,
} from 'lucide-react';
import { api, VibeState, VibeStatus, VibeResearchPhase, VibeHypothesis, VibeTheme, VibeGap } from '../lib/api';

interface VibeResearchViewProps {
  projectPath: string;
  sessionId: string;
  onComplete?: () => void;
  onDelete?: () => void;
  onOpenFile?: (filePath: string) => void;
}

// Phase configuration
const PHASE_CONFIG: Record<VibeResearchPhase, { label: string; color: string; icon: React.ReactNode }> = {
  scoping: { label: 'Scoping', color: 'bg-purple-100 text-purple-800', icon: <Target size={14} /> },
  discovery: { label: 'Discovery', color: 'bg-blue-100 text-blue-800', icon: <BookOpen size={14} /> },
  synthesis: { label: 'Synthesis', color: 'bg-emerald-100 text-emerald-800', icon: <RefreshCw size={14} /> },
  ideation: { label: 'Ideation', color: 'bg-yellow-100 text-yellow-800', icon: <Lightbulb size={14} /> },
  evaluation: { label: 'Evaluation', color: 'bg-orange-100 text-orange-800', icon: <Target size={14} /> },
  complete: { label: 'Complete', color: 'bg-green3 text-green1', icon: <CheckCircle size={14} /> },
};

// Collapsible section component
function CollapsibleSection({
  title,
  count,
  children,
  defaultOpen = false,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border-t border-black/6">
      <button
        className="w-full flex items-center gap-2 p-3 hover:bg-fill-secondary transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="typo-small-strong flex-1 text-left">{title}</span>
        <span className="badge badge-secondary">{count}</span>
      </button>
      {isOpen && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

// Theme display
function ThemeItem({ theme }: { theme: VibeTheme }) {
  return (
    <div className="bg-fill-secondary rounded-yw-md p-2.5 mb-2">
      <div className="typo-small-strong text-green1">{theme.name}</div>
      <div className="typo-ex-small text-secondary mt-1 line-clamp-2">{theme.description}</div>
      <div className="typo-ex-small text-tertiary mt-1">{theme.paper_ids.length} papers</div>
    </div>
  );
}

// Gap display
function GapItem({ gap }: { gap: VibeGap }) {
  const confidenceColor = {
    high: 'bg-green-100 text-green-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-gray-100 text-gray-800',
  }[gap.confidence];

  return (
    <div className="bg-fill-secondary rounded-yw-md p-2.5 mb-2">
      <div className="flex items-center gap-2">
        <span className={`badge typo-ex-small ${confidenceColor}`}>{gap.confidence.toUpperCase()}</span>
        <span className="typo-small-strong text-green1 flex-1">{gap.title}</span>
      </div>
      <div className="typo-ex-small text-secondary mt-1 line-clamp-2">{gap.evidence}</div>
    </div>
  );
}

// Hypothesis display
function HypothesisItem({ hypothesis }: { hypothesis: VibeHypothesis }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const totalScore = hypothesis.novelty_score + hypothesis.feasibility_score + hypothesis.impact_score;

  return (
    <div className="bg-fill-secondary rounded-yw-md p-2.5 mb-2">
      <button
        className="w-full flex items-center gap-2 text-left"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Lightbulb size={14} className="text-yellow-600" />
        <span className="typo-small-strong text-green1 flex-1 line-clamp-1">{hypothesis.title}</span>
        {totalScore > 0 && (
          <span className="typo-ex-small text-tertiary">
            N:{hypothesis.novelty_score} F:{hypothesis.feasibility_score} I:{hypothesis.impact_score}
          </span>
        )}
      </button>
      {isExpanded && (
        <div className="mt-2 space-y-2 pl-6">
          <div>
            <div className="typo-ex-small text-tertiary">Description</div>
            <div className="typo-small text-secondary">{hypothesis.description}</div>
          </div>
          <div>
            <div className="typo-ex-small text-tertiary">Rationale</div>
            <div className="typo-small text-secondary">{hypothesis.rationale}</div>
          </div>
          {hypothesis.building_blocks && (
            <div>
              <div className="typo-ex-small text-tertiary">Building Blocks</div>
              <div className="typo-small text-secondary">{hypothesis.building_blocks}</div>
            </div>
          )}
          {hypothesis.suggested_experiments && (
            <div>
              <div className="typo-ex-small text-tertiary">Suggested Experiments</div>
              <div className="typo-small text-secondary">{hypothesis.suggested_experiments}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function VibeResearchView({ projectPath, sessionId, onComplete, onDelete, onOpenFile }: VibeResearchViewProps) {
  const [state, setState] = useState<VibeState | null>(null);
  const [status, setStatus] = useState<VibeStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOutput, setLastOutput] = useState<string>('');

  // Load state
  const loadState = useCallback(async () => {
    try {
      const [stateData, statusData] = await Promise.all([
        api.getVibeState(projectPath, sessionId),
        api.getVibeStatus(projectPath, sessionId),
      ]);
      setState(stateData);
      setStatus(statusData);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load state');
    } finally {
      setIsLoading(false);
    }
  }, [projectPath, sessionId]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  // Poll for updates while running
  useEffect(() => {
    if (!isRunning) return;

    const pollInterval = setInterval(async () => {
      try {
        const [stateData, statusData] = await Promise.all([
          api.getVibeState(projectPath, sessionId),
          api.getVibeStatus(projectPath, sessionId),
        ]);
        setState(stateData);
        setStatus(statusData);
      } catch (e) {
        console.error('Polling error:', e);
      }
    }, 1500); // Poll every 1.5 seconds for responsive updates

    return () => clearInterval(pollInterval);
  }, [isRunning, projectPath, sessionId]);

  // Run one iteration
  const runIteration = async () => {
    if (isRunning || !state) return;

    setIsRunning(true);
    setError(null);

    try {
      const result = await api.runVibeIteration(projectPath, sessionId);
      setLastOutput(result.output);

      // Reload state after iteration
      await loadState();

      if (result.is_complete) {
        onComplete?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run iteration');
    } finally {
      setIsRunning(false);
      setIsStopping(false);
    }
  };

  // Stop running research
  const stopResearch = async () => {
    if (!isRunning) return;

    setIsStopping(true);
    try {
      await api.stopVibeResearch(sessionId);
      // The running iteration will check the stop flag and return
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to stop');
      setIsStopping(false);
    }
  };

  // Delete session
  const deleteSession = async () => {
    if (isRunning) {
      // Stop first if running
      await stopResearch();
    }

    if (!confirm('Delete this research session? This cannot be undone.')) {
      return;
    }

    try {
      await api.deleteVibeSession(projectPath, sessionId);
      onDelete?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete session');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="animate-spin text-green2" size={24} />
      </div>
    );
  }

  if (!state || !status) {
    return (
      <div className="p-4 text-center text-secondary">
        {error || 'Session not found'}
      </div>
    );
  }

  const phaseConfig = PHASE_CONFIG[state.current_phase];
  const progress = state.phase_progress[state.current_phase] || 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header with topic and phase */}
      <div className="p-3 border-b border-black/6">
        <div className="typo-small text-tertiary mb-1">Research Topic</div>
        <div className="typo-body-strong text-primary line-clamp-2">{state.topic}</div>

        {/* Phase indicator */}
        <div className="flex items-center gap-2 mt-3">
          <span className={`badge ${phaseConfig.color} flex items-center gap-1`}>
            {phaseConfig.icon}
            {phaseConfig.label}
          </span>
          <div className="flex-1 h-2 bg-fill-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-green2 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="typo-ex-small text-tertiary">{progress}%</span>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 mt-3 typo-ex-small text-secondary">
          <span>Papers: {status.papers_found} found, {status.papers_read} read</span>
          <span>Themes: {status.themes_count}</span>
          <span>Gaps: {status.gaps_count}</span>
          <span>Hypotheses: {status.hypotheses_count}</span>
          {isRunning && (
            <span className="flex items-center gap-1 text-green-600">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              Live
            </span>
          )}
        </div>

        {/* Current activity indicator */}
        {isRunning && state.current_activity && (
          <div className="flex items-center gap-2 mt-3 p-2 bg-blue-50 rounded-yw-md animate-pulse">
            <Loader2 size={14} className="animate-spin text-blue-600" />
            <span className="typo-small text-blue-700">
              {state.current_activity}
            </span>
          </div>
        )}

        {/* Stall warning */}
        {status.stall_count >= 2 && !state.is_complete && (
          <div className="flex items-center gap-2 mt-2 p-2 bg-orange-50 rounded-yw-md">
            <AlertTriangle size={14} className="text-orange1" />
            <span className="typo-ex-small text-orange1">
              Progress may be stalled ({status.stall_count}/3)
            </span>
          </div>
        )}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Themes section */}
        <CollapsibleSection title="Themes" count={state.themes.length} defaultOpen={state.themes.length > 0}>
          {state.themes.length === 0 ? (
            <div className="typo-ex-small text-tertiary italic">No themes identified yet</div>
          ) : (
            state.themes.map((theme) => <ThemeItem key={theme.theme_id} theme={theme} />)
          )}
        </CollapsibleSection>

        {/* Gaps section */}
        <CollapsibleSection title="Research Gaps" count={state.gaps.length} defaultOpen={state.gaps.length > 0}>
          {state.gaps.length === 0 ? (
            <div className="typo-ex-small text-tertiary italic">No gaps identified yet</div>
          ) : (
            state.gaps.map((gap) => <GapItem key={gap.gap_id} gap={gap} />)
          )}
        </CollapsibleSection>

        {/* Hypotheses section */}
        <CollapsibleSection title="Hypotheses" count={state.hypotheses.length} defaultOpen={state.hypotheses.length > 0}>
          {state.hypotheses.length === 0 ? (
            <div className="typo-ex-small text-tertiary italic">No hypotheses generated yet</div>
          ) : (
            state.hypotheses.map((h) => <HypothesisItem key={h.hypothesis_id} hypothesis={h} />)
          )}
        </CollapsibleSection>

        {/* Action history */}
        {state.action_history.length > 0 && (
          <CollapsibleSection title="Recent Actions" count={state.action_history.length}>
            <div className="space-y-1">
              {state.action_history.slice(-5).reverse().map((action, i) => (
                <div key={i} className="typo-ex-small text-secondary truncate">
                  {action}
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* Last output */}
        {lastOutput && (
          <div className="p-3 border-t border-black/6">
            <div className="typo-ex-small text-tertiary mb-1">Last Output</div>
            <div className="typo-small text-secondary bg-fill-secondary p-2 rounded-yw-md max-h-24 overflow-y-auto">
              {lastOutput}
            </div>
          </div>
        )}
      </div>

      {/* Error display */}
      {error && (
        <div className="p-3 bg-red-50 border-t border-red-200">
          <div className="typo-small text-red-700">{error}</div>
        </div>
      )}

      {/* Action buttons */}
      <div className="p-3 border-t border-black/6 flex items-center gap-2">
        {state.is_complete ? (
          <button
            className="btn-primary flex items-center gap-2 flex-1"
            onClick={async () => {
              try {
                const report = await api.getVibeReport(projectPath, sessionId);
                if (report.report_filename && onOpenFile) {
                  // Open the .tex file in the editor
                  onOpenFile(report.report_filename);
                } else {
                  alert('Report file not found. The research may need to complete first.');
                }
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Failed to open report');
              }
            }}
          >
            <FileText size={14} />
            View Report
          </button>
        ) : isRunning ? (
          <button
            className="btn-secondary flex items-center gap-2 flex-1"
            onClick={stopResearch}
            disabled={isStopping}
          >
            {isStopping ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Stopping...
              </>
            ) : (
              <>
                <Square size={14} />
                Stop
              </>
            )}
          </button>
        ) : (
          <button
            className="btn-primary flex items-center gap-2 flex-1"
            onClick={runIteration}
          >
            <Play size={14} />
            Run Next Iteration
          </button>
        )}
        <button
          className="btn-ghost"
          onClick={loadState}
          disabled={isLoading}
          title="Refresh state"
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
        </button>
        <button
          className="btn-ghost text-red-600 hover:bg-red-50"
          onClick={deleteSession}
          title="Delete session"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
