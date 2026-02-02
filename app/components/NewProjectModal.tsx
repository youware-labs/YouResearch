'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { X } from 'lucide-react';

interface NewProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string) => void;
}

export default function NewProjectModal({
  isOpen,
  onClose,
  onSubmit,
}: NewProjectModalProps) {
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setName('');
      setError('');
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      const trimmedName = name.trim();
      if (!trimmedName) {
        setError('Project name is required');
        return;
      }

      // Validate name (alphanumeric, hyphens, underscores)
      if (!/^[a-zA-Z0-9_-]+$/.test(trimmedName)) {
        setError('Name can only contain letters, numbers, hyphens, and underscores');
        return;
      }

      onSubmit(trimmedName);
      onClose();
    },
    [name, onSubmit, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20"
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div
        className="flex w-[392px] max-w-[calc(100vw-32px)] flex-col gap-4 rounded-yw-2xl bg-white p-5 shadow-modal animate-fade-in-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="typo-h2">New Project</h2>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full text-tertiary hover:bg-black/3 hover:text-secondary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="typo-small-strong text-secondary">
              Project Name
            </label>
            <input
              ref={inputRef}
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError('');
              }}
              placeholder="my-research-paper"
              className="input-field"
            />
            {error && (
              <p className="typo-small text-error">{error}</p>
            )}
          </div>

          {/* Info text */}
          <p className="typo-small text-tertiary">
            Creates a new LaTeX project with a basic article template.
          </p>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-yw-lg bg-black/6 py-2.5 typo-body-strong hover:bg-black/12 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 rounded-yw-lg bg-green1 py-2.5 typo-body-strong text-white hover:opacity-90 transition-opacity"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
