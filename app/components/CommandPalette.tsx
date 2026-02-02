'use client';

import { useEffect, useRef } from 'react';
import {
  Search,
  Microscope,
  BookOpen,
  FileSearch,
  Wrench,
  Trash2,
  Play,
  Cloud,
  Sparkles,
  ListChecks,
  LucideIcon,
} from 'lucide-react';
import { SlashCommand } from '../lib/commands';

// =============================================================================
// Icon Map
// =============================================================================

const iconMap: Record<string, LucideIcon> = {
  Search,
  Microscope,
  BookOpen,
  FileSearch,
  Wrench,
  Trash2,
  Play,
  Cloud,
  Sparkles,
  ListChecks,
};

// =============================================================================
// Component
// =============================================================================

interface CommandPaletteProps {
  commands: SlashCommand[];
  selectedIndex: number;
  onSelect: (command: SlashCommand) => void;
  onHover: (index: number) => void;
}

export default function CommandPalette({
  commands,
  selectedIndex,
  onSelect,
  onHover,
}: CommandPaletteProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);

  // Scroll selected item into view
  useEffect(() => {
    if (selectedRef.current && listRef.current) {
      selectedRef.current.scrollIntoView({
        block: 'nearest',
        behavior: 'smooth',
      });
    }
  }, [selectedIndex]);

  if (commands.length === 0) {
    return null;
  }

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 right-0 mb-2 bg-white rounded-yw-lg border border-black/12 shadow-lg overflow-hidden max-h-[280px] overflow-y-auto z-50"
    >
      <div className="p-1.5">
        {commands.map((cmd, index) => {
          const Icon = iconMap[cmd.icon] || Search;
          const isSelected = index === selectedIndex;

          return (
            <button
              key={cmd.name}
              ref={isSelected ? selectedRef : null}
              onClick={() => onSelect(cmd)}
              onMouseEnter={() => onHover(index)}
              className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-yw-md text-left transition-colors ${
                isSelected
                  ? 'bg-green3/50 text-green1'
                  : 'text-primary hover:bg-fill-secondary'
              }`}
            >
              <div
                className={`flex-shrink-0 w-7 h-7 rounded-yw-md flex items-center justify-center ${
                  isSelected ? 'bg-green2 text-white' : 'bg-fill-secondary text-secondary'
                }`}
              >
                <Icon size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="typo-small-strong">/{cmd.name}</span>
                  {cmd.requiresArg && (
                    <span className="typo-ex-small text-tertiary">
                      [{cmd.argPlaceholder}]
                    </span>
                  )}
                </div>
                <div className="typo-ex-small text-secondary mt-0.5 truncate">
                  {cmd.description}
                </div>
              </div>
              <div className="flex-shrink-0">
                <span
                  className={`typo-ex-small px-1.5 py-0.5 rounded ${
                    cmd.category === 'research'
                      ? 'bg-purple-100 text-purple-700'
                      : cmd.category === 'writing'
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {cmd.category}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
