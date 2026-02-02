'use client';

import { AlertTriangle, Check } from 'lucide-react';

interface FallbackNoticeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onContinue: () => void;
}

export default function FallbackNoticeModal({
  isOpen,
  onClose,
  onContinue,
}: FallbackNoticeModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-[20px] max-w-md w-full shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-5 border-b border-black/6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-warn/10 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-warn" />
            </div>
            <div>
              <h2 className="typo-h3 text-primary">Using Basic LaTeX</h2>
              <p className="typo-small text-secondary">Full environment downloading in background</p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <p className="typo-body text-secondary">
            The full LaTeX environment is being downloaded. In the meantime, you can use the basic compiler with some limitations:
          </p>

          <div className="bg-fill-secondary rounded-yw-lg p-4 space-y-2">
            <div className="flex items-start gap-2">
              <Check size={16} className="text-success mt-0.5 flex-shrink-0" />
              <span className="typo-small text-primary">Simple documents compile normally</span>
            </div>
            <div className="flex items-start gap-2">
              <Check size={16} className="text-success mt-0.5 flex-shrink-0" />
              <span className="typo-small text-primary">Basic packages available</span>
            </div>
            <div className="flex items-start gap-2">
              <AlertTriangle size={16} className="text-warn mt-0.5 flex-shrink-0" />
              <span className="typo-small text-secondary">Images and complex packages may not work</span>
            </div>
          </div>

          <p className="typo-small text-tertiary">
            You can check the download progress in the toolbar. Once complete, all features will be available.
          </p>
        </div>

        {/* Actions */}
        <div className="px-6 pb-6">
          <button
            onClick={() => {
              onContinue();
              onClose();
            }}
            className="w-full py-3 px-4 bg-green2 hover:bg-green1 text-white rounded-yw-lg transition-colors typo-body-strong"
          >
            Got it, continue
          </button>
        </div>
      </div>
    </div>
  );
}
