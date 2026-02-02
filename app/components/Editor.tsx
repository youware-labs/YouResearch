'use client';

import { useCallback, useRef, useEffect, useState } from 'react';
import MonacoEditor, { OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { Check, X, AlertCircle, FileCode } from 'lucide-react';

export interface PendingEdit {
  request_id: string;
  filepath: string;
  old_string: string;
  new_string: string;
}

export type SendToAgentAction = 'polish' | 'ask' | 'file';

export interface SendToAgentContext {
  text: string;
  action: SendToAgentAction;
  filePath: string | null;
  startLine: number;
  endLine: number;
}

interface EditorProps {
  content: string;
  filePath: string | null;
  onChange: (value: string | undefined) => void;
  onSave: () => void;
  pendingEdit?: PendingEdit | null;
  onApproveEdit?: (requestId: string) => void;
  onRejectEdit?: (requestId: string) => void;
  onSendToAgent?: (context: SendToAgentContext) => void;
  scrollToLine?: number | null;  // Line to scroll to (from SyncTeX)
  scrollToColumn?: number | null;  // Column to scroll to (from SyncTeX)
  onScrollComplete?: () => void;  // Called after scroll is done
}

// LaTeX language configuration
const latexLanguageConfig = {
  comments: {
    lineComment: '%',
  },
  brackets: [
    ['{', '}'],
    ['[', ']'],
    ['(', ')'],
  ],
  autoClosingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '(', close: ')' },
    { open: '$', close: '$' },
    { open: '`', close: "'" },
  ],
  surroundingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '(', close: ')' },
    { open: '$', close: '$' },
  ],
};

// LaTeX syntax highlighting tokens
const latexTokenProvider = {
  tokenizer: {
    root: [
      // Comments
      [/%.*$/, 'comment'],

      // Commands
      [/\\[a-zA-Z@]+/, 'keyword'],

      // Math mode
      [/\$\$/, { token: 'string', next: '@mathDisplay' }],
      [/\$/, { token: 'string', next: '@mathInline' }],

      // Environments
      [/\\begin\{[^}]+\}/, 'type'],
      [/\\end\{[^}]+\}/, 'type'],

      // Arguments
      [/\{/, 'delimiter.bracket'],
      [/\}/, 'delimiter.bracket'],
      [/\[/, 'delimiter.square'],
      [/\]/, 'delimiter.square'],

      // Special characters
      [/[&~^_]/, 'operator'],
    ],

    mathInline: [
      [/[^\$]+/, 'string'],
      [/\$/, { token: 'string', next: '@pop' }],
    ],

    mathDisplay: [
      [/[^\$]+/, 'string'],
      [/\$\$/, { token: 'string', next: '@pop' }],
    ],
  },
};

// Aura dark theme for Monaco
const auraTheme: editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6c7086', fontStyle: 'italic' },
    { token: 'keyword', foreground: '89b4fa' },
    { token: 'string', foreground: 'a6e3a1' },
    { token: 'type', foreground: 'f9e2af' },
    { token: 'operator', foreground: 'f38ba8' },
    { token: 'delimiter', foreground: 'cdd6f4' },
  ],
  colors: {
    'editor.background': '#282838',
    'editor.foreground': '#cdd6f4',
    'editor.lineHighlightBackground': '#313244',
    'editor.selectionBackground': '#45475a',
    'editorCursor.foreground': '#89b4fa',
    'editorLineNumber.foreground': '#6c7086',
    'editorLineNumber.activeForeground': '#cdd6f4',
  },
};

// Normalize whitespace for matching (collapse multiple spaces/newlines)
function normalizeWhitespace(str: string): string {
  return str.replace(/\s+/g, ' ').trim();
}

