import type { Mission, SubmitMissionRequest, ApiError, User } from '../types/mission';

// In production, use empty string to use same origin (nginx proxies)
// In development, use localhost:8080
const API_BASE_URL = import.meta.env.VITE_API_URL !== undefined
  ? import.meta.env.VITE_API_URL
  : 'http://localhost:8080';

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
      // Return a never-resolving promise since we're navigating away
      return new Promise(() => {});
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

  // User info
  async getCurrentUser(): Promise<User> {
    return this.fetch<User>('/api/me');
  }

  // Auth endpoints
  initiateLogin(): void {
    window.location.href = `${this.baseUrl}/login`;
  }

  initiateLogout(): void {
    window.location.href = `${this.baseUrl}/logout`;
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
