import { useState, useEffect } from 'react';
import { FieldInfo, FileFormat, UploadResponse, reparseUpload, listPatterns, Pattern } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { PatternModal } from './PatternLibrary';

interface PreviewProps {
  data: UploadResponse;
  onBack: () => void;
  onContinue: () => void;
  onDataUpdate?: (data: UploadResponse) => void;
}

// All supported file formats
const FILE_FORMATS: { value: FileFormat | 'custom'; label: string }[] = [
  { value: 'json_array', label: 'JSON Array' },
  { value: 'ndjson', label: 'NDJSON' },
  { value: 'csv', label: 'CSV' },
  { value: 'tsv', label: 'TSV' },
  { value: 'ltsv', label: 'LTSV' },
  { value: 'syslog', label: 'Syslog' },
  { value: 'logfmt', label: 'Logfmt' },
  { value: 'raw', label: 'Raw Lines' },
  { value: 'custom', label: 'Custom Pattern...' },
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatFileFormat(format: string): string {
  const found = FILE_FORMATS.find((f) => f.value === format);
  return found ? found.label : format;
}

function getTypeColor(type: string): string {
  switch (type) {
    case 'integer':
    case 'float':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    case 'boolean':
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    case 'object':
    case 'array':
      return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200';
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  }
}

function FieldBadge({ field }: { field: FieldInfo }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-medium text-gray-900 dark:text-white">{field.name}</span>
      <span className={`px-2 py-0.5 text-xs rounded ${getTypeColor(field.type)}`}>
        {field.type}
      </span>
    </div>
  );
}

const MULTILINE_PRESETS = [
  { label: 'Timestamp (ISO)', value: '^\\d{4}-\\d{2}-\\d{2}' },
  { label: 'Timestamp (Syslog)', value: '^[A-Z][a-z]{2}\\s+\\d+' },
  { label: 'Non-whitespace start', value: '^\\S' },
];

