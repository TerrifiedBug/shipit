import { useState, useEffect, useRef } from 'react';
import { Upload } from './components/Upload';
import { Preview } from './components/Preview';
import { Configure } from './components/Configure';
import { Result } from './components/Result';
import { History } from './components/History';
import { Login } from './components/Login';
import { ApiKeys } from './components/ApiKeys';
import { Users } from './components/Users';
import { Audit } from './components/Audit';
import { PatternLibrary } from './components/PatternLibrary';
import { PasswordChangeModal } from './components/PasswordChangeModal';
import { OpenSearchStatus } from './components/OpenSearchStatus';
import { CustomEcsMappings } from './components/CustomEcsMappings';
import { ModalErrorBoundary } from './components/ModalErrorBoundary';
import { IngestResponse, UploadResponse, deletePendingUpload } from './api/client';
import { useTheme } from './contexts/ThemeContext';
import { useAuth } from './contexts/AuthContext';
import { useVersion } from './hooks/useVersion';

type AppState = 'upload' | 'preview' | 'configure' | 'result';

function ThemeToggle() {
  const { setTheme, theme } = useTheme();

  const cycleTheme = () => {
    if (theme === 'light') setTheme('dark');
    else if (theme === 'dark') setTheme('system');
    else setTheme('light');
  };

  // Icon labels for tooltip
  const themeLabels = {
    light: 'Light mode',
    dark: 'Dark mode',
    system: 'System theme',
  };

  return (
    <button
      onClick={cycleTheme}
      className="p-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 flex items-center gap-1"
      title={`${themeLabels[theme]} (click to change)`}
    >
      {theme === 'light' ? (
        // Sun icon for light mode
        <svg className="w-5 h-5 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z" />
        </svg>
      ) : theme === 'dark' ? (
        // Moon icon for dark mode
        <svg className="w-5 h-5 text-indigo-400" fill="currentColor" viewBox="0 0 24 24">
          <path fillRule="evenodd" d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z" clipRule="evenodd" />
        </svg>
      ) : (
        // Computer/monitor icon for system/auto mode
        <svg className="w-5 h-5 text-gray-500 dark:text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12H3V5.25" />
        </svg>
      )}
      <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
        {theme === 'light' ? 'Light' : theme === 'dark' ? 'Dark' : 'Auto'}
      </span>
    </button>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [showPasswordChange, setShowPasswordChange] = useState(false);

  if (!user) return null;

  return (
    <>
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
        >
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium">
            {user.name.charAt(0).toUpperCase()}
          </div>
          <span className="text-sm text-gray-700 dark:text-gray-200">{user.name}</span>
          <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {isOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
            <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-md shadow-lg border border-gray-200 dark:border-gray-700 z-20">
              <div className="py-1">
                <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  {user.email}
                </div>
                {/* Only show password change for local users, not OIDC */}
                {user.auth_type === 'local' && (
                  <button
                    onClick={() => {
                      setShowPasswordChange(true);
                      setIsOpen(false);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Change Password
                  </button>
                )}
                <button
                  onClick={() => {
                    logout();
                    setIsOpen(false);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  Sign out
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {showPasswordChange && (
        <PasswordChangeModal
          onSuccess={() => setShowPasswordChange(false)}
          onCancel={() => setShowPasswordChange(false)}
        />
      )}
    </>
  );
}

function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex items-center justify-center">
      <svg
        className="animate-spin h-12 w-12 text-blue-600"
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
  );
}

function App() {
  const { user, loading, needsSetup, passwordChangeRequired, login, clearPasswordChangeRequired } = useAuth();
  const { currentVersion, updateAvailable, releaseUrl } = useVersion();
  const [state, setState] = useState<AppState>('upload');
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<IngestResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [showUsers, setShowUsers] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [showPatterns, setShowPatterns] = useState(false);
  const [showCustomEcsMappings, setShowCustomEcsMappings] = useState(false);

  // Track pending upload for cleanup on tab close
  const pendingUploadRef = useRef<string | null>(null);

  // Update ref when uploadData changes (only track if not yet ingested)
  useEffect(() => {
    pendingUploadRef.current = uploadData && !ingestResult ? uploadData.upload_id : null;
  }, [uploadData, ingestResult]);

  // Clean up pending upload on tab/window close
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (pendingUploadRef.current) {
        // Use fetch with keepalive for reliable delivery on page unload
        // (sendBeacon doesn't include credentials for cross-origin requests)
        const url = `${import.meta.env.VITE_API_URL || ''}/api/upload/${pendingUploadRef.current}/abandon`;
        fetch(url, {
          method: 'POST',
          credentials: 'include',
          keepalive: true,
        });
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  // Show loading spinner while checking auth
  if (loading) {
    return <LoadingSpinner />;
  }

  // Show login if not authenticated
  if (!user) {
    return <Login isSetupMode={needsSetup} onLogin={login} />;
  }

  // Show password change modal if required
  if (passwordChangeRequired) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
        <PasswordChangeModal onSuccess={clearPasswordChangeRequired} required />
      </div>
    );
  }

  const handleUploadComplete = (data: UploadResponse) => {
    setUploadData(data);
    setState('preview');
  };

  const handleContinueToConfigure = () => {
    setState('configure');
  };

  const handleIngestComplete = (result: IngestResponse) => {
    setIngestResult(result);
    setState('result');
  };

  const handleReset = () => {
    // If abandoning before ingestion started, delete the pending upload
    if (uploadData && !ingestResult) {
      deletePendingUpload(uploadData.upload_id);
    }
    setUploadData(null);
    setIngestResult(null);
    setState('upload');
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center">
            <button
              onClick={handleReset}
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
              title="Return to upload"
            >
              <span className="text-3xl" role="img" aria-label="ShipIt logo">🚀</span>
              <div className="flex items-baseline gap-2">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">ShipIt</h1>
                <span className="text-xs text-gray-400 dark:text-gray-500">v{currentVersion}</span>
              </div>
            </button>
            {updateAvailable && releaseUrl && (
              <a
                href={releaseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-500 hover:text-blue-600 hover:underline ml-2"
              >
                Update available
              </a>
            )}
            <div className="flex items-center gap-2">
              <OpenSearchStatus />
              <ThemeToggle />
              {user?.is_admin && (
                <>
                  <button
                    onClick={() => setShowAudit(true)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                  >
                    Audit
                  </button>
                  <button
                    onClick={() => setShowUsers(true)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                  >
                    Users
                  </button>
                </>
              )}
              {user?.role !== 'viewer' && (
                <button
                  onClick={() => setShowCustomEcsMappings(true)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  ECS Mappings
                </button>
              )}
              <button
                onClick={() => setShowPatterns(true)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Patterns
              </button>
              {user?.role !== 'viewer' && (
                <button
                  onClick={() => setShowApiKeys(true)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  API Keys
                </button>
              )}
              <button
                onClick={() => setShowHistory(true)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                History
              </button>
              <UserMenu />
            </div>
          </div>
        </div>
      </header>

      {showHistory && (
        <ModalErrorBoundary onClose={() => setShowHistory(false)} title="History Error">
          <History onClose={() => setShowHistory(false)} />
        </ModalErrorBoundary>
      )}
      {showApiKeys && (
        <ModalErrorBoundary onClose={() => setShowApiKeys(false)} title="API Keys Error">
          <ApiKeys onClose={() => setShowApiKeys(false)} />
        </ModalErrorBoundary>
      )}
      {showUsers && (
        <ModalErrorBoundary onClose={() => setShowUsers(false)} title="Users Error">
          <Users onClose={() => setShowUsers(false)} />
        </ModalErrorBoundary>
      )}
      {showAudit && (
        <ModalErrorBoundary onClose={() => setShowAudit(false)} title="Audit Error">
          <Audit onClose={() => setShowAudit(false)} />
        </ModalErrorBoundary>
      )}
      {showPatterns && (
        <ModalErrorBoundary onClose={() => setShowPatterns(false)} title="Patterns Error">
          <PatternLibrary onClose={() => setShowPatterns(false)} />
        </ModalErrorBoundary>
      )}
      {showCustomEcsMappings && (
        <ModalErrorBoundary onClose={() => setShowCustomEcsMappings(false)} title="ECS Mappings Error">
          <CustomEcsMappings onClose={() => setShowCustomEcsMappings(false)} />
        </ModalErrorBoundary>
      )}
      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          {state === 'upload' && (
            <Upload onUploadComplete={handleUploadComplete} />
          )}
          {state === 'preview' && uploadData && (
            <Preview
              data={uploadData}
              onBack={handleReset}
              onContinue={handleContinueToConfigure}
              onDataUpdate={setUploadData}
            />
          )}
          {state === 'configure' && uploadData && (
            <Configure
              data={uploadData}
              onBack={() => setState('preview')}
              onComplete={handleIngestComplete}
              onReset={handleReset}
            />
          )}
          {state === 'result' && ingestResult && (
            <Result result={ingestResult} onNewUpload={handleReset} />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
