import { useState, useEffect, useCallback } from 'react';
import {
  CustomEcsMapping,
  listCustomEcsMappings,
  createCustomEcsMapping,
  deleteCustomEcsMapping,
  getEcsFields,
  EcsField,
} from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface CustomEcsMappingsProps {
  onClose: () => void;
}

export function CustomEcsMappings({ onClose }: CustomEcsMappingsProps) {
  const [mappings, setMappings] = useState<CustomEcsMapping[]>([]);
  const [ecsFields, setEcsFields] = useState<Record<string, EcsField>>({});
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { addToast } = useToast();

  // Create form state
  const [sourcePattern, setSourcePattern] = useState('');
  const [ecsField, setEcsField] = useState('');
  const [creating, setCreating] = useState(false);

  // Check if form has unsaved changes
  const isCreateDirty = showCreateForm && (sourcePattern.trim() || ecsField.trim());

  // Wrap onClose with dirty state confirmation
  const handleClose = useCallback(() => {
    if (isCreateDirty) {
      if (window.confirm('You have unsaved changes. Discard them?')) {
        onClose();
      }
    } else {
      onClose();
    }
  }, [isCreateDirty, onClose]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showCreateForm) {
          if (isCreateDirty) {
            if (window.confirm('You have unsaved changes. Discard them?')) {
              setShowCreateForm(false);
              setSourcePattern('');
              setEcsField('');
            }
          } else {
            setShowCreateForm(false);
          }
          return;
        }
        handleClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleClose, showCreateForm, isCreateDirty]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [mappingsList, fields] = await Promise.all([
        listCustomEcsMappings(),
        getEcsFields(),
      ]);
      setMappings(mappingsList);
      setEcsFields(fields);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to load data', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);

    try {
      const newMapping = await createCustomEcsMapping({
        source_pattern: sourcePattern.trim(),
        ecs_field: ecsField.trim(),
      });
      setMappings([newMapping, ...mappings]);
      setSourcePattern('');
      setEcsField('');
      setShowCreateForm(false);
      addToast('Custom ECS mapping created', 'success');
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to create mapping', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (mapping: CustomEcsMapping) => {
    if (!confirm(`Delete mapping "${mapping.source_pattern}" -> "${mapping.ecs_field}"?`)) {
      return;
    }

    try {
      await deleteCustomEcsMapping(mapping.id);
      setMappings(mappings.filter((m) => m.id !== mapping.id));
      addToast('Mapping deleted', 'success');
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to delete mapping', 'error');
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Get sorted list of ECS fields for autocomplete
  const ecsFieldOptions = Object.keys(ecsFields).sort();

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !showCreateForm) {
      handleClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Custom ECS Mappings
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Define custom field-to-ECS mappings for your organization
            </p>
          </div>
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
          {/* Create Form */}
          {showCreateForm ? (
            <form onSubmit={handleCreate} className="mb-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <h3 className="font-medium text-gray-900 dark:text-white mb-3">Add New Mapping</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Source Field Pattern
                  </label>
                  <input
                    type="text"
                    value={sourcePattern}
                    onChange={(e) => setSourcePattern(e.target.value)}
                    required
                    placeholder="e.g., fw_src_addr"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Case-insensitive field name to match
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    ECS Field
                  </label>
                  <input
                    type="text"
                    value={ecsField}
                    onChange={(e) => setEcsField(e.target.value)}
                    required
                    placeholder="e.g., source.ip"
                    list="ecs-fields"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                  <datalist id="ecs-fields">
                    {ecsFieldOptions.map((field) => (
                      <option key={field} value={field} />
                    ))}
                  </datalist>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Target ECS field name
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateForm(false);
                    setSourcePattern('');
                    setEcsField('');
                  }}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Add Mapping'}
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
              Add Mapping
            </button>
          )}

          {/* Mappings List */}
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
          ) : mappings.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>No custom mappings defined.</p>
              <p className="text-sm mt-1">
                Custom mappings allow you to define organization-specific field-to-ECS mappings
                that will be suggested when users click "Apply ECS" during upload configuration.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-12 gap-2 px-4 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <div className="col-span-4">Source Pattern</div>
                <div className="col-span-4">ECS Field</div>
                <div className="col-span-3">Created</div>
                <div className="col-span-1"></div>
              </div>
              {mappings.map((mapping) => (
                <div
                  key={mapping.id}
                  className="grid grid-cols-12 gap-2 items-center px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                >
                  <div className="col-span-4">
                    <code className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-sm text-gray-900 dark:text-white">
                      {mapping.source_pattern}
                    </code>
                  </div>
                  <div className="col-span-4">
                    <code className="px-2 py-1 bg-blue-100 dark:bg-blue-900/50 rounded text-sm text-blue-700 dark:text-blue-300">
                      {mapping.ecs_field}
                    </code>
                  </div>
                  <div className="col-span-3 text-sm text-gray-500 dark:text-gray-400">
                    {formatDate(mapping.created_at)}
                  </div>
                  <div className="col-span-1 flex justify-end">
                    <button
                      onClick={() => handleDelete(mapping)}
                      className="p-2 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
                      title="Delete mapping"
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

        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Custom mappings take precedence over built-in ECS mappings.
            They are applied globally when any user clicks "Apply ECS" during upload configuration.
          </p>
        </div>
      </div>
    </div>
  );
}
