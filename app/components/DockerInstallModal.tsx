'use client';

import { X, Box, Download, ExternalLink } from 'lucide-react';

interface DockerInstallModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInstall: () => void;
}

export default function DockerInstallModal({
  isOpen,
  onClose,
  onInstall,
}: DockerInstallModalProps) {
  const dockerDownloadUrl = 'https://desktop.docker.com/mac/main/arm64/Docker.dmg';

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1a1a] border border-[#333] rounded-xl max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#333]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center">
              <Box size={24} className="text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Docker Recommended</h2>
              <p className="text-sm text-gray-400">For full LaTeX support</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[#333] rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {/* Why Docker */}
          <div>
            <h3 className="text-white font-medium text-sm mb-2">Why Docker?</h3>
            <p className="text-gray-300 text-sm leading-relaxed">
              Docker provides a complete LaTeX environment with all packages pre-installed.
              This ensures your documents compile correctly, especially those with images.
            </p>
          </div>

          {/* Features */}
          <div className="bg-[#252525] rounded-lg p-4">
            <h3 className="text-white font-medium text-sm mb-3">With Docker you get:</h3>
            <ul className="space-y-2">
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-0.5">✓</span>
                <span className="text-gray-300 text-sm">Full TeX Live distribution with all packages</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-0.5">✓</span>
                <span className="text-gray-300 text-sm">Support for images, figures, and complex layouts</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-0.5">✓</span>
                <span className="text-gray-300 text-sm">Consistent compilation results</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-0.5">✓</span>
                <span className="text-gray-300 text-sm">Works like Overleaf, but locally</span>
              </li>
            </ul>
          </div>

          {/* Installation Steps */}
          <div>
            <h3 className="text-white font-medium text-sm mb-3">Installation Steps</h3>
            <ol className="space-y-3">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-medium">1</span>
                <div>
                  <p className="text-white text-sm">Download Docker Desktop</p>
                  <p className="text-gray-400 text-xs">Free for personal use (~500MB)</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-medium">2</span>
                <div>
                  <p className="text-white text-sm">Open the .dmg and drag to Applications</p>
                  <p className="text-gray-400 text-xs">Standard macOS installation</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-medium">3</span>
                <div>
                  <p className="text-white text-sm">Launch Docker Desktop</p>
                  <p className="text-gray-400 text-xs">Wait for the whale icon in the menu bar</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-medium">4</span>
                <div>
                  <p className="text-white text-sm">Restart YouResearch</p>
                  <p className="text-gray-400 text-xs">Docker will be detected automatically</p>
                </div>
              </li>
            </ol>
          </div>

          {/* Note about basic mode */}
          <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-3">
            <p className="text-yellow-300 text-xs">
              <strong>Note:</strong> Without Docker, you can still compile simple LaTeX documents without images using the bundled Tectonic compiler.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#333] flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 px-4 bg-[#333] hover:bg-[#444] text-white rounded-lg transition-colors text-sm"
          >
            Maybe Later
          </button>
          <a
            href={dockerDownloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onInstall}
            className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium flex items-center justify-center gap-2"
          >
            <Download size={18} />
            Download Docker
            <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </div>
  );
}
