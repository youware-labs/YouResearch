'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X } from 'lucide-react';

interface RenameModalProps {
  isOpen: boolean;
  currentName: string;
  onClose: () => void;
  onRename: (newName: string) => void;
}

export default function RenameModal({
  isOpen,
  currentName,
  onClose,
  onRename,
}: RenameModalProps) {
  const [newName, setNewName] = useState(currentName);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset and focus when modal opens
  useEffect(() => {
    if (isOpen) {
      setNewName(currentName);
      // Focus and select the filename (without extension)
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          const dotIndex = currentName.lastIndexOf('.');
          if (dotIndex > 0) {
            inputRef.current.setSelectionRange(0, dotIndex);
          } else {
            inputRef.current.select();
          }
        }
      }, 50);
    }
  }, [isOpen, currentName]);

  const handleSubmit = useCallback(() => {
    const trimmedName = newName.trim();
    if (trimmedName && trimmedName !== currentName) {
      onRename(trimmedName);
    }
    onClose();
  }, [newName, currentName, onRename, onClose]);

  // Handle keyboard events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'Enter') {
        handleSubmit();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, handleSubmit]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-yw-xl shadow-lg w-[400px] p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="typo-body-strong text-primary">Rename</h2>
          <button
            onClick={onClose}
            className="btn-icon w-8 h-8"
          >
            <X size={16} className="text-secondary" />
          </button>
        </div>

        {/* Input */}
        <div className="mb-6">
          <input
            ref={inputRef}
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="w-full px-3 py-2 border border-black/10 rounded-yw-lg typo-body focus:outline-none focus:ring-2 focus:ring-green1/50 focus:border-green1"
            placeholder="Enter new name"
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 typo-small text-secondary hover:bg-black/5 rounded-yw-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!newName.trim() || newName.trim() === currentName}
            className="px-4 py-2 typo-small-strong text-white bg-green1 hover:bg-green1/90 rounded-yw-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Rename
          </button>
        </div>
      </div>
    </div>
  );
}
