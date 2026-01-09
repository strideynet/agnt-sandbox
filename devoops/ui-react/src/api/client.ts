import type { Mission, SubmitMissionRequest, ApiError, User, ClustersResponse } from '../types/mission';

// Use empty string for same-origin requests (React and Flask served via same nginx)
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      credentials: 'include', // Include cookies for session
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (response.status === 401) {
      // Redirect to login if unauthorized
      window.location.href = '/login-page';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({
        error: 'Unknown error occurred',
      }));
      throw new Error(error.error);
    }

    return response.json();
  }

  // Mission endpoints
  async getMissions(): Promise<Mission[]> {
    return this.fetch<Mission[]>('/api/missions');
  }

  async getMission(id: string): Promise<Mission> {
    return this.fetch<Mission>(`/api/missions/${id}`);
  }

  async submitMission(data: SubmitMissionRequest): Promise<Mission> {
    return this.fetch<Mission>('/api/missions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Human-in-the-loop endpoints
  async respondToClarification(
    missionId: string,
    response: string
  ): Promise<Mission> {
    return this.fetch<Mission>(`/api/missions/${missionId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ response }),
    });
  }

  async approvePlan(missionId: string): Promise<Mission> {
    return this.fetch<Mission>(`/api/missions/${missionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved: true }),
    });
  }

  async rejectPlan(
    missionId: string,
    rejectionReason: string
  ): Promise<Mission> {
    return this.fetch<Mission>(`/api/missions/${missionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        approved: false,
        rejection_reason: rejectionReason,
      }),
    });
  }

  // Cluster endpoints
  async getClusters(): Promise<ClustersResponse> {
    return this.fetch<ClustersResponse>('/api/clusters');
  }

  // Auth endpoints
  async getCurrentUser(): Promise<User> {
    return this.fetch<User>('/api/me');
  }

  initiateLogin(): void {
    window.location.href = '/login';
  }

  initiateLogout(): void {
    window.location.href = '/logout';
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
