'use client';

import { useState, useCallback, useEffect } from 'react';
import { ChevronRight, ChevronDown, List } from 'lucide-react';
import { api, OutlineSection } from '@/lib/api';
import ResizeHandle from './ResizeHandle';

interface FileOutlineProps {
  projectPath: string | null;
  currentFile: string | null;
  onNavigate: (line: number) => void;
  height: number;
  onResize: (delta: number) => void;
}

// Section level to icon/style mapping
function getSectionStyle(level: number): { indent: number; fontWeight: string } {
  switch (level) {
    case 0: // part
      return { indent: 0, fontWeight: 'font-semibold' };
    case 1: // chapter
      return { indent: 0, fontWeight: 'font-semibold' };
    case 2: // section
      return { indent: 0, fontWeight: 'font-medium' };
    case 3: // subsection
      return { indent: 12, fontWeight: 'font-normal' };
    case 4: // subsubsection
      return { indent: 24, fontWeight: 'font-normal' };
    case 5: // paragraph
      return { indent: 36, fontWeight: 'font-normal' };
    default:
      return { indent: 0, fontWeight: 'font-normal' };
  }
}

// Recursive outline node component
function OutlineNode({
  section,
  onNavigate,
  depth = 0,
}: {
  section: OutlineSection;
  onNavigate: (line: number) => void;
  depth?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = section.children && section.children.length > 0;
  const style = getSectionStyle(section.level);

  const handleClick = useCallback(() => {
    onNavigate(section.line);
  }, [section.line, onNavigate]);

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  }, [isExpanded]);

  return (
    <div>
      <div
        className={`
          flex items-center gap-1.5 py-1 px-2 cursor-pointer rounded-yw-lg mx-1
          hover:bg-black/3 transition-colors duration-200
          ${style.fontWeight}
        `}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
      >
        {/* Expand toggle for items with children */}
        {hasChildren ? (
          <button
            onClick={handleToggle}
            className="p-0.5 hover:bg-black/5 rounded"
          >
            {isExpanded ? (
              <ChevronDown size={12} className="text-tertiary" />
            ) : (
              <ChevronRight size={12} className="text-tertiary" />
            )}
          </button>
        ) : (
          <span className="w-[16px]" />
        )}

        <span className="truncate typo-small text-secondary">
          {section.name}
        </span>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div>
          {section.children.map((child, index) => (
            <OutlineNode
              key={`${child.line}-${index}`}
              section={child}
              onNavigate={onNavigate}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FileOutline({
  projectPath,
  currentFile,
  onNavigate,
  height,
  onResize,
}: FileOutlineProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [outline, setOutline] = useState<OutlineSection[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch outline when file changes
  useEffect(() => {
    async function fetchOutline() {
      if (!projectPath || !currentFile) {
        setOutline([]);
        return;
      }

      // Only fetch outline for .tex files
      if (!currentFile.endsWith('.tex')) {
        setOutline([]);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const result = await api.getOutline(projectPath, currentFile);
        setOutline(result);
      } catch (err) {
        console.error('[FileOutline] Failed to fetch outline:', err);
        setError('Failed to load outline');
        setOutline([]);
      } finally {
        setIsLoading(false);
      }
    }

    fetchOutline();
  }, [projectPath, currentFile]);

  // Don't render if no project or not a .tex file
  if (!projectPath || !currentFile?.endsWith('.tex')) {
    return null;
  }

  return (
    <div className="flex flex-col" style={{ height }}>
      {/* Resize Handle */}
      <ResizeHandle
        direction="vertical"
        onResize={onResize}
      />

      {/* Header with stronger border */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full panel-header hover:bg-black/3 transition-colors border-t-2 border-black/10"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown size={14} className="text-tertiary" />
          ) : (
            <ChevronRight size={14} className="text-tertiary" />
          )}
          <List size={14} className="text-tertiary" />
          <span className="typo-small-strong text-secondary uppercase tracking-wider">
            File Outline
          </span>
        </div>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="flex-1 overflow-auto py-2">
          {isLoading ? (
            <div className="px-4 py-2 typo-small text-tertiary">
              Loading...
            </div>
          ) : error ? (
            <div className="px-4 py-2 typo-small text-error">
              {error}
            </div>
          ) : outline.length > 0 ? (
            outline.map((section, index) => (
              <OutlineNode
                key={`${section.line}-${index}`}
                section={section}
                onNavigate={onNavigate}
              />
            ))
          ) : (
            <div className="px-4 py-2 typo-small text-tertiary">
              No sections found
            </div>
          )}
        </div>
      )}
    </div>
  );
}
