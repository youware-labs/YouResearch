'use client';

import { useState, useEffect } from 'react';
import { X, Clock, Key, ExternalLink } from 'lucide-react';

// Error types from backend
export interface APIKeyRequiredError {
  error: 'api_key_required';
  message: string;
  model_requested: string;
  free_models: Array<{ id: string; name: string }>;
  hint: string;
}

export interface RateLimitError {
  error: 'rate_limited';
  message: string;
  retry_after: number;
  rate_limit: {
    remaining: number;
    limit: number;
    window_seconds: number;
    reset_in: number;
  };
  hint: string;
}

export type APIError = APIKeyRequiredError | RateLimitError | null;

interface APIErrorBannerProps {
  error: APIError;
  onDismiss: () => void;
  onOpenSettings?: () => void;
}

export default function APIErrorBanner({ error, onDismiss, onOpenSettings }: APIErrorBannerProps) {
  const [countdown, setCountdown] = useState<number>(0);

  // Countdown timer for rate limit
  useEffect(() => {
    if (error?.error === 'rate_limited') {
      setCountdown(Math.ceil(error.retry_after));
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            onDismiss();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [error, onDismiss]);

  if (!error) return null;

  if (error.error === 'api_key_required') {
    return (
      <div className="bg-orange2/20 border border-orange1/30 rounded-yw-lg p-4 mb-4 animate-fade-in-down">
        <div className="flex items-start gap-3">
          <Key size={20} className="text-orange1 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <h4 className="typo-small-strong text-orange1">API Key Required</h4>
              <button
                onClick={onDismiss}
                className="text-tertiary hover:text-primary transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <p className="typo-small text-secondary mt-1">
              Model <code className="bg-black/5 px-1.5 py-0.5 rounded text-xs">{error.model_requested}</code> requires your own API key.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {onOpenSettings && (
                <button
                  onClick={onOpenSettings}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-orange1 text-white typo-small-strong rounded-yw-lg hover:bg-orange1/90 transition-colors"
                >
                  <Key size={14} />
                  Add API Key
                </button>
              )}
              <a
                href="https://openrouter.ai/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-black/10 typo-small text-secondary rounded-yw-lg hover:bg-fill-secondary transition-colors"
              >
                Get OpenRouter Key
                <ExternalLink size={12} />
              </a>
            </div>
            <details className="mt-3">
              <summary className="typo-ex-small text-tertiary cursor-pointer hover:text-secondary">
                Or use a free model ({error.free_models.length} available)
              </summary>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {error.free_models.slice(0, 6).map((model) => (
                  <span
                    key={model.id}
                    className="inline-block px-2 py-1 bg-white border border-black/10 rounded-yw-md typo-ex-small text-tertiary"
                  >
                    {model.name}
                  </span>
                ))}
                {error.free_models.length > 6 && (
                  <span className="inline-block px-2 py-1 typo-ex-small text-tertiary">
                    +{error.free_models.length - 6} more
                  </span>
                )}
              </div>
            </details>
          </div>
        </div>
      </div>
    );
  }

  if (error.error === 'rate_limited') {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-yw-lg p-4 mb-4 animate-fade-in-down">
        <div className="flex items-start gap-3">
          <Clock size={20} className="text-blue-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <h4 className="typo-small-strong text-blue-700">Rate Limit Reached</h4>
              <button
                onClick={onDismiss}
                className="text-tertiary hover:text-primary transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <p className="typo-small text-blue-600 mt-1">
              Free tier limit reached ({error.rate_limit.limit} calls/minute).
            </p>
            <div className="mt-2 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                  <span className="typo-small-strong text-blue-700">{countdown}</span>
                </div>
                <span className="typo-small text-blue-600">seconds until reset</span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {onOpenSettings && (
                <button
                  onClick={onOpenSettings}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 text-white typo-small-strong rounded-yw-lg hover:bg-blue-600 transition-colors"
                >
                  <Key size={14} />
                  Add API Key for Unlimited
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
