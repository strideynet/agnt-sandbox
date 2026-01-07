import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { Mission } from '../types/mission';

export function HomePage() {
  const [missionPrompt, setMissionPrompt] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Fetch missions with polling every 500ms
  const { data: missions = [], isLoading, error } = useQuery({
    queryKey: ['missions'],
    queryFn: () => apiClient.getMissions(),
    refetchInterval: 500,
  });

  // Submit mission mutation
  const submitMission = useMutation({
    mutationFn: (prompt: string) => apiClient.submitMission({ prompt }),
    onSuccess: (mission) => {
      setMissionPrompt('');
      queryClient.invalidateQueries({ queryKey: ['missions'] });
      navigate(`/missions/${mission.id}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (missionPrompt.trim()) {
      submitMission.mutate(missionPrompt);
    }
  };

  const handleLogout = () => {
    apiClient.initiateLogout();
  };

  const getStatusColor = (status: Mission['status']) => {
    switch (status) {
      case 'completed':
        return 'border-green-500';
      case 'failed':
        return 'border-red-500';
      case 'running':
        return 'border-yellow-500';
      default:
        return 'border-blue-500';
    }
  };

  const getStatusBadgeColor = (status: Mission['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'running':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  // Sort missions by created_at descending
  const sortedMissions = [...missions].sort((a, b) => {
    if (!a.created_at || !b.created_at) return 0;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-5">
      <div className="max-w-6xl mx-auto bg-white rounded-lg shadow-md p-10">
        <div className="flex justify-between items-start mb-5">
          <div>
            <h1 className="text-3xl font-semibold text-gray-800 mb-2 flex items-center gap-2">
              <span className="text-4xl">🤖</span>
              Devoops Mission Control
            </h1>
            <p className="text-gray-600">
              Submit DevOps missions to your Kubernetes agent
            </p>
          </div>
          <div className="text-right">
            <button
              onClick={handleLogout}
              className="text-blue-600 hover:underline text-sm"
            >
              Logout
            </button>
          </div>
        </div>

        <div className="bg-blue-50 border-l-4 border-blue-500 p-4 mb-5">
          <strong>How it works:</strong>
          <br />
          Submit a natural language mission describing what you want the agent
          to do in your Kubernetes cluster. The agent will use Claude to reason
          about the task and execute the necessary operations.
        </div>

        <div className="bg-gray-50 rounded p-5 mb-8">
          <h2 className="text-xl font-semibold mb-4">Submit New Mission</h2>
          <form onSubmit={handleSubmit}>
            <textarea
              value={missionPrompt}
              onChange={(e) => setMissionPrompt(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded resize-vertical min-h-[100px] font-sans text-sm"
              placeholder="e.g., Check if there are any crashlooping pods in the default namespace and investigate why"
              required
            />
            <button
              type="submit"
              disabled={submitMission.isPending}
              className="mt-2 px-6 py-3 bg-blue-600 text-white rounded font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {submitMission.isPending ? '🚀 Launching...' : '🚀 Launch Mission'}
            </button>
          </form>
        </div>

        <div className="bg-gray-50 rounded p-4 mb-8">
          <h3 className="font-semibold text-gray-800 mb-2">Example Missions:</h3>
          <ul className="list-disc pl-5 space-y-2 text-gray-600 text-sm">
            <li>"List all pods in the default namespace"</li>
            <li>"Scale the nginx deployment to 3 replicas"</li>
            <li>"Find all pods using more than 500Mi of memory"</li>
            <li>"Check if there are any crashlooping pods and investigate why"</li>
            <li>"Deploy a simple nginx web server with a Service and test it"</li>
          </ul>
        </div>

        <div className="mt-10">
          <h2 className="text-xl font-semibold mb-4">Mission History</h2>
          {isLoading && <p className="text-gray-400">Loading missions...</p>}
          {error && (
            <p className="text-red-600">
              Failed to load missions. Is the agent running?
            </p>
          )}
          {!isLoading && !error && sortedMissions.length === 0 && (
            <p className="text-gray-400">
              No missions yet. Submit your first mission above!
            </p>
          )}
          {!isLoading && !error && sortedMissions.length > 0 && (
            <div className="space-y-4">
              {sortedMissions.map((mission) => (
                <div
                  key={mission.id}
                  onClick={() => navigate(`/missions/${mission.id}`)}
                  className={`bg-gray-50 border-l-4 ${getStatusColor(
                    mission.status
                  )} p-4 rounded cursor-pointer hover:shadow-md transition-shadow`}
                >
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-bold text-gray-800">{mission.id}</span>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-semibold uppercase ${getStatusBadgeColor(
                        mission.status
                      )}`}
                    >
                      {mission.status}
                    </span>
                  </div>
                  <div className="italic text-gray-600 text-sm my-2">
                    "{mission.prompt}"
                  </div>
                  <div className="text-xs text-gray-400">
                    Created: {mission.created_at ? new Date(mission.created_at).toLocaleString() : 'N/A'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
