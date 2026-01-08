import { useState } from 'react';
import type { PendingInteraction } from '../types/mission';

interface ClarificationInputProps {
  interaction: PendingInteraction;
  onSubmit: (response: string) => void;
  isSubmitting: boolean;
}

export function ClarificationInput({
  interaction,
  onSubmit,
  isSubmitting,
}: ClarificationInputProps) {
  const [response, setResponse] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (response.trim()) {
      onSubmit(response);
    }
  };

  return (
    <div className="bg-amber-50 border-l-4 border-amber-500 p-5 mb-5 rounded">
      <h3 className="font-semibold text-amber-800 mb-2 flex items-center gap-2">
        <span className="text-xl">?</span>
        Agent Needs Clarification
      </h3>
      <p className="text-amber-800 mb-4">{interaction.message}</p>

      <form onSubmit={handleSubmit}>
        <textarea
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          className="w-full p-3 border border-amber-300 rounded resize-vertical min-h-[80px] focus:outline-none focus:ring-2 focus:ring-amber-500"
          placeholder="Type your response..."
          required
          disabled={isSubmitting}
        />
        <button
          type="submit"
          disabled={isSubmitting || !response.trim()}
          className="mt-2 px-6 py-3 bg-amber-600 text-white rounded font-medium hover:bg-amber-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {isSubmitting ? 'Sending...' : 'Send Response'}
        </button>
      </form>
    </div>
  );
}
