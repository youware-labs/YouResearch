'use client';

import { useState, useCallback, useEffect } from 'react';
import { X, Link, Eye, EyeOff, Loader2, Check, AlertCircle, Cpu, Plus, Trash2, Zap } from 'lucide-react';
import { api, SyncStatus } from '@/lib/api';
import {
  ProviderSettings,
  ProviderName,
  OPENROUTER_MODELS,
  DEFAULT_OPENROUTER_MODEL,
  DASHSCOPE_MODELS,
  DEFAULT_DASHSCOPE_MODEL,
  getProviderSettings,
  saveProviderSettings,
} from '@/lib/providerSettings';

// Custom provider type from backend
interface CustomProvider {
  name: string;
  display_name: string;
  builtin: boolean;
  models: string[];
  default_model: string;
  base_url: string;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectPath: string | null;
  onSyncSetup?: () => void;
  onProviderChange?: (settings: ProviderSettings) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  projectPath,
  onSyncSetup,
  onProviderChange,
}: SettingsModalProps) {
  // Provider settings
  const [providerSettings, setProviderSettings] = useState<ProviderSettings>({ provider: 'openrouter' });
  const [openrouterApiKey, setOpenrouterApiKey] = useState('');
  const [openrouterModel, setOpenrouterModel] = useState(DEFAULT_OPENROUTER_MODEL);
  const [dashscopeApiKey, setDashscopeApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [selectedModel, setSelectedModel] = useState(DEFAULT_DASHSCOPE_MODEL);

  // API Key verification status
  const [openrouterStatus, setOpenrouterStatus] = useState<'idle' | 'verifying' | 'success' | 'error'>('idle');
  const [openrouterError, setOpenrouterError] = useState<string | null>(null);

  // Overleaf settings
  const [overleafUrl, setOverleafUrl] = useState('');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);

  // Status
  const [isLoading, setIsLoading] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);

  // Custom providers
  const [customProviders, setCustomProviders] = useState<CustomProvider[]>([]);
  const [activeProvider, setActiveProvider] = useState<string>('openrouter');
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProvider, setNewProvider] = useState({
    name: '',
    display_name: '',
    base_url: '',
    api_key: '',
    models: '',
  });
  const [addingProvider, setAddingProvider] = useState(false);
  const [testingProvider, setTestingProvider] = useState<string | null>(null);

  const loadSyncStatus = useCallback(async () => {
    if (!projectPath) return;

    try {
      const status = await api.getSyncStatus(projectPath);
      setSyncStatus(status);
      if (status.remote_url) {
        // Extract clean URL (without credentials)
        const cleanUrl = status.remote_url.replace(/https:\/\/[^@]+@/, 'https://');
        setOverleafUrl(cleanUrl);
      }
    } catch (e) {
      console.error('Failed to load sync status:', e);
    }
  }, [projectPath]);

  // Load custom providers from backend
  const loadProviders = useCallback(async () => {
    try {
      const data = await api.listProviders();
      // Filter to only show custom (non-builtin) providers
      const custom = data.providers.filter(p => !p.builtin);
      setCustomProviders(custom);
      setActiveProvider(data.active);
    } catch (e) {
      console.error('Failed to load providers:', e);
    }
  }, []);

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      const settings = getProviderSettings();
      setProviderSettings(settings);
      if (settings.openrouter) {
        setOpenrouterApiKey(settings.openrouter.apiKey || '');
        setOpenrouterModel(settings.openrouter.selectedModel || DEFAULT_OPENROUTER_MODEL);
        // If there's an existing API key, show as configured
        if (settings.openrouter.apiKey) {
          setOpenrouterStatus('success');
        }
      }
      if (settings.dashscope) {
        setDashscopeApiKey(settings.dashscope.apiKey || '');
        setSelectedModel(settings.dashscope.selectedModel || DEFAULT_DASHSCOPE_MODEL);
      }
      if (projectPath) {
        loadSyncStatus();
      }
      // Load custom providers
      loadProviders();
    }
  }, [isOpen, projectPath, loadSyncStatus, loadProviders]);

  const handleSetup = useCallback(async () => {
    console.log('[SettingsModal] handleSetup called', { projectPath, overleafUrl, token: token ? '***' : 'empty' });

    if (!projectPath) {
      setError('No project open');
      return;
    }

    if (!overleafUrl) {
      setError('Please enter an Overleaf URL');
      return;
    }

    // Clean URL - remove any embedded credentials (e.g., git@ or user:pass@)
    const cleanUrl = overleafUrl.replace(/https:\/\/[^@]+@/, 'https://');

    // Validate URL format
    if (!cleanUrl.startsWith('https://git.overleaf.com/')) {
      setError('Invalid URL. Should be: https://git.overleaf.com/<project_id>');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await api.setupSync(
        projectPath,
        overleafUrl,  // Send original URL, backend will clean it
        undefined,
        token || undefined,
      );

      if (result.success) {
        setSuccess(result.message);
        await loadSyncStatus();
        onSyncSetup?.();
      } else {
        setError(result.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Setup failed');
    } finally {
      setIsLoading(false);
    }
  }, [projectPath, overleafUrl, token, onSyncSetup, loadSyncStatus]);

  const handleTest = useCallback(async () => {
    if (!projectPath) return;

    setIsTesting(true);
    setError(null);
    setSuccess(null);

    try {
      const status = await api.getSyncStatus(projectPath);
      setSyncStatus(status);

      if (status.status === 'not_initialized') {
        setError('Not connected to Overleaf. Please set up sync first.');
      } else if (status.status === 'error') {
        setError(status.error_message || 'Connection error');
      } else {
        setSuccess(`Connected! Status: ${status.status}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Test failed');
    } finally {
      setIsTesting(false);
    }
  }, [projectPath]);

  // Provider change handlers
  const handleProviderChange = useCallback(async (provider: ProviderName) => {
    const newSettings: ProviderSettings = {
      ...providerSettings,
      provider,
    };

    // Initialize openrouter settings if switching to openrouter
    if (provider === 'openrouter' && !newSettings.openrouter) {
      newSettings.openrouter = {
        apiKey: openrouterApiKey,
        selectedModel: openrouterModel,
      };
    }

    // Initialize dashscope settings if switching to dashscope
    if (provider === 'dashscope' && !newSettings.dashscope) {
      newSettings.dashscope = {
        apiKey: dashscopeApiKey,
        selectedModel: selectedModel,
      };
    }

    // When switching to builtin provider, also set it as active in backend
    if (provider === 'openrouter' || provider === 'dashscope') {
      try {
        await api.setActiveProvider('openrouter'); // Backend builtin
        setActiveProvider('openrouter');
      } catch (e) {
        console.error('Failed to set backend active provider:', e);
      }
    }

    setProviderSettings(newSettings);
    saveProviderSettings(newSettings);
    onProviderChange?.(newSettings);
  }, [providerSettings, openrouterApiKey, openrouterModel, dashscopeApiKey, selectedModel, onProviderChange]);

  const handleOpenRouterModelChange = useCallback((modelId: string) => {
    setOpenrouterModel(modelId);
    const newSettings: ProviderSettings = {
      ...providerSettings,
      openrouter: {
        apiKey: openrouterApiKey,
        selectedModel: modelId,
      },
    };
    setProviderSettings(newSettings);
    saveProviderSettings(newSettings);
    onProviderChange?.(newSettings);
  }, [providerSettings, openrouterApiKey, onProviderChange]);

  const handleDashScopeApiKeyChange = useCallback((apiKey: string) => {
    setDashscopeApiKey(apiKey);
    const newSettings: ProviderSettings = {
      ...providerSettings,
      dashscope: {
        apiKey,
        selectedModel,
      },
    };
    setProviderSettings(newSettings);
    saveProviderSettings(newSettings);
    onProviderChange?.(newSettings);
  }, [providerSettings, selectedModel, onProviderChange]);

  const handleDashScopeModelChange = useCallback((modelId: string) => {
    setSelectedModel(modelId);
    const newSettings: ProviderSettings = {
      ...providerSettings,
      dashscope: {
        apiKey: dashscopeApiKey,
        selectedModel: modelId,
      },
    };
    setProviderSettings(newSettings);
    saveProviderSettings(newSettings);
    onProviderChange?.(newSettings);
  }, [providerSettings, dashscopeApiKey, onProviderChange]);

  // Verify OpenRouter API key
  const verifyOpenRouterKey = useCallback(async () => {
    if (!openrouterApiKey) {
      setOpenrouterError('Please enter an API key');
      setOpenrouterStatus('error');
      return;
    }

    setOpenrouterStatus('verifying');
    setOpenrouterError(null);

    try {
      const response = await fetch('https://openrouter.ai/api/v1/models', {
        headers: {
          'Authorization': `Bearer ${openrouterApiKey}`,
        },
      });

      if (response.ok) {
        setOpenrouterStatus('success');
        // Save the settings
        const newSettings: ProviderSettings = {
          ...providerSettings,
          openrouter: {
            apiKey: openrouterApiKey,
            selectedModel: openrouterModel,
          },
        };
        setProviderSettings(newSettings);
        saveProviderSettings(newSettings);
        onProviderChange?.(newSettings);
      } else {
        const data = await response.json();
        setOpenrouterError(data.error?.message || 'Invalid API key');
        setOpenrouterStatus('error');
      }
    } catch (e) {
      setOpenrouterError('Failed to verify API key');
      setOpenrouterStatus('error');
    }
  }, [openrouterApiKey, openrouterModel, providerSettings, onProviderChange]);

  // Add custom provider
  const handleAddProvider = useCallback(async () => {
    if (!newProvider.name || !newProvider.base_url || !newProvider.models) {
      setError('Please fill in all required fields');
      return;
    }

    setAddingProvider(true);
    setError(null);

    try {
      const modelList = newProvider.models.split(',').map(m => m.trim()).filter(m => m);
      await api.addProvider({
        name: newProvider.name.toLowerCase().replace(/\s+/g, '-'),
        display_name: newProvider.display_name || newProvider.name,
        base_url: newProvider.base_url,
        api_key: newProvider.api_key,
        models: modelList,
        default_model: modelList[0] || '',
      });

      // Reset form and reload
      setNewProvider({ name: '', display_name: '', base_url: '', api_key: '', models: '' });
      setShowAddProvider(false);
      await loadProviders();
      setSuccess('Provider added successfully');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add provider');
    } finally {
      setAddingProvider(false);
    }
  }, [newProvider, loadProviders]);

  // Delete custom provider
  const handleDeleteProvider = useCallback(async (name: string) => {
    try {
      await api.deleteProvider(name);
      await loadProviders();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete provider');
    }
  }, [loadProviders]);

  // Test custom provider connection
  const handleTestProvider = useCallback(async (name: string) => {
    setTestingProvider(name);
    try {
      const result = await api.testProvider(name);
      if (result.success) {
        setSuccess(`Connection successful (${result.latency_ms}ms)`);
      } else {
        setError(result.error || 'Connection failed');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Test failed');
    } finally {
      setTestingProvider(null);
    }
  }, []);

  // Set active provider (backend) and update frontend settings
  const handleSetActiveCustomProvider = useCallback(async (name: string) => {
    try {
      await api.setActiveProvider(name);
      setActiveProvider(name);

      // Update frontend settings to use 'custom' provider type
      // This tells the frontend to not send provider_config, letting backend use its active provider
      const newSettings: ProviderSettings = {
        ...providerSettings,
        provider: 'custom',
      };
      setProviderSettings(newSettings);
      saveProviderSettings(newSettings);
      onProviderChange?.(newSettings);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to set active provider');
    }
  }, [providerSettings, onProviderChange]);

  if (!isOpen) return null;

  console.log('[SettingsModal] Rendering with projectPath:', projectPath);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 z-0"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg bg-white rounded-yw-2xl shadow-xl animate-fadeInUp">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/6">
          <h2 className="typo-h2">Settings</h2>
          <button
            onClick={onClose}
            className="btn-icon"
          >
            <X size={18} className="text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Model Provider Section */}
          <div>
            <h3 className="typo-body-strong mb-3 flex items-center gap-2">
              <Cpu size={16} className="text-green2" />
              Model Provider
            </h3>

            <div className="space-y-3">
              {/* OpenRouter Option */}
              <label
                className={`flex items-center gap-3 p-3 rounded-yw-lg border cursor-pointer transition-colors ${
                  providerSettings.provider === 'openrouter'
                    ? 'border-green2 bg-green2/5'
                    : 'border-black/10 hover:bg-black/3'
                }`}
              >
                <input
                  type="radio"
                  name="provider"
                  value="openrouter"
                  checked={providerSettings.provider === 'openrouter'}
                  onChange={() => handleProviderChange('openrouter')}
                  className="accent-green2"
                />
                <div>
                  <div className="typo-small-strong">OpenRouter</div>
                  <div className="typo-ex-small text-tertiary">Claude, GPT-4, Gemini, and more</div>
                </div>
              </label>

              {/* OpenRouter Settings (only shown when selected) */}
              {providerSettings.provider === 'openrouter' && (
                <div className="ml-6 space-y-3 pt-2">
                  {/* API Key */}
                  <div>
                    <label className="typo-small text-secondary block mb-1.5">
                      OpenRouter API Key
                    </label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <input
                          type={showApiKey ? 'text' : 'password'}
                          value={openrouterApiKey}
                          onChange={(e) => {
                            setOpenrouterApiKey(e.target.value);
                            setOpenrouterStatus('idle');
                            setOpenrouterError(null);
                          }}
                          placeholder="sk-or-xxxxxxxxxxxxx"
                          className="input-field w-full pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-tertiary hover:text-secondary"
                        >
                          {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                      <button
                        onClick={verifyOpenRouterKey}
                        disabled={openrouterStatus === 'verifying' || !openrouterApiKey}
                        className={`btn-secondary px-4 ${!openrouterApiKey ? 'opacity-50' : ''}`}
                      >
                        {openrouterStatus === 'verifying' ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : openrouterStatus === 'success' ? (
                          <Check size={14} className="text-success" />
                        ) : (
                          'Verify'
                        )}
                      </button>
                    </div>
                    {/* Status message */}
                    {openrouterStatus === 'success' && (
                      <p className="typo-ex-small text-success mt-1 flex items-center gap-1">
                        <Check size={12} /> API key verified and saved
                      </p>
                    )}
                    {openrouterStatus === 'error' && openrouterError && (
                      <p className="typo-ex-small text-error mt-1 flex items-center gap-1">
                        <AlertCircle size={12} /> {openrouterError}
                      </p>
                    )}
                    {openrouterStatus === 'idle' && (
                      <p className="typo-ex-small text-tertiary mt-1">
                        Get your key at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-green2 hover:underline">openrouter.ai/keys</a>
                      </p>
                    )}
                  </div>

                  {/* Model Selection */}
                  <div>
                    <label className="typo-small text-secondary block mb-1.5">
                      Default Model
                    </label>
                    <select
                      value={openrouterModel}
                      onChange={(e) => handleOpenRouterModelChange(e.target.value)}
                      className="input-field w-full"
                    >
                      {OPENROUTER_MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* DashScope Option */}
              <label
                className={`flex items-center gap-3 p-3 rounded-yw-lg border cursor-pointer transition-colors ${
                  providerSettings.provider === 'dashscope'
                    ? 'border-green2 bg-green2/5'
                    : 'border-black/10 hover:bg-black/3'
                }`}
              >
                <input
                  type="radio"
                  name="provider"
                  value="dashscope"
                  checked={providerSettings.provider === 'dashscope'}
                  onChange={() => handleProviderChange('dashscope')}
                  className="accent-green2"
                />
                <div>
                  <div className="typo-small-strong">DashScope (阿里云百炼)</div>
                  <div className="typo-ex-small text-tertiary">Chinese models: DeepSeek, Qwen, Kimi, GLM</div>
                </div>
              </label>

              {/* DashScope Settings (only shown when selected) */}
              {providerSettings.provider === 'dashscope' && (
                <div className="ml-6 space-y-3 pt-2">
                  {/* API Key */}
                  <div>
                    <label className="typo-small text-secondary block mb-1.5">
                      DashScope API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={dashscopeApiKey}
                        onChange={(e) => handleDashScopeApiKeyChange(e.target.value)}
                        placeholder="sk-xxxxxxxxxxxxx"
                        className="input-field w-full pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-tertiary hover:text-secondary"
                      >
                        {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    <p className="typo-ex-small text-tertiary mt-1">
                      Get your key at <a href="https://bailian.console.aliyun.com/" target="_blank" rel="noopener noreferrer" className="text-green2 hover:underline">bailian.console.aliyun.com</a>
                    </p>
                  </div>

                  {/* Model Selection */}
                  <div>
                    <label className="typo-small text-secondary block mb-1.5">
                      Default Model
                    </label>
                    <select
                      value={selectedModel}
                      onChange={(e) => handleDashScopeModelChange(e.target.value)}
                      className="input-field w-full"
                    >
                      {DASHSCOPE_MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* Custom Providers */}
              {customProviders.length > 0 && (
                <>
                  <div className="border-t border-black/6 my-3" />
                  <div className="typo-ex-small text-tertiary mb-2">Custom Providers</div>
                  {customProviders.map((provider) => (
                    <div
                      key={provider.name}
                      className={`flex items-center justify-between p-3 rounded-yw-lg border transition-colors ${
                        activeProvider === provider.name
                          ? 'border-green2 bg-green2/5'
                          : 'border-black/10 hover:bg-black/3'
                      }`}
                    >
                      <label className="flex items-center gap-3 cursor-pointer flex-1">
                        <input
                          type="radio"
                          name="provider"
                          value={provider.name}
                          checked={activeProvider === provider.name}
                          onChange={() => handleSetActiveCustomProvider(provider.name)}
                          className="accent-green2"
                        />
                        <div>
                          <div className="typo-small-strong">{provider.display_name}</div>
                          <div className="typo-ex-small text-tertiary">
                            {provider.models.slice(0, 3).join(', ')}
                            {provider.models.length > 3 && ` +${provider.models.length - 3} more`}
                          </div>
                        </div>
                      </label>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleTestProvider(provider.name)}
                          disabled={testingProvider === provider.name}
                          className="btn-icon"
                          title="Test connection"
                        >
                          {testingProvider === provider.name ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Zap size={14} />
                          )}
                        </button>
                        <button
                          onClick={() => handleDeleteProvider(provider.name)}
                          className="btn-icon text-error hover:bg-error/10"
                          title="Delete provider"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </>
              )}

              {/* Add Custom Provider Button */}
              {!showAddProvider && (
                <button
                  onClick={() => setShowAddProvider(true)}
                  className="w-full p-3 border border-dashed border-black/20 rounded-yw-lg text-tertiary hover:text-secondary hover:border-black/30 transition-colors flex items-center justify-center gap-2"
                >
                  <Plus size={16} />
                  <span className="typo-small">Add Custom Provider</span>
                </button>
              )}

              {/* Add Provider Form */}
              {showAddProvider && (
                <div className="p-4 border border-black/10 rounded-yw-lg space-y-3 bg-black/2">
                  <div className="flex items-center justify-between mb-2">
                    <span className="typo-small-strong">Add Custom Provider</span>
                    <button
                      onClick={() => setShowAddProvider(false)}
                      className="btn-icon"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  <div>
                    <label className="typo-ex-small text-secondary block mb-1">Name *</label>
                    <input
                      type="text"
                      value={newProvider.name}
                      onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })}
                      placeholder="e.g., My Ollama"
                      className="input-field w-full"
                    />
                  </div>

                  <div>
                    <label className="typo-ex-small text-secondary block mb-1">Base URL *</label>
                    <input
                      type="url"
                      value={newProvider.base_url}
                      onChange={(e) => setNewProvider({ ...newProvider, base_url: e.target.value })}
                      placeholder="http://localhost:11434/v1"
                      className="input-field w-full"
                    />
                  </div>

                  <div>
                    <label className="typo-ex-small text-secondary block mb-1">API Key (optional)</label>
                    <input
                      type="password"
                      value={newProvider.api_key}
                      onChange={(e) => setNewProvider({ ...newProvider, api_key: e.target.value })}
                      placeholder="sk-..."
                      className="input-field w-full"
                    />
                  </div>

                  <div>
                    <label className="typo-ex-small text-secondary block mb-1">Models * (comma-separated)</label>
                    <input
                      type="text"
                      value={newProvider.models}
                      onChange={(e) => setNewProvider({ ...newProvider, models: e.target.value })}
                      placeholder="llama3, mistral, codellama"
                      className="input-field w-full"
                    />
                  </div>

                  <button
                    onClick={handleAddProvider}
                    disabled={addingProvider}
                    className="btn-primary w-full"
                  >
                    {addingProvider ? (
                      <>
                        <Loader2 size={14} className="animate-spin mr-2" />
                        Adding...
                      </>
                    ) : (
                      'Add Provider'
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-black/6" />

          {/* Overleaf Sync Section */}
          <div>
            <h3 className="typo-body-strong mb-3 flex items-center gap-2">
              <Link size={16} className="text-green2" />
              Overleaf Sync
            </h3>

            {/* Current Status */}
            {syncStatus && (
              <div className={`mb-4 p-3 rounded-yw-lg ${
                syncStatus.status === 'clean' ? 'bg-success/10' :
                syncStatus.status === 'not_initialized' ? 'bg-black/5' :
                'bg-warn/10'
              }`}>
                <div className="flex items-center gap-2">
                  {syncStatus.status === 'clean' ? (
                    <Check size={14} className="text-success" />
                  ) : syncStatus.status === 'not_initialized' ? (
                    <AlertCircle size={14} className="text-tertiary" />
                  ) : (
                    <AlertCircle size={14} className="text-warn" />
                  )}
                  <span className="typo-small">
                    {syncStatus.status === 'not_initialized' ? 'Not connected' :
                     syncStatus.status === 'clean' ? 'Synced with Overleaf' :
                     syncStatus.status === 'local_changes' ? 'Local changes pending' :
                     syncStatus.status === 'ahead' ? `${syncStatus.commits_ahead} commits to push` :
                     syncStatus.status === 'behind' ? `${syncStatus.commits_behind} commits to pull` :
                     syncStatus.status === 'diverged' ? 'Local and remote have diverged' :
                     syncStatus.status}
                  </span>
                </div>
                {syncStatus.last_sync && (
                  <span className="typo-ex-small text-tertiary block mt-1">
                    Last sync: {new Date(syncStatus.last_sync).toLocaleString()}
                  </span>
                )}
              </div>
            )}

            {/* Overleaf URL Input */}
            <div className="space-y-3">
              <div>
                <label className="typo-small text-secondary block mb-1.5">
                  Overleaf Git URL
                </label>
                <input
                  type="url"
                  value={overleafUrl}
                  onChange={(e) => setOverleafUrl(e.target.value)}
                  placeholder="https://git.overleaf.com/..."
                  className="input-field w-full"
                />
                <p className="typo-ex-small text-tertiary mt-1">
                  Find this in Overleaf: Menu &rarr; Git &rarr; Clone URL
                </p>
              </div>

              <div>
                <label className="typo-small text-secondary block mb-1.5">
                  Git Token
                </label>
                <div className="relative">
                  <input
                    type={showToken ? 'text' : 'password'}
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="olp_xxxxxxxxxxxx"
                    className="input-field w-full pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken(!showToken)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-tertiary hover:text-secondary"
                  >
                    {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="typo-ex-small text-tertiary mt-1">
                  Create token in Overleaf: Account &rarr; Settings &rarr; Git Integration
                </p>
              </div>
            </div>

            {/* Error/Success Messages */}
            {error && (
              <div className="mt-3 p-3 bg-error/10 rounded-yw-lg">
                <span className="typo-small text-error">{error}</span>
              </div>
            )}
            {success && (
              <div className="mt-3 p-3 bg-success/10 rounded-yw-lg">
                <span className="typo-small text-success">{success}</span>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-2 mt-4">
              {!projectPath && (
                <p className="typo-small text-warn mb-2 w-full">Open a project first to connect to Overleaf</p>
              )}
              <button
                onClick={() => {
                  console.log('[SettingsModal] Connect button clicked');
                  handleSetup();
                }}
                disabled={isLoading || !projectPath}
                className={`btn-primary flex-1 ${!projectPath ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {isLoading ? (
                  <>
                    <Loader2 size={14} className="animate-spin mr-2" />
                    Connecting...
                  </>
                ) : (
                  'Connect to Overleaf'
                )}
              </button>
              <button
                onClick={handleTest}
                disabled={isTesting || !projectPath || !syncStatus?.has_remote}
                className="btn-secondary"
              >
                {isTesting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  'Test'
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-black/6 flex justify-end">
          <button
            onClick={onClose}
            className="btn-ghost"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