export function Preview({ data, onBack, onContinue, onDataUpdate }: PreviewProps) {
  const { filename, file_size, file_format, preview, fields, upload_id, raw_preview } = data;
  const [selectedFormat, setSelectedFormat] = useState<FileFormat | 'custom'>(file_format);
  const [isReparsing, setIsReparsing] = useState(false);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [selectedPatternId, setSelectedPatternId] = useState<string | null>(null);
  const [showPatternModal, setShowPatternModal] = useState(false);
  const [multilineEnabled, setMultilineEnabled] = useState(false);
  const [multilineStart, setMultilineStart] = useState('');
  const [isCustomMultilinePattern, setIsCustomMultilinePattern] = useState(false);
  const { addToast } = useToast();

  // Load patterns when custom format is selected
  useEffect(() => {
    if (selectedFormat === 'custom') {
      listPatterns().then(setPatterns).catch(console.error);
    }
  }, [selectedFormat]);

  // Refresh patterns when dropdown is focused (in case patterns were deleted elsewhere)
  const handlePatternDropdownFocus = () => {
    listPatterns().then(setPatterns).catch(console.error);
  };

  const handleFormatChange = async (newFormat: FileFormat | 'custom') => {
    if (newFormat === selectedFormat) return;

    // If switching away from custom, clear pattern selection
    if (newFormat !== 'custom') {
      setSelectedPatternId(null);
    }

    // Clear multiline state when switching to non-multiline formats
    if (!['raw', 'logfmt', 'custom'].includes(newFormat)) {
      setMultilineEnabled(false);
      setMultilineStart('');
      setIsCustomMultilinePattern(false);
    }

    setSelectedFormat(newFormat);

    // Don't reparse yet if custom - wait for pattern selection
    if (newFormat === 'custom') {
      return;
    }

    setIsReparsing(true);

    try {
      const result = await reparseUpload(upload_id, newFormat);
      // Update the parent with new preview data
      if (onDataUpdate) {
        onDataUpdate({
          ...data,
          file_format: result.file_format as FileFormat,
          preview: result.preview,
          fields: result.fields,
          raw_preview: result.raw_preview || data.raw_preview,
        });
      }
      addToast(`File reparsed as ${formatFileFormat(newFormat)}`, 'success');
    } catch (error) {
      // Revert format selection on error
      setSelectedFormat(file_format);
      addToast(
        error instanceof Error ? error.message : 'Failed to reparse file',
        'error'
      );
    } finally {
      setIsReparsing(false);
    }
  };

  const handlePatternChange = async (patternId: string) => {
    if (patternId === 'new') {
      setShowPatternModal(true);
      return;
    }

    setSelectedPatternId(patternId);
    setIsReparsing(true);

    try {
      const result = await reparseUpload(upload_id, 'custom', patternId);
      // Update the parent with new preview data
      if (onDataUpdate) {
        onDataUpdate({
          ...data,
          file_format: result.file_format as FileFormat,
          preview: result.preview,
          fields: result.fields,
          raw_preview: result.raw_preview || data.raw_preview,
        });
      }
      addToast('File reparsed with custom pattern', 'success');
    } catch (error) {
      addToast(error instanceof Error ? error.message : 'Failed to reparse file', 'error');
      setSelectedPatternId(null);
    } finally {
      setIsReparsing(false);
    }
  };

  const handlePatternCreated = async (pattern: Pattern) => {
    setShowPatternModal(false);
    setPatterns(prev => [...prev, pattern]);
    await handlePatternChange(pattern.id);
  };

  const handleReparse = async () => {
    setIsReparsing(true);
    try {
      const result = await reparseUpload(
        upload_id,
        selectedFormat,
        selectedPatternId || undefined,
        multilineEnabled ? multilineStart : undefined
      );
      if (onDataUpdate) {
        onDataUpdate({
          ...data,
          file_format: result.file_format as FileFormat,
          preview: result.preview,
          fields: result.fields,
          raw_preview: result.raw_preview || data.raw_preview,
        });
      }
      addToast('Preview updated', 'success');
    } catch (error) {
      addToast(error instanceof Error ? error.message : 'Failed to reparse', 'error');
    } finally {
      setIsReparsing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* File info header */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{filename}</h2>
            <div className="mt-1 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <span>{formatFileSize(file_size)}</span>
              {/* Format dropdown */}
              <div className="relative inline-block">
                <select
                  value={selectedFormat}
                  onChange={(e) => handleFormatChange(e.target.value as FileFormat | 'custom')}
                  disabled={isReparsing}
                  className="appearance-none px-3 py-0.5 pr-8 bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200 rounded border-0 text-sm font-medium cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {FILE_FORMATS.map((format) => (
                    <option key={format.value} value={format.value}>
                      {format.label}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                  {isReparsing ? (
                    <svg className="animate-spin h-4 w-4 text-indigo-600 dark:text-indigo-300" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  ) : (
                    <svg className="h-4 w-4 text-indigo-600 dark:text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  )}
                </div>
              </div>
              {/* Pattern selector - shown when Custom Pattern is selected */}
              {selectedFormat === 'custom' && (
                <select
                  value={selectedPatternId || ''}
                  onChange={(e) => handlePatternChange(e.target.value)}
                  onFocus={handlePatternDropdownFocus}
                  className="px-2 py-0.5 bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 rounded text-sm"
                  disabled={isReparsing}
                >
                  <option value="">Select pattern...</option>
                  {patterns.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.type})
                    </option>
                  ))}
                  <option value="new">+ Create New Pattern</option>
                </select>
              )}
              <span>{preview.length} records previewed</span>
            </div>
          </div>
          <button
            onClick={onBack}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Upload Different File
          </button>
        </div>

        {/* Multiline toggle - only for raw/logfmt/custom */}
        {['raw', 'logfmt', 'custom'].includes(selectedFormat) && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={multilineEnabled}
                onChange={(e) => setMultilineEnabled(e.target.checked)}
                className="rounded"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-200">Multi-line mode</span>
            </label>

            {multilineEnabled && (
              <div className="mt-2 space-y-2">
                <select
                  value={isCustomMultilinePattern ? 'custom' : (MULTILINE_PRESETS.find(p => p.value === multilineStart)?.value ?? '')}
                  onChange={(e) => {
                    if (e.target.value === 'custom') {
                      setIsCustomMultilinePattern(true);
                      setMultilineStart('');
                    } else {
                      setIsCustomMultilinePattern(false);
                      setMultilineStart(e.target.value);
                    }
                  }}
                  className="w-full px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                >
                  <option value="">Select pattern...</option>
                  {MULTILINE_PRESETS.map(preset => (
                    <option key={preset.label} value={preset.value}>
                      {preset.label}
                    </option>
                  ))}
                  <option value="custom">Custom...</option>
                </select>

                {isCustomMultilinePattern && (
                  <input
                    type="text"
                    value={multilineStart}
                    onChange={(e) => setMultilineStart(e.target.value)}
                    placeholder="^\\d{4}-\\d{2}-\\d{2}"
                    className="w-full px-2 py-1 text-sm font-mono border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                )}

                <button
                  onClick={handleReparse}
                  disabled={!multilineStart || isReparsing}
                  className="px-3 py-1 text-sm bg-blue-600 text-white rounded disabled:opacity-50 hover:bg-blue-700"
                >
                  Apply
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Detected fields */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">Detected Fields ({fields.length})</h3>
        <div className="flex flex-wrap gap-3">
          {fields.map((field) => (
            <FieldBadge key={field.name} field={field} />
          ))}
        </div>
      </div>

      {/* Data table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                {fields.map((field) => (
                  <th
                    key={field.name}
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap"
                  >
                    {field.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {preview.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  {fields.map((field) => (
                    <td
                      key={field.name}
                      className="px-4 py-2 text-sm text-gray-900 dark:text-white whitespace-nowrap max-w-xs truncate"
                      title={String(row[field.name] ?? '')}
                    >
                      {formatCellValue(row[field.name])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Action buttons - sticky at bottom */}
      <div className="sticky bottom-0 bg-gray-100 dark:bg-gray-900 py-4 -mx-4 px-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex justify-end">
          <button
            onClick={onContinue}
            className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700"
          >
            Continue to Configure
          </button>
        </div>
      </div>

      {/* Pattern creation modal */}
      {showPatternModal && (
        <PatternModal
          onClose={() => setShowPatternModal(false)}
          onSave={handlePatternCreated}
          initialTestSample={
            raw_preview?.[0] ||
            preview[0]?.raw_message as string ||
            JSON.stringify(preview[0], null, 2)
          }
        />
      )}
    </div>
  );
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}
