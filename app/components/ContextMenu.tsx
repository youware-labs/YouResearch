'use client';

import { useEffect, useRef, useCallback } from 'react';
import {
  Columns,
  FolderOpen,
  MessageSquare,
  Scissors,
  Copy,
  ClipboardPaste,
  Link,
  FileText,
  Play,
  Eye,
  Pencil,
  Trash2,
  ChevronRight,
} from 'lucide-react';

export interface ContextMenuItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  shortcut?: string;
  disabled?: boolean;
  danger?: boolean;
  separator?: boolean;
  submenu?: ContextMenuItem[];
  onClick?: () => void;
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

function MenuItemComponent({
  item,
  onClose,
}: {
  item: ContextMenuItem;
  onClose: () => void;
}) {
  if (item.separator) {
    return <div className="h-px bg-black/8 my-1 mx-2" />;
  }

  const handleClick = () => {
    if (!item.disabled && item.onClick) {
      item.onClick();
      onClose();
    }
  };

  return (
    <button
      className={`
        w-full flex items-center gap-3 px-3 py-1.5 text-left
        transition-colors duration-100 rounded-yw-sm mx-1
        ${item.disabled
          ? 'text-tertiary cursor-not-allowed'
          : item.danger
            ? 'text-error hover:bg-error/10'
            : 'text-primary hover:bg-black/5'
        }
      `}
      style={{ width: 'calc(100% - 8px)' }}
      onClick={handleClick}
      disabled={item.disabled}
    >
      {/* Icon */}
      <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
        {item.icon}
      </span>

      {/* Label */}
      <span className="flex-1 typo-small truncate">{item.label}</span>

      {/* Shortcut or submenu indicator */}
      {item.shortcut && (
        <span className="typo-small text-tertiary ml-4">{item.shortcut}</span>
      )}
      {item.submenu && (
        <ChevronRight size={12} className="text-tertiary" />
      )}
    </button>
  );
}

export default function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  // Adjust position to stay within viewport
  const adjustPosition = useCallback(() => {
    if (!menuRef.current) return { x, y };

    const rect = menuRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let adjustedX = x;
    let adjustedY = y;

    if (x + rect.width > viewportWidth) {
      adjustedX = viewportWidth - rect.width - 8;
    }
    if (y + rect.height > viewportHeight) {
      adjustedY = viewportHeight - rect.height - 8;
    }

    return { x: adjustedX, y: adjustedY };
  }, [x, y]);

  const position = adjustPosition();

  return (
    <div
      ref={menuRef}
      className="fixed z-50 min-w-[220px] py-1.5 bg-white rounded-yw-xl shadow-lg border border-black/8"
      style={{
        left: position.x,
        top: position.y,
      }}
    >
      {items.map((item, index) => (
        <MenuItemComponent
          key={item.id || index}
          item={item}
          onClose={onClose}
        />
      ))}
    </div>
  );
}

// Helper to create file context menu items for Aura
export function createFileContextMenuItems(
  filePath: string,
  fileType: 'file' | 'directory',
  handlers: {
    onOpenToSide?: () => void;
    onRevealInFinder?: () => void;
    onAddToChat?: () => void;
    onCut?: () => void;
    onCopy?: () => void;
    onPaste?: () => void;
    onCopyPath?: () => void;
    onCopyRelativePath?: () => void;
    onCompile?: () => void;
    onPreviewPDF?: () => void;
    onRename?: () => void;
    onDelete?: () => void;
  },
  clipboardHasContent?: boolean
): ContextMenuItem[] {
  const isTexFile = filePath.endsWith('.tex');
  const isPdfFile = filePath.endsWith('.pdf');
  const isDirectory = fileType === 'directory';

  const items: ContextMenuItem[] = [
    // Open actions
    {
      id: 'open-side',
      label: 'Open to the Side',
      icon: <Columns size={14} />,
      shortcut: '⌥ ↵',
      disabled: isDirectory,
      onClick: handlers.onOpenToSide,
    },
    {
      id: 'reveal-finder',
      label: 'Reveal in Finder',
      icon: <FolderOpen size={14} />,
      shortcut: '⌥⌘R',
      onClick: handlers.onRevealInFinder,
    },
    { id: 'sep1', label: '', separator: true },

    // Aura Chat integration
    {
      id: 'add-to-chat',
      label: 'Add to Aura Chat',
      icon: <MessageSquare size={14} />,
      disabled: isDirectory,
      onClick: handlers.onAddToChat,
    },
    { id: 'sep2', label: '', separator: true },

    // Cut/Copy/Paste
    {
      id: 'cut',
      label: 'Cut',
      icon: <Scissors size={14} />,
      shortcut: '⌘X',
      onClick: handlers.onCut,
    },
    {
      id: 'copy',
      label: 'Copy',
      icon: <Copy size={14} />,
      shortcut: '⌘C',
      onClick: handlers.onCopy,
    },
    {
      id: 'paste',
      label: 'Paste',
      icon: <ClipboardPaste size={14} />,
      shortcut: '⌘V',
      disabled: !clipboardHasContent,
      onClick: handlers.onPaste,
    },
    { id: 'sep3', label: '', separator: true },

    // Copy path actions
    {
      id: 'copy-path',
      label: 'Copy Path',
      icon: <Link size={14} />,
      shortcut: '⌥⌘C',
      onClick: handlers.onCopyPath,
    },
    {
      id: 'copy-relative-path',
      label: 'Copy Relative Path',
      icon: <FileText size={14} />,
      shortcut: '⇧⌥⌘C',
      onClick: handlers.onCopyRelativePath,
    },
    { id: 'sep4', label: '', separator: true },
  ];

  // LaTeX-specific actions
  if (isTexFile) {
    items.push(
      {
        id: 'compile',
        label: 'Compile LaTeX',
        icon: <Play size={14} />,
        onClick: handlers.onCompile,
      },
      { id: 'sep5', label: '', separator: true },
    );
  }

  // PDF preview
  if (isPdfFile) {
    items.push(
      {
        id: 'preview-pdf',
        label: 'Preview PDF',
        icon: <Eye size={14} />,
        onClick: handlers.onPreviewPDF,
      },
      { id: 'sep6', label: '', separator: true },
    );
  }

  // File management
  items.push(
    {
      id: 'rename',
      label: 'Rename...',
      icon: <Pencil size={14} />,
      shortcut: '↵',
      onClick: handlers.onRename,
    },
    {
      id: 'delete',
      label: 'Delete',
      icon: <Trash2 size={14} />,
      shortcut: '⌘⌫',
      danger: true,
      onClick: handlers.onDelete,
    },
  );

  return items;
}
