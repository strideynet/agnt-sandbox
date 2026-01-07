export type MissionStatus = 'pending' | 'running' | 'completed' | 'failed';

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
}

export interface User {
  username: string;
  email: string;
}

export interface SubmitMissionRequest {
  prompt: string;
}

export interface ApiError {
  error: string;
}
