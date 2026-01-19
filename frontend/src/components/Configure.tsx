import { useState, useMemo, useEffect } from 'react';
import {
  cancelIngest,
  FieldInfo,
  FieldTransform,
  IngestResponse,
  ProgressEvent,
  startIngest,
  subscribeToProgress,
  suggestEcs,
  UploadResponse,
} from '../api/client';
import { useToast } from '../contexts/ToastContext';

// Available transforms that can be applied to fields
const AVAILABLE_TRANSFORMS = [
  { name: 'lowercase', label: 'Lowercase', options: [] as string[] },
  { name: 'uppercase', label: 'Uppercase', options: [] as string[] },
  { name: 'trim', label: 'Trim Whitespace', options: [] as string[] },
  { name: 'truncate', label: 'Truncate', options: ['max_length'] },
  { name: 'regex_extract', label: 'Regex Extract', options: ['pattern'] },
  { name: 'regex_replace', label: 'Regex Replace', options: ['pattern', 'replacement'] },
  { name: 'base64_decode', label: 'Base64 Decode', options: [] as string[] },
  { name: 'url_decode', label: 'URL Decode', options: [] as string[] },
  { name: 'hash_sha256', label: 'SHA256 Hash', options: [] as string[] },
  { name: 'mask_email', label: 'Mask Email', options: [] as string[] },
  { name: 'mask_ip', label: 'Mask IP', options: [] as string[] },
  { name: 'default', label: 'Default Value', options: ['default_value'] },
  { name: 'parse_json', label: 'Parse JSON', options: ['path'] },
  { name: 'parse_kv', label: 'Parse Key=Value', options: ['delimiter', 'separator'] },
];

interface ConfigureProps {
  data: UploadResponse;
  onBack: () => void;
  onComplete: (result: IngestResponse) => void;
  onReset: () => void;
}

const INDEX_PREFIX = 'shipit-';

// Keywords that suggest a field is a timestamp (must be whole words or clear suffixes)
const TIMESTAMP_KEYWORDS = ['time', 'date', 'created', 'updated', 'timestamp', 'datetime', 'createdat', 'updatedat', 'startedat', 'endedat'];

// Patterns that look like timestamps (string formats only - numeric epochs handled separately)
const TIMESTAMP_PATTERNS = [
  /^\d{4}-\d{2}-\d{2}/, // ISO date start (2024-01-15)
  /^\d{2}\/\w{3}\/\d{4}/, // Nginx/Apache CLF (15/Jan/2024)
  /T\d{2}:\d{2}/, // ISO datetime contains T00:00
  /^\d{4}\/\d{2}\/\d{2}/, // Slash date (2024/01/15)
  /^\w{3}\s+\d{1,2},?\s+\d{4}/, // Month day year (Jan 15, 2024)
];

function looksLikeTimestamp(value: unknown): boolean {
  if (value === null || value === undefined) return false;

  // Numeric values: must be in valid epoch range (year 2001 to 2100)
  // This prevents false positives from fields like Duration, ContentSize, Status codes
  if (typeof value === 'number') {
    // Epoch seconds: 1000000000 (Sep 2001) to 4102444800 (Jan 2100)
    // Epoch milliseconds: 1000000000000 (Sep 2001) to 4102444800000 (Jan 2100)
    const isEpochSeconds = value >= 1000000000 && value < 4102444800;
    const isEpochMillis = value >= 1000000000000 && value < 4102444800000;
    return isEpochSeconds || isEpochMillis;
  }

  const str = String(value).trim();
  if (!str) return false;

  // Reject pure numeric strings that are too short (< 10 digits) or too long (> 13 digits)
  // This prevents matching HTTP status codes (200), content sizes, etc.
  if (/^\d+$/.test(str)) {
    const len = str.length;
    if (len < 10 || len > 13) return false;
    // Also check the numeric range for string epochs
    const num = parseInt(str, 10);
    const isEpochSeconds = num >= 1000000000 && num < 4102444800;
    const isEpochMillis = num >= 1000000000000 && num < 4102444800000;
    return isEpochSeconds || isEpochMillis;
  }

  return TIMESTAMP_PATTERNS.some(pattern => pattern.test(str));
}

