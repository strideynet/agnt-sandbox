import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { ClarificationInput } from '../components/ClarificationInput';
import { PlanApproval } from '../components/PlanApproval';
import type { Mission } from '../types/mission';

export function MissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logsEndRef = useRef<HTMLDivElement>(null);

  const { data: mission, isLoading, error } = useQuery({
    queryKey: ['mission', id],
    queryFn: () => apiClient.getMission(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const mission = query.state.data as Mission | undefined;
      // Stop polling if mission is completed or failed
      if (mission?.status === 'completed' || mission?.status === 'failed') {
        return false;
      }
      return 500;
    },
  });

  // Mutations for user interactions
  const respondMutation = useMutation({
    mutationFn: (response: string) =>
      apiClient.respondToClarification(id!, response),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mission', id] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => apiClient.approvePlan(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mission', id] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => apiClient.rejectPlan(id!, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mission', id] });
    },
  });

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [mission?.logs]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 py-12 px-5">
        <div className="max-w-6xl mx-auto bg-white rounded-lg shadow-md p-10">
          <p className="text-gray-400">Loading mission...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-100 py-12 px-5">
        <div className="max-w-6xl mx-auto bg-white rounded-lg shadow-md p-10">
          <p className="text-red-600">Error loading mission: {String(error)}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 px-6 py-3 bg-blue-600 text-white rounded font-medium hover:bg-blue-700"
          >
            Back to Mission Control
          </button>
        </div>
      </div>
    );
  }

  if (!mission) {
    return null;
  }

  const getStatusBadgeColor = (status: Mission['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'running':
        return 'bg-yellow-100 text-yellow-800';
      case 'awaiting_clarification':
        return 'bg-amber-100 text-amber-800';
      case 'awaiting_approval':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  const getStatusLabel = (status: Mission['status']) => {
    switch (status) {
      case 'awaiting_clarification':
        return 'awaiting clarification';
      case 'awaiting_approval':
        return 'awaiting approval';
      default:
        return status;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-5">
      <div className="max-w-6xl mx-auto bg-white rounded-lg shadow-md p-10">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-semibold text-gray-800">{mission.id}</h1>
          <span
            className={`px-4 py-2 rounded-full text-sm font-semibold uppercase flex items-center gap-2 ${getStatusBadgeColor(
              mission.status
            )}`}
          >
            {getStatusLabel(mission.status)}
            {(mission.status === 'running' ||
              mission.status === 'awaiting_clarification' ||
              mission.status === 'awaiting_approval') && (
              <span className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
            )}
          </span>
        </div>

        <div className="bg-gray-50 rounded p-5 mb-5">
          <h3 className="font-semibold text-gray-800 mb-2">Mission Prompt:</h3>
          <div className="bg-white p-2.5 border-l-4 border-blue-500 italic text-gray-600">
            {mission.prompt}
          </div>

          <p className="text-xs text-gray-400 mt-4">
            <strong>Created:</strong> {mission.created_at ? new Date(mission.created_at).toLocaleString() : 'N/A'}
            <br />
            {mission.started_at && (
              <>
                <strong>Started:</strong> {new Date(mission.started_at).toLocaleString()}
                <br />
              </>
            )}
            {mission.completed_at && (
              <>
                <strong>Completed:</strong> {new Date(mission.completed_at).toLocaleString()}
              </>
            )}
          </p>
        </div>

        {/* Clarification Request UI */}
        {mission.status === 'awaiting_clarification' && mission.pending_interaction && (
          <ClarificationInput
            interaction={mission.pending_interaction}
            onSubmit={(response) => respondMutation.mutate(response)}
            isSubmitting={respondMutation.isPending}
          />
        )}

        {/* Plan Approval UI */}
        {mission.status === 'awaiting_approval' && mission.pending_interaction && (
          <PlanApproval
            interaction={mission.pending_interaction}
            onApprove={() => approveMutation.mutate()}
            onReject={(reason) => rejectMutation.mutate(reason)}
            isSubmitting={approveMutation.isPending || rejectMutation.isPending}
          />
        )}

        {mission.result && (
          <div className="bg-green-50 border-l-4 border-green-500 p-5 mb-5 rounded">
            <h3 className="font-semibold text-green-800 mb-2">
              Mission Result:
            </h3>
            <div className="whitespace-pre-wrap text-green-800">
              {mission.result}
            </div>
          </div>
        )}

        {mission.error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-5 mb-5 rounded">
            <h3 className="font-semibold text-red-800 mb-2">Error:</h3>
            <div className="whitespace-pre-wrap text-red-800">
              {mission.error}
            </div>
          </div>
        )}

        <h3 className="text-xl font-semibold mb-4">Execution Logs:</h3>
        <div className="bg-gray-900 text-gray-300 p-5 rounded font-mono text-sm max-h-[500px] overflow-y-auto">
          {mission.logs && mission.logs.length > 0 ? (
            <>
              {mission.logs.map((log, index) => (
                <div key={index} className="mb-1 leading-relaxed">
                  {log}
                </div>
              ))}
              <div ref={logsEndRef} />
            </>
          ) : (
            <div className="text-gray-500">No logs yet...</div>
          )}
        </div>

        <p className="mt-5">
          <button
            onClick={() => navigate('/')}
            className="px-6 py-3 bg-blue-600 text-white rounded font-medium hover:bg-blue-700"
          >
            Back to Mission Control
          </button>
        </p>
      </div>
    </div>
  );
}
