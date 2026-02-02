'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  X,
  Download,
  Box,
  CheckCircle,
  Loader2,
  ArrowRight,
  ArrowLeft,
  Play,
  RefreshCw,
  Package,
  AlertCircle,
} from 'lucide-react';

interface DockerSetupWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: () => void;
}

type WizardStep = 'welcome' | 'download' | 'install' | 'start' | 'pull-image' | 'complete';

interface DockerStatus {
  status: string;
  docker_installed: boolean;
  docker_running: boolean;
  image_pulled: boolean;
  download_progress: number;
  download_path: string | null;
  error: string | null;
}

const API_BASE = 'http://localhost:8001';

export default function DockerSetupWizard({
  isOpen,
  onClose,
  onComplete,
}: DockerSetupWizardProps) {
  const [step, setStep] = useState<WizardStep>('welcome');
  const [status, setStatus] = useState<DockerStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  // Fetch Docker status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/docker/status`);
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        return data;
      }
    } catch (e) {
      console.error('Failed to fetch Docker status:', e);
    }
    return null;
  }, []);

  // Initial status check
  useEffect(() => {
    if (isOpen) {
      fetchStatus();
    }
  }, [isOpen, fetchStatus]);

  // Poll for status changes during install/start steps
  useEffect(() => {
    if (!polling) return;

    const interval = setInterval(async () => {
      const newStatus = await fetchStatus();
      if (newStatus) {
        // Auto-advance based on status
        if (step === 'install' && newStatus.docker_installed) {
          setStep('start');
          setPolling(false);
        } else if (step === 'start' && newStatus.docker_running) {
          setStep('pull-image');
          setPolling(false);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [polling, step, fetchStatus]);

  // Handle download
  const handleDownload = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/docker/download`, { method: 'POST' });
      const data = await res.json();

      if (data.error) {
        setError(data.error);
      } else if (data.download_path) {
        // Open the installer after download
        await fetch(`${API_BASE}/api/docker/open-installer`, { method: 'POST' });
        setStep('install');
        setPolling(true);
      }
    } catch (e) {
      setError('Failed to download Docker');
    } finally {
      setLoading(false);
    }
  };

  // Handle start Docker
  const handleStartDocker = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/docker/start`, { method: 'POST' });
      const data = await res.json();

      if (data.error) {
        setError(data.error);
      } else if (data.docker_running) {
        setStep('pull-image');
      } else {
        // Start polling for Docker to be ready
        setPolling(true);
      }
    } catch (e) {
      setError('Failed to start Docker');
    } finally {
      setLoading(false);
    }
  };

  // Handle pull image
  const handlePullImage = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/docker/pull-image`, { method: 'POST' });
      const data = await res.json();

      if (data.error) {
        setError(data.error);
      } else if (data.image_pulled) {
        setStep('complete');
      }
    } catch (e) {
      setError('Failed to pull image');
    } finally {
      setLoading(false);
    }
  };

  // Skip to appropriate step based on status
  const handleSkipToCurrentStep = useCallback(() => {
    if (!status) return;

    if (status.image_pulled) {
      setStep('complete');
    } else if (status.docker_running) {
      setStep('pull-image');
    } else if (status.docker_installed) {
      setStep('start');
    } else {
      setStep('download');
    }
  }, [status]);

  if (!isOpen) return null;

  const renderStepIndicator = () => {
    const steps: WizardStep[] = ['welcome', 'download', 'install', 'start', 'pull-image', 'complete'];
    const currentIndex = steps.indexOf(step);

    return (
      <div className="flex items-center justify-center gap-2 mb-6">
        {steps.slice(1, -1).map((s, i) => (
          <div
            key={s}
            className={`w-2 h-2 rounded-full transition-colors ${
              i + 1 <= currentIndex ? 'bg-accent' : 'bg-border'
            }`}
          />
        ))}
      </div>
    );
  };

  const renderWelcome = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
          <Box size={32} className="text-blue-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">Set Up Docker for LaTeX</h3>
        <p className="typo-body text-secondary">
          Docker provides a complete LaTeX environment with full package support.
          This one-time setup takes a few minutes.
        </p>
      </div>

      <div className="bg-surface rounded-lg p-4 space-y-3">
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0">
            <span className="typo-small text-blue-500 font-medium">1</span>
          </div>
          <div>
            <p className="typo-body text-primary font-medium">Download Docker Desktop</p>
            <p className="typo-small text-secondary">Free for personal use (~500MB)</p>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0">
            <span className="typo-small text-blue-500 font-medium">2</span>
          </div>
          <div>
            <p className="typo-body text-primary font-medium">Install & Start Docker</p>
            <p className="typo-small text-secondary">Drag to Applications, then launch</p>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0">
            <span className="typo-small text-blue-500 font-medium">3</span>
          </div>
          <div>
            <p className="typo-body text-primary font-medium">Pull LaTeX Image</p>
            <p className="typo-small text-secondary">One-time download of TeX Live</p>
          </div>
        </div>
      </div>

      {status?.docker_installed && (
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3">
          <p className="typo-small text-green-600 dark:text-green-400">
            <CheckCircle size={14} className="inline mr-1" />
            Docker is already installed! We can skip some steps.
          </p>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={onClose}
          className="flex-1 px-4 py-3 bg-surface hover:bg-hover rounded-lg transition-colors typo-body"
        >
          Maybe Later
        </button>
        <button
          onClick={() => {
            if (status?.docker_installed) {
              handleSkipToCurrentStep();
            } else {
              setStep('download');
            }
          }}
          className="flex-1 px-4 py-3 bg-accent hover:bg-accent/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2"
        >
          Get Started
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );

  const renderDownload = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
          <Download size={32} className="text-blue-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">Download Docker Desktop</h3>
        <p className="typo-body text-secondary">
          Click the button below to download Docker Desktop for Mac.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="typo-small text-red-600 dark:text-red-400">
            <AlertCircle size={14} className="inline mr-1" />
            {error}
          </p>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => setStep('welcome')}
          className="px-4 py-3 bg-surface hover:bg-hover rounded-lg transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <button
          onClick={handleDownload}
          disabled={loading}
          className="flex-1 px-4 py-3 bg-blue-500 hover:bg-blue-500/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              Downloading...
            </>
          ) : (
            <>
              <Download size={18} />
              Download Docker (~500MB)
            </>
          )}
        </button>
      </div>
    </div>
  );

  const renderInstall = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
          <Package size={32} className="text-blue-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">Install Docker Desktop</h3>
        <p className="typo-body text-secondary">
          A window opened with the Docker installer. Follow these steps:
        </p>
      </div>

      <div className="bg-surface rounded-lg p-4 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-accent text-white flex items-center justify-center flex-shrink-0">
            <span className="typo-small font-medium">1</span>
          </div>
          <p className="typo-body text-secondary">
            Drag the <strong className="text-primary">Docker</strong> icon to <strong className="text-primary">Applications</strong>
          </p>
        </div>
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-accent text-white flex items-center justify-center flex-shrink-0">
            <span className="typo-small font-medium">2</span>
          </div>
          <p className="typo-body text-secondary">
            Open <strong className="text-primary">Docker</strong> from your Applications folder
          </p>
        </div>
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-full bg-accent text-white flex items-center justify-center flex-shrink-0">
            <span className="typo-small font-medium">3</span>
          </div>
          <p className="typo-body text-secondary">
            Accept the license agreement when prompted
          </p>
        </div>
      </div>

      {polling && (
        <div className="flex items-center justify-center gap-2 text-secondary">
          <Loader2 size={16} className="animate-spin" />
          <span className="typo-small">Waiting for Docker to be installed...</span>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => {
            setPolling(false);
            setStep('download');
          }}
          className="px-4 py-3 bg-surface hover:bg-hover rounded-lg transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <button
          onClick={async () => {
            const newStatus = await fetchStatus();
            if (newStatus?.docker_installed) {
              setStep('start');
              setPolling(false);
            }
          }}
          className="flex-1 px-4 py-3 bg-accent hover:bg-accent/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2"
        >
          <RefreshCw size={18} />
          Check Installation
        </button>
      </div>
    </div>
  );

  const renderStart = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-green-500/10 flex items-center justify-center mx-auto mb-4">
          <Play size={32} className="text-green-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">Start Docker Desktop</h3>
        <p className="typo-body text-secondary">
          Docker is installed! Now let&apos;s start it up.
        </p>
      </div>

      <div className="bg-surface rounded-lg p-4">
        <p className="typo-body text-secondary">
          Click the button below to launch Docker Desktop.
          Wait for the whale icon to appear in your menu bar.
        </p>
      </div>

      {polling && (
        <div className="flex items-center justify-center gap-2 text-secondary">
          <Loader2 size={16} className="animate-spin" />
          <span className="typo-small">Waiting for Docker to start...</span>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="typo-small text-red-600 dark:text-red-400">
            <AlertCircle size={14} className="inline mr-1" />
            {error}
          </p>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => setStep('install')}
          className="px-4 py-3 bg-surface hover:bg-hover rounded-lg transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <button
          onClick={handleStartDocker}
          disabled={loading}
          className="flex-1 px-4 py-3 bg-green-500 hover:bg-green-500/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              Starting...
            </>
          ) : (
            <>
              <Play size={18} />
              Start Docker
            </>
          )}
        </button>
      </div>
    </div>
  );

  const renderPullImage = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-purple-500/10 flex items-center justify-center mx-auto mb-4">
          <Package size={32} className="text-purple-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">Pull LaTeX Image</h3>
        <p className="typo-body text-secondary">
          Docker is running! Now let&apos;s download the LaTeX environment.
        </p>
      </div>

      <div className="bg-surface rounded-lg p-4">
        <p className="typo-body text-secondary">
          This will download a complete TeX Live installation.
          It may take a few minutes depending on your internet connection.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="typo-small text-red-600 dark:text-red-400">
            <AlertCircle size={14} className="inline mr-1" />
            {error}
          </p>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => setStep('start')}
          className="px-4 py-3 bg-surface hover:bg-hover rounded-lg transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <button
          onClick={handlePullImage}
          disabled={loading}
          className="flex-1 px-4 py-3 bg-purple-500 hover:bg-purple-500/90 text-white rounded-lg transition-colors typo-body font-medium flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              Building Image...
            </>
          ) : (
            <>
              <Package size={18} />
              Build LaTeX Image
            </>
          )}
        </button>
      </div>
    </div>
  );

  const renderComplete = () => (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-green-500/10 flex items-center justify-center mx-auto mb-4">
          <CheckCircle size={32} className="text-green-500" />
        </div>
        <h3 className="typo-heading text-primary mb-2">All Set!</h3>
        <p className="typo-body text-secondary">
          Docker is ready. You can now compile any LaTeX document with full package support.
        </p>
      </div>

      <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
        <div className="flex items-center gap-3 mb-2">
          <CheckCircle size={18} className="text-green-500" />
          <span className="typo-body text-green-600 dark:text-green-400 font-medium">
            Docker is running
          </span>
        </div>
        <div className="flex items-center gap-3">
          <CheckCircle size={18} className="text-green-500" />
          <span className="typo-body text-green-600 dark:text-green-400 font-medium">
            LaTeX image is ready
          </span>
        </div>
      </div>

      <button
        onClick={() => {
          onComplete();
          onClose();
        }}
        className="w-full px-4 py-3 bg-accent hover:bg-accent/90 text-white rounded-lg transition-colors typo-body font-medium"
      >
        Start Compiling
      </button>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-panel border border-border rounded-xl max-w-md w-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="typo-heading text-primary">Docker Setup</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-hover rounded-lg transition-colors"
          >
            <X size={20} className="text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step !== 'welcome' && step !== 'complete' && renderStepIndicator()}

          {step === 'welcome' && renderWelcome()}
          {step === 'download' && renderDownload()}
          {step === 'install' && renderInstall()}
          {step === 'start' && renderStart()}
          {step === 'pull-image' && renderPullImage()}
          {step === 'complete' && renderComplete()}
        </div>
      </div>
    </div>
  );
}
