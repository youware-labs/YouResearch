/**
 * Slash Command Registry
 *
 * Defines all available slash commands for the Aura chat interface.
 */

import { api } from './api';

// =============================================================================
// Types
// =============================================================================

export interface CommandContext {
  projectPath: string;
  argument: string;
}

export interface CommandResult {
  success: boolean;
  message?: string;
  switchMode?: 'chat' | 'vibe' | 'verifier';
  vibeSessionId?: string;
}

export interface SlashCommand {
  name: string;
  description: string;
  icon: string;
  category: 'research' | 'writing' | 'project';
  requiresArg: boolean;
  argPlaceholder?: string;
  executionType: 'agent' | 'api';
  /** For agent commands: transforms argument into natural language message */
  toAgentMessage?: (arg: string) => string;
  /** For API commands: executes directly and returns result */
  execute?: (ctx: CommandContext) => Promise<CommandResult>;
}

// =============================================================================
// Command Definitions
// =============================================================================

export const commands: SlashCommand[] = [
  // ─────────────────────────────────────────────────────────────────────────
  // Research Commands
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'research',
    description: 'Search for papers on a topic',
    icon: 'Search',
    category: 'research',
    requiresArg: true,
    argPlaceholder: 'topic',
    executionType: 'agent',
    toAgentMessage: (arg) => `Search for academic papers about: ${arg}`,
  },
  {
    name: 'vibe',
    description: 'Start deep autonomous research',
    icon: 'Microscope',
    category: 'research',
    requiresArg: true,
    argPlaceholder: 'topic',
    executionType: 'api',
    execute: async ({ projectPath, argument }) => {
      try {
        const session = await api.startVibeResearch(projectPath, argument);
        return {
          success: true,
          message: `Started vibe research: "${argument}"`,
          switchMode: 'vibe',
          vibeSessionId: session.session_id,
        };
      } catch (error) {
        return {
          success: false,
          message: `Failed to start vibe research: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
      }
    },
  },
  {
    name: 'cite',
    description: 'Add a citation to the document',
    icon: 'BookOpen',
    category: 'research',
    requiresArg: true,
    argPlaceholder: 'arxiv:id or search query',
    executionType: 'agent',
    toAgentMessage: (arg) => `Add a citation for: ${arg}`,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Writing Commands
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'polish',
    description: 'Polish and improve selected text',
    icon: 'Sparkles',
    category: 'writing',
    requiresArg: true,
    argPlaceholder: 'selected text',
    executionType: 'agent',
    toAgentMessage: (arg) => `Polish and improve ONLY the following text, then use edit_file to replace it in the document.

CRITICAL RULES:
- ONLY polish the exact text provided below
- Do NOT edit any other parts of the document
- When you finish editing this text, STOP immediately

INSTRUCTIONS:
1. Use search_in_file to find the exact location of this text
2. Read the SURROUNDING CONTEXT (lines before and after) to understand the flow
3. Polish the text - ensure it fits naturally with the surrounding content
4. Use edit_file to replace the original text with the polished version
5. After the edit is applied, STOP. Do NOT make any more edits.

Text to polish:
---
${arg}
---

Remember: Read context first, make ONE edit, then STOP.`,
  },
  {
    name: 'analyze',
    description: 'Analyze document structure',
    icon: 'FileSearch',
    category: 'writing',
    requiresArg: false,
    executionType: 'agent',
    toAgentMessage: () => 'Analyze the structure of this LaTeX document. Show me the section hierarchy, figures, tables, and any structural issues.',
  },
  {
    name: 'fix',
    description: 'Fix LaTeX compilation errors',
    icon: 'Wrench',
    category: 'writing',
    requiresArg: false,
    executionType: 'agent',
    toAgentMessage: () => 'Check for and fix any LaTeX compilation errors in the document.',
  },
  {
    name: 'clean-bib',
    description: 'Remove unused bibliography entries',
    icon: 'Trash2',
    category: 'writing',
    requiresArg: false,
    executionType: 'agent',
    toAgentMessage: () => 'Clean the bibliography by identifying and removing any unused citation entries.',
  },
  {
    name: 'literature-verifier',
    description: 'Verify all citations are real and used correctly',
    icon: 'BookCheck',
    category: 'writing',
    requiresArg: false,
    executionType: 'api',
    execute: async ({ projectPath: _projectPath }) => {
      // This command switches the UI to verifier mode
      // The actual verification is handled by AgentPanel
      return {
        success: true,
        message: 'Opening literature verifier...',
        switchMode: 'verifier' as const,
      };
    },
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Project Commands
  // ─────────────────────────────────────────────────────────────────────────
  {
    name: 'compile',
    description: 'Compile the LaTeX document',
    icon: 'Play',
    category: 'project',
    requiresArg: false,
    executionType: 'api',
    execute: async ({ projectPath }) => {
      try {
        const result = await api.compile(projectPath);
        if (result.success) {
          return {
            success: true,
            message: 'Compiled successfully',
          };
        } else {
          return {
            success: false,
            message: `Compilation failed: ${result.error_summary || 'Unknown error'}`,
          };
        }
      } catch (error) {
        return {
          success: false,
          message: `Compilation error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
      }
    },
  },
  {
    name: 'sync',
    description: 'Sync with Overleaf',
    icon: 'Cloud',
    category: 'project',
    requiresArg: false,
    executionType: 'api',
    execute: async ({ projectPath }) => {
      try {
        const result = await api.syncProject(projectPath);
        if (result.success) {
          const filesChanged = result.files_changed?.length || 0;
          return {
            success: true,
            message: filesChanged > 0
              ? `Synced successfully (${filesChanged} files changed)`
              : 'Already in sync',
          };
        } else {
          return {
            success: false,
            message: `Sync failed: ${result.message || 'Unknown error'}`,
          };
        }
      } catch (error) {
        return {
          success: false,
          message: `Sync error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
      }
    },
  },
  {
    name: 'plan',
    description: 'Create a structured plan for a task',
    icon: 'ListChecks',
    category: 'project',
    requiresArg: true,
    argPlaceholder: 'task description',
    executionType: 'agent',
    toAgentMessage: (arg) => `Create a detailed plan for this task: ${arg}

Use the plan_task tool to create a structured execution plan with clear steps. Break down the task into manageable steps that can be executed one by one.`,
  },
];

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Find a command by name
 */
export function findCommand(name: string): SlashCommand | undefined {
  return commands.find((cmd) => cmd.name === name);
}

/**
 * Filter commands by search query
 */
export function filterCommands(query: string): SlashCommand[] {
  const lowerQuery = query.toLowerCase();
  return commands.filter(
    (cmd) =>
      cmd.name.toLowerCase().includes(lowerQuery) ||
      cmd.description.toLowerCase().includes(lowerQuery)
  );
}

/**
 * Parse input to extract command name and argument
 * Returns null if input doesn't start with /
 */
export function parseCommandInput(input: string): { name: string; argument: string } | null {
  if (!input.startsWith('/')) return null;

  const match = input.match(/^\/(\S+)\s*(.*)/);
  if (!match) return null;

  return {
    name: match[1],
    argument: match[2].trim(),
  };
}
