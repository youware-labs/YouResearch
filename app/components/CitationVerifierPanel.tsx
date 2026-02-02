'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Check,
  FileText,
} from 'lucide-react';
import { api, VerificationResult } from '../lib/api';

interface CitationVerifierPanelProps {
  projectPath: string;
  onClose: () => void;
}

interface VerifierStats {
  verified: number;
  warnings: number;
  errors: number;
}

interface BibPair {
  tex_file: string | null;
  bib_file: string;
  display_name: string;
}

export default function CitationVerifierPanel({
  projectPath,
  onClose,
}: CitationVerifierPanelProps) {
  const [results, setResults] = useState<Map<string, VerificationResult>>(new Map());
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<VerifierStats>({ verified: 0, warnings: 0, errors: 0 });
  const [isRunning, setIsRunning] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const abortControllerRef = useRef<AbortController | null>(null);

  // File selection state
  const [pairs, setPairs] = useState<BibPair[]>([]);
  const [selectedBib, setSelectedBib] = useState<string | null>(null);
  const [isLoadingPairs, setIsLoadingPairs] = useState(true);

  // Load initial state and file pairs
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        // Load pairs
        setIsLoadingPairs(true);
        const pairsData = await api.getTexBibPairs(projectPath);
        setPairs(pairsData.pairs);

        // Auto-select if only one bib file
        if (pairsData.pairs.length === 1) {
          setSelectedBib(pairsData.pairs[0].bib_file);
        }

        // Load approved state
        const state = await api.getVerifierState(projectPath);
        setApproved(new Set(state.approved_citations));
      } catch (e) {
        console.error('Failed to load initial data:', e);
      } finally {
        setIsLoadingPairs(false);
      }
    };
    loadInitialData();
  }, [projectPath]);

  // Run verification
  const runVerification = useCallback(async () => {
    if (isRunning || !selectedBib) return;

    setIsRunning(true);
    setResults(new Map());
    setStats({ verified: 0, warnings: 0, errors: 0 });

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(api.getVerifyReferencesUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: projectPath, bib_file: selectedBib }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());

              if (data.cite_key) {
                // This is a verification result
                setResults((prev) => {
                  const next = new Map(prev);
                  next.set(data.cite_key, data as VerificationResult);
                  return next;
                });
              } else if (data.verified !== undefined) {
                // This is the final stats
                setStats(data);
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Verification error:', error);
      }
    } finally {
      setIsRunning(false);
      abortControllerRef.current = null;
    }
  }, [projectPath, selectedBib]);

  // Auto-run when a bib file is selected (only if single file)
  useEffect(() => {
    if (selectedBib && pairs.length === 1) {
      runVerification();
    }
    return () => {
      abortControllerRef.current?.abort();
    };
  }, [selectedBib, pairs.length]);

  // Approve a citation
  const handleApprove = async (citeKey: string) => {
    try {
      await api.approveCitation(projectPath, citeKey);
      setApproved((prev) => new Set([...prev, citeKey]));
      setResults((prev) => {
        const next = new Map(prev);
        const result = next.get(citeKey);
        if (result) {
          next.set(citeKey, { ...result, status: 'verified' });
        }
        return next;
      });
    } catch (e) {
      console.error('Failed to approve:', e);
    }
  };

  // Toggle expansion
  const toggleExpand = (citeKey: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(citeKey)) {
        next.delete(citeKey);
      } else {
        next.add(citeKey);
      }
      return next;
    });
  };

  // Sort results: errors first, then warnings, then verified
  const sortedResults = Array.from(results.values()).sort((a, b) => {
    const order = { error: 0, warning: 1, pending: 2, verified: 3 };
    return order[a.status] - order[b.status];
  });

  return (
    <div className="h-full flex flex-col bg-fill-secondary">
      {/* Header */}
      <div className="panel-header bg-white border-b border-black/6">
        <div className="flex items-center justify-between w-full">
          <h2 className="typo-h4 flex items-center gap-2">
            📚 Reference Verification
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={runVerification}
              disabled={isRunning || !selectedBib}
              className="btn-ghost typo-small flex items-center gap-1.5"
            >
              <RefreshCw size={14} className={isRunning ? 'animate-spin' : ''} />
              {isRunning ? 'Verifying...' : 'Run Again'}
            </button>
            <button
              onClick={onClose}
              className="btn-ghost typo-small"
            >
              Close
            </button>
          </div>
        </div>
      </div>

      {/* File selection */}
      {isLoadingPairs ? (
        <div className="px-4 py-3 bg-white border-b border-black/6">
          <div className="flex items-center gap-2 text-secondary">
            <Loader2 size={14} className="animate-spin" />
            <span className="typo-small">Loading bibliography files...</span>
          </div>
        </div>
      ) : pairs.length === 0 ? (
        <div className="px-4 py-3 bg-white border-b border-black/6">
          <div className="flex items-center gap-2 text-error">
            <XCircle size={14} />
            <span className="typo-small">No .bib files found in project</span>
          </div>
        </div>
      ) : pairs.length > 1 || !selectedBib ? (
        <div className="px-4 py-3 bg-white border-b border-black/6">
          <label className="typo-small text-secondary block mb-2">
            Select bibliography file to verify:
          </label>
          <div className="space-y-1">
            {pairs.map((pair) => (
              <button
                key={pair.bib_file}
                onClick={() => setSelectedBib(pair.bib_file)}
                className={`w-full text-left px-3 py-2 rounded-yw-md flex items-center gap-2 transition-colors ${
                  selectedBib === pair.bib_file
                    ? 'bg-green1/10 border border-green1/30'
                    : 'bg-fill-tertiary hover:bg-fill-quaternary border border-transparent'
                }`}
              >
                <FileText size={14} className={selectedBib === pair.bib_file ? 'text-green1' : 'text-tertiary'} />
                <div className="flex-1 min-w-0">
                  <div className="typo-small font-mono truncate">{pair.bib_file}</div>
                  {pair.tex_file && (
                    <div className="typo-ex-small text-tertiary truncate">
                      Paired with: {pair.tex_file}
                    </div>
                  )}
                </div>
                {selectedBib === pair.bib_file && (
                  <Check size={14} className="text-green1 flex-shrink-0" />
                )}
              </button>
            ))}
          </div>
          {selectedBib && (
            <button
              onClick={runVerification}
              disabled={isRunning}
              className="mt-3 w-full btn-primary typo-small flex items-center justify-center gap-2"
            >
              {isRunning ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  <RefreshCw size={14} />
                  Verify Selected File
                </>
              )}
            </button>
          )}
        </div>
      ) : (
        <div className="px-4 py-2 bg-white border-b border-black/6">
          <div className="typo-small text-tertiary flex items-center gap-2">
            <FileText size={14} />
            <span className="font-mono">{selectedBib}</span>
          </div>
        </div>
      )}

      {/* Stats bar - only show when we have results */}
      {results.size > 0 && (
        <div className="px-4 py-2 bg-white border-b border-black/6 flex items-center gap-4">
          <span className="typo-small flex items-center gap-1.5 text-success">
            <CheckCircle size={14} />
            {stats.verified} verified
          </span>
          <span className="typo-small flex items-center gap-1.5 text-orange1">
            <AlertTriangle size={14} />
            {stats.warnings} warnings
          </span>
          <span className="typo-small flex items-center gap-1.5 text-error">
            <XCircle size={14} />
            {stats.errors} errors
          </span>
        </div>
      )}

      {/* Results list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {!selectedBib && pairs.length > 0 && (
          <div className="text-center py-8 text-secondary">
            <FileText size={24} className="mx-auto mb-2 text-tertiary" />
            <p className="typo-small">Select a bibliography file to verify</p>
          </div>
        )}

        {sortedResults.length === 0 && isRunning && (
          <div className="text-center py-8 text-secondary">
            <Loader2 size={24} className="animate-spin mx-auto mb-2" />
            <p className="typo-small">Verifying references...</p>
          </div>
        )}

        {sortedResults.map((result) => (
          <CitationCard
            key={result.cite_key}
            result={result}
            isExpanded={expandedKeys.has(result.cite_key)}
            isApproved={approved.has(result.cite_key)}
            onToggleExpand={() => toggleExpand(result.cite_key)}
            onApprove={() => handleApprove(result.cite_key)}
          />
        ))}
      </div>
    </div>
  );
}

// Individual citation card
function CitationCard({
  result,
  isExpanded,
  isApproved,
  onToggleExpand,
  onApprove,
}: {
  result: VerificationResult;
  isExpanded: boolean;
  isApproved: boolean;
  onToggleExpand: () => void;
  onApprove: () => void;
}) {
  const statusIcon = {
    verified: <CheckCircle size={16} className="text-success" />,
    warning: <AlertTriangle size={16} className="text-orange1" />,
    error: <XCircle size={16} className="text-error" />,
    pending: <Loader2 size={16} className="text-tertiary animate-spin" />,
  }[result.status];

  const statusClass = {
    verified: 'border-success/20 bg-success/5',
    warning: 'border-orange1/20 bg-orange1/5',
    error: 'border-error/20 bg-error/5',
    pending: 'border-black/6 bg-white',
  }[result.status];

  return (
    <div className={`rounded-yw-lg border p-3 ${statusClass}`}>
      {/* Header row */}
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={onToggleExpand}
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-tertiary" />
        ) : (
          <ChevronRight size={14} className="text-tertiary" />
        )}
        {statusIcon}
        <span className="typo-small-strong flex-1 font-mono">{result.cite_key}</span>

        {/* Actions */}
        {result.status !== 'verified' && !isApproved && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onApprove();
            }}
            className="btn-ghost typo-ex-small flex items-center gap-1 text-success"
          >
            <Check size={12} />
            Approve
          </button>
        )}
      </div>

      {/* Title */}
      {result.matched_paper && (
        <div className="mt-1 ml-6 typo-small text-secondary">
          &quot;{result.matched_paper.title}&quot; ({result.matched_paper.year || 'n.d.'})
        </div>
      )}

      {/* Issues */}
      {result.metadata_issues.length > 0 && (
        <div className="mt-1 ml-6 typo-ex-small text-orange1">
          {result.metadata_issues.join(', ')}
        </div>
      )}

      {/* Context score */}
      {result.checked_via !== 'skipped' && (
        <div className="mt-1 ml-6 typo-ex-small text-tertiary">
          {result.usages.length} usage{result.usages.length !== 1 ? 's' : ''} ·
          Context: {result.context_explanation || `${(result.context_score * 100).toFixed(0)}% confidence`}
        </div>
      )}

      {/* Expanded details */}
      {isExpanded && (
        <div className="mt-3 ml-6 space-y-2">
          {/* Paper link */}
          {result.matched_paper?.url && (
            <a
              href={result.matched_paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="typo-small text-green1 flex items-center gap-1 hover:underline"
            >
              <ExternalLink size={12} />
              View on Semantic Scholar
            </a>
          )}

          {/* Usages */}
          {result.usages.length > 0 && (
            <div>
              <div className="typo-ex-small text-tertiary mb-1">Usages in document:</div>
              {result.usages.map((usage, i) => (
                <div key={i} className="typo-ex-small bg-white rounded p-2 mb-1 border border-black/6">
                  <div className="text-tertiary">Line {usage.line_number}</div>
                  <div className="text-primary italic">&quot;{usage.claim}&quot;</div>
                </div>
              ))}
            </div>
          )}

          {/* BibTeX info */}
          {result.bib_entry && (
            <div>
              <div className="typo-ex-small text-tertiary mb-1">BibTeX fields:</div>
              <pre className="typo-ex-small bg-white rounded p-2 border border-black/6 overflow-x-auto font-mono">
                {JSON.stringify(result.bib_entry.fields, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