// Find exact character position where a string appears in content
function findStringLocation(content: string, searchStr: string): {
  startLine: number;
  endLine: number;
  startColumn: number;
  endColumn: number;
} | null {
  if (!searchStr || !content) return null;

  // Try exact match first
  let index = content.indexOf(searchStr);

  // If not found, try with normalized whitespace
  if (index === -1) {
    const normalizedContent = normalizeWhitespace(content);
    const normalizedSearch = normalizeWhitespace(searchStr);

    const normalizedIndex = normalizedContent.indexOf(normalizedSearch);
    if (normalizedIndex === -1) return null;

    // Find the approximate position in original content
    // by counting normalized characters
    let originalIndex = 0;
    let normalizedCount = 0;
    const targetNormalizedIndex = normalizedIndex;

    while (originalIndex < content.length && normalizedCount < targetNormalizedIndex) {
      const char = content[originalIndex];
      if (/\s/.test(char)) {
        // Skip consecutive whitespace (they become single space in normalized)
        while (originalIndex < content.length && /\s/.test(content[originalIndex])) {
          originalIndex++;
        }
        normalizedCount++; // One space in normalized version
      } else {
        originalIndex++;
        normalizedCount++;
      }
    }
    index = originalIndex;
  }

  if (index === -1) return null;

  const beforeMatch = content.substring(0, index);
  const linesBeforeMatch = beforeMatch.split('\n');
  const startLine = linesBeforeMatch.length;

  // Start column is the position within the last line before the match
  // Monaco columns are 1-indexed
  const startColumn = (linesBeforeMatch[linesBeforeMatch.length - 1]?.length || 0) + 1;

  // For the end position, we need to find where the match ends in original content
  // If we used normalized matching, find the end by matching normalized length
  let matchEndIndex = index;
  const normalizedSearchLen = normalizeWhitespace(searchStr).length;
  let normalizedMatchLen = 0;

  while (matchEndIndex < content.length && normalizedMatchLen < normalizedSearchLen) {
    const char = content[matchEndIndex];
    if (/\s/.test(char)) {
      while (matchEndIndex < content.length && /\s/.test(content[matchEndIndex])) {
        matchEndIndex++;
      }
      normalizedMatchLen++;
    } else {
      matchEndIndex++;
      normalizedMatchLen++;
    }
  }

  const matchedText = content.substring(index, matchEndIndex);
  const matchLines = matchedText.split('\n');
  const endLine = startLine + matchLines.length - 1;

  // End column is where the match ends on the last line of the match
  let endColumn: number;
  if (matchLines.length === 1) {
    endColumn = startColumn + matchedText.length;
  } else {
    endColumn = (matchLines[matchLines.length - 1]?.length || 0) + 1;
  }

  return { startLine, endLine, startColumn, endColumn };
}

