import { useState } from 'react';
import type { PendingInteraction, PlannedAction } from '../types/mission';

interface PlanApprovalProps {
  interaction: PendingInteraction;
  onApprove: () => void;
  onReject: (reason: string) => void;
  isSubmitting: boolean;
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

  const handleReject = () => {
    if (rejectionReason.trim()) {
      onReject(rejectionReason);
    }
  };

  return (
    <div className="bg-blue-50 border-l-4 border-blue-500 p-5 mb-5 rounded">
      <h3 className="font-semibold text-blue-800 mb-2 flex items-center gap-2">
        <span className="text-xl">!</span>
        Plan Requires Approval
      </h3>
      <p className="text-blue-800 mb-4">{interaction.message}</p>

      {/* Planned Actions List */}
      <div className="bg-white rounded p-4 mb-4">
        <h4 className="font-semibold text-gray-700 mb-3">Planned Actions:</h4>
        <ul className="space-y-3">
          {interaction.planned_actions.map((action, index) => {
            const isExpanded = expandedActions.has(index);
            return (
              <li key={index} className="bg-gray-50 rounded overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleAction(index)}
                  className="w-full flex items-start gap-3 p-3 text-left hover:bg-gray-100 transition-colors"
                >
                  <span className="text-gray-400 font-mono">{index + 1}.</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-gray-800">
                        {action.description}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${getRiskBadgeColor(action.risk_level)}`}
                      >
                        {action.risk_level}
                      </span>
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
