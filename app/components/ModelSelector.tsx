'use client';

import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import { DashScopeModel } from '@/lib/providerSettings';

interface ModelSelectorProps {
  models: DashScopeModel[];
  selectedModel: string;
  onSelect: (modelId: string) => void;
}

export default function ModelSelector({
  models,
  selectedModel,
  onSelect,
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Close on escape key
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  const selected = models.find((m) => m.id === selectedModel);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-yw-lg
                   bg-fill-secondary hover:bg-black/6 transition-colors
                   text-secondary hover:text-primary"
      >
        <span className="typo-small">{selected?.name || selectedModel}</span>
        <ChevronDown
          size={14}
          className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className="absolute right-0 mt-1 w-48 bg-white rounded-yw-xl
                     shadow-lg border border-black/6 py-1 z-[100]
                     animate-fadeInUp"
        >
          {models.map((model) => (
            <button
              key={model.id}
              onClick={() => {
                onSelect(model.id);
                setIsOpen(false);
              }}
              className={`w-full flex items-center gap-2 px-3 py-2
                         hover:bg-fill-secondary transition-colors text-left
                         ${model.id === selectedModel ? 'bg-green2/5' : ''}`}
            >
              <span className="typo-small flex-1">{model.name}</span>
              {model.id === selectedModel && (
                <Check size={14} className="text-green2" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
