import { useState, useEffect } from 'react';
import {
  BuiltinGrokPattern,
  GrokPattern,
  GrokPatternCreate,
  Pattern,
  PatternCreate,
  createGrokPattern,
  createPattern,
  deleteGrokPattern,
  deletePattern,
  listBuiltinGrokPatterns,
  listGrokPatterns,
  listPatterns,
  updateGrokPattern,
  updatePattern,
} from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { HighlightedInput, GROUP_COLORS, Highlight } from './HighlightedInput';
import { usePatternMatch } from '../hooks/usePatternMatch';

interface PatternLibraryProps {
  onClose: () => void;
}

type Tab = 'builtin' | 'custom-grok' | 'patterns';

export function PatternLibrary({ onClose }: PatternLibraryProps) {
  const [activeTab, setActiveTab] = useState<Tab>('builtin');
  const [builtinPatterns, setBuiltinPatterns] = useState<BuiltinGrokPattern[]>([]);
  const [customGrokPatterns, setCustomGrokPatterns] = useState<GrokPattern[]>([]);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddGrokModal, setShowAddGrokModal] = useState(false);
  const [showAddPatternModal, setShowAddPatternModal] = useState(false);
  const [editingGrok, setEditingGrok] = useState<GrokPattern | null>(null);
  const [editingPattern, setEditingPattern] = useState<Pattern | null>(null);
  const { addToast } = useToast();

  useEffect(() => {
    loadAllPatterns();
  }, []);

  const loadAllPatterns = async () => {
    setLoading(true);
    try {
      const [builtin, customGrok, customPatterns] = await Promise.all([
        listBuiltinGrokPatterns(),
        listGrokPatterns(),
        listPatterns(),
      ]);
      setBuiltinPatterns(builtin);
      setCustomGrokPatterns(customGrok);
      setPatterns(customPatterns);
    } catch (error) {
      addToast(
        error instanceof Error ? error.message : 'Failed to load patterns',
        'error'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteGrok = async (id: string) => {
    if (!confirm('Are you sure you want to delete this grok pattern?')) return;
    try {
      await deleteGrokPattern(id);
      setCustomGrokPatterns((prev) => prev.filter((p) => p.id !== id));
      addToast('Grok pattern deleted', 'success');
    } catch (error) {
      addToast(
        error instanceof Error ? error.message : 'Failed to delete pattern',
        'error'
      );
    }
  };

  const handleDeletePattern = async (id: string) => {
    if (!confirm('Are you sure you want to delete this pattern?')) return;
    try {
      await deletePattern(id);
      setPatterns((prev) => prev.filter((p) => p.id !== id));
      addToast('Pattern deleted', 'success');
    } catch (error) {
      addToast(
        error instanceof Error ? error.message : 'Failed to delete pattern',
        'error'
      );
    }
  };

  const filteredBuiltin = builtinPatterns.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredCustomGrok = customGrokPatterns.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.description?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false)
  );

  const filteredPatterns = patterns.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.description?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false)
  );

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Pattern Library
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b dark:border-gray-700">
          <button
            onClick={() => setActiveTab('builtin')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'builtin'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Built-in Grok ({builtinPatterns.length})
          </button>
          <button
            onClick={() => setActiveTab('custom-grok')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'custom-grok'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Custom Grok ({customGrokPatterns.length})
          </button>
          <button
            onClick={() => setActiveTab('patterns')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'patterns'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Parsing Patterns ({patterns.length})
          </button>
        </div>

        {/* Search and Add */}
        <div className="flex items-center gap-4 p-4">
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="Search patterns..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400"
            />
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          {activeTab === 'custom-grok' && (
            <button
              onClick={() => setShowAddGrokModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Grok Pattern
            </button>
          )}
          {activeTab === 'patterns' && (
            <button
              onClick={() => setShowAddPatternModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Pattern
            </button>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            </div>
          ) : activeTab === 'builtin' ? (
            <BuiltinPatternList patterns={filteredBuiltin} />
          ) : activeTab === 'custom-grok' ? (
            <CustomGrokPatternList
              patterns={filteredCustomGrok}
              onEdit={setEditingGrok}
              onDelete={handleDeleteGrok}
            />
          ) : (
            <PatternList
              patterns={filteredPatterns}
              onEdit={setEditingPattern}
              onDelete={handleDeletePattern}
            />
          )}
        </div>
      </div>

      {/* Add/Edit Grok Modal */}
      {(showAddGrokModal || editingGrok) && (
        <GrokPatternModal
          pattern={editingGrok}
          onClose={() => {
            setShowAddGrokModal(false);
            setEditingGrok(null);
          }}
          onSave={async (data) => {
            try {
              if (editingGrok) {
                const updated = await updateGrokPattern(editingGrok.id, {
                  regex: data.regex,
                  description: data.description,
                });
                setCustomGrokPatterns((prev) =>
                  prev.map((p) => (p.id === editingGrok.id ? updated : p))
                );
                addToast('Grok pattern updated', 'success');
              } else {
                const created = await createGrokPattern(data);
                setCustomGrokPatterns((prev) => [...prev, created]);
                addToast('Grok pattern created', 'success');
              }
              setShowAddGrokModal(false);
              setEditingGrok(null);
            } catch (error) {
              addToast(
                error instanceof Error ? error.message : 'Failed to save pattern',
                'error'
              );
            }
          }}
        />
      )}

      {/* Add/Edit Pattern Modal */}
      {(showAddPatternModal || editingPattern) && (
        <PatternModal
          pattern={editingPattern}
          onClose={() => {
            setShowAddPatternModal(false);
            setEditingPattern(null);
          }}
          onSave={(savedPattern) => {
            if (editingPattern) {
              setPatterns((prev) =>
                prev.map((p) => (p.id === editingPattern.id ? savedPattern : p))
              );
              addToast('Pattern updated', 'success');
            } else {
              setPatterns((prev) => [...prev, savedPattern]);
              addToast('Pattern created', 'success');
            }
            setShowAddPatternModal(false);
            setEditingPattern(null);
          }}
        />
      )}
    </div>
  );
}

// Built-in grok patterns list (read-only)
function BuiltinPatternList({ patterns }: { patterns: BuiltinGrokPattern[] }) {
  const [copiedName, setCopiedName] = useState<string | null>(null);

  const copyToClipboard = (name: string) => {
    navigator.clipboard.writeText(`%{${name}}`);
    setCopiedName(name);
    setTimeout(() => setCopiedName(null), 2000);
  };

  if (patterns.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No patterns found
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {patterns.map((pattern) => (
        <div
          key={pattern.name}
          className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <code className="text-sm font-mono font-semibold text-blue-600 dark:text-blue-400">
                  %{'{' + pattern.name + '}'}
                </code>
                <button
                  onClick={() => copyToClipboard(pattern.name)}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                  title="Copy to clipboard"
                >
                  {copiedName === pattern.name ? (
                    <svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  )}
                </button>
              </div>
              {pattern.description && (
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {pattern.description}
                </p>
              )}
              <code className="mt-2 block text-xs font-mono text-gray-500 dark:text-gray-400 truncate">
                {pattern.regex}
              </code>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Custom grok patterns list (editable)
function CustomGrokPatternList({
  patterns,
  onEdit,
  onDelete,
}: {
  patterns: GrokPattern[];
  onEdit: (pattern: GrokPattern) => void;
  onDelete: (id: string) => void;
}) {
  if (patterns.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No custom grok patterns. Click "Add Grok Pattern" to create one.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {patterns.map((pattern) => (
        <div
          key={pattern.id}
          className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <code className="text-sm font-mono font-semibold text-blue-600 dark:text-blue-400">
                %{'{' + pattern.name + '}'}
              </code>
              {pattern.description && (
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {pattern.description}
                </p>
              )}
              <code className="mt-2 block text-xs font-mono text-gray-500 dark:text-gray-400 truncate">
                {pattern.regex}
              </code>
              <p className="mt-2 text-xs text-gray-400">
                Created by {pattern.created_by} on{' '}
                {new Date(pattern.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onEdit(pattern)}
                className="p-2 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
                title="Edit"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                onClick={() => onDelete(pattern.id)}
                className="p-2 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
                title="Delete"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Custom parsing patterns list (editable)
function PatternList({
  patterns,
  onEdit,
  onDelete,
}: {
  patterns: Pattern[];
  onEdit: (pattern: Pattern) => void;
  onDelete: (id: string) => void;
}) {
  if (patterns.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No custom patterns. Click "Add Pattern" to create one.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {patterns.map((pattern) => (
        <div
          key={pattern.id}
          className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-900 dark:text-white">
                  {pattern.name}
                </span>
                <span
                  className={`px-2 py-0.5 text-xs rounded ${
                    pattern.type === 'grok'
                      ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                      : 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  }`}
                >
                  {pattern.type}
                </span>
              </div>
              {pattern.description && (
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {pattern.description}
                </p>
              )}
              <code className="mt-2 block text-xs font-mono text-gray-500 dark:text-gray-400 truncate">
                {pattern.pattern}
              </code>
              <p className="mt-2 text-xs text-gray-400">
                Created by {pattern.created_by} on{' '}
                {new Date(pattern.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onEdit(pattern)}
                className="p-2 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
                title="Edit"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                onClick={() => onDelete(pattern.id)}
                className="p-2 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
                title="Delete"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Modal for adding/editing grok patterns
function GrokPatternModal({
  pattern,
  onClose,
  onSave,
}: {
  pattern: GrokPattern | null;
  onClose: () => void;
  onSave: (data: GrokPatternCreate) => Promise<void>;
}) {
  const [name, setName] = useState(pattern?.name || '');
  const [regex, setRegex] = useState(pattern?.regex || '');
  const [description, setDescription] = useState(pattern?.description || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track if form has unsaved changes
  const isDirty =
    name !== (pattern?.name || '') ||
    regex !== (pattern?.regex || '') ||
    description !== (pattern?.description || '');

  const handleClose = () => {
    if (isDirty && !confirm('You have unsaved changes. Are you sure you want to close?')) {
      return;
    }
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      await onSave({ name, regex, description: description || undefined });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full mx-4 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {pattern ? 'Edit Grok Pattern' : 'Add Grok Pattern'}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400 rounded-md">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Pattern Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
              placeholder="MY_PATTERN"
              required
              disabled={!!pattern}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Uppercase letters, numbers, and underscores only
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Regex Pattern
            </label>
            <input
              type="text"
              value={regex}
              onChange={(e) => setRegex(e.target.value)}
              placeholder="[a-zA-Z0-9_]+"
              required
              className="w-full px-3 py-2 font-mono text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description (optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this pattern matches"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : pattern ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Modal for adding/editing parsing patterns
interface PatternModalProps {
  pattern?: Pattern | null;
  onClose: () => void;
  onSave: (pattern: Pattern) => void;
  initialTestSample?: string;
}

export function PatternModal({
  pattern,
  onClose,
  onSave,
  initialTestSample,
}: PatternModalProps) {
  const [name, setName] = useState(pattern?.name || '');
  const [type, setType] = useState<'regex' | 'grok'>(pattern?.type || 'grok');
  const [patternStr, setPatternStr] = useState(pattern?.pattern || '');
  const [description, setDescription] = useState(pattern?.description || '');
  const [testSample, setTestSample] = useState(initialTestSample || pattern?.test_sample || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live pattern matching
  const { result: matchResult, error: matchError, loading: matchLoading } = usePatternMatch(
    patternStr,
    testSample,
    type
  );

  // Convert match result to highlights
  const highlights: Highlight[] = matchResult?.groups.map((group, idx) => ({
    start: group.start,
    end: group.end,
    colorIndex: idx,
  })) || [];

  // Track if form has unsaved changes
  const isDirty =
    name !== (pattern?.name || '') ||
    type !== (pattern?.type || 'grok') ||
    patternStr !== (pattern?.pattern || '') ||
    description !== (pattern?.description || '') ||
    testSample !== (pattern?.test_sample || '');

  const handleClose = () => {
    if (isDirty && !confirm('You have unsaved changes. Are you sure you want to close?')) {
      return;
    }
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      const data: PatternCreate = {
        name,
        type,
        pattern: patternStr,
        description: description || undefined,
        test_sample: testSample || undefined,
      };

      let result: Pattern;
      if (pattern) {
        result = await updatePattern(pattern.id, data);
      } else {
        result = await createPattern(data);
      }
      onSave(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 max-h-[90vh] overflow-auto">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {pattern ? 'Edit Pattern' : 'Add Pattern'}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400 rounded-md">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Pattern Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Pattern"
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Pattern Type
              </label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as 'regex' | 'grok')}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                <option value="grok">Grok</option>
                <option value="regex">Regex</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Pattern
            </label>
            <textarea
              value={patternStr}
              onChange={(e) => setPatternStr(e.target.value)}
              placeholder={type === 'grok' ? '%{IP:client} - %{USER:user} \\[%{HTTPDATE:timestamp}\\]' : '(?P<client>[\\d.]+) - (?P<user>\\S+)'}
              required
              rows={3}
              className="w-full px-3 py-2 font-mono text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
            {type === 'grok' ? (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Use %{'{PATTERN:field}'} syntax. See Built-in Grok tab for available patterns.
              </p>
            ) : (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Python regex syntax. Named groups: {'(?P<name>...)'}. PCRE syntax {'(?<name>...)'} is auto-converted.
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description (optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this pattern is for"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>

          {/* Test Sample with Live Highlighting */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Test Sample
              {matchLoading && (
                <span className="ml-2 text-xs text-gray-500">(matching...)</span>
              )}
            </label>
            <HighlightedInput
              value={testSample}
              onChange={setTestSample}
              highlights={highlights}
              placeholder="192.168.1.1 - admin [17/Jan/2026:10:00:00 +0000]"
              rows={2}
            />
          </div>

          {/* Match Results Legend */}
          {matchResult && matchResult.groups.length > 0 && (
            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Captured Groups
              </label>
              <div className="bg-gray-50 dark:bg-gray-800 rounded-md p-3 space-y-2">
                {matchResult.groups.map((group, idx) => (
                  <div key={group.name} className="flex items-center gap-2 text-sm">
                    <span
                      className={`w-3 h-3 rounded ${GROUP_COLORS[idx % GROUP_COLORS.length]}`}
                    />
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {group.name}:
                    </span>
                    <code className="text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-1 rounded">
                      {group.value}
                    </code>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No match indicator */}
          {testSample && patternStr && !matchResult && !matchError && !matchLoading && (
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Pattern does not match the test sample
            </div>
          )}

          {/* Error display */}
          {matchError && (
            <div className="text-sm text-red-600 dark:text-red-400">
              {matchError}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : pattern ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
