import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '../api/client';

interface JwtClaims {
  sub?: string;
  iss?: string;
  aud?: string | string[];
  exp?: number;
  iat?: number;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
}

function KeyClaimsTable({ claims }: { claims: Record<string, unknown> }) {
  const c = claims as JwtClaims;
  return (
    <div className="mt-4 bg-gray-50 rounded p-4">
      <h3 className="font-medium text-gray-700 mb-3">Key Claims</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {c.sub && (
          <>
            <dt className="font-medium text-gray-600">Subject (sub):</dt>
            <dd className="text-gray-800 font-mono">{c.sub}</dd>
          </>
        )}
        {c.iss && (
          <>
            <dt className="font-medium text-gray-600">Issuer (iss):</dt>
            <dd className="text-gray-800 font-mono break-all">{c.iss}</dd>
          </>
        )}
        {c.aud && (
          <>
            <dt className="font-medium text-gray-600">Audience (aud):</dt>
            <dd className="text-gray-800 font-mono">
              {Array.isArray(c.aud) ? c.aud.join(', ') : c.aud}
            </dd>
          </>
        )}
        {c.exp && (
          <>
            <dt className="font-medium text-gray-600">Expires (exp):</dt>
            <dd className="text-gray-800">
              {new Date(c.exp * 1000).toLocaleString()}
            </dd>
          </>
        )}
        {c.iat && (
          <>
            <dt className="font-medium text-gray-600">Issued At (iat):</dt>
            <dd className="text-gray-800">
              {new Date(c.iat * 1000).toLocaleString()}
            </dd>
          </>
        )}
        {c.preferred_username && (
          <>
            <dt className="font-medium text-gray-600">Preferred Username:</dt>
            <dd className="text-gray-800">{c.preferred_username}</dd>
          </>
        )}
        {c.email && (
          <>
            <dt className="font-medium text-gray-600">Email:</dt>
            <dd className="text-gray-800">{c.email}</dd>
          </>
        )}
        {c.realm_access && (
          <>
            <dt className="font-medium text-gray-600">Realm Roles:</dt>
            <dd className="text-gray-800">
              {c.realm_access.roles?.join(', ') || 'None'}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}

export function AuthDebugPage() {
  const { data: user, isLoading, error } = useQuery({
    queryKey: ['currentUser'],
    queryFn: () => apiClient.getCurrentUser(),
  });

  const handleLogout = () => {
    apiClient.initiateLogout();
  };

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-5">
      <div className="max-w-4xl mx-auto bg-white rounded-lg shadow-md p-10">
        <div className="flex justify-between items-start mb-8">
          <div>
            <h1 className="text-3xl font-semibold text-gray-800 mb-2">
              Authentication Debug
            </h1>
            <p className="text-gray-600">
              View your current authentication state and token claims
            </p>
          </div>
          <div className="space-x-3">
            <Link to="/" className="text-blue-600 hover:underline text-sm">
              Back to Home
            </Link>
            <button
              onClick={handleLogout}
              className="text-blue-600 hover:underline text-sm"
            >
              Logout
            </button>
          </div>
        </div>

        {isLoading && <p className="text-gray-400">Loading user info...</p>}

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-5">
            <p className="text-red-700">
              Failed to load user info: {(error as Error).message}
            </p>
          </div>
        )}

        {user && (
          <div className="space-y-6">
            {/* Basic User Info */}
            <section>
              <h2 className="text-xl font-semibold text-gray-800 mb-3">
                User Info
              </h2>
              <div className="bg-gray-50 rounded p-4">
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                  <dt className="font-medium text-gray-600">Username:</dt>
                  <dd className="text-gray-800">{user.username}</dd>
                  <dt className="font-medium text-gray-600">Email:</dt>
                  <dd className="text-gray-800">{user.email}</dd>
                </dl>
              </div>
            </section>

            {/* Token Header */}
            {user.token?.header && (
              <section>
                <h2 className="text-xl font-semibold text-gray-800 mb-3">
                  Token Header
                </h2>
                <div className="bg-gray-900 rounded p-4 overflow-x-auto">
                  <pre className="text-green-400 text-sm font-mono">
                    {JSON.stringify(user.token.header, null, 2)}
                  </pre>
                </div>
              </section>
            )}

            {/* Token Claims */}
            {user.token?.claims && (
              <section>
                <h2 className="text-xl font-semibold text-gray-800 mb-3">
                  Token Claims
                </h2>
                <div className="bg-gray-900 rounded p-4 overflow-x-auto">
                  <pre className="text-green-400 text-sm font-mono">
                    {JSON.stringify(user.token.claims, null, 2)}
                  </pre>
                </div>

                {/* Parsed Claims Table */}
                <KeyClaimsTable claims={user.token.claims} />
              </section>
            )}

            {/* Raw Token */}
            {user.token?.raw && (
              <section>
                <h2 className="text-xl font-semibold text-gray-800 mb-3">
                  Raw Access Token
                </h2>
                <div className="bg-gray-900 rounded p-4 overflow-x-auto">
                  <pre className="text-yellow-400 text-xs font-mono break-all whitespace-pre-wrap">
                    {user.token.raw}
                  </pre>
                </div>
              </section>
            )}

            {/* Token Error */}
            {user.token?.error && (
              <section>
                <h2 className="text-xl font-semibold text-gray-800 mb-3">
                  Token Error
                </h2>
                <div className="bg-red-50 border-l-4 border-red-500 p-4">
                  <p className="text-red-700">{user.token.error}</p>
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
