'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  X,
  Plus,
  Trash2,
  Edit2,
  Book,
  Quote,
  ListChecks,
  FileText,
  AlertTriangle,
  Check,
  BookOpen,
} from 'lucide-react';
import {
  api,
  MemoryData,
  MemoryEntryType,
  PaperEntry,
  CitationEntry,
  ConventionEntry,
  TodoEntry,
  NoteEntry,
} from '@/lib/api';

interface MemoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectPath: string | null;
}

type TabType = 'papers' | 'citations' | 'conventions' | 'todos' | 'notes';

const TABS: { id: TabType; label: string; icon: React.ReactNode }[] = [
  { id: 'papers', label: 'Papers', icon: <Book size={14} /> },
  { id: 'citations', label: 'Citations', icon: <Quote size={14} /> },
  { id: 'conventions', label: 'Conventions', icon: <BookOpen size={14} /> },
  { id: 'todos', label: 'Todos', icon: <ListChecks size={14} /> },
  { id: 'notes', label: 'Notes', icon: <FileText size={14} /> },
];

export default function MemoryModal({
  isOpen,
  onClose,
  projectPath,
}: MemoryModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('papers');
  const [memory, setMemory] = useState<MemoryData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state for adding/editing
  const [formData, setFormData] = useState<Record<string, string>>({});

  const loadMemory = useCallback(async () => {
    if (!projectPath) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.getMemory(projectPath);
      setMemory(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load memory');
    } finally {
      setIsLoading(false);
    }
  }, [projectPath]);

  // Load memory on open
  useEffect(() => {
    if (isOpen && projectPath) {
      loadMemory();
    }
  }, [isOpen, projectPath, loadMemory]);

  const handleAdd = async () => {
    if (!projectPath) return;

    try {
      switch (activeTab) {
        case 'papers':
          await api.addPaper(projectPath, {
            title: formData.title || '',
            authors: (formData.authors || '').split(',').map(a => a.trim()).filter(Boolean),
            arxiv_id: formData.arxiv_id || '',
            summary: formData.summary || '',
            tags: (formData.tags || '').split(',').map(t => t.trim()).filter(Boolean),
          });
          break;
        case 'citations':
          await api.addCitation(projectPath, {
            bibtex_key: formData.bibtex_key || '',
            reason: formData.reason || '',
          });
          break;
        case 'conventions':
          await api.addConvention(projectPath, {
            rule: formData.rule || '',
            example: formData.example || '',
          });
          break;
        case 'todos':
          await api.addTodo(projectPath, {
            task: formData.task || '',
            priority: formData.priority || 'medium',
          });
          break;
        case 'notes':
          await api.addNote(projectPath, {
            content: formData.content || '',
            tags: (formData.tags || '').split(',').map(t => t.trim()).filter(Boolean),
          });
          break;
      }

      setFormData({});
      setIsAdding(false);
      loadMemory();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add entry');
    }
  };

  const handleDelete = async (entryType: MemoryEntryType, entryId: string) => {
    if (!projectPath) return;

    try {
      await api.deleteMemoryEntry(projectPath, entryType, entryId);
      loadMemory();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete entry');
    }
  };

  const handleClearAll = async () => {
    if (!projectPath) return;

    const confirmed = window.confirm(
      'Are you sure you want to clear ALL memory entries? This cannot be undone.'
    );
    if (!confirmed) return;

    try {
      await api.clearMemory(projectPath);
      loadMemory();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to clear memory');
    }
  };

  const handleUpdate = async (entryType: MemoryEntryType, entryId: string) => {
    if (!projectPath) return;

    try {
      let data: Record<string, unknown> = {};

      switch (entryType) {
        case 'papers':
          data = {
            title: formData.title || '',
            authors: (formData.authors || '').split(',').map(a => a.trim()).filter(Boolean),
            arxiv_id: formData.arxiv_id || '',
            summary: formData.summary || '',
            tags: (formData.tags || '').split(',').map(t => t.trim()).filter(Boolean),
          };
          break;
        case 'citations':
          data = {
            bibtex_key: formData.bibtex_key || '',
            reason: formData.reason || '',
          };
          break;
        case 'conventions':
          data = {
            rule: formData.rule || '',
            example: formData.example || '',
          };
          break;
        case 'todos':
          data = {
            task: formData.task || '',
            priority: formData.priority || 'medium',
            status: formData.status || 'pending',
          };
          break;
        case 'notes':
          data = {
            content: formData.content || '',
            tags: (formData.tags || '').split(',').map(t => t.trim()).filter(Boolean),
          };
          break;
      }

      await api.updateMemoryEntry(projectPath, entryType, entryId, data);
      setFormData({});
      setEditingId(null);
      loadMemory();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update entry');
    }
  };

  const startEdit = (entry: PaperEntry | CitationEntry | ConventionEntry | TodoEntry | NoteEntry) => {
    setEditingId(entry.id as string);
    const data: Record<string, string> = {};

    Object.entries(entry).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        data[key] = value.join(', ');
      } else if (typeof value === 'string') {
        data[key] = value;
      }
    });

    setFormData(data);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setIsAdding(false);
    setFormData({});
  };

  const renderEntryCard = (
    entry: PaperEntry | CitationEntry | ConventionEntry | TodoEntry | NoteEntry,
    entryType: MemoryEntryType
  ) => {
    const isEditing = editingId === entry.id;

    if (isEditing) {
      return renderForm(entryType, true, entry.id as string);
    }

    return (
      <div
        key={entry.id as string}
        className="p-3 bg-black/5 rounded-yw-lg border border-black/8"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            {entryType === 'papers' && (
              <>
                <div className="typo-body-strong truncate">{(entry as PaperEntry).title}</div>
                <div className="typo-small text-secondary">
                  {(entry as PaperEntry).authors.join(', ')}
                  {(entry as PaperEntry).arxiv_id && ` • ${(entry as PaperEntry).arxiv_id}`}
                </div>
                {(entry as PaperEntry).summary && (
                  <div className="typo-small text-tertiary mt-1 line-clamp-2">
                    {(entry as PaperEntry).summary}
                  </div>
                )}
                {(entry as PaperEntry).tags.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {(entry as PaperEntry).tags.map(tag => (
                      <span key={tag} className="px-1.5 py-0.5 bg-green1/10 text-green2 rounded typo-ex-small">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </>
            )}

            {entryType === 'citations' && (
              <>
                <div className="typo-body-strong font-mono">{(entry as CitationEntry).bibtex_key}</div>
                <div className="typo-small text-secondary mt-1">{(entry as CitationEntry).reason}</div>
              </>
            )}

            {entryType === 'conventions' && (
              <>
                <div className="typo-body">{(entry as ConventionEntry).rule}</div>
                {(entry as ConventionEntry).example && (
                  <div className="typo-small text-tertiary mt-1 font-mono">
                    e.g., {(entry as ConventionEntry).example}
                  </div>
                )}
              </>
            )}

            {entryType === 'todos' && (
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded typo-ex-small ${
                  (entry as TodoEntry).priority === 'high' ? 'bg-error/10 text-error' :
                  (entry as TodoEntry).priority === 'medium' ? 'bg-warn/10 text-warn' :
                  'bg-black/5 text-tertiary'
                }`}>
                  {(entry as TodoEntry).priority.toUpperCase()}
                </span>
                <span className={`typo-body ${(entry as TodoEntry).status === 'completed' ? 'line-through text-tertiary' : ''}`}>
                  {(entry as TodoEntry).task}
                </span>
                <span className="typo-ex-small text-tertiary">({(entry as TodoEntry).status})</span>
              </div>
            )}

            {entryType === 'notes' && (
              <>
                <div className="typo-body line-clamp-4 whitespace-pre-wrap break-words">
                  {(entry as NoteEntry).content}
                </div>
                {(entry as NoteEntry).content.length > 300 && (
                  <div className="typo-ex-small text-tertiary mt-1">
                    ({(entry as NoteEntry).content.length} characters)
                  </div>
                )}
                {(entry as NoteEntry).tags.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {(entry as NoteEntry).tags.map(tag => (
                      <span key={tag} className="text-green2 typo-small">#{tag}</span>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="flex gap-1 flex-shrink-0">
            <button
              onClick={() => startEdit(entry)}
              className="p-1.5 hover:bg-black/5 rounded-yw-sm"
              title="Edit"
            >
              <Edit2 size={14} className="text-secondary" />
            </button>
            <button
              onClick={() => handleDelete(entryType, entry.id as string)}
              className="p-1.5 hover:bg-error/10 rounded-yw-sm"
              title="Delete"
            >
              <Trash2 size={14} className="text-error" />
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderForm = (entryType: TabType, isEdit = false, entryId?: string) => {
    return (
      <div className="p-3 bg-black/3 rounded-yw-lg space-y-3">
        {entryType === 'papers' && (
          <>
            <input
              type="text"
              placeholder="Paper title"
              value={formData.title || ''}
              onChange={e => setFormData({ ...formData, title: e.target.value })}
              className="input-field w-full"
            />
            <input
              type="text"
              placeholder="Authors (comma-separated)"
              value={formData.authors || ''}
              onChange={e => setFormData({ ...formData, authors: e.target.value })}
              className="input-field w-full"
            />
            <input
              type="text"
              placeholder="arXiv ID (optional)"
              value={formData.arxiv_id || ''}
              onChange={e => setFormData({ ...formData, arxiv_id: e.target.value })}
              className="input-field w-full"
            />
            <textarea
              placeholder="Summary (optional)"
              value={formData.summary || ''}
              onChange={e => setFormData({ ...formData, summary: e.target.value })}
              className="input-field w-full h-20 resize-none"
            />
            <input
              type="text"
              placeholder="Tags (comma-separated)"
              value={formData.tags || ''}
              onChange={e => setFormData({ ...formData, tags: e.target.value })}
              className="input-field w-full"
            />
          </>
        )}

        {entryType === 'citations' && (
          <>
            <input
              type="text"
              placeholder="BibTeX key (e.g., vaswani2017attention)"
              value={formData.bibtex_key || ''}
              onChange={e => setFormData({ ...formData, bibtex_key: e.target.value })}
              className="input-field w-full font-mono"
            />
            <textarea
              placeholder="Why is this cited?"
              value={formData.reason || ''}
              onChange={e => setFormData({ ...formData, reason: e.target.value })}
              className="input-field w-full h-20 resize-none"
            />
          </>
        )}

        {entryType === 'conventions' && (
          <>
            <input
              type="text"
              placeholder="Rule (e.g., Use \\cref{} instead of \\ref{})"
              value={formData.rule || ''}
              onChange={e => setFormData({ ...formData, rule: e.target.value })}
              className="input-field w-full"
            />
            <input
              type="text"
              placeholder="Example (optional)"
              value={formData.example || ''}
              onChange={e => setFormData({ ...formData, example: e.target.value })}
              className="input-field w-full font-mono"
            />
          </>
        )}

        {entryType === 'todos' && (
          <>
            <input
              type="text"
              placeholder="Task description"
              value={formData.task || ''}
              onChange={e => setFormData({ ...formData, task: e.target.value })}
              className="input-field w-full"
            />
            <div className="flex gap-2">
              <select
                value={formData.priority || 'medium'}
                onChange={e => setFormData({ ...formData, priority: e.target.value })}
                className="input-field"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
              {isEdit && (
                <select
                  value={formData.status || 'pending'}
                  onChange={e => setFormData({ ...formData, status: e.target.value })}
                  className="input-field"
                >
                  <option value="pending">Pending</option>
                  <option value="in_progress">In Progress</option>
                  <option value="completed">Completed</option>
                </select>
              )}
            </div>
          </>
        )}

        {entryType === 'notes' && (
          <>
            <textarea
              placeholder="Note content"
              value={formData.content || ''}
              onChange={e => setFormData({ ...formData, content: e.target.value })}
              className="input-field w-full h-24 resize-none"
            />
            <input
              type="text"
              placeholder="Tags (comma-separated)"
              value={formData.tags || ''}
              onChange={e => setFormData({ ...formData, tags: e.target.value })}
              className="input-field w-full"
            />
          </>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={cancelEdit} className="btn-ghost">
            Cancel
          </button>
          <button
            onClick={() => isEdit && entryId ? handleUpdate(entryType, entryId) : handleAdd()}
            className="btn-primary"
          >
            <Check size={14} />
            {isEdit ? 'Save' : 'Add'}
          </button>
        </div>
      </div>
    );
  };

  if (!isOpen) return null;

  const entries = memory?.entries[activeTab] || [];
  const tokenCount = memory?.stats.token_count || 0;
  const tokenWarning = memory?.stats.warning || false;
  const tokenThreshold = memory?.stats.threshold || 4000;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-2xl max-h-[80vh] bg-white rounded-yw-2xl shadow-xl flex flex-col animate-fadeInUp">
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-black/6">
          <h2 className="typo-h2">Project Memory</h2>
          <button onClick={onClose} className="btn-icon">
            <X size={18} className="text-secondary" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex-shrink-0 flex gap-1 px-6 py-3 border-b border-black/6 overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setIsAdding(false);
                setEditingId(null);
                setFormData({});
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full typo-small transition-colors ${
                activeTab === tab.id
                  ? 'bg-green1 text-white'
                  : 'hover:bg-black/5 text-secondary'
              }`}
            >
              {tab.icon}
              {tab.label}
              {memory && (
                <span className={`ml-1 ${activeTab === tab.id ? 'text-white/70' : 'text-tertiary'}`}>
                  ({memory.entries[tab.id].length})
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 p-3 bg-error/10 rounded-yw-lg typo-small text-error">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="text-center py-8 text-tertiary">Loading...</div>
          ) : (
            <div className="space-y-3">
              {entries.map(entry => renderEntryCard(entry, activeTab))}

              {isAdding ? (
                renderForm(activeTab)
              ) : (
                <button
                  onClick={() => setIsAdding(true)}
                  className="w-full p-3 border-2 border-dashed border-black/10 rounded-yw-lg text-secondary hover:border-green1 hover:text-green1 transition-colors flex items-center justify-center gap-2"
                >
                  <Plus size={16} />
                  Add {activeTab.slice(0, -1)}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Footer with token counter */}
        <div className="flex-shrink-0 px-6 py-3 border-t border-black/6 flex items-center justify-between">
          <div className={`flex items-center gap-2 typo-small ${tokenWarning ? 'text-warn' : 'text-tertiary'}`}>
            {tokenWarning && <AlertTriangle size={14} />}
            Memory size: {tokenCount.toLocaleString()} / {tokenThreshold.toLocaleString()} tokens
          </div>
          <div className="flex gap-2">
            {tokenCount > 0 && (
              <button
                onClick={handleClearAll}
                className="btn-ghost text-error hover:bg-error/10"
                title="Clear all memory entries"
              >
                <Trash2 size={14} />
                Clear All
              </button>
            )}
            <button onClick={onClose} className="btn-ghost">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
