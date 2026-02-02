'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  Image,
  ChevronRight,
  ChevronDown,
  Plus,
  RefreshCw,
  FilePlus,
  FolderPlus,
  Upload,
} from 'lucide-react';
import ContextMenu, { createFileContextMenuItems } from './ContextMenu';

interface FileContextMenuHandlers {
  onOpenToSide?: (path: string) => void;
  onRevealInFinder?: (path: string) => void;
  onAddToChat?: (path: string) => void;
  onCut?: (path: string) => void;
  onCopy?: (path: string) => void;
  onPaste?: (path: string, isDirectory: boolean) => void;
  onCopyPath?: (path: string) => void;
  onCopyRelativePath?: (path: string) => void;
  onCompile?: (path: string) => void;
  onPreviewPDF?: (path: string) => void;
  onRename?: (path: string) => void;
  onDelete?: (path: string) => void;
}

interface FileTreeProps {
  projectPath: string | null;
  files: string[];
  currentFile: string | null;
  onFileSelect: (filePath: string) => void;
  onRefresh?: () => void;
  onCreateFile?: (filename: string, targetDir?: string) => Promise<void>;
  onCreateFolder?: (foldername: string, targetDir?: string) => Promise<void>;
  onUploadFiles?: (files: FileList, targetDir?: string) => Promise<void>;
  contextMenuHandlers?: FileContextMenuHandlers;
  clipboardHasContent?: boolean;
}

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

// LaTeX auxiliary file extensions to hide
const HIDDEN_EXTENSIONS = [
  '.aux',
  '.bbl',
  '.blg',
  '.log',
  '.out',
  '.toc',
  '.fls',
  '.fdb_latexmk',
  '.synctex.gz',
  '.synctex',
  '.nav',
  '.snm',
  '.vrb',
  '.lof',
  '.lot',
  '.idx',
  '.ind',
  '.ilg',
  '.glo',
  '.gls',
  '.glg',
  '.bcf',
  '.run.xml',
];

// Check if a file should be hidden
function isHiddenFile(filename: string): boolean {
  const lowerName = filename.toLowerCase();
  return HIDDEN_EXTENSIONS.some(ext => lowerName.endsWith(ext));
}

// Get icon for file type - YouWare green palette
function getFileIcon(name: string) {
  if (name.endsWith('.tex')) return <FileCode size={14} className="text-green1" />;
  if (name.endsWith('.bib')) return <FileText size={14} className="text-orange1" />;
  if (name.endsWith('.pdf')) return <FileText size={14} className="text-error" />;
  if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg')) {
    // eslint-disable-next-line jsx-a11y/alt-text -- This is a lucide-react icon, not an HTML img
    return <Image size={14} className="text-success" />;
  }
  if (name.endsWith('.sty') || name.endsWith('.cls')) {
    return <FileCode size={14} className="text-green2" />;
  }
  return <FileText size={14} className="text-tertiary" />;
}