function isLikelyTimestampField(fieldName: string, sampleValues: unknown[]): boolean {
  const nameLower = fieldName.toLowerCase();

  // Check if field name contains timestamp keywords
  const hasTimestampName = TIMESTAMP_KEYWORDS.some(keyword => nameLower.includes(keyword));

  // Get valid sample values
  const validSamples = sampleValues.filter(v => v !== null && v !== undefined && String(v).trim() !== '');

  // If name suggests timestamp, verify at least some values look like timestamps
  if (hasTimestampName && validSamples.length > 0) {
    const timestampCount = validSamples.filter(looksLikeTimestamp).length;
    return timestampCount >= validSamples.length * 0.5;
  }

  // If name doesn't suggest timestamp, require stronger value evidence
  if (validSamples.length > 0) {
    const timestampCount = validSamples.filter(looksLikeTimestamp).length;
    // At least 80% of values should look like timestamps
    return timestampCount >= validSamples.length * 0.8;
  }

  return false;
}

// IP address regex - matches IPv4 and IPv6
const IP_PATTERN = /^(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)){3}|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,7}:|::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4})$/;

function looksLikeIpValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  const str = String(value).trim();
  return IP_PATTERN.test(str);
}

// Helper to detect IP fields - checks sample values only
function isLikelyIpField(_fieldName: string, sampleValues: unknown[]): boolean {
  const validSamples = sampleValues.filter(v =>
    v !== null && v !== undefined && String(v).trim() !== ''
  );
  if (validSamples.length === 0) return false;

  // At least 50% of non-empty samples should look like IPs
  const ipCount = validSamples.filter(looksLikeIpValue).length;
  return ipCount >= validSamples.length * 0.5;
}

interface FieldMapping {
  originalName: string;
  mappedName: string;
  excluded: boolean;
}

interface ProgressState {
  processed: number;
  total: number;
  success: number;
  failed: number;
  records_per_second: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
}

