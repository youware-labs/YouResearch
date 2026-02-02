'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import {
  Send,
  User,
  Loader2,
  Code,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Sparkles,
  Square,
  MessageSquare,
  Microscope,
  BookOpen,
  Plus,
  X,
  Check,
  FileCode,
  Trash2,
  ExternalLink,
  GraduationCap,
  BookMarked,
  FileText,
} from 'lucide-react';
import { PendingEdit, SendToAgentContext } from './Editor';
import PlanDisplay, { Plan, PlanStep } from './PlanDisplay';
import VibeResearchView from './VibeResearchView';
import CitationVerifierPanel from './CitationVerifierPanel';
import CommandPalette from './CommandPalette';
import TaskList, { Task } from './TaskList';
import { api, VibeSessionSummary, ChatSession } from '../lib/api';
import VenuePreferenceModal from './VenuePreferenceModal';
import DomainPreferenceModal from './DomainPreferenceModal';
import {
  filterCommands,
  parseCommandInput,
  findCommand,
  SlashCommand,
} from '../lib/commands';
import {
  ProviderSettings,
  DASHSCOPE_MODELS,
  getProviderSettings,
  saveProviderSettings,
  getProviderConfigForRequest,
} from '../lib/providerSettings';
import ModelSelector from './ModelSelector';

// Mode types
type AgentMode = 'chat' | 'vibe' | 'verifier';

interface AgentPanelProps {
  projectPath: string | null;
  onApprovalRequest?: (edit: PendingEdit) => void;
  onApprovalResolved?: () => void;
  onOpenFile?: (filePath: string) => void;
  quotedContext?: SendToAgentContext | null;
  onClearQuote?: () => void;
}

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'running' | 'success' | 'error' | 'waiting_approval';
  request_id?: string;  // HITL approval request ID
}

interface MessagePart {
  type: 'text' | 'tool' | 'taskList';
  content?: string;
  toolCall?: ToolCall;
  taskList?: {
    mainTask: string;
    tasks: Task[];
    planId?: string;
  };
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  parts: MessagePart[];
  timestamp: Date;
}