// Tree node component
function TreeNode({
  node,
  depth,
  currentFile,
  onFileSelect,
  onContextMenu,
  dragOverPath,
  onDragOver,
  onDragLeave,
  onDrop,
}: {
  node: FileNode;
  depth: number;
  currentFile: string | null;
  onFileSelect: (path: string) => void;
  onContextMenu: (e: React.MouseEvent, node: FileNode) => void;
  dragOverPath: string | null;
  onDragOver: (path: string) => void;
  onDragLeave: () => void;
  onDrop: (path: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const isSelected = currentFile === node.path;
  const isDragOver = dragOverPath === node.path && node.type === 'directory';

  const handleClick = useCallback(() => {
    if (node.type === 'directory') {
      setIsExpanded(!isExpanded);
    } else {
      onFileSelect(node.path);
    }
  }, [node, isExpanded, onFileSelect]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu(e, node);
  }, [node, onContextMenu]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (node.type === 'directory') {
      onDragOver(node.path);
    }
  }, [node, onDragOver]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onDragLeave();
  }, [onDragLeave]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (node.type === 'directory') {
      onDrop(node.path);
    }
  }, [node, onDrop]);

  return (
    <div>
      <div
        className={`
          flex items-center gap-2 py-1.5 px-2 cursor-pointer rounded-yw-lg mx-1
          transition-colors duration-200
          ${isSelected
            ? 'bg-green3 text-green1'
            : isDragOver
              ? 'bg-green3/50 ring-2 ring-green2'
              : 'hover:bg-black/3'
          }
        `}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Expand icon for directories */}
        {node.type === 'directory' ? (
          <>
            {isExpanded ? (
              <ChevronDown size={14} className="text-tertiary" />
            ) : (
              <ChevronRight size={14} className="text-tertiary" />
            )}
            {isExpanded ? (
              <FolderOpen size={14} className="text-green2" />
            ) : (
              <Folder size={14} className="text-green2" />
            )}
          </>
        ) : (
          <>
            <span className="w-[14px]" />
            {getFileIcon(node.name)}
          </>
        )}
        <span className={`truncate typo-small ${isSelected ? 'typo-small-strong' : ''}`}>
          {node.name}
        </span>
      </div>

      {/* Children */}
      {node.type === 'directory' && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              currentFile={currentFile}
              onFileSelect={onFileSelect}
              onContextMenu={onContextMenu}
              dragOverPath={dragOverPath}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FileTree({
  projectPath,
  files,
  currentFile,
  onFileSelect,
  onRefresh,
  onCreateFile,
  onCreateFolder,
  onUploadFiles,
  contextMenuHandlers,
  clipboardHasContent,
}: FileTreeProps) {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showNewFileInput, setShowNewFileInput] = useState(false);
  const [showNewFolderInput, setShowNewFolderInput] = useState(false);
  const [newItemName, setNewItemName] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [dragOverPath, setDragOverPath] = useState<string | null>(null);
  const addMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const newItemInputRef = useRef<HTMLInputElement>(null);

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    node: FileNode;
  } | null>(null);

  // Handle right-click on a node
  const handleContextMenu = useCallback((e: React.MouseEvent, node: FileNode) => {
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      node,
    });
  }, []);

  // Close context menu
  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // Handle new file creation
  const handleNewFile = useCallback(() => {
    setShowAddMenu(false);
    setShowNewFileInput(true);
    setNewItemName('');
    setTimeout(() => newItemInputRef.current?.focus(), 50);
  }, []);

  // Handle new folder creation
  const handleNewFolder = useCallback(() => {
    setShowAddMenu(false);
    setShowNewFolderInput(true);
    setNewItemName('');
    setTimeout(() => newItemInputRef.current?.focus(), 50);
  }, []);

  // Handle upload click
  const handleUploadClick = useCallback(() => {
    setShowAddMenu(false);
    fileInputRef.current?.click();
  }, []);

  // Handle file input change (upload)
  const handleFileInputChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0 && onUploadFiles) {
      await onUploadFiles(files);
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [onUploadFiles]);

  // Handle new item submit
  const handleNewItemSubmit = useCallback(async () => {
    if (!newItemName.trim()) {
      setShowNewFileInput(false);
      setShowNewFolderInput(false);
      return;
    }

    try {
      if (showNewFileInput && onCreateFile) {
        await onCreateFile(newItemName.trim());
      } else if (showNewFolderInput && onCreateFolder) {
        await onCreateFolder(newItemName.trim());
      }
    } catch (error) {
      console.error('Failed to create item:', error);
    }

    setShowNewFileInput(false);
    setShowNewFolderInput(false);
    setNewItemName('');
  }, [newItemName, showNewFileInput, showNewFolderInput, onCreateFile, onCreateFolder]);

  // Handle key press in new item input
  const handleNewItemKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleNewItemSubmit();
    } else if (e.key === 'Escape') {
      setShowNewFileInput(false);
      setShowNewFolderInput(false);
      setNewItemName('');
    }
  }, [handleNewItemSubmit]);

  // Handle drag over (container level - for root drops)
  const handleContainerDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (projectPath) {
      setIsDragOver(true);
      // Only set root if not over a specific directory
      if (!dragOverPath) {
        setDragOverPath('');  // Empty string = root
      }
    }
  }, [projectPath, dragOverPath]);

  // Handle drag leave (container level)
  const handleContainerDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only clear if leaving the container entirely
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
      setIsDragOver(false);
      setDragOverPath(null);
    }
  }, []);

  // Handle drop (container level - for root drops)
  const handleContainerDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    if (!projectPath || !onUploadFiles) {
      setDragOverPath(null);
      return;
    }

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      // Use dragOverPath if set, otherwise root
      const targetDir = dragOverPath || '';
      await onUploadFiles(files, targetDir);
    }
    setDragOverPath(null);
  }, [projectPath, onUploadFiles, dragOverPath]);

  // Handle drag over a specific directory node
  const handleNodeDragOver = useCallback((path: string) => {
    setDragOverPath(path);
  }, []);

  // Handle drag leave from a node
  const handleNodeDragLeave = useCallback(() => {
    // Don't clear immediately - let the next dragOver set it
  }, []);

  // Handle drop on a specific directory node
  const handleNodeDrop = useCallback(async (_targetPath: string) => {
    setIsDragOver(false);
    setDragOverPath(null);
    // The actual drop is handled by container drop with dragOverPath
  }, []);

  // Close add menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (showAddMenu && addMenuRef.current && !addMenuRef.current.contains(e.target as Node)) {
        setShowAddMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAddMenu]);

  // Build tree from file list
  const buildTree = useCallback((filePaths: string[]): FileNode[] => {
    // Filter out hidden auxiliary files
    const visibleFiles = filePaths.filter(path => {
      const filename = path.split('/').pop() || '';
      return !isHiddenFile(filename);
    });

    const root: Map<string, FileNode> = new Map();

    for (const filePath of visibleFiles) {
      const parts = filePath.split('/').filter(Boolean);
      let currentPath = '';

      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        const parentPath = currentPath;
        currentPath = currentPath ? `${currentPath}/${part}` : part;

        if (!root.has(currentPath)) {
          const isFile = i === parts.length - 1;
          const node: FileNode = {
            name: part,
            path: currentPath,
            type: isFile ? 'file' : 'directory',
            children: isFile ? undefined : [],
          };

          root.set(currentPath, node);

          // Add to parent
          if (parentPath) {
            const parent = root.get(parentPath);
            if (parent && parent.children) {
              parent.children.push(node);
            }
          }
        }
      }
    }

    // Get root level nodes
    const rootNodes: FileNode[] = [];
    root.forEach((node, path) => {
      if (!path.includes('/')) {
        rootNodes.push(node);
      }
    });

    // Sort: directories first, then alphabetically
    const sortNodes = (nodes: FileNode[]): FileNode[] => {
      return nodes.sort((a, b) => {
        if (a.type !== b.type) {
          return a.type === 'directory' ? -1 : 1;
        }
        return a.name.localeCompare(b.name);
      }).map((node) => ({
        ...node,
        children: node.children ? sortNodes(node.children) : undefined,
      }));
    };

    return sortNodes(rootNodes);
  }, []);

  // Fetch files from backend
  const fetchFiles = useCallback(async () => {
    if (!projectPath) return;

    setIsLoading(true);
    try {
      if (onRefresh) {
        await onRefresh();
      }
    } catch (error) {
      console.error('Failed to fetch files:', error);
    } finally {
      setIsLoading(false);
    }
  }, [projectPath, onRefresh]);

  // Build tree when files prop changes
  useEffect(() => {
    if (files && files.length > 0) {
      setTree(buildTree(files));
    } else if (projectPath) {
      setTree([]);
    } else {
      setTree([]);
    }
  }, [files, projectPath, buildTree]);

  return (
    <div
      className={`h-full flex flex-col ${isDragOver ? 'bg-green3/30' : ''}`}
      onDragOver={handleContainerDragOver}
      onDragLeave={handleContainerDragLeave}
      onDrop={handleContainerDrop}
    >
      {/* Hidden file input for uploads */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* Header */}
      <div className="panel-header">
        <span className="typo-small-strong text-secondary uppercase tracking-wider">
          Files
        </span>
        <div className="flex gap-1">
          <div className="relative" ref={addMenuRef}>
            <button
              className="btn-icon w-6 h-6"
              title="Add"
              onClick={() => projectPath && setShowAddMenu(!showAddMenu)}
              disabled={!projectPath}
            >
              <Plus size={14} className={projectPath ? "text-secondary" : "text-tertiary"} />
            </button>

            {/* Add Menu Dropdown */}
            {showAddMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-black/10 py-1 z-50 min-w-[140px]">
                <button
                  className="w-full px-3 py-1.5 text-left typo-small hover:bg-black/5 flex items-center gap-2"
                  onClick={handleNewFile}
                >
                  <FilePlus size={14} className="text-secondary" />
                  New File
                </button>
                <button
                  className="w-full px-3 py-1.5 text-left typo-small hover:bg-black/5 flex items-center gap-2"
                  onClick={handleNewFolder}
                >
                  <FolderPlus size={14} className="text-secondary" />
                  New Folder
                </button>
                <div className="border-t border-black/5 my-1" />
                <button
                  className="w-full px-3 py-1.5 text-left typo-small hover:bg-black/5 flex items-center gap-2"
                  onClick={handleUploadClick}
                >
                  <Upload size={14} className="text-secondary" />
                  Upload Files
                </button>
              </div>
            )}
          </div>
          <button
            className="btn-icon w-6 h-6"
            title="Refresh"
            onClick={fetchFiles}
          >
            <RefreshCw size={14} className={`text-secondary ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* New File/Folder Input */}
      {(showNewFileInput || showNewFolderInput) && (
        <div className="px-2 py-1 border-b border-black/5">
          <div className="flex items-center gap-2">
            {showNewFileInput ? (
              <FilePlus size={14} className="text-green2" />
            ) : (
              <FolderPlus size={14} className="text-green2" />
            )}
            <input
              ref={newItemInputRef}
              type="text"
              className="flex-1 px-2 py-1 text-sm border border-green2 rounded focus:outline-none focus:ring-1 focus:ring-green2"
              placeholder={showNewFileInput ? "filename.tex" : "folder name"}
              value={newItemName}
              onChange={(e) => setNewItemName(e.target.value)}
              onKeyDown={handleNewItemKeyDown}
              onBlur={handleNewItemSubmit}
            />
          </div>
        </div>
      )}

      {/* Tree */}
      <div className="flex-1 overflow-auto py-2">
        {projectPath ? (
          tree.length > 0 ? (
            tree.map((node) => (
              <TreeNode
                key={node.path}
                node={node}
                depth={0}
                currentFile={currentFile}
                onFileSelect={onFileSelect}
                onContextMenu={handleContextMenu}
                dragOverPath={dragOverPath}
                onDragOver={handleNodeDragOver}
                onDragLeave={handleNodeDragLeave}
                onDrop={handleNodeDrop}
              />
            ))
          ) : (
            <div className="p-4 text-center typo-small text-tertiary">
              {isDragOver ? 'Drop files here' : 'No files found'}
            </div>
          )
        ) : (
          <div className="p-6 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-black/3 flex items-center justify-center">
              <Folder size={24} className="text-tertiary" />
            </div>
            <p className="typo-small text-tertiary">
              Open a project to see files
            </p>
          </div>
        )}
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={createFileContextMenuItems(
            contextMenu.node.path,
            contextMenu.node.type,
            {
              onOpenToSide: () => contextMenuHandlers?.onOpenToSide?.(contextMenu.node.path),
              onRevealInFinder: () => contextMenuHandlers?.onRevealInFinder?.(contextMenu.node.path),
              onAddToChat: () => contextMenuHandlers?.onAddToChat?.(contextMenu.node.path),
              onCut: () => contextMenuHandlers?.onCut?.(contextMenu.node.path),
              onCopy: () => contextMenuHandlers?.onCopy?.(contextMenu.node.path),
              onPaste: () => contextMenuHandlers?.onPaste?.(contextMenu.node.path, contextMenu.node.type === 'directory'),
              onCopyPath: () => contextMenuHandlers?.onCopyPath?.(contextMenu.node.path),
              onCopyRelativePath: () => contextMenuHandlers?.onCopyRelativePath?.(contextMenu.node.path),
              onCompile: () => contextMenuHandlers?.onCompile?.(contextMenu.node.path),
              onPreviewPDF: () => contextMenuHandlers?.onPreviewPDF?.(contextMenu.node.path),
              onRename: () => contextMenuHandlers?.onRename?.(contextMenu.node.path),
              onDelete: () => contextMenuHandlers?.onDelete?.(contextMenu.node.path),
            },
            clipboardHasContent
          )}
          onClose={closeContextMenu}
        />
      )}
    </div>
  );
}
