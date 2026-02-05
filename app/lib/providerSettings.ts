/**
 * Provider Settings
 *
 * Manages model provider configuration (OpenRouter vs DashScope).
 * Settings are persisted via Electron IPC (for production) with localStorage as cache.
 */

// =============================================================================
// Types
// =============================================================================

export type ProviderName = 'openrouter' | 'dashscope' | 'custom';

export interface DashScopeModel {
  id: string;
  name: string;
}

export interface OpenRouterModel {
  id: string;
  name: string;
}

export interface ProviderSettings {
  provider: ProviderName;
  openrouter?: {
    apiKey: string;
    selectedModel: string;
  };
  dashscope?: {
    apiKey: string;
    selectedModel: string;
  };
}

// =============================================================================
// Constants
// =============================================================================

const STORAGE_KEY = 'aura_provider_settings';

export const OPENROUTER_MODELS: OpenRouterModel[] = [
  // Claude models
  { id: 'anthropic/claude-sonnet-4.5', name: 'Claude Sonnet 4.5' },
  // OpenAI models
  { id: 'openai/gpt-5.2', name: 'GPT-5.2' },
  // Google
  { id: 'google/gemini-3-flash-preview', name: 'Gemini 3 Flash Preview' },
  // Free model (no tool support)
  { id: 'openrouter/free', name: 'OpenRouter Free (Auto)' },
];

export const DEFAULT_OPENROUTER_MODEL = 'anthropic/claude-sonnet-4.5';

export const DASHSCOPE_MODELS: DashScopeModel[] = [
  { id: 'deepseek-v3.2', name: 'DeepSeek V3.2' },
  { id: 'qwen-max-latest', name: 'Qwen Max' },
  { id: 'kimi-k2-thinking', name: 'Kimi K2' },
  { id: 'glm-4.7', name: 'GLM-4.7' },
];

export const DEFAULT_DASHSCOPE_MODEL = 'deepseek-v3.2';

// =============================================================================
// Electron IPC Helpers
// =============================================================================

function isElectron(): boolean {
  return typeof window !== 'undefined' && 'aura' in window && typeof window.aura?.getSettings === 'function';
}

/**
 * Initialize settings from Electron storage.
 * Call this once on app startup to sync Electron-persisted settings to localStorage.
 */
export async function initializeSettings(): Promise<void> {
  if (typeof window === 'undefined') return;

  if (isElectron()) {
    try {
      const settings = await window.aura!.getSettings();
      if (settings?.provider_settings) {
        // Sync Electron storage to localStorage for fast sync access
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.provider_settings));
      }
    } catch (e) {
      console.error('Failed to load settings from Electron:', e);
    }
  }
}

// =============================================================================
// Storage Functions
// =============================================================================

export function getProviderSettings(): ProviderSettings {
  if (typeof window === 'undefined') {
    return { provider: 'openrouter' };
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored) as ProviderSettings;
    }
  } catch (e) {
    console.error('Failed to load provider settings:', e);
  }

  return { provider: 'openrouter' };
}

export function saveProviderSettings(settings: ProviderSettings): void {
  if (typeof window === 'undefined') return;

  try {
    // Always save to localStorage for sync access
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));

    // Also save to Electron storage for persistence across app restarts
    if (isElectron()) {
      // Get current settings and update provider_settings
      window.aura!.getSettings().then((currentSettings) => {
        const newSettings = {
          ...(currentSettings || {}),
          provider_settings: settings,
        };
        window.aura!.saveSettings(newSettings);
      }).catch((e: Error) => {
        console.error('Failed to save settings to Electron:', e);
      });
    }

    // Dispatch custom event for same-tab listeners
    window.dispatchEvent(new CustomEvent('aura-provider-changed'));
  } catch (e) {
    console.error('Failed to save provider settings:', e);
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

export function isOpenRouterConfigured(settings: ProviderSettings): boolean {
  return (
    settings.provider === 'openrouter' &&
    !!settings.openrouter?.apiKey
  );
}

export function isDashScopeConfigured(settings: ProviderSettings): boolean {
  return (
    settings.provider === 'dashscope' &&
    !!settings.dashscope?.apiKey &&
    !!settings.dashscope?.selectedModel
  );
}

export function getSelectedModelName(settings: ProviderSettings): string | null {
  if (settings.provider === 'openrouter' && settings.openrouter?.selectedModel) {
    const model = OPENROUTER_MODELS.find(m => m.id === settings.openrouter?.selectedModel);
    return model?.name || settings.openrouter.selectedModel;
  }

  if (settings.provider === 'dashscope' && settings.dashscope?.selectedModel) {
    const model = DASHSCOPE_MODELS.find(m => m.id === settings.dashscope?.selectedModel);
    return model?.name || settings.dashscope.selectedModel;
  }

  return null;
}

export function getProviderConfigForRequest(settings: ProviderSettings): {
  name: ProviderName;
  model?: string;
  api_key?: string;
} | undefined {
  // Custom provider - let backend use its active provider from ProviderManager
  if (settings.provider === 'custom') {
    return undefined;
  }

  if (settings.provider === 'openrouter') {
    // Always send OpenRouter config - backend will validate API key
    return {
      name: 'openrouter',
      model: settings.openrouter?.selectedModel || DEFAULT_OPENROUTER_MODEL,
      api_key: settings.openrouter?.apiKey || '',
    };
  }

  if (settings.provider === 'dashscope' && settings.dashscope) {
    return {
      name: 'dashscope',
      model: settings.dashscope.selectedModel,
      api_key: settings.dashscope.apiKey,
    };
  }

  return undefined;
}