// Tool call display component
function ToolCallDisplay({
  toolCall,
  onApprove,
  onReject,
}: {
  toolCall: ToolCall;
  onApprove?: (requestId: string) => void;
  onReject?: (requestId: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const statusIcon = {
    pending: <Loader2 size={14} className="text-tertiary" />,
    running: <Loader2 size={14} className="text-green2 animate-spin" />,
    waiting_approval: <AlertCircle size={14} className="text-orange1" />,
    success: <CheckCircle size={14} className="text-success" />,
    error: <XCircle size={14} className="text-error" />,
  }[toolCall.status];

  const statusLabel = {
    pending: '',
    running: '',
    waiting_approval: 'awaiting approval',
    success: '',
    error: '',
  }[toolCall.status];

  const needsApproval = (toolCall.name === 'write_file' || toolCall.name === 'edit_file') && toolCall.status === 'waiting_approval';

  return (
    <div className="bg-fill-secondary rounded-yw-lg p-2.5 my-2 border border-black/6">
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-tertiary" />
        ) : (
          <ChevronRight size={14} className="text-tertiary" />
        )}
        <Code size={14} className="text-green2" />
        <span className="typo-small-strong text-green1">{toolCall.name}</span>
        {statusLabel && (
          <span className="badge badge-warning typo-ex-small">{statusLabel}</span>
        )}
        <span className="flex-1" />
        {statusIcon}
      </div>

      {isExpanded && (
        <div className="mt-3 space-y-2">
          <div>
            <div className="typo-ex-small text-tertiary mb-1">Arguments</div>
            <pre className="bg-white p-2.5 rounded-yw-md text-xs overflow-x-auto border border-black/6 font-mono">
              {JSON.stringify(toolCall.args, null, 2)}</pre>
          </div>

          {toolCall.result && (
            <div>
              <div className="typo-ex-small text-tertiary mb-1">Result</div>
              <pre className="bg-white p-2.5 rounded-yw-md text-xs overflow-x-auto max-h-32 overflow-y-auto border border-black/6 font-mono">
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Approval buttons for file edits and new file creation */}
      {needsApproval && toolCall.request_id && onApprove && onReject && (
        <div className="mt-3 flex items-center gap-2 pt-2 border-t border-black/6">
          <button
            onClick={(e) => { e.stopPropagation(); onReject(toolCall.request_id!); }}
            className="flex items-center gap-1.5 px-3 py-1.5 typo-small-strong bg-error/10 text-error rounded-yw-lg hover:bg-error/20 transition-colors"
          >
            <X size={12} />
            Reject
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onApprove(toolCall.request_id!); }}
            className="flex items-center gap-1.5 px-3 py-1.5 typo-small-strong bg-success/10 text-success rounded-yw-lg hover:bg-success/20 transition-colors"
          >
            <Check size={12} />
            Accept
          </button>
        </div>
      )}
    </div>
  );
}

// Academic paper link detection and styling
interface AcademicSource {
  name: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
}

function getAcademicSource(url: string): AcademicSource | null {
  const urlLower = url.toLowerCase();

  if (urlLower.includes('arxiv.org')) {
    return {
      name: 'arXiv',
      icon: <FileText className="w-3.5 h-3.5" />,
      color: 'text-red-600',
      bgColor: 'bg-red-50 border-red-200 hover:bg-red-100',
    };
  }
  if (urlLower.includes('ieeexplore.ieee.org') || urlLower.includes('ieee.org')) {
    return {
      name: 'IEEE',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 border-blue-200 hover:bg-blue-100',
    };
  }
  if (urlLower.includes('springer.com') || urlLower.includes('link.springer')) {
    return {
      name: 'Springer',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-blue-700',
      bgColor: 'bg-sky-50 border-sky-200 hover:bg-sky-100',
    };
  }
  if (urlLower.includes('acm.org') || urlLower.includes('dl.acm.org')) {
    return {
      name: 'ACM',
      icon: <GraduationCap className="w-3.5 h-3.5" />,
      color: 'text-green-700',
      bgColor: 'bg-green-50 border-green-200 hover:bg-green-100',
    };
  }
  if (urlLower.includes('scholar.google')) {
    return {
      name: 'Scholar',
      icon: <GraduationCap className="w-3.5 h-3.5" />,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 border-blue-200 hover:bg-blue-100',
    };
  }
  if (urlLower.includes('semanticscholar.org')) {
    return {
      name: 'S2',
      icon: <GraduationCap className="w-3.5 h-3.5" />,
      color: 'text-yellow-700',
      bgColor: 'bg-yellow-50 border-yellow-200 hover:bg-yellow-100',
    };
  }
  if (urlLower.includes('pubmed') || urlLower.includes('ncbi.nlm.nih.gov')) {
    return {
      name: 'PubMed',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-teal-600',
      bgColor: 'bg-teal-50 border-teal-200 hover:bg-teal-100',
    };
  }
  if (urlLower.includes('nature.com')) {
    return {
      name: 'Nature',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-red-700',
      bgColor: 'bg-red-50 border-red-200 hover:bg-red-100',
    };
  }
  if (urlLower.includes('sciencedirect.com') || urlLower.includes('elsevier.com')) {
    return {
      name: 'Elsevier',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50 border-orange-200 hover:bg-orange-100',
    };
  }
  if (urlLower.includes('nowpublishers.com')) {
    return {
      name: 'Now Pub',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50 border-purple-200 hover:bg-purple-100',
    };
  }
  if (urlLower.includes('wiley.com') || urlLower.includes('onlinelibrary.wiley')) {
    return {
      name: 'Wiley',
      icon: <BookMarked className="w-3.5 h-3.5" />,
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-50 border-indigo-200 hover:bg-indigo-100',
    };
  }
  if (urlLower.includes('openreview.net')) {
    return {
      name: 'OpenReview',
      icon: <FileText className="w-3.5 h-3.5" />,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50 border-purple-200 hover:bg-purple-100',
    };
  }
  if (urlLower.includes('proceedings.neurips.cc') || urlLower.includes('neurips.cc')) {
    return {
      name: 'NeurIPS',
      icon: <GraduationCap className="w-3.5 h-3.5" />,
      color: 'text-violet-600',
      bgColor: 'bg-violet-50 border-violet-200 hover:bg-violet-100',
    };
  }
  if (urlLower.includes('proceedings.mlr.press') || urlLower.includes('mlr.press')) {
    return {
      name: 'PMLR',
      icon: <GraduationCap className="w-3.5 h-3.5" />,
      color: 'text-pink-600',
      bgColor: 'bg-pink-50 border-pink-200 hover:bg-pink-100',
    };
  }

  return null;
}

function extractPaperId(url: string): string {
  // Extract meaningful ID from URL, keep it short
  if (url.includes('arxiv.org')) {
    const match = url.match(/(\d{4}\.\d{4,5})/);
    return match ? match[1] : '';
  }
  if (url.includes('doi.org')) {
    const match = url.match(/doi\.org\/(.+)$/);
    if (match) {
      const doi = match[1];
      return doi.length > 15 ? doi.substring(0, 12) + '...' : doi;
    }
    return '';
  }
  // For other URLs, extract last path segment and truncate
  const parts = url.split('/').filter(p => p && p !== 'abstract' && p !== 'document' && p !== 'pdf');
  const lastPart = parts[parts.length - 1] || '';
  return lastPart.length > 12 ? lastPart.substring(0, 10) + '...' : lastPart;
}

// Paper link component with nice styling - opens in system browser
function PaperLinkDisplay({ href, children }: { href: string; children: React.ReactNode }) {
  const source = getAcademicSource(href);
  const childText = typeof children === 'string' ? children : '';
  const isUrlAsText = childText.startsWith('http');

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    // Open in system default browser via Electron
    if (typeof window !== 'undefined' && window.aura?.openExternal) {
      window.aura.openExternal(href);
    } else {
      // Fallback for non-Electron (web browser)
      window.open(href, '_blank', 'noopener,noreferrer');
    }
  };

  if (source) {
    const paperId = extractPaperId(href);
    return (
      <button
        onClick={handleClick}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${source.bgColor} ${source.color}`}
        title={href}
      >
        {source.icon}
        <span>{source.name}</span>
        {paperId && <span className="opacity-60 max-w-[80px] truncate">· {paperId}</span>}
        <ExternalLink className="w-3 h-3 opacity-50 flex-shrink-0" />
      </button>
    );
  }

  // Non-academic links - if the text is just a URL, truncate it nicely
  if (isUrlAsText && href.length > 50) {
    try {
      const domain = new URL(href).hostname.replace('www.', '');
      return (
        <button
          onClick={handleClick}
          className="inline-flex items-center gap-1 text-green1 hover:text-green2 underline underline-offset-2 cursor-pointer"
          title={href}
        >
          <span>{domain}</span>
          <ExternalLink className="w-3 h-3" />
        </button>
      );
    } catch {
      // Invalid URL, fall through to regular link
    }
  }

  // Regular link
  return (
    <button
      onClick={handleClick}
      className="text-green1 underline underline-offset-2 hover:text-green2 cursor-pointer"
    >
      {children}
    </button>
  );
}

// Text part display with LaTeX support
function TextPartDisplay({ content }: { content: string }) {
  if (!content.trim()) return null;

  // Convert plain URLs to markdown links (but not already-linked URLs)
  const processedContent = content.replace(
    /(?<!\[.*?\]\()(?<!\()(https?:\/\/[^\s\)]+)/g,
    '[$1]($1)'
  );

  return (
    <div className="typo-body prose prose-sm max-w-none prose-headings:text-primary prose-p:text-primary prose-strong:text-primary prose-code:text-green1 prose-code:bg-green3/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-fill-secondary prose-pre:border prose-pre:border-black/6 prose-ul:text-primary prose-ol:text-primary prose-li:text-primary prose-table:w-full prose-th:bg-fill-secondary prose-th:border prose-th:border-black/12 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-td:border prose-td:border-black/12 prose-td:px-3 prose-td:py-2 prose-a:text-green1 prose-a:underline prose-a:underline-offset-2 hover:prose-a:text-green2 my-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children }) => {
            if (!href) return <span>{children}</span>;
            return <PaperLinkDisplay href={href}>{children}</PaperLinkDisplay>;
          },
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}

// Message display component
function MessageDisplay({
  message,
  onApprove,
  onReject,
}: {
  message: Message;
  onApprove?: (requestId: string) => void;
  onReject?: (requestId: string) => void;
}) {
  const isUser = message.role === 'user';

  return (
    <div
      className={`
        rounded-yw-xl p-3 animate-fade-in-up
        ${isUser
          ? 'bg-green3/50 border border-green2/20 ml-8'
          : 'bg-white border border-black/6'
        }
      `}
    >
      <div className="flex items-start gap-2.5">
        <div
          className={`
            w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0
            ${isUser ? 'bg-green2' : 'bg-green3'}
          `}
        >
          {isUser ? (
            <User size={14} className="text-white" />
          ) : (
            <Sparkles size={14} className="text-green1" />
          )}
        </div>
        <div className="flex-1 min-w-0 pt-0.5">
          {isUser ? (
            <div className="typo-body whitespace-pre-wrap break-words">
              {message.parts[0]?.content || ''}
            </div>
          ) : (
            <div className="space-y-1">
              {message.parts.map((part, index) => (
                part.type === 'text' ? (
                  <TextPartDisplay key={index} content={part.content || ''} />
                ) : part.type === 'taskList' && part.taskList ? (
                  <TaskList
                    key={index}
                    mainTask={part.taskList.mainTask}
                    tasks={part.taskList.tasks}
                  />
                ) : part.toolCall ? (
                  <ToolCallDisplay
                    key={index}
                    toolCall={part.toolCall}
                    onApprove={onApprove}
                    onReject={onReject}
                  />
                ) : null
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentPanel({
  projectPath,
  onApprovalRequest,
  onApprovalResolved,
  onOpenFile,
  quotedContext,
  onClearQuote,
}: AgentPanelProps) {
  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [currentPlan, setCurrentPlan] = useState<Plan | null>(null);
  const [domainPreferenceModal, setDomainPreferenceModal] = useState<{
    isOpen: boolean;
    requestId: string;
    topic: string;
    suggestedDomain: string;
  }>({ isOpen: false, requestId: '', topic: '', suggestedDomain: '' });
  const [venuePreferenceModal, setVenuePreferenceModal] = useState<{
    isOpen: boolean;
    requestId: string;
    topic: string;
    domain: string;
    suggestedVenues: string[];
  }>({ isOpen: false, requestId: '', topic: '', domain: '', suggestedVenues: [] });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingMessageRef = useRef<string | null>(null);

  // Mode state
  const [mode, setMode] = useState<AgentMode>('chat');
  const [vibeSessions, setVibeSessions] = useState<VibeSessionSummary[]>([]);
  const [selectedVibeSession, setSelectedVibeSession] = useState<string | null>(null);

  // Provider settings state
  const [providerSettings, setProviderSettings] = useState<ProviderSettings>({ provider: 'openrouter' });

  // Chat session state
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [selectedChatSession, setSelectedChatSession] = useState<string | null>(null);
  const [isLoadingChatSessions, setIsLoadingChatSessions] = useState(false);

  // Command palette state
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [showNewResearchInput, setShowNewResearchInput] = useState(false);
  const [newResearchTopic, setNewResearchTopic] = useState('');
  const [isStartingResearch, setIsStartingResearch] = useState(false);

  // Handle quoted text from Editor
  useEffect(() => {
    if (quotedContext) {
      // Set the input based on the action
      if (quotedContext.action === 'polish') {
        setInput('/polish ');
      } else {
        setInput('');
      }
      // Focus the input
      inputRef.current?.focus();
    }
  }, [quotedContext]);

  // Helper to truncate text to first N words
  const truncateToWords = (text: string, wordCount: number): string => {
    if (!text || typeof text !== 'string') return '';
    const words = text.trim().split(/\s+/);
    if (words.length <= wordCount) return text.trim();
    return words.slice(0, wordCount).join(' ') + '...';
  };

  const loadVibeSessions = useCallback(async () => {
    if (!projectPath) return;
    setIsLoadingSessions(true);
    try {
      const result = await api.listVibeSessions(projectPath);
      setVibeSessions(result.sessions);
      // Auto-select first incomplete session if none selected
      if (result.sessions.length > 0) {
        const incomplete = result.sessions.find(s => !s.is_complete);
        if (incomplete) {
          setSelectedVibeSession(incomplete.session_id);
        }
      }
    } catch (e) {
      console.error('Failed to load vibe sessions:', e);
    } finally {
      setIsLoadingSessions(false);
    }
  }, [projectPath]);

  // Load vibe sessions when mode changes or project changes
  useEffect(() => {
    if (mode === 'vibe' && projectPath) {
      loadVibeSessions();
    }
  }, [mode, projectPath, loadVibeSessions]);

  // Load provider settings on mount
  useEffect(() => {
    setProviderSettings(getProviderSettings());
  }, []);

  // Listen for storage changes (when SettingsModal updates provider settings)
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'aura_provider_settings') {
        setProviderSettings(getProviderSettings());
      }
    };

    // Also listen for custom event (for same-tab updates)
    const handleProviderChange = () => {
      setProviderSettings(getProviderSettings());
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('aura-provider-changed', handleProviderChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('aura-provider-changed', handleProviderChange);
    };
  }, []);

  // Handle model change from ModelSelector
  const handleModelSelectorChange = useCallback((modelId: string) => {
    const newSettings: ProviderSettings = {
      ...providerSettings,
      dashscope: {
        ...providerSettings.dashscope,
        apiKey: providerSettings.dashscope?.apiKey || '',
        selectedModel: modelId,
      },
    };
    setProviderSettings(newSettings);
    saveProviderSettings(newSettings);
  }, [providerSettings]);

  // Load chat sessions
  const loadChatSessions = useCallback(async (autoSelect: boolean = false) => {
    if (!projectPath) return;
    setIsLoadingChatSessions(true);
    try {
      const result = await api.listChatSessions(projectPath);
      setChatSessions(result.sessions);
      // Auto-select the most recent session if requested
      if (autoSelect && result.sessions.length > 0) {
        setSelectedChatSession(result.sessions[0].session_id);
        // Load messages for the auto-selected session
        try {
          const session = await api.getChatSession(projectPath, result.sessions[0].session_id);
          const uiMessages: Message[] = session.messages.map((msg, index) => ({
            id: `loaded-${index}`,
            role: msg.role,
            parts: [{ type: 'text', content: msg.content }],
            timestamp: new Date(),
          }));
          setMessages(uiMessages);
        } catch (e) {
          console.error('Failed to load auto-selected session:', e);
        }
      }
    } catch (e) {
      console.error('Failed to load chat sessions:', e);
    } finally {
      setIsLoadingChatSessions(false);
    }
  }, [projectPath]);

  // Reset chat state when project changes
  useEffect(() => {
    setSelectedChatSession(null);
    setMessages([]);
    setChatSessions([]);
    setCurrentPlan(null);
  }, [projectPath]);

  // Load chat sessions when entering a project in chat mode
  useEffect(() => {
    if (mode === 'chat' && projectPath) {
      // Load existing sessions instead of creating a new one immediately
      // A new session will be created when the user sends their first message
      loadChatSessions(true);
    }
  }, [mode, projectPath, loadChatSessions]);

  // Handle chat session change - load messages for selected session
  const handleChatSessionChange = useCallback(async (sessionId: string | null) => {
    setSelectedChatSession(sessionId);
    if (!sessionId || !projectPath) {
      setMessages([]);
      return;
    }

    try {
      const session = await api.getChatSession(projectPath, sessionId);
      // Convert stored messages to UI format
      const uiMessages: Message[] = session.messages.map((msg, index) => ({
        id: `loaded-${index}`,
        role: msg.role,
        parts: [{ type: 'text', content: msg.content }],
        timestamp: new Date(),
      }));
      setMessages(uiMessages);
    } catch (e) {
      console.error('Failed to load chat session:', e);
      setMessages([]);
    }
  }, [projectPath]);

  // Create new chat session
  const createNewChatSession = useCallback(async () => {
    if (!projectPath) return;

    try {
      const session = await api.createChatSession(projectPath);
      setSelectedChatSession(session.session_id);
      setMessages([]);
      setCurrentPlan(null);
      // Refresh the session list without auto-selecting (we already selected the new one)
      await loadChatSessions(false);
    } catch (e) {
      console.error('Failed to create chat session:', e);
    }
  }, [projectPath, loadChatSessions]);

  // Delete current chat session
  const deleteCurrentChatSession = useCallback(async () => {
    if (!projectPath || !selectedChatSession) return;

    try {
      await api.deleteChatSession(projectPath, selectedChatSession);
      setSelectedChatSession(null);
      setMessages([]);
      setCurrentPlan(null);
      // Refresh the session list without auto-selecting
      await loadChatSessions(false);
    } catch (e) {
      console.error('Failed to delete chat session:', e);
    }
  }, [projectPath, selectedChatSession, loadChatSessions]);

  // HITL approval handlers for new file creation
  const handleApproveToolCall = useCallback(async (requestId: string) => {
    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId }),
      });

      // Update the tool call status to success
      setMessages(prev => prev.map(msg => ({
        ...msg,
        parts: msg.parts.map(part => {
          if (part.toolCall && part.toolCall.request_id === requestId) {
            return { ...part, toolCall: { ...part.toolCall, status: 'success' as const } };
          }
          return part;
        }),
      })));

      onApprovalResolved?.();
    } catch (error) {
      console.error('Failed to approve:', error);
    }
  }, [onApprovalResolved]);

  const handleRejectToolCall = useCallback(async (requestId: string) => {
    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      await fetch(`${backendUrl}/api/hitl/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId }),
      });

      // Update the tool call status to error
      setMessages(prev => prev.map(msg => ({
        ...msg,
        parts: msg.parts.map(part => {
          if (part.toolCall && part.toolCall.request_id === requestId) {
            return { ...part, toolCall: { ...part.toolCall, status: 'error' as const, result: 'Rejected by user' } };
          }
          return part;
        }),
      })));

      onApprovalResolved?.();
    } catch (error) {
      console.error('Failed to reject:', error);
    }
  }, [onApprovalResolved]);

  const startNewResearch = async () => {
    if (!projectPath || !newResearchTopic.trim()) return;
    setIsStartingResearch(true);
    try {
      const session = await api.startVibeResearch(projectPath, newResearchTopic.trim());
      setSelectedVibeSession(session.session_id);
      setShowNewResearchInput(false);
      setNewResearchTopic('');
      await loadVibeSessions();
    } catch (e) {
      console.error('Failed to start research:', e);
    } finally {
      setIsStartingResearch(false);
    }
  };

  // Keep ref in sync with state for use in callbacks
  useEffect(() => {
    pendingMessageRef.current = pendingMessage;
  }, [pendingMessage]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-scroll to pending message when it changes
  useEffect(() => {
    if (pendingMessage && messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, [pendingMessage]);

  // Reference to sendMessage for use in effect
  const sendMessageRef = useRef<(content?: string) => Promise<void>>();

  // Track previous streaming state to detect when it ends
  const wasStreamingRef = useRef(false);
  useEffect(() => {
    // When streaming ends and there's a pending message, send it
    if (wasStreamingRef.current && !isStreaming && pendingMessageRef.current) {
      const pending = pendingMessageRef.current;
      setPendingMessage(null);
      // Use setTimeout to ensure state updates have propagated
      setTimeout(() => {
        sendMessageRef.current?.(pending);
      }, 100);
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Send message to agent
  const sendMessage = useCallback(async (messageContent?: string, displayContent?: string) => {
    let content = messageContent || input.trim();
    if (!content || isStreaming || !projectPath) return;

    // Display content is what shows in the UI (shorter version for commands)
    const displayMessage = displayContent || content;

    // If no session is selected, create one first
    let sessionId = selectedChatSession;
    if (!sessionId) {
      try {
        const session = await api.createChatSession(projectPath);
        sessionId = session.session_id;
        setSelectedChatSession(sessionId);
        // Refresh session list in background
        loadChatSessions(false);
      } catch (e) {
        console.error('Failed to create chat session:', e);
        return;
      }
    }

    // If there's quoted context, append it to the content with file/line info
    if (quotedContext) {
      const locationInfo = quotedContext.filePath
        ? `[File: ${quotedContext.filePath}, Lines ${quotedContext.startLine}-${quotedContext.endLine}]`
        : '';

      if (quotedContext.action === 'file') {
        content = content + '\n\n[Regarding file: ' + quotedContext.text + ']';
      } else {
        // Include location info and the selected text
        content = locationInfo
          ? content + '\n\n' + locationInfo + '\n```\n' + quotedContext.text + '\n```'
          : content + '\n\n' + quotedContext.text;
      }
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      parts: [{ type: 'text', content: displayMessage }],
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!messageContent) {
      setInput('');
    }
    // Clear the quote after sending
    onClearQuote?.();
    setIsStreaming(true);

    // Create abort controller for this request
    abortControllerRef.current = new AbortController();

    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      parts: [],
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      let backendUrl = 'http://127.0.0.1:8001';
      if (typeof window !== 'undefined' && window.aura) {
        backendUrl = await window.aura.getBackendUrl();
      }

      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: content,
          project_path: projectPath,
          session_id: sessionId,
          history: messages.map((m) => ({
            role: m.role,
            content: m.parts
              .filter((p) => p.type === 'text')
              .map((p) => p.content)
              .join('\n'),
          })),
          provider: getProviderConfigForRequest(providerSettings),
        }),
        signal: abortControllerRef.current?.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) continue;

          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());

              if (data.type === 'text_delta' && data.content) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last.role === 'assistant') {
                    const parts = [...last.parts];
                    const lastPart = parts[parts.length - 1];

                    if (lastPart && lastPart.type === 'text') {
                      parts[parts.length - 1] = {
                        ...lastPart,
                        content: (lastPart.content || '') + data.content,
                      };
                    } else {
                      parts.push({ type: 'text', content: data.content });
                    }

                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });
              } else if (data.type === 'tool_call') {
                const toolCall: ToolCall = {
                  id: data.tool_call_id || crypto.randomUUID(),
                  name: data.tool_name,
                  args: data.args || {},
                  status: 'running',
                };
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last.role === 'assistant') {
                    const parts = [...last.parts, { type: 'tool' as const, toolCall }];
                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });
              } else if (data.type === 'tool_result') {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last.role === 'assistant') {
                    const parts = [...last.parts];
                    let matched = false;

                    // First try to match by tool_call_id (exact match)
                    if (data.tool_call_id) {
                      for (let i = 0; i < parts.length; i++) {
                        const part = parts[i];
                        if (part.type === 'tool' && part.toolCall &&
                            part.toolCall.id === data.tool_call_id) {
                          parts[i] = {
                            ...part,
                            toolCall: { ...part.toolCall, result: data.result, status: 'success' },
                          };
                          matched = true;
                          break;
                        }
                      }
                    }

                    // If no ID match, match by name (iterate forwards to match in order)
                    if (!matched) {
                      for (let i = 0; i < parts.length; i++) {
                        const part = parts[i];
                        if (part.type === 'tool' && part.toolCall) {
                          const tc = part.toolCall;
                          if (tc.name === data.tool_name &&
                              (tc.status === 'running' || tc.status === 'waiting_approval')) {
                            parts[i] = {
                              ...part,
                              toolCall: { ...tc, result: data.result, status: 'success' },
                            };
                            break;
                          }
                        }
                      }
                    }

                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });
              } else if (data.type === 'error') {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last.role === 'assistant') {
                    const parts = [...last.parts];
                    parts.push({
                      type: 'text',
                      content: `\n\n**Error:** ${data.message || 'Unknown error'}`
                    });
                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });
              } else if (data.type === 'approval_required') {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last.role === 'assistant') {
                    const parts = [...last.parts];
                    for (let i = parts.length - 1; i >= 0; i--) {
                      const part = parts[i];
                      if (part.type === 'tool' && part.toolCall &&
                          part.toolCall.name === data.tool_name &&
                          part.toolCall.status === 'running') {
                        parts[i] = {
                          ...part,
                          toolCall: {
                            ...part.toolCall,
                            status: 'waiting_approval',
                            request_id: data.request_id,
                          },
                        };
                        break;
                      }
                    }
                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });

                if (onApprovalRequest && data.tool_name === 'edit_file') {
                  onApprovalRequest({
                    request_id: data.request_id,
                    filepath: data.tool_args?.filepath || '',
                    old_string: data.tool_args?.old_string || '',
                    new_string: data.tool_args?.new_string || '',
                  });
                } else if (onApprovalRequest && data.tool_name === 'write_file') {
                  onApprovalRequest({
                    request_id: data.request_id,
                    filepath: data.tool_args?.filepath || '',
                    old_string: '',
                    new_string: data.tool_args?.content || '',
                  });
                }
              } else if (data.type === 'approval_resolved') {
                onApprovalResolved?.();
              } else if (data.type === 'plan_created') {
                // A new plan was created - add TaskList to current message
                console.log('[Agent] Plan created event:', data);
                const planSteps = (data.steps || []).map((s: { step_number: number; title: string; description?: string; status?: string; files?: string[] }) => ({
                  step_number: s.step_number,
                  title: s.title,
                  description: s.description || '',
                  status: (s.status || 'pending') as PlanStep['status'],
                  files: s.files || [],
                }));

                setCurrentPlan({
                  plan_id: data.plan_id,
                  goal: data.goal,
                  complexity: data.complexity,
                  steps: planSteps,
                });

                // Add TaskList part to current assistant message
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIndex = updated.length - 1;
                  const last = updated[lastIndex];
                  if (last && last.role === 'assistant') {
                    const tasks: Task[] = planSteps.map((s: { step_number: number; title: string; status: string }) => ({
                      id: `step-${s.step_number}`,
                      title: s.title,
                      status: s.status === 'in_progress' ? 'in_progress' : s.status === 'completed' ? 'completed' : 'pending',
                    }));
                    const parts = [...last.parts, {
                      type: 'taskList' as const,
                      taskList: {
                        mainTask: data.goal,
                        tasks,
                        planId: data.plan_id,
                      },
                    }];
                    updated[lastIndex] = { ...last, parts };
                  }
                  return updated;
                });
              } else if (data.type === 'plan_step') {
                // A plan step status changed - update both plan and TaskList
                console.log('[Agent] Plan step event:', data);
                setCurrentPlan((prev) => {
                  if (!prev || prev.plan_id !== data.plan_id) return prev;
                  return {
                    ...prev,
                    steps: prev.steps.map((step) =>
                      step.step_number === data.step_number
                        ? { ...step, status: data.status as PlanStep['status'] }
                        : step
                    ),
                  };
                });

                // Update TaskList in messages
                setMessages((prev) => {
                  const updated = [...prev];
                  for (let i = updated.length - 1; i >= 0; i--) {
                    const msg = updated[i];
                    if (msg.role === 'assistant') {
                      const parts = msg.parts.map((part) => {
                        if (part.type === 'taskList' && part.taskList && part.taskList.planId === data.plan_id) {
                          const updatedTasks = part.taskList.tasks.map((task) =>
                            task.id === `step-${data.step_number}`
                              ? { ...task, status: data.status === 'in_progress' ? 'in_progress' as const : data.status === 'completed' ? 'completed' as const : 'pending' as const }
                              : task
                          );
                          return {
                            ...part,
                            taskList: {
                              ...part.taskList,
                              tasks: updatedTasks,
                            },
                          };
                        }
                        return part;
                      });
                      updated[i] = { ...msg, parts };
                      break; // Found and updated the TaskList
                    }
                  }
                  return updated;
                });
              } else if (data.type === 'plan_completed') {
                // Plan finished - mark all steps as their final status
                // Keep the plan visible so user can see completion
              } else if (data.type === 'domain_preference_request') {
                // Research agent is requesting domain preference (step 1)
                console.log('[Agent] Domain preference request:', data);
                setDomainPreferenceModal({
                  isOpen: true,
                  requestId: data.request_id,
                  topic: data.topic || '',
                  suggestedDomain: data.suggested_domain || '',
                });
              } else if (data.type === 'venue_preference_request') {
                // Research agent is requesting venue preferences (step 2)
                console.log('[Agent] Venue preference request:', data);
                setVenuePreferenceModal({
                  isOpen: true,
                  requestId: data.request_id,
                  topic: data.topic || '',
                  domain: data.domain || '',
                  suggestedVenues: data.suggested_venues || [],
                });
              }
            } catch (e) {
              console.error('[Agent] JSON parse error:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Agent stream error:', error);
      setMessages((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        const last = updated[lastIndex];
        if (last.role === 'assistant') {
          const parts = [...last.parts];
          parts.push({
            type: 'text',
            content: `**Error:** ${error instanceof Error ? error.message : 'Unknown error'}`
          });
          updated[lastIndex] = { ...last, parts };
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [input, isStreaming, projectPath, messages, onApprovalRequest, onApprovalResolved, quotedContext, onClearQuote, selectedChatSession, providerSettings, loadChatSessions]);

  // Keep sendMessageRef in sync
  useEffect(() => {
    sendMessageRef.current = sendMessage;
  }, [sendMessage]);

  // Stop the current generation
  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);

    // Add a note that generation was stopped
    setMessages((prev) => {
      const updated = [...prev];
      const lastIndex = updated.length - 1;
      const last = updated[lastIndex];
      if (last.role === 'assistant') {
        const parts = [...last.parts];
        parts.push({ type: 'text', content: '\n\n*[Generation stopped]*' });
        updated[lastIndex] = { ...last, parts };
      }
      return updated;
    });
  }, []);

  // Queue a message to be sent after current generation
  const queuePendingMessage = useCallback(() => {
    if (!input.trim()) return;
    setPendingMessage(input.trim());
    setInput('');
    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input]);

  // Clear pending message
  const clearPendingMessage = useCallback(() => {
    setPendingMessage(null);
  }, []);

  // Add a system message (for command results)
  const addSystemMessage = useCallback((content: string, isError: boolean = false) => {
    const systemMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      parts: [{
        type: 'text',
        content: isError ? `**Error:** ${content}` : `*${content}*`,
      }],
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, systemMessage]);
  }, []);

  // Handle domain preference submission
  const handleDomainPreferenceSubmit = useCallback(async (domain: string) => {
    const { requestId } = domainPreferenceModal;
    setDomainPreferenceModal({ isOpen: false, requestId: '', topic: '', suggestedDomain: '' });

    try {
      await api.submitDomainPreference(requestId, domain);
      console.log('[Agent] Domain preference submitted:', domain);
    } catch (error) {
      console.error('[Agent] Failed to submit domain preference:', error);
    }
  }, [domainPreferenceModal]);

  // Handle domain preference modal close (cancel)
  const handleDomainPreferenceClose = useCallback(() => {
    // On close/cancel, submit the suggested domain
    const { suggestedDomain } = domainPreferenceModal;
    handleDomainPreferenceSubmit(suggestedDomain || 'General Science');
  }, [domainPreferenceModal, handleDomainPreferenceSubmit]);

  // Handle venue preference submission
  const handleVenuePreferenceSubmit = useCallback(async (venues: string[]) => {
    const { requestId } = venuePreferenceModal;
    setVenuePreferenceModal({ isOpen: false, requestId: '', topic: '', domain: '', suggestedVenues: [] });

    try {
      await api.submitVenuePreferences(requestId, venues);
      console.log('[Agent] Venue preferences submitted:', venues);
    } catch (error) {
      console.error('[Agent] Failed to submit venue preferences:', error);
    }
  }, [venuePreferenceModal]);

  // Handle venue preference modal close (cancel)
  const handleVenuePreferenceClose = useCallback(() => {
    // On close/cancel, submit empty venues (no filter)
    handleVenuePreferenceSubmit([]);
  }, [handleVenuePreferenceSubmit]);

  // Handle input change - detect slash commands
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Auto-resize textarea
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';

    // Show/hide command palette based on input
    if (value.startsWith('/') && !value.includes('\n')) {
      const query = value.slice(1).split(' ')[0].toLowerCase();
      const filtered = filterCommands(query);
      setFilteredCommands(filtered);
      setShowCommandPalette(filtered.length > 0 && !value.includes(' '));
      setSelectedCommandIndex(0);
    } else {
      setShowCommandPalette(false);
    }
  }, []);

  // Execute a slash command
  const executeCommand = useCallback(async (cmd: SlashCommand, argument: string) => {
    if (!projectPath) return;

    // Check if argument is required but missing
    if (cmd.requiresArg && !argument.trim()) {
      setInput(`/${cmd.name} `);
      inputRef.current?.focus();
      return;
    }

    if (cmd.executionType === 'agent') {
      // Transform to natural language and send to agent
      const message = cmd.toAgentMessage?.(argument) || argument;
      // Create a short display version: /command argument_preview...
      const argPreview = argument.length > 50 ? argument.substring(0, 50) + '...' : argument;
      const displayMessage = `/${cmd.name} ${argPreview}`.trim();
      sendMessage(message, displayMessage);
    } else if (cmd.executionType === 'api' && cmd.execute) {
      // Direct API execution
      try {
        const result = await cmd.execute({ projectPath, argument });

        if (result.switchMode) {
          setMode(result.switchMode);
          if (result.vibeSessionId) {
            setSelectedVibeSession(result.vibeSessionId);
          }
        }

        if (result.message) {
          addSystemMessage(result.message, !result.success);
        }
      } catch (error) {
        addSystemMessage(
          error instanceof Error ? error.message : 'Command failed',
          true
        );
      }
    }
  }, [projectPath, sendMessage, addSystemMessage]);

  // Select a command from the palette
  const selectCommand = useCallback((cmd: SlashCommand) => {
    if (cmd.requiresArg) {
      // Insert command with space, wait for argument
      setInput(`/${cmd.name} `);
      setShowCommandPalette(false);
      inputRef.current?.focus();
    } else {
      // Execute immediately
      setInput('');
      setShowCommandPalette(false);
      executeCommand(cmd, '');
    }
  }, [executeCommand]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Command palette navigation
      if (showCommandPalette) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedCommandIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedCommandIndex((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (filteredCommands[selectedCommandIndex]) {
            selectCommand(filteredCommands[selectedCommandIndex]);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowCommandPalette(false);
          return;
        }
        if (e.key === 'Tab') {
          e.preventDefault();
          if (filteredCommands[selectedCommandIndex]) {
            selectCommand(filteredCommands[selectedCommandIndex]);
          }
          return;
        }
      }

      // Handle slash command execution
      if (e.key === 'Enter' && !e.shiftKey && input.startsWith('/')) {
        e.preventDefault();
        const parsed = parseCommandInput(input);
        if (parsed) {
          const cmd = findCommand(parsed.name);
          if (cmd) {
            // Use quotedContext text as argument if no argument in input
            const argument = parsed.argument || quotedContext?.text || '';
            setInput('');
            onClearQuote?.(); // Clear the quote
            executeCommand(cmd, argument);
            return;
          }
        }
        // If command not found, send as regular message
        sendMessage();
        return;
      }

      // Normal Enter handling
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (isStreaming) {
          queuePendingMessage();
        } else {
          sendMessage();
        }
      }
    },
    [sendMessage, queuePendingMessage, isStreaming, showCommandPalette, filteredCommands, selectedCommandIndex, selectCommand, input, executeCommand, quotedContext, onClearQuote]
  );

  return (
    <div className="h-full flex flex-col bg-fill-secondary">
      {/* Header with Mode Toggle */}
      <div className="panel-header bg-white overflow-visible">
        <div className="flex items-center gap-2 w-full min-w-0">
          {/* Mode toggle buttons */}
          <div className="flex items-center bg-fill-secondary rounded-yw-lg p-0.5 min-w-0">
            <button
              onClick={() => setMode('chat')}
              disabled={isStreaming}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-yw-md typo-small transition-all whitespace-nowrap ${
                mode === 'chat'
                  ? 'bg-white text-green1 shadow-sm'
                  : 'text-secondary hover:text-primary'
              } ${isStreaming ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <MessageSquare size={14} className="flex-shrink-0" />
              <span className="hidden sm:inline">Chat</span>
            </button>
            <button
              onClick={() => setMode('vibe')}
              disabled={isStreaming}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-yw-md typo-small transition-all whitespace-nowrap ${
                mode === 'vibe'
                  ? 'bg-white text-green1 shadow-sm'
                  : 'text-secondary hover:text-primary'
              } ${isStreaming ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <Microscope size={14} className="flex-shrink-0" />
              <span className="hidden sm:inline">Vibe</span>
            </button>
            <button
              onClick={() => setMode('verifier')}
              disabled={isStreaming}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-yw-md typo-small transition-all whitespace-nowrap ${
                mode === 'verifier'
                  ? 'bg-white text-green1 shadow-sm'
                  : 'text-secondary hover:text-primary'
              } ${isStreaming ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <BookOpen size={14} className="flex-shrink-0" />
              <span className="hidden sm:inline">Verify</span>
            </button>
          </div>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Model selector - only when DashScope is active */}
          {providerSettings.provider === 'dashscope' && providerSettings.dashscope?.selectedModel && (
            <ModelSelector
              models={DASHSCOPE_MODELS}
              selectedModel={providerSettings.dashscope.selectedModel}
              onSelect={handleModelSelectorChange}
            />
          )}
        </div>
      </div>

      {/* Content based on mode */}
      {mode === 'chat' && (
        <>
          {/* Chat Session Selector */}
          <div className="p-3 border-b border-black/6 bg-white flex items-center gap-2 min-w-0">
            <select
              value={selectedChatSession || ''}
              onChange={(e) => handleChatSessionChange(e.target.value || null)}
              className="flex-1 min-w-0 rounded-yw-md border border-black/12 bg-white px-3 py-2 typo-small focus:outline-none focus:ring-1 focus:ring-green2/20 truncate"
              disabled={isLoadingChatSessions || isStreaming}
            >
              <option value="">Select a chat session...</option>
              {chatSessions.map((session) => (
                <option key={session.session_id} value={session.session_id}>
                  {session.name} ({session.message_count} messages)
                </option>
              ))}
            </select>
            <button
              onClick={createNewChatSession}
              disabled={isStreaming}
              className="flex h-[36px] w-[36px] items-center justify-center rounded-yw-md bg-green1 text-white hover:opacity-90 transition-all flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
              title="New chat"
            >
              <Plus size={14} />
            </button>
            {selectedChatSession && (
              <button
                onClick={deleteCurrentChatSession}
                disabled={isStreaming}
                className="flex h-[36px] w-[36px] items-center justify-center rounded-yw-md bg-error/10 text-error hover:bg-error/20 transition-all flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                title="Delete session"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>

          {/* Chat Messages */}
          <div ref={messagesContainerRef} className="flex-1 overflow-auto p-3">
        {messages.length === 0 && !currentPlan ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center px-6">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green3 flex items-center justify-center">
                <Sparkles size={28} className="text-green1" />
              </div>
              <h3 className="typo-h3 mb-2">Ask the AI Assistant</h3>
              <p className="typo-small text-secondary">
                Research papers, write LaTeX, fix errors, and more
              </p>
            </div>
          </div>
        ) : (
          <div className="min-h-full flex flex-col justify-end space-y-3">
            {messages.map((msg) => (
              <MessageDisplay
                key={msg.id}
                message={msg}
                onApprove={handleApproveToolCall}
                onReject={handleRejectToolCall}
              />
            ))}
            {/* Pending message box */}
            {pendingMessage && (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-yw-lg bg-orange2/30 border border-orange1/30 p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Loader2 size={12} className="text-orange1 animate-spin" />
                    <span className="typo-ex-small text-orange1">Pending - will send when current generation ends</span>
                  </div>
                  <div className="typo-body text-primary">{pendingMessage}</div>
                  <button
                    onClick={clearPendingMessage}
                    className="mt-2 typo-ex-small text-tertiary hover:text-error transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {/* Active Plan Display - appears inline after messages */}
            {currentPlan && (
              <PlanDisplay
                plan={currentPlan}
                onClear={() => setCurrentPlan(null)}
              />
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

          {/* Chat Input */}
          <div className="border-t border-black/6 p-3 bg-white">
            {/* Quote Box - shows selected text from editor or file reference */}
            {quotedContext && (
              <div className="mb-2 p-2.5 bg-fill-secondary rounded-yw-lg border border-black/6 flex items-start gap-2">
                {quotedContext.action === 'file' ? (
                  <>
                    <FileCode size={16} className="flex-shrink-0 text-green1 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="typo-ex-small text-tertiary mb-0.5">
                        About this file:
                      </div>
                      <div className="typo-small text-primary font-medium truncate">
                        {quotedContext.text}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex-1 min-w-0">
                    <div className="typo-ex-small text-tertiary mb-1">
                      {quotedContext.action === 'polish' ? 'Polish this text' : 'About this text'}
                      {quotedContext.filePath && (
                        <span className="ml-1 text-green2">
                          ({quotedContext.filePath.split('/').pop()}:{quotedContext.startLine}-{quotedContext.endLine})
                        </span>
                      )}
                    </div>
                    <div className="typo-small text-secondary italic truncate">
                      &ldquo;{truncateToWords(quotedContext.text, 10)}&rdquo;
                    </div>
                  </div>
                )}
                <button
                  onClick={onClearQuote}
                  className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-black/6 text-tertiary hover:text-secondary transition-colors"
                  title="Remove"
                >
                  <X size={12} />
                </button>
              </div>
            )}
            <div className="relative flex gap-2">
              {/* Command Palette */}
              {showCommandPalette && (
                <CommandPalette
                  commands={filteredCommands}
                  selectedIndex={selectedCommandIndex}
                  onSelect={selectCommand}
                  onHover={setSelectedCommandIndex}
                />
              )}
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={
                  !projectPath
                    ? "Open a project first"
                    : isStreaming
                    ? "Queue next message..."
                    : "Type / for commands, or ask anything..."
                }
                disabled={!projectPath || !!pendingMessage}
                className={`flex-1 min-h-[44px] max-h-[200px] rounded-yw-lg border bg-white pl-3 pr-3 py-2.5 typo-body placeholder:text-tertiary focus:outline-none focus:ring-1 transition-colors resize-none overflow-y-auto ${
                  isStreaming
                    ? 'border-orange1/20 focus:border-orange1 focus:ring-orange1/20'
                    : 'border-black/12 focus:border-green2 focus:ring-green2/20'
                }`}
                rows={1}
              />
              {isStreaming ? (
                <>
                  {/* Queue button - only show when there's input and no pending message */}
                  {input.trim() && !pendingMessage && (
                    <button
                      onClick={queuePendingMessage}
                      className="flex h-[44px] w-[44px] items-center justify-center rounded-yw-lg bg-orange1 text-white hover:opacity-90 transition-all flex-shrink-0"
                      title="Queue message"
                    >
                      <Send size={14} />
                    </button>
                  )}
                  {/* Stop button */}
                  <button
                    onClick={stopGeneration}
                    className="flex h-[44px] w-[44px] items-center justify-center rounded-yw-lg bg-error text-white hover:opacity-90 transition-all flex-shrink-0"
                    title="Stop generation"
                  >
                    <Square size={14} fill="currentColor" />
                  </button>
                </>
              ) : (
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || !projectPath}
                  className={`flex h-[44px] w-[44px] items-center justify-center rounded-yw-lg transition-all flex-shrink-0 ${
                    !input.trim() || !projectPath
                      ? 'bg-black/6 text-tertiary cursor-not-allowed'
                      : 'bg-green1 text-white hover:opacity-90'
                  }`}
                >
                  <Send size={14} />
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {mode === 'vibe' && (
        /* Vibe Research Mode */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Session selector */}
          <div className="p-3 border-b border-black/6 bg-white">
            <div className="flex items-center gap-2">
              <select
                value={selectedVibeSession || ''}
                onChange={(e) => setSelectedVibeSession(e.target.value || null)}
                className="flex-1 rounded-yw-md border border-black/12 bg-white px-3 py-2 typo-small focus:outline-none focus:ring-1 focus:ring-green2/20"
                disabled={isLoadingSessions}
              >
                <option value="">Select a research session...</option>
                {vibeSessions.map((session) => (
                  <option key={session.session_id} value={session.session_id}>
                    {session.topic.slice(0, 40)}{session.topic.length > 40 ? '...' : ''}
                    ({session.current_phase}{session.is_complete ? ' - Complete' : ''})
                  </option>
                ))}
              </select>
              <button
                onClick={() => setShowNewResearchInput(true)}
                className="flex h-[36px] w-[36px] items-center justify-center rounded-yw-md bg-green1 text-white hover:opacity-90 transition-all flex-shrink-0"
                title="New research"
              >
                <Plus size={14} />
              </button>
            </div>

            {/* New research input */}
            {showNewResearchInput && (
              <div className="mt-3 p-3 bg-fill-secondary rounded-yw-lg">
                <div className="typo-small-strong mb-2">Start New Research</div>
                <textarea
                  value={newResearchTopic}
                  onChange={(e) => setNewResearchTopic(e.target.value)}
                  placeholder="Enter your research topic or question..."
                  className="w-full rounded-yw-md border border-black/12 bg-white px-3 py-2 typo-small focus:outline-none focus:ring-1 focus:ring-green2/20 resize-none"
                  rows={2}
                />
                <div className="flex items-center gap-2 mt-2">
                  <button
                    onClick={startNewResearch}
                    disabled={!newResearchTopic.trim() || isStartingResearch}
                    className="btn-primary typo-small flex items-center gap-1"
                  >
                    {isStartingResearch ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Microscope size={12} />
                    )}
                    Start Research
                  </button>
                  <button
                    onClick={() => {
                      setShowNewResearchInput(false);
                      setNewResearchTopic('');
                    }}
                    className="btn-ghost typo-small"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Vibe Research View */}
          {selectedVibeSession && projectPath ? (
            <VibeResearchView
              projectPath={projectPath}
              sessionId={selectedVibeSession}
              onComplete={loadVibeSessions}
              onDelete={() => {
                setSelectedVibeSession(null);
                loadVibeSessions();
              }}
              onOpenFile={onOpenFile}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center px-6">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-purple-100 flex items-center justify-center">
                  <Microscope size={28} className="text-purple-600" />
                </div>
                <h3 className="typo-h3 mb-2">Vibe Research</h3>
                <p className="typo-small text-secondary mb-4">
                  AI-led autonomous research that discovers papers, identifies gaps, and generates novel hypotheses
                </p>
                <button
                  onClick={() => setShowNewResearchInput(true)}
                  className="btn-primary flex items-center gap-2 mx-auto"
                >
                  <Plus size={14} />
                  Start New Research
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {mode === 'verifier' && projectPath && (
        <CitationVerifierPanel
          projectPath={projectPath}
          onClose={() => setMode('chat')}
        />
      )}

      {/* Domain Preference Modal */}
      <DomainPreferenceModal
        isOpen={domainPreferenceModal.isOpen}
        requestId={domainPreferenceModal.requestId}
        topic={domainPreferenceModal.topic}
        suggestedDomain={domainPreferenceModal.suggestedDomain}
        onClose={handleDomainPreferenceClose}
        onSubmit={handleDomainPreferenceSubmit}
      />

      {/* Venue Preference Modal */}
      <VenuePreferenceModal
        isOpen={venuePreferenceModal.isOpen}
        requestId={venuePreferenceModal.requestId}
        topic={venuePreferenceModal.topic}
        domain={venuePreferenceModal.domain}
        suggestedVenues={venuePreferenceModal.suggestedVenues}
        onClose={handleVenuePreferenceClose}
        onSubmit={handleVenuePreferenceSubmit}
      />
    </div>
  );
}
