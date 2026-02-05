'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle,
  XCircle,
  Eye,
  ChevronDown,
  ChevronRight,
  Clock,
  Check,
  X,
  Loader2,
  AlertTriangle,
} from 'lucide-react';

export interface PendingOperation {
  operation_id: string;
  session_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected' | 'executing' | 'completed' | 'failed' | 'expired';
  created_at: string;
  expires_at: string;
  file_path?: string;
  diff_preview?: {
    old_content: string;
    new_content: string;
  };
  result?: string;
  error?: string;
  rejection_reason?: string;
}

interface ApprovalQueuePanelProps {
  sessionId: string;
  projectPath: string;
  onViewDiff?: (operation: PendingOperation) => void;
  onClearDiff?: () => void;
}

export default function ApprovalQueuePanel({
  sessionId,
  projectPath,
  onViewDiff,
  onClearDiff,
}: ApprovalQueuePanelProps) {
  const [operations, setOperations] = useState<PendingOperation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);
  const [selectedOps, setSelectedOps] = useState<Set<string>>(new Set());
  const [viewingOpId, setViewingOpId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Connect to WebSocket for real-time updates
  useEffect(() => {
    if (!sessionId) return;

    const connectWebSocket = async () => {
      try {
        let backendUrl = 'http://127.0.0.1:8001';
        if (typeof window !== 'undefined' && window.aura) {
          backendUrl = await window.aura.getBackendUrl();
        }
        const wsUrl = backendUrl.replace('http', 'ws') + `/ws/hitl/${sessionId}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('[ApprovalQueue] WebSocket connected');
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
          } catch (e) {
            console.error('[ApprovalQueue] Failed to parse WebSocket message:', e);
          }
        };

        ws.onclose = () => {
          console.log('[ApprovalQueue] WebSocket disconnected');
          // Reconnect after a delay
          reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
          console.error('[ApprovalQueue] WebSocket error:', error);
        };
      } catch (e) {
        console.error('[ApprovalQueue] Failed to connect WebSocket:', e);
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [sessionId]);

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((message: { type: string; data: PendingOperation | { operation_id: string; status: string; result?: string; error?: string } }) => {
    if (message.type === 'pending') {
      // New pending operation
      const op = message.data as PendingOperation;
      setOperations((prev) => {
        // Avoid duplicates
        if (prev.some((o) => o.operation_id === op.operation_id)) {
          return prev;
        }
        return [...prev, op];
      });
    } else if (message.type === 'status') {
      // Status changed
      const { operation_id, status } = message.data as { operation_id: string; status: string };
      setOperations((prev) =>
        prev.map((op) =>
          op.operation_id === operation_id
            ? { ...op, status: status as PendingOperation['status'] }
            : op
        )
      );
    } else if (message.type === 'result') {
      // Execution result
      const { operation_id, status, result, error } = message.data as { operation_id: string; status: string; result?: string; error?: string };
      setOperations((prev) =>
        prev.map((op) =>
          op.operation_id === operation_id
            ? { ...op, status: status as PendingOperation['status'], result, error }
            : op
        )
      );
    }
  }, []);

  // Load initial pending operations
  useEffect(() => {
    if (!sessionId) return;

    const loadPending = async () => {
      setIsLoading(true);
      try {
        let backendUrl = 'http://127.0.0.1:8001';
        if (typeof window !== 'undefined' && window.aura) {
          backendUrl = await window.aura.getBackendUrl();
        }

        const response = await fetch(
          `${backendUrl}/api/hitl/v2/pending?session_id=${encodeURIComponent(sessionId)}`
        );
        if (response.ok) {
          const data = await response.json();
          setOperations(data);
        }
      } catch (e) {
        console.error('[ApprovalQueue] Failed to load pending operations:', e);
      } finally {
        setIsLoading(false);
      }
    };

    loadPending();
  }, [sessionId]);

  // Approve a single operation
  const approveOperation = useCallback(async (operationId: string) => {
    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      // Approve
      const approveResponse = await fetch(`${backendUrl}/api/hitl/v2/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: operationId }),
      });

      if (!approveResponse.ok) {
        throw new Error('Failed to approve');
      }

      // Execute
      const executeResponse = await fetch(`${backendUrl}/api/hitl/v2/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_id: operationId, project_path: projectPath }),
      });

      if (!executeResponse.ok) {
        throw new Error('Failed to execute');
      }

      // Update local state
      setOperations((prev) =>
        prev.map((op) =>
          op.operation_id === operationId ? { ...op, status: 'completed' } : op
        )
      );

      // Clear diff view if we were viewing this operation
      if (viewingOpId === operationId) {
        setViewingOpId(null);
        onClearDiff?.();
      }
    } catch (e) {
      console.error('[ApprovalQueue] Failed to approve operation:', e);
    }
  }, [projectPath, viewingOpId, onClearDiff]);

  // Reject a single operation
  const rejectOperation = useCallback(async (operationId: string) => {
    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/v2/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: operationId }),
      });

      // Update local state
      setOperations((prev) =>
        prev.map((op) =>
          op.operation_id === operationId ? { ...op, status: 'rejected' } : op
        )
      );

      // Clear diff view if we were viewing this operation
      if (viewingOpId === operationId) {
        setViewingOpId(null);
        onClearDiff?.();
      }
    } catch (e) {
      console.error('[ApprovalQueue] Failed to reject operation:', e);
    }
  }, [viewingOpId, onClearDiff]);

  // Batch approve selected operations
  const approveSelected = useCallback(async () => {
    const ids = Array.from(selectedOps);
    if (ids.length === 0) return;

    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      // Batch approve
      await fetch(`${backendUrl}/api/hitl/v2/batch-approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_ids: ids }),
      });

      // Batch execute
      await fetch(`${backendUrl}/api/hitl/v2/batch-execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_ids: ids, project_path: projectPath }),
      });

      // Clear selection
      setSelectedOps(new Set());

      // Refresh list
      setOperations((prev) =>
        prev.map((op) =>
          ids.includes(op.operation_id) ? { ...op, status: 'completed' } : op
        )
      );
    } catch (e) {
      console.error('[ApprovalQueue] Batch approve failed:', e);
    }
  }, [selectedOps, projectPath]);

  // Batch reject selected operations
  const rejectSelected = useCallback(async () => {
    const ids = Array.from(selectedOps);
    if (ids.length === 0) return;

    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/v2/batch-reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_ids: ids }),
      });

      // Clear selection
      setSelectedOps(new Set());

      // Refresh list
      setOperations((prev) =>
        prev.map((op) =>
          ids.includes(op.operation_id) ? { ...op, status: 'rejected' } : op
        )
      );
    } catch (e) {
      console.error('[ApprovalQueue] Batch reject failed:', e);
    }
  }, [selectedOps]);

  // View diff for an operation
  const handleViewDiff = useCallback((operation: PendingOperation) => {
    if (viewingOpId === operation.operation_id) {
      // Toggle off
      setViewingOpId(null);
      onClearDiff?.();
    } else {
      setViewingOpId(operation.operation_id);
      onViewDiff?.(operation);
    }
  }, [viewingOpId, onViewDiff, onClearDiff]);

  // Toggle selection
  const toggleSelection = useCallback((operationId: string) => {
    setSelectedOps((prev) => {
      const next = new Set(prev);
      if (next.has(operationId)) {
        next.delete(operationId);
      } else {
        next.add(operationId);
      }
      return next;
    });
  }, []);

  // Select/deselect all pending
  const toggleSelectAll = useCallback(() => {
    const pendingIds = operations
      .filter((op) => op.status === 'pending')
      .map((op) => op.operation_id);

    if (selectedOps.size === pendingIds.length && pendingIds.every((id) => selectedOps.has(id))) {
      setSelectedOps(new Set());
    } else {
      setSelectedOps(new Set(pendingIds));
    }
  }, [operations, selectedOps]);

  // Filter to show only pending operations
  const pendingOps = operations.filter((op) => op.status === 'pending');
  const recentOps = operations.filter((op) => op.status !== 'pending').slice(0, 5);

  if (pendingOps.length === 0 && recentOps.length === 0) {
    return null; // Don't show panel if nothing to show
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <Clock size={14} className="text-orange1" />;
      case 'approved':
      case 'executing':
        return <Loader2 size={14} className="text-green2 animate-spin" />;
      case 'completed':
        return <CheckCircle size={14} className="text-success" />;
      case 'rejected':
        return <XCircle size={14} className="text-error" />;
      case 'failed':
        return <AlertTriangle size={14} className="text-error" />;
      case 'expired':
        return <Clock size={14} className="text-tertiary" />;
      default:
        return null;
    }
  };

  return (
    <div className="border-t border-black/6 bg-white">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 flex items-center gap-2 hover:bg-fill-secondary transition-colors"
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-tertiary" />
        ) : (
          <ChevronRight size={14} className="text-tertiary" />
        )}
        <span className="typo-small-strong text-primary">Pending Operations</span>
        {pendingOps.length > 0 && (
          <span className="badge badge-warning typo-ex-small">{pendingOps.length}</span>
        )}
        <span className="flex-1" />
        {isLoading && <Loader2 size={14} className="text-tertiary animate-spin" />}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3">
          {/* Batch actions */}
          {pendingOps.length > 0 && (
            <div className="flex items-center gap-2 mb-2">
              <label className="flex items-center gap-1.5 typo-ex-small text-tertiary cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedOps.size === pendingOps.length && pendingOps.length > 0}
                  onChange={toggleSelectAll}
                  className="w-3.5 h-3.5 rounded border-black/20"
                />
                Select all
              </label>
              <span className="flex-1" />
              {selectedOps.size > 0 && (
                <>
                  <button
                    onClick={rejectSelected}
                    className="flex items-center gap-1 px-2 py-1 typo-ex-small bg-error/10 text-error rounded-yw-md hover:bg-error/20 transition-colors"
                  >
                    <X size={10} />
                    Reject ({selectedOps.size})
                  </button>
                  <button
                    onClick={approveSelected}
                    className="flex items-center gap-1 px-2 py-1 typo-ex-small bg-success/10 text-success rounded-yw-md hover:bg-success/20 transition-colors"
                  >
                    <Check size={10} />
                    Approve ({selectedOps.size})
                  </button>
                </>
              )}
            </div>
          )}

          {/* Pending operations list */}
          <div className="space-y-1.5">
            {pendingOps.map((op) => (
              <div
                key={op.operation_id}
                className={`flex items-center gap-2 p-2 rounded-yw-md border transition-colors ${
                  viewingOpId === op.operation_id
                    ? 'bg-orange2/20 border-orange1/30'
                    : 'bg-fill-secondary border-transparent hover:border-black/6'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedOps.has(op.operation_id)}
                  onChange={() => toggleSelection(op.operation_id)}
                  className="w-3.5 h-3.5 rounded border-black/20"
                />
                {getStatusIcon(op.status)}
                <div className="flex-1 min-w-0">
                  <div className="typo-small text-primary truncate">
                    {op.tool_name}: {op.file_path || 'unknown'}
                  </div>
                </div>
                {op.diff_preview && (
                  <button
                    onClick={() => handleViewDiff(op)}
                    className={`flex items-center gap-1 px-2 py-1 typo-ex-small rounded-yw-md transition-colors ${
                      viewingOpId === op.operation_id
                        ? 'bg-orange1 text-white'
                        : 'bg-black/6 text-secondary hover:bg-black/12'
                    }`}
                  >
                    <Eye size={10} />
                    Diff
                  </button>
                )}
                <button
                  onClick={() => rejectOperation(op.operation_id)}
                  className="flex items-center justify-center w-6 h-6 rounded-yw-md bg-error/10 text-error hover:bg-error/20 transition-colors"
                  title="Reject"
                >
                  <X size={12} />
                </button>
                <button
                  onClick={() => approveOperation(op.operation_id)}
                  className="flex items-center justify-center w-6 h-6 rounded-yw-md bg-success/10 text-success hover:bg-success/20 transition-colors"
                  title="Approve"
                >
                  <Check size={12} />
                </button>
              </div>
            ))}
          </div>

          {/* Recent completed/rejected operations */}
          {recentOps.length > 0 && (
            <div className="mt-3 pt-3 border-t border-black/6">
              <div className="typo-ex-small text-tertiary mb-1.5">Recent</div>
              <div className="space-y-1">
                {recentOps.map((op) => (
                  <div
                    key={op.operation_id}
                    className="flex items-center gap-2 p-1.5 rounded-yw-md opacity-60"
                  >
                    {getStatusIcon(op.status)}
                    <span className="typo-ex-small text-secondary truncate flex-1">
                      {op.tool_name}: {op.file_path || 'unknown'}
                    </span>
                    <span className="typo-ex-small text-tertiary">
                      {op.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
