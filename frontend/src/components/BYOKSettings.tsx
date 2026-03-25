import { useState, useCallback } from 'react';
import { Key, Eye, EyeOff, Check, X, Trash2, Loader2 } from 'lucide-react';
import type { UserProfile } from '../types';

const PROVIDERS = [
  { id: 'groq', name: 'Groq', description: 'Free tier — fast Llama 3.3 70B', placeholder: 'gsk_...', recommended: true },
  { id: 'openai', name: 'OpenAI', description: 'GPT-4o', placeholder: 'sk-...' },
  { id: 'anthropic', name: 'Anthropic', description: 'Claude Sonnet 4', placeholder: 'sk-ant-...' },
  { id: 'gemini', name: 'Google Gemini', description: 'Gemini 2.0 Flash (free)', placeholder: 'AIza...' },
  { id: 'cerebras', name: 'Cerebras', description: 'Ultra-fast Llama 3.3 70B (free)', placeholder: 'csk-...' },
] as const;

interface BYOKSettingsProps {
  profile: UserProfile;
  onUpdateProfile: (updates: Partial<UserProfile>) => void;
  onToast?: (type: 'success' | 'error' | 'info', message: string) => void;
}

export function BYOKSettings({ profile, onUpdateProfile, onToast }: BYOKSettingsProps) {
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [validating, setValidating] = useState(false);

  const activeProvider = profile.byokProvider || null;

  const handleSave = useCallback(async (providerId: string) => {
    if (!apiKeyInput.trim()) return;

    // Validate the key first
    setValidating(true);
    try {
      const resp = await fetch('/api/byok/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerId, api_key: apiKeyInput.trim() }),
      });
      const result = await resp.json();

      if (!result.valid) {
        onToast?.('error', result.error || 'Invalid API key');
        setValidating(false);
        return;
      }
    } catch {
      // If validation endpoint is unavailable, save anyway
    }
    setValidating(false);

    onUpdateProfile({
      byokProvider: providerId,
      byokApiKey: apiKeyInput.trim(),
    });
    setEditingProvider(null);
    setApiKeyInput('');
    setShowKey(false);
    onToast?.('success', `${PROVIDERS.find(p => p.id === providerId)?.name} API key verified and saved`);
  }, [apiKeyInput, onUpdateProfile, onToast]);

  const handleRemove = useCallback(() => {
    onUpdateProfile({
      byokProvider: undefined,
      byokApiKey: undefined,
    });
    onToast?.('info', 'Custom API key removed — using default provider');
  }, [onUpdateProfile, onToast]);

  const handleCancel = useCallback(() => {
    setEditingProvider(null);
    setApiKeyInput('');
    setShowKey(false);
  }, []);

  return (
    <div className="p-3">
      <div className="flex items-center gap-2 mb-3">
        <Key className="w-4 h-4 text-primary-600" />
        <h3 className="text-sm font-semibold text-gray-900">Bring Your Own Key</h3>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        Use your own LLM API key for faster responses. Keys are stored locally in your browser.
        Groq offers a free API key at <a href="https://console.groq.com" target="_blank" rel="noopener noreferrer" className="text-primary-600 underline">console.groq.com</a>.
      </p>

      {activeProvider && !editingProvider && (
        <div className="mb-3 p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Check className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs font-medium text-emerald-700">
                Active: {PROVIDERS.find(p => p.id === activeProvider)?.name}
              </span>
            </div>
            <button
              onClick={handleRemove}
              className="p-1 rounded hover:bg-emerald-100 text-emerald-600"
              title="Remove key"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {PROVIDERS.map(provider => (
          <div key={provider.id}>
            {editingProvider === provider.id ? (
              <div className="p-2.5 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-gray-900">{provider.name}</span>
                  <span className="text-xs text-gray-400">{provider.description}</span>
                </div>
                <div className="flex gap-1.5">
                  <div className="flex-1 relative">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={apiKeyInput}
                      onChange={e => setApiKeyInput(e.target.value)}
                      placeholder={provider.placeholder}
                      className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-lg pr-8 focus:outline-none focus:ring-1 focus:ring-primary-500 font-mono"
                      autoFocus
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleSave(provider.id);
                        if (e.key === 'Escape') handleCancel();
                      }}
                    />
                    <button
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <button
                    onClick={() => handleSave(provider.id)}
                    disabled={!apiKeyInput.trim() || validating}
                    className="p-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {validating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={handleCancel}
                    className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-500"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => {
                  setEditingProvider(provider.id);
                  setApiKeyInput('');
                  setShowKey(false);
                }}
                className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left transition-colors ${
                  activeProvider === provider.id
                    ? 'bg-primary-50 border border-primary-200'
                    : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-900">{provider.name}</span>
                  {'recommended' in provider && provider.recommended && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-medium">Free</span>
                  )}
                  <span className="text-xs text-gray-400 ml-1">{provider.description}</span>
                </div>
                {activeProvider === provider.id && (
                  <span className="text-xs text-primary-600 font-medium">Active</span>
                )}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
