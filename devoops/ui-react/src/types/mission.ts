export type MissionStatus =
  | 'pending'
  | 'running'
  | 'awaiting_clarification'
  | 'awaiting_approval'
  | 'completed'
  | 'failed';

export type InteractionType = 'clarification' | 'plan_approval';

export interface PlannedAction {
  tool_name: string;
  description: string;
  parameters: Record<string, unknown>;
  risk_level: 'low' | 'medium' | 'high';
}

export interface PendingInteraction {
  interaction_type: InteractionType;
  message: string;
  planned_actions: PlannedAction[];
  created_at: string;
}

export interface Mission {
  id: string;
  prompt: string;
  status: MissionStatus;
  logs: string[];
  result: string | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  pending_interaction: PendingInteraction | null;
  plan_approved: boolean;
}

export interface TokenInfo {
  header?: Record<string, unknown>;
  claims?: Record<string, unknown>;
  raw?: string;
  error?: string;
}

export interface User {
  username: string;
  email: string;
  token?: TokenInfo;
}

export interface SubmitMissionRequest {
  prompt: string;
}

export interface ClarificationResponse {
  response: string;
}

export interface PlanApprovalResponse {
  approved: boolean;
  rejection_reason?: string;
}

export interface ApiError {
  error: string;
}