export default function Editor({
  content,
  filePath,
  onChange,
  onSave,
  pendingEdit,
  onApproveEdit,
  onRejectEdit,
  onSendToAgent,
  scrollToLine,
  scrollToColumn,
  onScrollComplete,
}: EditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof import('monaco-editor') | null>(null);
  const decorationsRef = useRef<string[]>([]);
  const viewZoneIdRef = useRef<string | null>(null);
  const [editLocation, setEditLocation] = useState<{
    startLine: number;
    endLine: number;
    startColumn: number;
    endColumn: number;
  } | null>(null);
  const layoutListenerRef = useRef<{ dispose: () => void } | null>(null);
  const onSendToAgentRef = useRef(onSendToAgent);
  const filePathRef = useRef(filePath);

  // Keep refs in sync with props
  useEffect(() => {
    onSendToAgentRef.current = onSendToAgent;
  }, [onSendToAgent]);

  useEffect(() => {
    filePathRef.current = filePath;
  }, [filePath]);

  // Handle scrollToLine prop for SyncTeX navigation
  useEffect(() => {
    if (scrollToLine && editorRef.current && monacoRef.current) {
      const editor = editorRef.current;
      const monaco = monacoRef.current;
      const model = editor.getModel();

      if (!model) return;

      // Get the line content
      const lineContent = model.getLineContent(scrollToLine);
      const lineLength = lineContent.length;

      // Calculate the highlight range based on column
      let startColumn = 1;
      let endColumn = lineLength + 1;

      if (scrollToColumn && scrollToColumn > 0 && lineLength > 0) {
        // Find word boundaries around the column position
        const col = Math.min(scrollToColumn, lineLength);

        // Check if we're on whitespace; if so, find nearest word
        let targetCol = col;
        if (/\s/.test(lineContent[col - 1] || '')) {
          // We're on whitespace - find the nearest non-whitespace
          // Look forward first
          let forward = col;
          while (forward <= lineLength && /\s/.test(lineContent[forward - 1] || '')) {
            forward++;
          }
          // Look backward
          let backward = col;
          while (backward > 1 && /\s/.test(lineContent[backward - 2] || '')) {
            backward--;
          }
          // Use the closer one
          if (forward <= lineLength) {
            targetCol = forward;
          } else if (backward >= 1) {
            targetCol = backward - 1;
          }
        }

        // Find word start (go backwards until whitespace or start)
        let wordStart = targetCol;
        while (wordStart > 1 && !/\s/.test(lineContent[wordStart - 2] || '')) {
          wordStart--;
        }

        // Find word end (go forwards until whitespace or end)
        let wordEnd = targetCol;
        while (wordEnd < lineLength && !/\s/.test(lineContent[wordEnd] || '')) {
          wordEnd++;
        }

        // If we found a valid word range, use it
        if (wordEnd > wordStart) {
          startColumn = wordStart;
          endColumn = wordEnd + 1;
        } else {
          // Fallback: highlight a small region around the column
          startColumn = Math.max(1, col - 5);
          endColumn = Math.min(lineLength + 1, col + 15);
        }
      }

      // Scroll to the position and center it
      editor.revealPositionInCenter({
        lineNumber: scrollToLine,
        column: startColumn,
      });

      // Set cursor position at the highlighted location
      editor.setPosition({
        lineNumber: scrollToLine,
        column: startColumn,
      });

      // Create decorations: highlight the specific word/region AND the line glyph
      const decorations = editor.deltaDecorations([], [
        // Word/region highlight (inline, more visible)
        {
          range: new monaco.Range(scrollToLine, startColumn, scrollToLine, endColumn),
          options: {
            className: 'synctex-highlight-word',
            inlineClassName: 'synctex-highlight-word-inline',
          },
        },
        // Line glyph margin indicator
        {
          range: new monaco.Range(scrollToLine, 1, scrollToLine, 1),
          options: {
            isWholeLine: true,
            className: 'synctex-highlight-line',
            glyphMarginClassName: 'synctex-highlight-glyph',
          },
        },
      ]);

      // Remove highlight after a short delay
      setTimeout(() => {
        editor.deltaDecorations(decorations, []);
      }, 2000);

      // Focus the editor
      editor.focus();

      // Notify parent that scroll is complete
      onScrollComplete?.();
    }
  }, [scrollToLine, scrollToColumn, onScrollComplete]);

  // Function to calculate view zone height based on current editor width
  const calculateViewZoneHeight = useCallback((
    editorInstance: editor.IStandaloneCodeEditor,
    newString: string
  ): number => {
    const newLines = newString.split('\n');
    const editorWidth = editorInstance.getLayoutInfo().contentWidth;
    const charWidth = 7.5; // Approximate character width for monospace

    let totalVisualLines = 0;
    newLines.forEach(line => {
      if (line.length === 0) {
        totalVisualLines += 1;
      } else {
        // Account for "+ " prefix and padding
        const availableWidth = Math.max(editorWidth - 80, 100);
        const charsPerLine = Math.max(10, Math.floor(availableWidth / charWidth));
        const wrappedLines = Math.max(1, Math.ceil(line.length / charsPerLine));
        totalVisualLines += wrappedLines;
      }
    });

    // Buffer for padding
    return totalVisualLines + 2;
  }, []);

  // Function to create or update the view zone
  const updateViewZone = useCallback((
    editorInstance: editor.IStandaloneCodeEditor,
    monacoInstance: typeof import('monaco-editor'),
    newString: string,
    afterLine: number
  ) => {
    // Clear existing view zone
    if (viewZoneIdRef.current) {
      editorInstance.changeViewZones((accessor) => {
        if (viewZoneIdRef.current) {
          accessor.removeZone(viewZoneIdRef.current);
          viewZoneIdRef.current = null;
        }
      });
    }

    if (!newString) return;

    const newLines = newString.split('\n');
    const lineHeight = editorInstance.getOption(monacoInstance.editor.EditorOption.lineHeight);
    const finalHeight = calculateViewZoneHeight(editorInstance, newString);

    editorInstance.changeViewZones((accessor) => {
      const domNode = document.createElement('div');
      domNode.className = 'pending-edit-add-zone';
      domNode.style.backgroundColor = 'rgba(166, 227, 161, 0.15)';
      domNode.style.borderLeft = '4px solid #a6e3a1';
      domNode.style.paddingLeft = '8px';
      domNode.style.paddingRight = '8px';
      domNode.style.paddingTop = '4px';
      domNode.style.paddingBottom = '4px';
      domNode.style.fontFamily = "'JetBrains Mono', 'Fira Code', monospace";
      domNode.style.fontSize = '14px';
      domNode.style.lineHeight = `${lineHeight}px`;
      domNode.style.color = '#a6e3a1';
      domNode.style.whiteSpace = 'pre-wrap';
      domNode.style.wordBreak = 'break-word';
      domNode.style.overflowWrap = 'break-word';
      domNode.style.boxSizing = 'border-box';
      domNode.style.overflow = 'hidden';

      newLines.forEach((line) => {
        const lineDiv = document.createElement('div');
        lineDiv.style.display = 'flex';
        lineDiv.style.alignItems = 'flex-start';
        const plusSpan = document.createElement('span');
        plusSpan.textContent = '+ ';
        plusSpan.style.color = '#40a02b';
        plusSpan.style.marginRight = '4px';
        plusSpan.style.userSelect = 'none';
        plusSpan.style.flexShrink = '0';
        const textSpan = document.createElement('span');
        textSpan.textContent = line || ' ';
        textSpan.style.flex = '1';
        lineDiv.appendChild(plusSpan);
        lineDiv.appendChild(textSpan);
        domNode.appendChild(lineDiv);
      });

      const zoneId = accessor.addZone({
        afterLineNumber: afterLine,
        heightInLines: finalHeight,
        domNode: domNode,
        suppressMouseDown: true,
      });

      viewZoneIdRef.current = zoneId;
    });
  }, [calculateViewZoneHeight]);

  // Handle editor mount
  const handleEditorMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      monacoRef.current = monaco;

      // Register LaTeX language
      monaco.languages.register({ id: 'latex' });
      monaco.languages.setLanguageConfiguration('latex', latexLanguageConfig as any);
      monaco.languages.setMonarchTokensProvider('latex', latexTokenProvider as any);

      // Register theme
      monaco.editor.defineTheme('aura-dark', auraTheme);
      monaco.editor.setTheme('aura-dark');

      // Add save keybinding
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        onSave();
      });

      // Add context menu actions for AI (use 'z_aura' group to put at bottom with separator)
      editor.addAction({
        id: 'aura-polish',
        label: '✨ Polish with AI',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyP],
        contextMenuGroupId: 'z_aura',
        contextMenuOrder: 1,
        run: (ed) => {
          const selection = ed.getSelection();
          if (selection && !selection.isEmpty()) {
            const selectedText = ed.getModel()?.getValueInRange(selection);
            if (selectedText && selectedText.trim() && onSendToAgentRef.current) {
              onSendToAgentRef.current({
                text: selectedText,
                action: 'polish',
                filePath: filePathRef.current,
                startLine: selection.startLineNumber,
                endLine: selection.endLineNumber,
              });
            }
          }
        },
      });

      editor.addAction({
        id: 'aura-ask-ai',
        label: '💬 Ask AI',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyA],
        contextMenuGroupId: 'z_aura',
        contextMenuOrder: 2,
        run: (ed) => {
          const selection = ed.getSelection();
          if (selection && !selection.isEmpty()) {
            const selectedText = ed.getModel()?.getValueInRange(selection);
            if (selectedText && selectedText.trim() && onSendToAgentRef.current) {
              onSendToAgentRef.current({
                text: selectedText,
                action: 'ask',
                filePath: filePathRef.current,
                startLine: selection.startLineNumber,
                endLine: selection.endLineNumber,
              });
            }
          }
        },
      });

      // Focus editor
      editor.focus();
    },
    [onSave]
  );

  // Apply decorations when pendingEdit changes
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;

    console.log('[Editor] useEffect triggered - pendingEdit:', pendingEdit?.request_id);
    console.log('[Editor] filePath:', filePath);

    if (!editor || !monaco) {
      console.log('[Editor] Editor or Monaco not ready');
      return;
    }

    // Clear existing decorations
    if (decorationsRef.current.length > 0) {
      editor.deltaDecorations(decorationsRef.current, []);
      decorationsRef.current = [];
    }

    // Clear existing view zones
    if (viewZoneIdRef.current) {
      editor.changeViewZones((accessor) => {
        if (viewZoneIdRef.current) {
          accessor.removeZone(viewZoneIdRef.current);
          viewZoneIdRef.current = null;
        }
      });
    }

    // Check if this edit is for the current file
    if (!pendingEdit || !filePath) {
      console.log('[Editor] No pendingEdit or filePath, clearing');
      setEditLocation(null);
      return;
    }

    // Check if the pending edit is for this file
    // Handle both relative and absolute paths
    const editPath = pendingEdit.filepath;
    const currentPath = filePath;

    // Check multiple matching strategies:
    // 1. Exact match
    // 2. Filename match
    // 3. Current path ends with edit path (relative path within project)
    const editFilename = editPath.split('/').pop();
    const currentFilename = currentPath.split('/').pop();
    const pathMatches = (
      editPath === currentPath ||
      editFilename === currentFilename ||
      currentPath.endsWith('/' + editPath) ||
      currentPath.endsWith(editPath)
    );

    console.log('[Editor] Checking file match:', {
      editPath,
      currentPath,
      editFilename,
      currentFilename,
      pathMatches
    });

    if (!pathMatches) {
      console.log('[Editor] File mismatch, clearing');
      setEditLocation(null);
      return;
    }

    // Find where the old string is in the content
    const location = findStringLocation(content, pendingEdit.old_string);
    console.log('[Editor] Found location:', location);
    if (!location) {
      console.log('[Editor] Could not find old_string in content');
      console.log('[Editor] old_string length:', pendingEdit.old_string?.length);
      console.log('[Editor] old_string first 200 chars:', pendingEdit.old_string?.substring(0, 200));
      console.log('[Editor] content length:', content?.length);
      // Try to find partial match for debugging
      const firstLine = pendingEdit.old_string?.split('\n')[0];
      if (firstLine) {
        const partialMatch = content.indexOf(firstLine);
        console.log('[Editor] First line of old_string found at index:', partialMatch);
      }
      setEditLocation(null);
      return;
    }

    console.log('[Editor] Setting editLocation and creating decorations');
    setEditLocation(location);

    // Create decorations for the exact text being changed
    const decorations: editor.IModelDeltaDecoration[] = [];

    // Use exact character positions for the decoration range
    const exactRange = new monaco.Range(
      location.startLine,
      location.startColumn,
      location.endLine,
      location.endColumn
    );

    // Highlight background for the exact text being removed
    decorations.push({
      range: exactRange,
      options: {
        className: 'pending-edit-remove-inline',
        overviewRuler: {
          color: '#f38ba8',
          position: monaco.editor.OverviewRulerLane.Full,
        },
      },
    });

    // Add glyph margin indicator on the first line
    decorations.push({
      range: new monaco.Range(location.startLine, 1, location.startLine, 1),
      options: {
        glyphMarginClassName: 'pending-edit-remove-glyph',
      },
    });

    // Add inline strikethrough decoration for the exact text being removed
    decorations.push({
      range: exactRange,
      options: {
        inlineClassName: 'pending-edit-remove-text',
      },
    });

    decorationsRef.current = editor.deltaDecorations([], decorations);

    // Add view zone to show new content in green after the removed lines
    if (pendingEdit.new_string) {
      updateViewZone(editor, monaco, pendingEdit.new_string, location.endLine);

      // Set up layout listener to recalculate view zone on resize
      if (layoutListenerRef.current) {
        layoutListenerRef.current.dispose();
      }
      layoutListenerRef.current = editor.onDidLayoutChange(() => {
        if (pendingEdit?.new_string && viewZoneIdRef.current) {
          updateViewZone(editor, monaco, pendingEdit.new_string, location.endLine);
        }
      });
    }

    // Scroll to the edit location
    editor.revealLineInCenter(location.startLine);

    // Cleanup layout listener when effect is re-run or unmounted
    return () => {
      if (layoutListenerRef.current) {
        layoutListenerRef.current.dispose();
        layoutListenerRef.current = null;
      }
    };
  }, [pendingEdit, content, filePath, updateViewZone]);

  // Determine language from file extension
  const getLanguage = (path: string | null): string => {
    if (!path) return 'latex';
    if (path.endsWith('.tex')) return 'latex';
    if (path.endsWith('.bib')) return 'bibtex';
    if (path.endsWith('.sty')) return 'latex';
    if (path.endsWith('.cls')) return 'latex';
    if (path.endsWith('.json')) return 'json';
    if (path.endsWith('.md')) return 'markdown';
    return 'plaintext';
  };

  // Check if the pending edit applies to current file
  const isEditForCurrentFile = pendingEdit && filePath && (
    pendingEdit.filepath === filePath ||
    pendingEdit.filepath.split('/').pop() === filePath.split('/').pop() ||
    filePath.endsWith('/' + pendingEdit.filepath) ||
    filePath.endsWith(pendingEdit.filepath)
  );

  return (
    <div className="h-full flex flex-col bg-editor-surface">
      {/* File tab */}
      {filePath && (
        <div className="h-9 bg-editor-bg border-b border-editor-border flex items-center px-3">
          <span className="typo-small text-editor-text truncate">
            {filePath.split('/').pop()}
          </span>
        </div>
      )}

      {/* Pending Edit Banner */}
      {isEditForCurrentFile && editLocation && (
        <div className="bg-orange2/20 border-b border-orange1/30 px-4 py-2.5 flex items-center gap-3">
          <AlertCircle size={16} className="text-orange1 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="typo-small-strong text-orange1">Pending Edit</div>
            <div className="typo-ex-small text-orange1/70">
              Lines {editLocation.startLine}-{editLocation.endLine} will be modified
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => onRejectEdit?.(pendingEdit!.request_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 typo-small-strong bg-error/10 text-error rounded-yw-lg hover:bg-error/20 transition-colors"
            >
              <X size={12} />
              Reject
            </button>
            <button
              onClick={() => onApproveEdit?.(pendingEdit!.request_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 typo-small-strong bg-success/10 text-success rounded-yw-lg hover:bg-success/20 transition-colors"
            >
              <Check size={12} />
              Accept
            </button>
          </div>
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 dark-scrollbar">
        {filePath ? (
          <MonacoEditor
            height="100%"
            language={getLanguage(filePath)}
            value={content}
            onChange={onChange}
            onMount={handleEditorMount}
            options={{
              fontSize: 14,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontLigatures: true,
              minimap: { enabled: false },
              lineNumbers: 'on',
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              renderWhitespace: 'selection',
              tabSize: 2,
              automaticLayout: true,
              padding: { top: 10 },
              readOnly: !!pendingEdit,
            }}
            theme="aura-dark"
          />
        ) : (
          <div className="h-full flex items-center justify-center bg-editor-bg">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-editor-surface flex items-center justify-center">
                <FileCode size={32} className="text-editor-muted" />
              </div>
              <p className="typo-large text-editor-text mb-1">No file selected</p>
              <p className="typo-small text-editor-muted">Open a project to start editing</p>
            </div>
          </div>
        )}
      </div>

      {/* CSS for decorations */}
      <style jsx global>{`
        .pending-edit-remove-inline {
          background-color: rgba(243, 139, 168, 0.25) !important;
          border-radius: 2px;
        }
        .pending-edit-remove-glyph {
          background-color: #f38ba8;
          width: 4px !important;
          margin-left: 3px;
        }
        .pending-edit-remove-text {
          text-decoration: line-through;
          text-decoration-color: #f38ba8;
          opacity: 0.8;
        }
      `}</style>
    </div>
  );
}