export function Configure({ data, onBack, onComplete, onReset }: ConfigureProps) {
  const { addToast } = useToast();
  const [indexName, setIndexName] = useState('');
  const [timestampField, setTimestampField] = useState<string | null>(null);
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>(
    data.fields.map((f) => ({
      originalName: f.name,
      mappedName: f.name,
      excluded: false,
    }))
  );
  const [isIngesting, setIsIngesting] = useState(false);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [includeFilename, setIncludeFilename] = useState(false);
  const [filenameField, setFilenameField] = useState('source_file');
  const [fieldTypes, setFieldTypes] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    data.fields.forEach(f => {
      initial[f.name] = f.type;
    });
    return initial;
  });
  const [fieldTransforms, setFieldTransforms] = useState<Record<string, FieldTransform[]>>({});

  // GeoIP and ECS mapping state
  const [geoipFields, setGeoipFields] = useState<string[]>([]);
  const [geoipAvailable, setGeoipAvailable] = useState(false);
  const [ecsSuggestions, setEcsSuggestions] = useState<Record<string, string>>({});

  const setFieldType = (fieldName: string, type: string) => {
    setFieldTypes(prev => ({ ...prev, [fieldName]: type }));
  };

  const addTransform = (fieldName: string, transformName: string) => {
    setFieldTransforms(prev => ({
      ...prev,
      [fieldName]: [...(prev[fieldName] || []), { name: transformName }]
    }));
  };

  const removeTransform = (fieldName: string, index: number) => {
    setFieldTransforms(prev => ({
      ...prev,
      [fieldName]: prev[fieldName].filter((_, i) => i !== index)
    }));
  };

  const updateTransformOption = (fieldName: string, index: number, option: string, value: string | number) => {
    setFieldTransforms(prev => ({
      ...prev,
      [fieldName]: prev[fieldName].map((t, i) =>
        i === index ? { ...t, [option]: value } : t
      )
    }));
  };

  // Fetch ECS suggestions on mount
  useEffect(() => {
    if (data.upload_id) {
      suggestEcs(data.upload_id)
        .then((response) => {
          setGeoipAvailable(response.geoip_available);
          setEcsSuggestions(response.suggestions);
        })
        .catch((err) => {
          console.warn('Failed to fetch ECS suggestions:', err);
        });
    }
  }, [data.upload_id]);

  // Track if form has been modified
  const isDirty = useMemo(() => {
    if (indexName.trim()) return true;
    if (timestampField !== null) return true;
    if (includeFilename) return true;
    if (filenameField !== 'source_file') return true;
    // Check if any field mappings have changed
    if (fieldMappings.some(
      (f, i) => f.excluded || f.mappedName !== data.fields[i].name
    )) return true;
    // Check if any field types have changed
    if (data.fields.some(f => fieldTypes[f.name] !== f.type)) return true;
    // Check if any field has transforms
    if (Object.keys(fieldTransforms).some(k => fieldTransforms[k]?.length > 0)) return true;
    return false;
  }, [indexName, timestampField, includeFilename, filenameField, fieldMappings, fieldTypes, fieldTransforms, data.fields]);

  const handleBack = () => {
    if (isDirty && !isIngesting) {
      if (window.confirm('You have unsaved configuration changes. Discard them?')) {
        onBack();
      }
    } else {
      onBack();
    }
  };

  const handleFieldNameChange = (index: number, newName: string) => {
    setFieldMappings((prev) =>
      prev.map((f, i) => (i === index ? { ...f, mappedName: newName } : f))
    );
  };

  const handleExcludeToggle = (index: number) => {
    setFieldMappings((prev) =>
      prev.map((f, i) => (i === index ? { ...f, excluded: !f.excluded } : f))
    );
  };

  const handleIngest = async () => {
    if (!indexName.trim()) {
      setError('Index name is required');
      return;
    }

    // Validate index name
    if (indexName !== indexName.toLowerCase()) {
      setError('Index name must be lowercase');
      return;
    }

    const invalidChars = ['\\', '/', '*', '?', '"', '<', '>', '|', ' ', ',', '#', ':'];
    for (const char of invalidChars) {
      if (indexName.includes(char)) {
        setError(`Index name cannot contain '${char}'`);
        return;
      }
    }

    setError(null);
    setIsIngesting(true);
    setProgress(null);

    try {
      // Build field mappings (only include changed names)
      const mappings: Record<string, string> = {};
      const excluded: string[] = [];

      for (const field of fieldMappings) {
        if (field.excluded) {
          excluded.push(field.originalName);
        } else if (field.mappedName !== field.originalName) {
          mappings[field.originalName] = field.mappedName;
        }
      }

      // Build field type overrides (only include changed types)
      const typeOverrides: Record<string, string> = {};
      data.fields.forEach(f => {
        if (fieldTypes[f.name] && fieldTypes[f.name] !== f.type) {
          typeOverrides[f.name] = fieldTypes[f.name];
        }
      });

      // Build field transforms (only include fields with transforms)
      const transforms: Record<string, FieldTransform[]> = {};
      Object.keys(fieldTransforms).forEach(fieldName => {
        if (fieldTransforms[fieldName]?.length > 0) {
          transforms[fieldName] = fieldTransforms[fieldName];
        }
      });

      // Start ingestion (returns immediately)
      const startResult = await startIngest(data.upload_id, {
        index_name: indexName,
        timestamp_field: timestampField,
        field_mappings: mappings,
        excluded_fields: excluded,
        field_types: typeOverrides,
        field_transforms: Object.keys(transforms).length > 0 ? transforms : undefined,
        include_filename: includeFilename,
        filename_field: filenameField,
        geoip_fields: geoipFields.length > 0 ? geoipFields : undefined,
      });

      // Subscribe to progress updates via SSE
      const unsubscribe = subscribeToProgress(
        data.upload_id,
        // onProgress
        (progressData: ProgressEvent) => {
          setProgress(progressData);
        },
        // onComplete
        (finalData: ProgressEvent) => {
          setProgress(finalData);
          setIsIngesting(false);
          addToast(`Ingestion complete: ${finalData.success} records indexed`, 'success');
          onComplete({
            upload_id: data.upload_id,
            index_name: startResult.index_name,
            processed: finalData.processed,
            success: finalData.success,
            failed: finalData.failed,
          });
        },
        // onError
        (errorMsg: string) => {
          setError(errorMsg);
          setIsIngesting(false);
          addToast(errorMsg, 'error');
        }
      );

      // Store unsubscribe function for cleanup (not used currently but good practice)
      return () => unsubscribe();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingestion failed');
      setIsIngesting(false);
    }
  };

  const handleCancel = async (deleteIndex: boolean) => {
    try {
      const result = await cancelIngest(data.upload_id, deleteIndex);
      if (deleteIndex) {
        if (result.index_deleted) {
          addToast('Ingestion cancelled and index deleted', 'success');
        } else {
          addToast('Ingestion cancelled but failed to delete index', 'warning');
        }
      } else {
        addToast('Ingestion cancelled', 'info');
      }
      onReset();
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to cancel', 'error');
    }
  };

  const activeFields = fieldMappings.filter((f) => !f.excluded);

  // Filter to only fields that look like timestamps
  const timestampCandidates = activeFields.filter((field) => {
    const sampleValues = data.preview.map((row) => row[field.originalName]);
    return isLikelyTimestampField(field.originalName, sampleValues);
  });

  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const progressPercent = progress
    ? Math.round((progress.processed / progress.total) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Progress Panel (shown during ingestion) */}
      {isIngesting && progress && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Ingestion Progress</h3>

          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-300 mb-1">
              <span>{progress.processed.toLocaleString()} / {progress.total.toLocaleString()} records</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
              <div
                className="bg-indigo-600 h-4 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-green-600">
                {progress.success.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Success</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-red-600">
                {progress.failed.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Failed</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-indigo-600">
                {progress.records_per_second.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Records/sec</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-gray-700 dark:text-gray-200">
                {formatTime(progress.elapsed_seconds)}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Elapsed</div>
            </div>
          </div>

          {progress.estimated_remaining_seconds > 0 && (
            <div className="mt-4 text-center text-sm text-gray-500 dark:text-gray-400">
              Estimated time remaining: {formatTime(progress.estimated_remaining_seconds)}
            </div>
          )}

          <div className="mt-4 flex justify-center">
            <button
              onClick={() => setShowCancelDialog(true)}
              className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-600 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Index Configuration */}
      <div className={`bg-white dark:bg-gray-800 shadow rounded-lg p-6 ${isIngesting ? 'opacity-50 pointer-events-none' : ''}`}>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Index Configuration</h3>

        <div className="space-y-4">
          {/* Index Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Index Name
            </label>
            <div className="flex">
              <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-sm">
                {INDEX_PREFIX}
              </span>
              <input
                type="text"
                value={indexName}
                onChange={(e) => setIndexName(e.target.value.toLowerCase())}
                placeholder="my-index-name"
                className="flex-1 min-w-0 block w-full px-3 py-2 rounded-none rounded-r-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-indigo-500 focus:border-indigo-500"
                disabled={isIngesting}
              />
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Full index name will be: {INDEX_PREFIX}{indexName || '<name>'}
            </p>
          </div>

          {/* Timestamp Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Timestamp Field
            </label>
            <select
              value={timestampField || ''}
              onChange={(e) => setTimestampField(e.target.value || null)}
              className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-indigo-500 focus:border-indigo-500"
              disabled={isIngesting}
            >
              <option value="">None</option>
              {timestampCandidates.map((field) => (
                <option key={field.originalName} value={field.originalName}>
                  {field.mappedName}
                </option>
              ))}
            </select>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {timestampCandidates.length > 0
                ? 'Selected field will be parsed and mapped to @timestamp'
                : 'No timestamp-like fields detected'}
            </p>
          </div>

          {/* Include Filename */}
          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeFilename}
                onChange={(e) => setIncludeFilename(e.target.checked)}
                disabled={isIngesting}
                className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                Add source filename to each record
              </span>
            </label>
            {includeFilename && (
              <div className="mt-2 ml-6">
                <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                  Field name
                </label>
                <input
                  type="text"
                  value={filenameField}
                  onChange={(e) => setFilenameField(e.target.value)}
                  disabled={isIngesting}
                  className="block w-full max-w-xs px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-indigo-500 focus:border-indigo-500"
                  placeholder="source_file"
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Field Mapping */}
      <div className={`bg-white dark:bg-gray-800 shadow rounded-lg p-6 ${isIngesting ? 'opacity-50 pointer-events-none' : ''}`}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">
            Field Mapping ({activeFields.length} of {fieldMappings.length} fields)
          </h3>
          <button
            onClick={() => {
              // Apply ECS suggestions to field mappings
              setFieldMappings(prev =>
                prev.map(f => ({
                  ...f,
                  mappedName: ecsSuggestions[f.originalName] || f.mappedName,
                }))
              );
              addToast(`Applied ${Object.keys(ecsSuggestions).length} ECS mappings`, 'success');
            }}
            disabled={Object.keys(ecsSuggestions).length === 0 || isIngesting}
            className="px-3 py-1.5 text-sm font-medium text-indigo-600 dark:text-indigo-400 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Apply ECS Mapping ({Object.keys(ecsSuggestions).length})
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Original Field
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Target Field
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Transforms
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Enrich
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Exclude
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {fieldMappings.map((field, index) => {
                const fieldInfo = data.fields.find(
                  (f) => f.name === field.originalName
                ) as FieldInfo;
                return (
                  <tr
                    key={field.originalName}
                    className={field.excluded ? 'bg-gray-50 dark:bg-gray-700 opacity-50' : ''}
                  >
                    <td className="px-4 py-2 text-sm font-medium text-gray-900 dark:text-white">
                      {field.originalName}
                    </td>
                    <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                      <select
                        value={fieldTypes[field.originalName] || fieldInfo?.type || 'string'}
                        onChange={(e) => setFieldType(field.originalName, e.target.value)}
                        disabled={field.excluded || isIngesting}
                        className="px-2 py-0.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50"
                      >
                        <option value="string">string</option>
                        <option value="integer">integer</option>
                        <option value="float">float</option>
                        <option value="boolean">boolean</option>
                      </select>
                    </td>
                    <td className="px-4 py-2">
                      <input
                        type="text"
                        value={field.mappedName}
                        onChange={(e) => handleFieldNameChange(index, e.target.value)}
                        disabled={field.excluded || isIngesting}
                        className="block w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 dark:disabled:bg-gray-600"
                      />
                    </td>
                    <td className="px-4 py-2">
                      <div className="space-y-1">
                        {/* Show existing transforms */}
                        {(fieldTransforms[field.originalName] || []).map((transform, idx) => {
                          const transformDef = AVAILABLE_TRANSFORMS.find(t => t.name === transform.name);
                          return (
                            <div key={idx} className="flex items-center gap-1 text-xs">
                              <span className="bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 px-2 py-0.5 rounded">
                                {transformDef?.label || transform.name}
                              </span>
                              {/* Options inputs */}
                              {transformDef?.options.map(opt => (
                                <input
                                  key={opt}
                                  type={opt === 'max_length' ? 'number' : 'text'}
                                  placeholder={opt}
                                  value={(transform[opt] as string | number) || ''}
                                  onChange={(e) => updateTransformOption(field.originalName, idx, opt, e.target.value)}
                                  className="w-20 px-1 py-0.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                  disabled={field.excluded || isIngesting}
                                />
                              ))}
                              <button
                                onClick={() => removeTransform(field.originalName, idx)}
                                className="text-red-500 hover:text-red-700"
                                disabled={field.excluded || isIngesting}
                              >
                                x
                              </button>
                            </div>
                          );
                        })}
                        {/* Add transform dropdown */}
                        <select
                          value=""
                          onChange={(e) => e.target.value && addTransform(field.originalName, e.target.value)}
                          disabled={field.excluded || isIngesting}
                          className="text-xs border border-gray-300 dark:border-gray-600 rounded px-1 py-0.5 bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50"
                        >
                          <option value="">+ Add transform</option>
                          {AVAILABLE_TRANSFORMS.map(t => (
                            <option key={t.name} value={t.name}>{t.label}</option>
                          ))}
                        </select>
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      {fieldInfo?.type === 'string' && isLikelyIpField(field.originalName, data.preview.map(row => row[field.originalName])) && geoipAvailable && (
                        <label className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={geoipFields.includes(field.originalName)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setGeoipFields([...geoipFields, field.originalName]);
                              } else {
                                setGeoipFields(geoipFields.filter(f => f !== field.originalName));
                              }
                            }}
                            disabled={field.excluded || isIngesting}
                            className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 dark:border-gray-600 rounded"
                          />
                          <span className="text-gray-700 dark:text-gray-300">GeoIP</span>
                        </label>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={field.excluded}
                        onChange={() => handleExcludeToggle(index)}
                        disabled={isIngesting}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 dark:border-gray-600 rounded"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <button
          onClick={handleBack}
          disabled={isIngesting}
          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
        >
          Back to Preview
        </button>
        <button
          onClick={handleIngest}
          disabled={isIngesting || !indexName.trim()}
          className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
        >
          {isIngesting ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Ingesting...
            </>
          ) : (
            'Start Ingestion'
          )}
        </button>
      </div>

      {/* Cancel Confirmation Dialog */}
      {showCancelDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Cancel Ingestion?
            </h3>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to cancel the current ingestion?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowCancelDialog(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Continue Ingesting
              </button>
              <button
                onClick={() => {
                  setShowCancelDialog(false);
                  if (progress && progress.success > 0) {
                    setShowDeleteDialog(true);
                  } else {
                    handleCancel(false);
                  }
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                Cancel Ingestion
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Index Dialog */}
      {showDeleteDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Delete Indexed Records?
            </h3>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              {progress?.success.toLocaleString()} records have already been indexed. Would you like to keep or delete them?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  handleCancel(false);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Keep Records
              </button>
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  handleCancel(true);
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                Delete Index
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
