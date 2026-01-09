import { useMemo, useState } from 'react';
import type { PendingInteraction, PlannedAction } from '../types/mission';
import { KubernetesIcon } from './KubernetesIcon';

interface PlanApprovalProps {
  interaction: PendingInteraction;
  onApprove: () => void;
  onReject: (reason: string) => void;
  isSubmitting: boolean;
}

// Extract cluster from action parameters
function getActionCluster(action: PlannedAction): string | null {
  const params = action.parameters as Record<string, unknown>;
  if (typeof params.cluster === 'string') {
    return params.cluster;
  }
  return null;
}

// Group actions by cluster
function groupActionsByCluster(actions: PlannedAction[]): Map<string, PlannedAction[]> {
  const groups = new Map<string, PlannedAction[]>();

  for (const action of actions) {
    const cluster = getActionCluster(action) ?? 'unknown';
    const existing = groups.get(cluster) ?? [];
    existing.push(action);
    groups.set(cluster, existing);
  }

  return groups;
}

export function PlanApproval({
  interaction,
  onApprove,
  onReject,
  isSubmitting,
}: PlanApprovalProps) {
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [expandedActions, setExpandedActions] = useState<Set<number>>(new Set());

  // Group actions by cluster and check if multi-cluster
  const actionsByCluster = useMemo(
    () => groupActionsByCluster(interaction.planned_actions),
    [interaction.planned_actions]
  );
  const isMultiCluster = actionsByCluster.size > 1;

  const toggleAction = (index: number) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const getRiskBadgeColor = (risk: PlannedAction['risk_level']) => {
    switch (risk) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'low':
        return 'bg-green-100 text-green-800';
    }
  };

  const getClusterBadgeColor = (cluster: string): string => {
    // Generate a consistent color based on cluster name
    const colors = [
      'bg-purple-100 text-purple-800',
      'bg-blue-100 text-blue-800',
      'bg-indigo-100 text-indigo-800',
      'bg-cyan-100 text-cyan-800',
      'bg-teal-100 text-teal-800',
    ];
    let hash = 0;
    for (let i = 0; i < cluster.length; i++) {
      hash = cluster.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  const handleReject = () => {
    if (rejectionReason.trim()) {
      onReject(rejectionReason);
    }
  };

  // Build a global index for each action (for expandedActions tracking)
  const getGlobalIndex = (clusterIdx: number, actionIdx: number) =>
    clusterIdx * 1000 + actionIdx;

  return (
    <div className="bg-blue-50 border-l-4 border-blue-500 p-5 mb-5 rounded">
      <h3 className="font-semibold text-blue-800 mb-2 flex items-center gap-2">
        <span className="text-xl">!</span>
        Plan Requires Approval
      </h3>
      <p className="text-blue-800 mb-4">{interaction.message}</p>

      {/* Multi-cluster warning */}
      {isMultiCluster && (
        <div className="bg-amber-50 border border-amber-300 rounded p-3 mb-4 flex items-center gap-2">
          <span className="text-amber-600 text-lg">&#9888;</span>
          <span className="text-amber-800 font-medium">
            This plan affects multiple clusters ({actionsByCluster.size} clusters)
          </span>
        </div>
      )}

      {/* Planned Actions List - grouped by cluster */}
      <div className="bg-white rounded p-4 mb-4">
        <h4 className="font-semibold text-gray-700 mb-3">Planned Actions:</h4>

        {Array.from(actionsByCluster.entries()).map(([cluster, actions], clusterIdx) => (
          <div key={cluster} className="mb-4 last:mb-0">
            {/* Cluster header */}
            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-gray-200">
              <KubernetesIcon size={18} />
              <span className={`px-2 py-1 rounded text-sm font-semibold ${getClusterBadgeColor(cluster)}`}>
                {cluster}
              </span>
              <span className="text-gray-500 text-sm">
                ({actions.length} action{actions.length !== 1 ? 's' : ''})
              </span>
            </div>

            <ul className="space-y-3 pl-4">
              {actions.map((action, actionIdx) => {
                const globalIdx = getGlobalIndex(clusterIdx, actionIdx);
                const isExpanded = expandedActions.has(globalIdx);
                const actionCluster = getActionCluster(action);

                return (
                  <li key={actionIdx} className="bg-gray-50 rounded overflow-hidden">
                    <button
                      type="button"
                      onClick={() => toggleAction(globalIdx)}
                      className="w-full flex items-start gap-3 p-3 text-left hover:bg-gray-100 transition-colors"
                    >
                      <span className="text-gray-400 font-mono">{actionIdx + 1}.</span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-medium text-gray-800">
                            {action.description}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-semibold ${getRiskBadgeColor(action.risk_level)}`}
                          >
                            {action.risk_level}
                          </span>
                          {actionCluster && (
                            <span
                              className={`px-2 py-0.5 rounded text-xs font-semibold ${getClusterBadgeColor(actionCluster)}`}
                            >
                              {actionCluster}
                            </span>
                          )}
                        </div>
                        <code className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                          {action.tool_name}
                        </code>
                      </div>
                      <span className="text-gray-400 text-sm">
                        {isExpanded ? '▼' : '▶'}
                      </span>
                    </button>
                    {isExpanded && (
                      <div className="px-3 pb-3 pt-0">
                        <div className="bg-gray-900 rounded p-3 overflow-x-auto">
                          <div className="space-y-3">
                            {Object.entries(action.parameters).map(([key, value]) => (
                              <div key={key}>
                                <span className="text-blue-400 text-xs font-mono font-semibold">{key}:</span>
                                {typeof value === 'string' && value.includes('\n') ? (
                                  <pre className="text-green-400 text-xs font-mono whitespace-pre mt-1 pl-3 border-l-2 border-gray-700">
                                    {value}
                                  </pre>
                                ) : (
                                  <span className="text-green-400 text-xs font-mono ml-2">
                                    {typeof value === 'string' ? value : JSON.stringify(value)}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Approval Buttons */}
      {!showRejectInput ? (
        <div className="flex gap-3">
          <button
            onClick={onApprove}
            disabled={isSubmitting}
            className="px-6 py-3 bg-green-600 text-white rounded font-medium hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Processing...' : 'Approve Plan'}
          </button>
          <button
            onClick={() => setShowRejectInput(true)}
            disabled={isSubmitting}
            className="px-6 py-3 bg-red-600 text-white rounded font-medium hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            Reject
          </button>
        </div>
      ) : (
        <div>
          <textarea
            value={rejectionReason}
            onChange={(e) => setRejectionReason(e.target.value)}
            className="w-full p-3 border border-red-300 rounded resize-vertical min-h-[80px] mb-2 focus:outline-none focus:ring-2 focus:ring-red-500"
            placeholder="Please explain why you're rejecting this plan..."
            required
            disabled={isSubmitting}
          />
          <div className="flex gap-3">
            <button
              onClick={handleReject}
              disabled={isSubmitting || !rejectionReason.trim()}
              className="px-6 py-3 bg-red-600 text-white rounded font-medium hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Sending...' : 'Send Rejection'}
            </button>
            <button
              onClick={() => setShowRejectInput(false)}
              disabled={isSubmitting}
              className="px-6 py-3 bg-gray-300 text-gray-700 rounded font-medium hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
