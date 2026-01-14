import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

export function AppHeader() {
  const { data: user } = useQuery({
    queryKey: ['currentUser'],
    queryFn: () => apiClient.getCurrentUser(),
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    retry: false,
  });

  const handleLogout = () => {
    apiClient.initiateLogout();
  };

  return (
    <header className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-6xl mx-auto px-5 py-3 flex justify-between items-center">
        <Link to="/" className="flex items-center gap-2 text-gray-800 hover:text-gray-600">
          <span className="text-2xl">🤖</span>
          <span className="font-semibold text-lg">Devoops</span>
        </Link>

        <div className="flex items-center gap-4">
          {user && (
            <>
              <span className="text-gray-600 text-sm">{user.email}</span>
              <Link
                to="/settings"
                className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              >
                Settings
              </Link>
              <Link
                to="/auth"
                className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              >
                Auth Debug
              </Link>
              <button
                onClick={handleLogout}
                className="px-3 py-1.5 text-sm font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-md transition-colors"
              >
                Logout
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
