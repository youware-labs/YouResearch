'use client';

import { Loader2, Check, AlertCircle, Package, X } from 'lucide-react';

interface DockerBuildModalProps {
  isOpen: boolean;
  onClose: () => void;
  progress: number;
  phase: 'idle' | 'starting' | 'pulling' | 'building' | 'complete' | 'error';
  error?: string | null;
  onRetry?: () => void;
}

export default function DockerBuildModal({
  isOpen,
  onClose,
  progress,
  phase,
  error,
  onRetry,
}: DockerBuildModalProps) {
  if (!isOpen) return null;

  const getPhaseText = () => {
    switch (phase) {
      case 'idle':
      case 'starting':
        return 'Initializing...';
      case 'pulling':
        return 'Downloading TeX Live image (~2GB)...';
      case 'building':
        return 'Building LaTeX environment...';
      case 'complete':
        return 'Setup complete!';
      case 'error':
        return 'Setup failed';
    }
  };

  const getPhaseDescription = () => {
    switch (phase) {
      case 'idle':
      case 'starting':
      case 'pulling':
        return 'This may take 10-30 minutes on first run. You can close this and continue working.';
      case 'building':
        return 'Installing LaTeX packages and tools...';
      case 'complete':
        return 'You can now compile LaTeX documents with full package support.';
      case 'error':
        return error || 'An error occurred during setup.';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-[20px] max-w-md w-full shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-green2 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                <Package className="w-5 h-5 text-white" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Setting Up LaTeX</h2>
                <p className="text-sm text-white/80">
                  {phase === 'complete' ? 'Ready to use' : 'Downloading in background'}
                </p>
              </div>
            </div>
            {phase !== 'complete' && (
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors"
              >
                <X className="w-4 h-4 text-white" />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Progress indicator */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="typo-body-strong text-primary">{getPhaseText()}</span>
              {phase !== 'error' && phase !== 'complete' && (
                <span className="typo-small text-secondary">{Math.round(progress)}%</span>
              )}
            </div>

            {/* Progress bar */}
            <div className="h-2 bg-black/5 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  phase === 'error' ? 'bg-error' : phase === 'complete' ? 'bg-success' : 'bg-green2'
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>

            <p className="typo-small text-secondary">{getPhaseDescription()}</p>
          </div>

          {/* Status icon */}
          <div className="flex justify-center py-4">
            {phase === 'complete' ? (
              <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center">
                <Check className="w-8 h-8 text-success" />
              </div>
            ) : phase === 'error' ? (
              <div className="w-16 h-16 rounded-full bg-error/10 flex items-center justify-center">
                <AlertCircle className="w-8 h-8 text-error" />
              </div>
            ) : (
              <div className="w-16 h-16 rounded-full bg-green3 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-green2 animate-spin" />
              </div>
            )}
          </div>

          {/* Actions */}
          {phase === 'error' && onRetry && (
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-3 px-4 border border-black/10 hover:bg-black/3 rounded-yw-lg transition-colors typo-body"
              >
                Cancel
              </button>
              <button
                onClick={onRetry}
                className="flex-1 py-3 px-4 bg-green2 hover:bg-green1 text-white rounded-yw-lg transition-colors typo-body-strong"
              >
                Retry
              </button>
            </div>
          )}

          {phase === 'complete' && (
            <button
              onClick={onClose}
              className="w-full py-3 px-4 bg-green2 hover:bg-green1 text-white rounded-yw-lg transition-colors typo-body-strong"
            >
              Done
            </button>
          )}

          {(phase === 'starting' || phase === 'pulling' || phase === 'building') && (
            <button
              onClick={onClose}
              className="w-full py-3 px-4 border border-black/10 hover:bg-black/3 rounded-yw-lg transition-colors typo-body"
            >
              Continue in background
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
