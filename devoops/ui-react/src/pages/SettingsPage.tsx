import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { apiClient } from '../api/client';

export function SettingsPage() {
  const [copied, setCopied] = useState(false);

  const {
    data: publicKeyData,
    isLoading: keyLoading,
    error: keyError,
  } = useQuery({
    queryKey: ['sshPublicKey'],
    queryFn: () => apiClient.getSSHPublicKey(),
    retry: false,
  });

  const {
    data: serversData,
    isLoading: serversLoading,
    error: serversError,
  } = useQuery({
    queryKey: ['sshServers'],
    queryFn: () => apiClient.getSSHServers(),
  });

  const handleCopy = async () => {
    if (publicKeyData?.public_key) {
      await navigator.clipboard.writeText(publicKeyData.public_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const sshConfigured = publicKeyData?.public_key && !keyError;

  return (
    <div className="py-12 px-5">
      <div className="max-w-4xl mx-auto bg-white rounded-lg shadow-md p-10">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-gray-800 mb-2">Settings</h1>
          <p className="text-gray-600">
            Configure SSH access and view agent settings
          </p>
        </div>

        {/* SSH Public Key Section */}
        <section className="mb-10">
          <h2 className="text-xl font-semibold text-gray-800 mb-3">
            Agent SSH Public Key
          </h2>
          <p className="text-gray-600 mb-4">
            Add this public key to the{' '}
            <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">
              ~/.ssh/authorized_keys
            </code>{' '}
            file on servers you want the agent to access.
          </p>

          {keyLoading && <p className="text-gray-400">Loading SSH key...</p>}

          {keyError && (
            <div className="bg-yellow-50 border-l-4 border-yellow-500 p-4">
              <p className="text-yellow-700">
                SSH is not configured on this agent. To enable SSH support:
              </p>
              <ol className="list-decimal list-inside mt-2 text-yellow-700 text-sm">
                <li>Generate an SSH keypair for the agent</li>
                <li>Create a Kubernetes secret with the keypair</li>
                <li>Mount the secret to the agent deployment</li>
              </ol>
            </div>
          )}

          {sshConfigured && (
            <div className="relative">
              <div className="bg-gray-900 rounded p-4 overflow-x-auto">
                <pre className="text-green-400 text-sm font-mono break-all whitespace-pre-wrap">
                  {publicKeyData.public_key}
                </pre>
              </div>
              <button
                onClick={handleCopy}
                className="absolute top-2 right-2 px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
              {publicKeyData.instructions && (
                <p className="text-sm text-gray-500 mt-2">
                  {publicKeyData.instructions}
                </p>
              )}
            </div>
          )}
        </section>

        {/* Configured SSH Servers */}
        <section>
          <h2 className="text-xl font-semibold text-gray-800 mb-3">
            Configured SSH Servers
          </h2>

          {serversLoading && (
            <p className="text-gray-400">Loading SSH servers...</p>
          )}

          {serversError && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4">
              <p className="text-red-700">
                Failed to load SSH servers: {(serversError as Error).message}
              </p>
            </div>
          )}

          {serversData?.servers && serversData.servers.length === 0 && (
            <div className="bg-gray-50 rounded p-4">
              <p className="text-gray-500">
                No SSH servers configured. Add servers to the SSH configuration
                file to enable SSH operations.
              </p>
            </div>
          )}

          {serversData?.servers && serversData.servers.length > 0 && (
            <div className="space-y-3">
              {serversData.servers.map((server) => (
                <div
                  key={server.name}
                  className="bg-gray-50 border border-gray-200 rounded p-4"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-gray-800">
                      {server.displayName}
                    </span>
                    <code className="text-xs text-gray-500 bg-gray-200 px-1.5 py-0.5 rounded">
                      {server.name}
                    </code>
                    {serversData.default_server === server.name && (
                      <span className="text-xs text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded">
                        default
                      </span>
                    )}
                  </div>
                  {server.description && (
                    <p className="text-sm text-gray-600 mb-2">
                      {server.description}
                    </p>
                  )}
                  <p className="text-sm text-gray-500 font-mono">
                    {server.username}@{server.host}:{server.port}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
