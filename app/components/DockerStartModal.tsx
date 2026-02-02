'use client';

import { X, Play, Loader2 } from 'lucide-react';

interface DockerStartModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStart: () => void;
  isStarting?: boolean;
}

export default function DockerStartModal({
  isOpen,
  onClose,
  onStart,
  isStarting = false,
}: DockerStartModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1a1a] border border-[#333] rounded-xl max-w-md w-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#333]">
          <h2 className="text-lg font-semibold text-white">Start Docker?</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[#333] rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <p className="text-gray-300 text-sm leading-relaxed">
            Docker Desktop is installed but not running. Starting Docker enables full LaTeX compilation with images and all packages.
          </p>

          <div className="bg-[#252525] rounded-lg p-4">
            <h3 className="text-white font-medium text-sm mb-2">With Docker you can:</h3>
            <ul className="space-y-1 text-sm text-gray-300">
              <li>• Compile documents with images</li>
              <li>• Use any LaTeX package</li>
              <li>• Get consistent results every time</li>
            </ul>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 py-3 px-4 bg-[#333] hover:bg-[#444] text-white rounded-lg transition-colors text-sm"
            >
              Not Now
            </button>
            <button
              onClick={onStart}
              disabled={isStarting}
              className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isStarting ? (
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
      </div>
    </div>
  );
}
