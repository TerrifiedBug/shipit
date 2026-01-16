import { useState, useEffect } from 'react';
import { login, setup, User, getAuthConfig, getOidcLoginUrl, AuthConfig } from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface LoginProps {
  isSetupMode: boolean;
  onLogin: (user: User) => void;
}

export function Login({ isSetupMode, onLogin }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [showLocalLogin, setShowLocalLogin] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    // Check for error in URL (from OIDC callback)
    const params = new URLSearchParams(window.location.search);
    const error = params.get('error');
    if (error) {
      addToast(error, 'error');
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname);
    }

    // Fetch auth config
    getAuthConfig().then(setAuthConfig);
  }, [addToast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      let user: User;
      if (isSetupMode) {
        user = await setup(email, password, name);
        addToast('Account created successfully!', 'success');
      } else {
        user = await login(email, password);
      }
      onLogin(user);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Authentication failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const showOidc = authConfig?.oidc_enabled && !isSetupMode;
  const showLocal = isSetupMode || showLocalLogin || !showOidc;

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex items-center justify-center px-4">
      <div className="max-w-md w-full">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
          <div className="text-center mb-8">
            <span className="text-5xl mb-4 block" role="img" aria-label="ShipIt logo">🚀</span>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">ShipIt</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              {isSetupMode ? 'Create your admin account' : 'Sign in to your account'}
            </p>
          </div>

          {/* SSO Login Button */}
          {showOidc && (
            <div className="mb-6">
              <a
                href={getOidcLoginUrl()}
                className="w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                Sign in with SSO
              </a>

              {!showLocalLogin && (
                <button
                  onClick={() => setShowLocalLogin(true)}
                  className="mt-4 w-full text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Sign in with email instead
                </button>
              )}
            </div>
          )}

          {/* Divider */}
          {showOidc && showLocalLogin && (
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300 dark:border-gray-600" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                  Or continue with email
                </span>
              </div>
            </div>
          )}

          {/* Local Login Form */}
          {showLocal && (
            <form onSubmit={handleSubmit} className="space-y-6">
              {isSetupMode && (
                <div>
                  <label
                    htmlFor="name"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    Name
                  </label>
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-gray-900 dark:text-white placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="Your name"
                  />
                </div>
              )}

              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-gray-900 dark:text-white placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-gray-900 dark:text-white placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="********"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <svg
                    className="animate-spin h-5 w-5 text-white"
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
                ) : isSetupMode ? (
                  'Create Account'
                ) : (
                  'Sign In'
                )}
              </button>

              {showOidc && showLocalLogin && (
                <button
                  type="button"
                  onClick={() => setShowLocalLogin(false)}
                  className="w-full text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Back to SSO
                </button>
              )}
            </form>
          )}

          {isSetupMode && (
            <p className="mt-4 text-sm text-gray-500 dark:text-gray-400 text-center">
              This will be the first admin account for ShipIt.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
