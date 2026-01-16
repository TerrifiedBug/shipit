import React, { useEffect, useState } from 'react';
import { getAuditLogs, getAuditEventTypes, AuditLogEntry } from '../api/client';

interface AuditProps {
  onClose: () => void;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString();
}

function formatEventType(eventType: string): string {
  return eventType
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function EventTypeBadge({ eventType }: { eventType: string }) {
  const getStyle = () => {
    if (eventType.includes('login_success')) return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    if (eventType.includes('login_failed')) return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    if (eventType.includes('created')) return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    if (eventType.includes('deleted')) return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    if (eventType.includes('modified')) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    if (eventType.includes('logout')) return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
    return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded ${getStyle()}`}>
      {formatEventType(eventType)}
    </span>
  );
}

export function Audit({ onClose }: AuditProps) {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [selectedEventType, setSelectedEventType] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const pageSize = 50;

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  // Handle ESC key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Load event types on mount
  useEffect(() => {
    loadEventTypes();
  }, []);

  // Load logs when filter or page changes
  useEffect(() => {
    loadLogs();
  }, [selectedEventType, page]);

  async function loadEventTypes() {
    try {
      const types = await getAuditEventTypes();
      setEventTypes(types);
    } catch (err) {
      console.error('Failed to load event types:', err);
    }
  }

  async function loadLogs() {
    setLoading(true);
    setError(null);
    try {
      const response = await getAuditLogs({
        page,
        page_size: pageSize,
        event_type: selectedEventType || undefined,
      });
      setLogs(response.logs);
      setTotalPages(response.total_pages);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  }

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-6xl w-full mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Audit Log</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {total} total events
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-4">
            <select
              value={selectedEventType}
              onChange={(e) => {
                setSelectedEventType(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              <option value="">All Events</option>
              {eventTypes.map((type) => (
                <option key={type} value={type}>
                  {formatEventType(type)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
          )}

          {error && (
            <div className="text-center py-12">
              <p className="text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={loadLogs}
                className="mt-4 px-4 py-2 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
              >
                Retry
              </button>
            </div>
          )}

          {!loading && !error && logs.length === 0 && (
            <p className="text-center text-gray-500 dark:text-gray-400 py-8">No audit logs yet</p>
          )}

          {!loading && !error && logs.length > 0 && (
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-3 w-8"></th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Timestamp
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Event
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Actor
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Target
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    IP Address
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {logs.map((log) => (
                  <React.Fragment key={log.id}>
                    <tr
                      onClick={() => toggleExpand(log.id)}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
                    >
                      <td className="px-4 py-2">
                        <svg
                          className={`w-5 h-5 text-gray-400 transition-transform ${expandedId === log.id ? 'rotate-90' : ''}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {formatDate(log.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <EventTypeBadge eventType={log.event_type} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                        {log.actor_name || log.actor_id || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                        {log.target_type ? (
                          <span>
                            <span className="text-gray-500 dark:text-gray-400">{log.target_type}:</span>{' '}
                            {log.target_id || '-'}
                          </span>
                        ) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 font-mono">
                        {log.ip_address || '-'}
                      </td>
                    </tr>
                    {expandedId === log.id && (
                      <tr>
                        <td colSpan={6} className="px-4 py-4 bg-gray-50 dark:bg-gray-700/50">
                          <div className="space-y-3">
                            {/* Event details */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                              <div>
                                <span className="text-gray-500 dark:text-gray-400">Event ID:</span>{' '}
                                <span className="text-gray-900 dark:text-white font-mono text-xs">{log.id}</span>
                              </div>
                              {log.actor_id && (
                                <div>
                                  <span className="text-gray-500 dark:text-gray-400">Actor ID:</span>{' '}
                                  <span className="text-gray-900 dark:text-white font-mono text-xs">{log.actor_id}</span>
                                </div>
                              )}
                              {log.target_id && (
                                <div>
                                  <span className="text-gray-500 dark:text-gray-400">Target ID:</span>{' '}
                                  <span className="text-gray-900 dark:text-white font-mono text-xs">{log.target_id}</span>
                                </div>
                              )}
                            </div>

                            {/* Details JSON */}
                            {log.details && Object.keys(log.details).length > 0 && (
                              <div>
                                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Details</h4>
                                <pre className="text-sm bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white p-3 rounded overflow-x-auto">
                                  {JSON.stringify(log.details, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Page {page} of {totalPages}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}

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
    </div>
  );
}
