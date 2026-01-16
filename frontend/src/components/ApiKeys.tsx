import { useState, useEffect, useCallback } from 'react';
import { ApiKey, CreateKeyResponse, listApiKeys, createApiKey, deleteApiKey } from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface ApiKeysProps {
  onClose: () => void;
}

export function ApiKeys({ onClose }: ApiKeysProps) {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [expiresInDays, setExpiresInDays] = useState(90);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<CreateKeyResponse | null>(null);
  const [keyToDelete, setKeyToDelete] = useState<ApiKey | null>(null);
  const { addToast } = useToast();

  // Check if form has unsaved changes
  const isDirty = showCreateForm && newKeyName.trim().length > 0;

  // Wrap onClose with dirty state confirmation
  const handleClose = useCallback(() => {
    if (isDirty) {
      if (window.confirm('You have unsaved changes. Discard them?')) {
        onClose();
      }
    } else {
      onClose();
    }
  }, [isDirty, onClose]);

  // Handle ESC key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !keyToDelete && !newlyCreatedKey) {
        handleClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleClose, keyToDelete, newlyCreatedKey]);

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const apiKeys = await listApiKeys();
      setKeys(apiKeys);
    } catch (err) {
      addToast('Failed to load API keys', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);

    try {
      const newKey = await createApiKey(newKeyName, expiresInDays);
      setNewlyCreatedKey(newKey);
      setKeys([newKey, ...keys]);
      setNewKeyName('');
      setShowCreateForm(false);
      addToast('API key created successfully', 'success');
    } catch (err) {
      addToast('Failed to create API key', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!keyToDelete) return;

    try {
      await deleteApiKey(keyToDelete.id);
      setKeys(keys.filter((k) => k.id !== keyToDelete.id));
      setKeyToDelete(null);
      addToast('API key deleted', 'success');
    } catch (err) {
      addToast('Failed to delete API key', 'error');
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const isExpired = (expiresAt: string) => {
    return new Date(expiresAt) < new Date();
  };

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !keyToDelete && !newlyCreatedKey) {
      handleClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">API Keys</h2>
          <button
            onClick={handleClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 overflow-y-auto flex-1">
          {/* Newly Created Key Dialog */}
          {newlyCreatedKey && (
            <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
              <div className="flex items-start gap-3">
                <svg
                  className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div className="flex-1">
                  <h3 className="font-medium text-green-800 dark:text-green-200">
                    API Key Created
                  </h3>
                  <p className="text-sm text-green-700 dark:text-green-300 mt-1">
                    Copy this key now. You won't be able to see it again!
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <code className="flex-1 bg-white dark:bg-gray-900 px-3 py-2 rounded border border-green-300 dark:border-green-700 text-sm font-mono text-gray-900 dark:text-gray-100 break-all">
                      {newlyCreatedKey.key}
                    </code>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(newlyCreatedKey.key);
                        addToast('Copied to clipboard', 'success');
                      }}
                      className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                      Copy
                    </button>
                  </div>
                  <button
                    onClick={() => setNewlyCreatedKey(null)}
                    className="mt-2 text-sm text-green-600 dark:text-green-400 hover:underline"
                  >
                    I've saved the key
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Create Form */}
          {showCreateForm ? (
            <form onSubmit={handleCreate} className="mb-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <h3 className="font-medium text-gray-900 dark:text-white mb-3">Create New API Key</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    required
                    placeholder="e.g., Production Server"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Expires In
                  </label>
                  <select
                    value={expiresInDays}
                    onChange={(e) => setExpiresInDays(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    <option value={30}>30 days</option>
                    <option value={90}>90 days</option>
                    <option value={180}>180 days</option>
                    <option value={365}>1 year</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Key'}
                </button>
              </div>
            </form>
          ) : (
            <button
              onClick={() => setShowCreateForm(true)}
              className="mb-4 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create New Key
            </button>
          )}

          {/* Keys List */}
          {loading ? (
            <div className="flex justify-center py-8">
              <svg
                className="animate-spin h-8 w-8 text-blue-600"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </div>
          ) : keys.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              No API keys yet. Create one to get started.
            </div>
          ) : (
            <div className="space-y-2">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className={`p-4 border rounded-lg ${
                    isExpired(key.expires_at)
                      ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-white">{key.name}</h4>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Created: {formatDate(key.created_at)}
                        {' | '}
                        {isExpired(key.expires_at) ? (
                          <span className="text-red-600 dark:text-red-400">
                            Expired: {formatDate(key.expires_at)}
                          </span>
                        ) : (
                          <>Expires: {formatDate(key.expires_at)}</>
                        )}
                      </p>
                      {key.last_used && (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          Last used: {formatDate(key.last_used)}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={() => setKeyToDelete(key)}
                      className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                    >
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Delete Confirmation Dialog */}
        {keyToDelete && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-60">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-md mx-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Delete API Key?</h3>
              <p className="mt-2 text-gray-600 dark:text-gray-400">
                Are you sure you want to delete "{keyToDelete.name}"? This action cannot be undone.
                Any applications using this key will stop working.
              </p>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  onClick={() => setKeyToDelete(null)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
