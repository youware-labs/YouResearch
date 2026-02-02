'use client';

import { useState, useEffect } from 'react';
import { X, Play, Loader2, CheckCircle } from 'lucide-react';

interface DockerGuideProps {
  isOpen: boolean;
  onClose: () => void;
  onDockerStarted?: () => void;
}

const API_BASE = 'http://localhost:8001';

export default function DockerGuide({ isOpen, onClose, onDockerStarted }: DockerGuideProps) {
  const [starting, setStarting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [dockerRunning, setDockerRunning] = useState(false);

  // Poll for Docker status
  useEffect(() => {
    if (!polling) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/docker/status`);
        if (res.ok) {
          const status = await res.json();
          if (status.docker_running) {
            setDockerRunning(true);
            setPolling(false);
            // Auto-close after a brief success message
            setTimeout(() => {
              onDockerStarted?.();
              onClose();
            }, 1500);
          }
        }
      } catch (e) {
        console.error('Failed to check Docker status:', e);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [polling, onClose, onDockerStarted]);

  const handleStartDocker = async () => {
    setStarting(true);
    try {
      await fetch(`${API_BASE}/api/docker/start`, { method: 'POST' });
      setPolling(true);
    } catch (e) {
      console.error('Failed to start Docker:', e);
    } finally {
      setStarting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-panel border border-border rounded-xl max-w-sm w-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="typo-heading text-primary">Start Docker</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-hover rounded-lg transition-colors"
          >
            <X size={20} className="text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {dockerRunning ? (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-green-500/10 flex items-center justify-center mx-auto">
                <CheckCircle size={32} className="text-green-500" />
              </div>
              <div>
                <h3 className="typo-heading text-primary mb-1">Docker is Running!</h3>
                <p className="typo-body text-secondary">You can now compile your document.</p>
              </div>
            </div>
          ) : (
            <>
              <p className="typo-body text-secondary text-center">
                Docker Desktop needs to be running to compile LaTeX documents with images.
              </p>

              <button
                onClick={handleStartDocker}
                disabled={starting || polling}
                className="w-full py-3 px-4 bg-blue-500 hover:bg-blue-500/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {polling ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    Waiting for Docker...
                  </>
                ) : starting ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play size={20} />
                    Start Docker Desktop
                  </>
                )}
              </button>

              {polling && (
                <p className="typo-small text-secondary text-center">
                  Docker is starting. This may take a moment...
                </p>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!dockerRunning && (
          <div className="p-4 border-t border-border">
            <p className="typo-small text-tertiary text-center">
              Or open Docker manually from your Applications folder
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
