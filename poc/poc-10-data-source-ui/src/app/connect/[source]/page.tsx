'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useDataSourceStore } from '@/lib/store';
import { SourceIcon } from '@/components/SourceIcon';
import { CredentialForm } from '@/components/CredentialForm';
import type { SourceInfo } from '@/lib/types';

type Step = 'credentials' | 'config' | 'confirm';

export default function ConnectWizardPage() {
  const params = useParams();
  const sourceType = params.source as string;
  const [step, setStep] = useState<Step>('credentials');
  const [source, setSource] = useState<SourceInfo | null>(null);
  const [name, setName] = useState('');
  const [authMethod, setAuthMethod] = useState('');
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);

  const { sources, loadSources, createConnector } = useDataSourceStore();

  useEffect(() => {
    loadSources();
  }, []);

  useEffect(() => {
    const found = sources.find((s) => s.source_type === sourceType);
    if (found) {
      setSource(found);
      setAuthMethod(found.default_auth);
      setName(`My ${found.display_name}`);
    }
  }, [sources, sourceType]);

  if (!source) {
    return <div className="p-6 text-gray-400">Loading source info...</div>;
  }

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      await createConnector({
        name,
        source_type: sourceType,
        auth_method: authMethod,
        credentials,
        config,
      });
      window.location.href = '/connections';
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create connector');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <SourceIcon sourceType={source.source_type} size={36} />
        <div>
          <h2 className="text-xl font-bold">Connect {source.display_name}</h2>
          <p className="text-sm text-gray-500">{source.description}</p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="flex gap-1 mb-6">
        {(['credentials', 'config', 'confirm'] as const).map((s, i) => (
          <div
            key={s}
            className={`flex-1 h-1.5 rounded-full ${
              step === s ? 'bg-brand-600' : i < ['credentials', 'config', 'confirm'].indexOf(step) ? 'bg-brand-300' : 'bg-gray-200'
            }`}
          />
        ))}
      </div>

      {/* Step: Credentials */}
      {step === 'credentials' && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="font-medium mb-4">1. Authentication</h3>

          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm mb-4"
          />

          <label className="block text-sm font-medium text-gray-700 mb-1">Auth Method</label>
          <select
            value={authMethod}
            onChange={(e) => setAuthMethod(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm mb-4"
          >
            {source.auth_methods.map((m) => (
              <option key={m} value={m}>
                {m.replace('_', ' ')}
              </option>
            ))}
          </select>

          <CredentialForm
            authMethod={authMethod}
            sourceType={source.source_type}
            credentials={credentials}
            onChange={setCredentials}
          />

          <div className="flex justify-end mt-6">
            <button
              onClick={() => setStep('config')}
              className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* Step: Config */}
      {step === 'config' && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="font-medium mb-4">2. Configuration</h3>

          {Object.entries(source.config_schema).map(([key, field]) => (
            <div key={key} className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {key.replace(/_/g, ' ')}
                {field.required && <span className="text-red-500 ml-1">*</span>}
              </label>
              {field.description && (
                <p className="text-xs text-gray-400 mb-1">{field.description}</p>
              )}
              {field.type === 'boolean' ? (
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!!config[key]}
                    onChange={(e) =>
                      setConfig({ ...config, [key]: e.target.checked })
                    }
                  />
                  <span className="text-sm text-gray-600">Enable</span>
                </label>
              ) : field.type === 'array' ? (
                <input
                  value={(config[key] as string[])?.join(', ') || ''}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      [key]: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                    })
                  }
                  placeholder="Comma-separated values"
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              ) : (
                <input
                  value={String(config[key] ?? field.default ?? '')}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      [key]:
                        field.type === 'number' || field.type === 'integer'
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              )}
            </div>
          ))}

          <div className="flex justify-between mt-6">
            <button
              onClick={() => setStep('credentials')}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep('confirm')}
              className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* Step: Confirm */}
      {step === 'confirm' && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="font-medium mb-4">3. Review & Connect</h3>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-gray-500">Name:</span>{' '}
              <span className="font-medium">{name}</span>
            </div>
            <div>
              <span className="text-gray-500">Source:</span>{' '}
              <span className="font-medium">{source.display_name}</span>
            </div>
            <div>
              <span className="text-gray-500">Auth:</span>{' '}
              <span className="font-medium">{authMethod}</span>
            </div>
            <div>
              <span className="text-gray-500">Config:</span>
              <pre className="mt-1 bg-gray-50 rounded p-2 text-xs overflow-auto">
                {JSON.stringify(config, null, 2)}
              </pre>
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-50 text-red-600 text-sm rounded-lg">{error}</div>
          )}

          <div className="flex justify-between mt-6">
            <button
              onClick={() => setStep('config')}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
            >
              ← Back
            </button>
            <button
              onClick={handleCreate}
              disabled={creating}
              className="px-6 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50"
            >
              {creating ? 'Creating...' : 'Connect'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
