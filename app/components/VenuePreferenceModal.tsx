'use client';

import { useState, useEffect, useRef } from 'react';
import { X, Plus, Check } from 'lucide-react';

interface VenuePreferenceModalProps {
  isOpen: boolean;
  requestId: string;
  topic: string;
  domain: string;
  suggestedVenues: string[];
  onClose: () => void;
  onSubmit: (venues: string[]) => void;
}

export default function VenuePreferenceModal({
  isOpen,
  requestId: _requestId,
  topic,
  domain,
  suggestedVenues,
  onClose,
  onSubmit,
}: VenuePreferenceModalProps) {
  const [selectedVenues, setSelectedVenues] = useState<string[]>([]);
  const [customVenue, setCustomVenue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset when modal opens
  useEffect(() => {
    if (isOpen) {
      // Pre-select first 3 suggested venues
      setSelectedVenues(suggestedVenues.slice(0, 3));
      setCustomVenue('');
    }
  }, [isOpen, suggestedVenues]);

  // Handle keyboard events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const toggleVenue = (venue: string) => {
    setSelectedVenues((prev) =>
      prev.includes(venue)
        ? prev.filter((v) => v !== venue)
        : [...prev, venue]
    );
  };

  const addCustomVenue = () => {
    const trimmed = customVenue.trim();
    if (trimmed && !selectedVenues.includes(trimmed)) {
      setSelectedVenues((prev) => [...prev, trimmed]);
      setCustomVenue('');
      inputRef.current?.focus();
    }
  };

  const handleSubmit = () => {
    onSubmit(selectedVenues);
  };

  const handleSkip = () => {
    onSubmit([]); // Empty array = no filter
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
            <h2 className="typo-body-strong text-primary">Select Venues</h2>
            <p className="typo-small text-secondary mt-1">
              Focus your search on specific conferences & journals
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
          {/* Topic and domain display */}
          <div className="mb-4 p-3 bg-green1/5 rounded-yw-lg">
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 bg-green1/20 text-green1 rounded-yw typo-caption">
                {domain}
              </span>
            </div>
            <p className="typo-small text-secondary">Searching for:</p>
            <p className="typo-body text-primary mt-1">{topic}</p>
          </div>

          {/* Suggested venues (from LLM) */}
          {suggestedVenues.length > 0 && (
            <div className="mb-4">
              <p className="typo-small-strong text-secondary mb-2">
                Recommended venues for {domain}:
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedVenues.map((venue) => (
                  <button
                    key={venue}
                    onClick={() => toggleVenue(venue)}
                    className={`px-3 py-1.5 rounded-yw-full typo-small transition-colors flex items-center gap-1.5 ${
                      selectedVenues.includes(venue)
                        ? 'bg-green1 text-white'
                        : 'bg-green1/10 text-green1 hover:bg-green1/20'
                    }`}
                  >
                    {selectedVenues.includes(venue) && <Check size={14} />}
                    {venue}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Custom venue input */}
          <div className="mb-4">
            <p className="typo-small-strong text-secondary mb-2">Add custom venue:</p>
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={customVenue}
                onChange={(e) => setCustomVenue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addCustomVenue();
                  }
                }}
                className="flex-1 px-3 py-2 border border-black/10 rounded-yw-lg typo-body focus:outline-none focus:ring-2 focus:ring-green1/50 focus:border-green1"
                placeholder="e.g., Journal of Physiology, Cell..."
              />
              <button
                onClick={addCustomVenue}
                disabled={!customVenue.trim()}
                className="px-3 py-2 bg-black/5 hover:bg-black/10 rounded-yw-lg transition-colors disabled:opacity-50"
              >
                <Plus size={16} className="text-secondary" />
              </button>
            </div>
          </div>

          {/* Selected venues summary */}
          {selectedVenues.length > 0 && (
            <div className="p-3 bg-black/3 rounded-yw-lg">
              <p className="typo-small text-secondary mb-2">
                Selected ({selectedVenues.length}):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {selectedVenues.map((venue) => (
                  <span
                    key={venue}
                    className="px-2 py-1 bg-green1/10 text-green1 rounded-yw typo-small flex items-center gap-1"
                  >
                    {venue}
                    <button
                      onClick={() => toggleVenue(venue)}
                      className="hover:text-green1/70"
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-between items-center p-6 pt-4 border-t border-black/5">
          <button
            onClick={handleSkip}
            className="px-4 py-2 typo-small text-secondary hover:bg-black/5 rounded-yw-lg transition-colors"
          >
            Skip (search all venues)
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
              className="px-4 py-2 typo-small-strong text-white bg-green1 hover:bg-green1/90 rounded-yw-lg transition-colors"
            >
              Search {selectedVenues.length > 0 ? `(${selectedVenues.length} venues)` : ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
