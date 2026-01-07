import { apiClient } from '../api/client';

export function LoginPage() {
  const handleLogin = () => {
    apiClient.initiateLogin();
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-5">
      <div className="bg-white rounded-lg shadow-md p-16 max-w-2xl w-full text-center">
        <div className="text-8xl mb-5">🤖</div>
        <h1 className="text-3xl font-semibold text-gray-800 mb-2">
          Devoops Mission Control
        </h1>
        <p className="text-lg text-gray-600 mb-10">
          DevOps Agent for Kubernetes
        </p>

        <div className="bg-blue-50 border-l-4 border-blue-500 p-5 mb-8 text-left">
          <strong>Authentication Required</strong>
          <br />
          <br />
          You need to log in to access the Mission Control interface and submit
          missions to the DevOps agent.
        </div>

        <button
          onClick={handleLogin}
          className="inline-block px-8 py-4 bg-blue-600 text-white rounded font-medium text-lg hover:bg-blue-700 transition-colors"
        >
          Log In with Keycloak
        </button>

        <p className="mt-8 text-sm text-gray-400">
          Demo users: alice / password, bob / password
        </p>
      </div>
    </div>
  );
}
