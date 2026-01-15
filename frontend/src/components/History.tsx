import { useEffect, useState } from 'react';
import { deleteIndex, downloadFailures, getFailuresDownloadUrl, getHistory, UploadRecord } from '../api/client';

interface HistoryProps {
  onClose: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString();
}

function StatusBadge({ status }: { status: UploadRecord['status'] }) {
  const styles = {
    pending: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
    in_progress: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    cancelled: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  };

  const labels = {
    pending: 'Pending',
    in_progress: 'In Progress',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

export function History({ onClose }: HistoryProps) {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUpload, setSelectedUpload] = useState<UploadRecord | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; indexName: string } | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  useEffect(() => {
    loadHistory();
  }, [statusFilter]);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      const response = await getHistory(50, 0, statusFilter || undefined);
      setUploads(response.uploads);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteIndex() {
    if (!deleteTarget) return;

    setDeleteLoading(true);
    try {
      await deleteIndex(deleteTarget.indexName);
      setToast({ message: `Index ${deleteTarget.indexName} deleted successfully`, type: 'success' });
      setDeleteTarget(null);
      loadHistory();
    } catch (err) {
      setToast({ message: err instanceof Error ? err.message : 'Failed to delete index', type: 'error' });
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-5xl w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Upload History</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="mb-4 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
          >
            <option value="">All Status</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="in_progress">In Progress</option>
            <option value="cancelled">Cancelled</option>
          </select>

          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
          )}

          {error && (
            <div className="text-center py-12">
              <p className="text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={loadHistory}
                className="mt-4 px-4 py-2 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
              >
                Retry
              </button>
            </div>
          )}

          {!loading && !error && uploads.length === 0 && (
            <p className="text-center text-gray-500 dark:text-gray-400 py-8">No uploads yet</p>
          )}

          {!loading && !error && uploads.length > 0 && (
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-3 w-8"></th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Filename
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Index
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Records
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {uploads.map((upload) => (
                  <>
                    <tr
                      key={upload.id}
                      onClick={() => toggleExpand(upload.id)}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
                    >
                      <td className="px-4 py-2">
                        <svg
                          className={`w-5 h-5 text-gray-400 transition-transform ${expandedId === upload.id ? 'rotate-90' : ''}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                        <div className="font-medium">{upload.filename}</div>
                        <div className="text-gray-500 dark:text-gray-400">{formatFileSize(upload.file_size)}</div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                        {upload.index_name || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                        {upload.total_records !== null ? (
                          <div>
                            <span className="text-green-600 dark:text-green-400">{upload.success_count}</span>
                            {upload.failure_count !== null && upload.failure_count > 0 && (
                              <span className="text-red-600 dark:text-red-400 ml-1">/ {upload.failure_count} failed</span>
                            )}
                          </div>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={upload.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(upload.created_at)}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedUpload(upload);
                            }}
                            className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
                          >
                            Details
                          </button>
                          {upload.failure_count && upload.failure_count > 0 && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                downloadFailures(upload.id);
                              }}
                              className="p-1 text-orange-600 hover:text-orange-800 dark:text-orange-400 dark:hover:text-orange-300"
                              title={`Download ${upload.failure_count} failed records`}
                            >
                              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                            </button>
                          )}
                          {upload.status === 'completed' && upload.index_name && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setDeleteTarget({ id: upload.id, indexName: upload.index_name! });
                              }}
                              className="p-1 text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                              title={`Delete index ${upload.index_name}`}
                            >
                              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedId === upload.id && (
                      <tr key={`${upload.id}-expanded`}>
                        <td colSpan={7} className="px-4 py-4 bg-gray-50 dark:bg-gray-700/50">
                          <div className="space-y-3">
                            {/* Field mappings */}
                            {upload.field_mappings && Object.keys(upload.field_mappings).length > 0 && (
                              <div>
                                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Field Mappings</h4>
                                <div className="flex flex-wrap gap-2">
                                  {Object.entries(upload.field_mappings).map(([from, to]) => (
                                    <span key={from} className="text-sm bg-gray-200 dark:bg-gray-600 px-2 py-1 rounded">
                                      {from} → {to as string}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Error message */}
                            {upload.error_message && (
                              <div>
                                <h4 className="text-sm font-medium text-red-700 dark:text-red-400 mb-1">Error</h4>
                                <p className="text-sm text-red-600 dark:text-red-300">{upload.error_message}</p>
                              </div>
                            )}

                            {/* Download failures button */}
                            {upload.failure_count && upload.failure_count > 0 && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  downloadFailures(upload.id);
                                }}
                                className="text-sm text-orange-600 dark:text-orange-400 hover:underline"
                              >
                                Download {upload.failure_count} failed records
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Close
          </button>
        </div>
      </div>

      {/* Details Modal */}
      {selectedUpload && (
        <UploadDetails
          upload={selectedUpload}
          onClose={() => setSelectedUpload(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Delete Index
            </h3>
            <p className="text-gray-600 dark:text-gray-300 mb-2">
              Are you sure you want to delete the index:
            </p>
            <p className="font-mono text-sm bg-gray-100 dark:bg-gray-700 p-2 rounded mb-4 break-all">
              {deleteTarget.indexName}
            </p>
            <p className="text-red-600 dark:text-red-400 text-sm mb-6">
              This action cannot be undone. All documents in this index will be permanently deleted.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteIndex}
                disabled={deleteLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
              >
                {deleteLoading && (
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                )}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-4 right-4 z-[70] px-4 py-3 rounded-lg shadow-lg ${
          toast.type === 'success'
            ? 'bg-green-600 text-white'
            : 'bg-red-600 text-white'
        }`}>
          <div className="flex items-center gap-2">
            {toast.type === 'success' ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            <span>{toast.message}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function UploadDetails({ upload, onClose }: { upload: UploadRecord; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full mx-4">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Upload Details</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Filename</label>
            <p className="text-gray-900 dark:text-white">{upload.filename}</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">File Size</label>
              <p className="text-gray-900 dark:text-white">{formatFileSize(upload.file_size)}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Format</label>
              <p className="text-gray-900 dark:text-white">{upload.file_format}</p>
            </div>
          </div>

          {upload.index_name && (
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Index Name</label>
              <p className="text-gray-900 dark:text-white font-mono">{upload.index_name}</p>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Total</label>
              <p className="text-gray-900 dark:text-white">{upload.total_records ?? '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Success</label>
              <p className="text-green-600 dark:text-green-400">{upload.success_count ?? '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Failed</label>
              <p className="text-red-600 dark:text-red-400">{upload.failure_count ?? '-'}</p>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Status</label>
            <div className="mt-1">
              <StatusBadge status={upload.status} />
            </div>
          </div>

          {upload.error_message && (
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Error</label>
              <p className="text-red-600 dark:text-red-400 text-sm bg-red-50 dark:bg-red-900/20 p-2 rounded mt-1">
                {upload.error_message}
              </p>
            </div>
          )}

          {upload.field_mappings && Object.keys(upload.field_mappings).length > 0 && (
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Field Mappings</label>
              <div className="mt-1 text-sm bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2 rounded font-mono">
                {Object.entries(upload.field_mappings).map(([from, to]) => (
                  <div key={from}>
                    {from} → {to}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Created</label>
              <p className="text-gray-900 dark:text-white">{formatDate(upload.created_at)}</p>
            </div>
            {upload.completed_at && (
              <div>
                <label className="text-sm font-medium text-gray-500 dark:text-gray-400">Completed</label>
                <p className="text-gray-900 dark:text-white">{formatDate(upload.completed_at)}</p>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end p-4 border-t border-gray-200 dark:border-gray-700 gap-2">
          {upload.failure_count !== null && upload.failure_count > 0 && (
            <a
              href={getFailuresDownloadUrl(upload.id)}
              className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-md hover:bg-red-100 dark:hover:bg-red-900/30"
              download
            >
              Download Failures
            </a>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
