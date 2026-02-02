'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Check, ChevronDown } from 'lucide-react';

interface DomainPreferenceModalProps {
  isOpen: boolean;
  requestId: string;
  topic: string;
  suggestedDomain: string;
  onClose: () => void;
  onSubmit: (domain: string) => void;
}

// Common research domains for quick selection
const COMMON_DOMAINS = [
  // Computer Science
  { name: 'Computer Science', category: 'CS' },
  { name: 'Machine Learning', category: 'CS' },
  { name: 'Artificial Intelligence', category: 'CS' },
  { name: 'Natural Language Processing', category: 'CS' },
  { name: 'Computer Vision', category: 'CS' },
  { name: 'Robotics', category: 'CS' },
  // Life Sciences
  { name: 'Biology', category: 'Life Sciences' },
  { name: 'Physiology', category: 'Life Sciences' },
  { name: 'Neuroscience', category: 'Life Sciences' },
  { name: 'Biochemistry', category: 'Life Sciences' },
  { name: 'Genetics', category: 'Life Sciences' },
  // Medicine
  { name: 'Medicine', category: 'Health' },
  { name: 'Public Health', category: 'Health' },
  { name: 'Pharmacology', category: 'Health' },
  // Physical Sciences
  { name: 'Physics', category: 'Physical Sciences' },
  { name: 'Chemistry', category: 'Physical Sciences' },
  { name: 'Materials Science', category: 'Physical Sciences' },
  // Other
  { name: 'Mathematics', category: 'Other' },
  { name: 'Economics', category: 'Other' },
  { name: 'Psychology', category: 'Other' },
  { name: 'Environmental Science', category: 'Other' },
];

export default function DomainPreferenceModal({
  isOpen,
  requestId: _requestId,
  topic,
  suggestedDomain,
  onClose,
  onSubmit,
}: DomainPreferenceModalProps) {
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [customDomain, setCustomDomain] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset when modal opens
  useEffect(() => {
    if (isOpen) {
      // Pre-select suggested domain if it exists
      if (suggestedDomain) {
        setSelectedDomain(suggestedDomain);
      } else {
        setSelectedDomain('');
      }
      setCustomDomain('');
      setShowCustomInput(false);
    }
  }, [isOpen, suggestedDomain]);

  const handleSubmit = useCallback(() => {
    if (selectedDomain) {
      onSubmit(selectedDomain);
    }
  }, [selectedDomain, onSubmit]);

  // Handle keyboard events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'Enter' && !showCustomInput && selectedDomain) {
        handleSubmit();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, selectedDomain, showCustomInput, handleSubmit]);

  // Focus custom input when shown
  useEffect(() => {
    if (showCustomInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showCustomInput]);

  const handleDomainSelect = (domain: string) => {
    setSelectedDomain(domain);
    setShowCustomInput(false);
  };

  const handleCustomSubmit = () => {
    const trimmed = customDomain.trim();
    if (trimmed) {
      setSelectedDomain(trimmed);
      setShowCustomInput(false);
    }
  };

  const handleSkip = () => {
    // Use suggested domain if skipping
    onSubmit(suggestedDomain || 'General Science');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-yw-xl shadow-lg w-[500px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 pb-4 border-b border-black/5">
          <div>
            <h2 className="typo-body-strong text-primary">Research Domain</h2>
            <p className="typo-small text-secondary mt-1">
              Select the field for your research
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn-icon w-8 h-8"
          >
            <X size={16} className="text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Topic display */}
          <div className="mb-4 p-3 bg-green1/5 rounded-yw-lg">
            <p className="typo-small text-secondary">Searching for:</p>
            <p className="typo-body text-primary mt-1">{topic}</p>
          </div>

          {/* Suggested domain */}
          {suggestedDomain && (
            <div className="mb-4">
              <p className="typo-small-strong text-secondary mb-2">Suggested domain:</p>
              <button
                onClick={() => handleDomainSelect(suggestedDomain)}
                className={`px-4 py-2 rounded-yw-lg typo-body transition-colors flex items-center gap-2 ${
                  selectedDomain === suggestedDomain
                    ? 'bg-green1 text-white'
                    : 'bg-green1/10 text-green1 hover:bg-green1/20'
                }`}
              >
                {selectedDomain === suggestedDomain && <Check size={16} />}
                {suggestedDomain}
              </button>
            </div>
          )}

          {/* All domains by category */}
          <div className="mb-4">
            <p className="typo-small-strong text-secondary mb-2">All domains:</p>
            {['CS', 'Life Sciences', 'Health', 'Physical Sciences', 'Other'].map((category) => (
              <div key={category} className="mb-3">
                <p className="typo-caption text-tertiary mb-1.5">{category}</p>
                <div className="flex flex-wrap gap-2">
                  {COMMON_DOMAINS.filter((d) => d.category === category).map((domain) => (
                    <button
                      key={domain.name}
                      onClick={() => handleDomainSelect(domain.name)}
                      className={`px-3 py-1.5 rounded-yw-full typo-small transition-colors flex items-center gap-1.5 ${
                        selectedDomain === domain.name
                          ? 'bg-green1 text-white'
                          : 'bg-black/5 text-secondary hover:bg-black/10'
                      }`}
                    >
                      {selectedDomain === domain.name && <Check size={14} />}
                      {domain.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Custom domain input */}
          <div className="mb-4">
            {!showCustomInput ? (
              <button
                onClick={() => setShowCustomInput(true)}
                className="px-3 py-2 typo-small text-secondary hover:bg-black/5 rounded-yw-lg transition-colors flex items-center gap-2"
              >
                <ChevronDown size={14} />
                Enter custom domain...
              </button>
            ) : (
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={customDomain}
                  onChange={(e) => setCustomDomain(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleCustomSubmit();
                    }
                  }}
                  className="flex-1 px-3 py-2 border border-black/10 rounded-yw-lg typo-body focus:outline-none focus:ring-2 focus:ring-green1/50 focus:border-green1"
                  placeholder="e.g., Cognitive Science, Astronomy..."
                />
                <button
                  onClick={handleCustomSubmit}
                  disabled={!customDomain.trim()}
                  className="px-4 py-2 bg-green1 text-white hover:bg-green1/90 rounded-yw-lg transition-colors disabled:opacity-50 typo-small-strong"
                >
                  Set
                </button>
              </div>
            )}
          </div>

          {/* Selected domain display */}
          {selectedDomain && (
            <div className="p-3 bg-black/3 rounded-yw-lg">
              <p className="typo-small text-secondary">
                Selected domain:
              </p>
              <p className="typo-body-strong text-green1 mt-1">
                {selectedDomain}
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-between items-center p-6 pt-4 border-t border-black/5">
          <button
            onClick={handleSkip}
            className="px-4 py-2 typo-small text-secondary hover:bg-black/5 rounded-yw-lg transition-colors"
          >
            Skip (use suggestion)
          </button>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 typo-small text-secondary hover:bg-black/5 rounded-yw-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!selectedDomain}
              className="px-4 py-2 typo-small-strong text-white bg-green1 hover:bg-green1/90 rounded-yw-lg transition-colors disabled:opacity-50"
            >
              Continue
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
