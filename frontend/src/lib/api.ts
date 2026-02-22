/**
 * lib/api.ts
 *
 * Typed API client for all backend endpoints.
 * All methods throw on error with a consistent ApiError shape.
 *
 * Usage:
 *   const { goal } = await api.goals.getActive()
 *   const task = await api.tasks.getToday()
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

// ── Types ──────────────────────────────────────────────────────────────────

export interface ApiError {
  error: string
  detail: string | unknown
  status: number
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: UserSummary
}

export interface UserSummary {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  onboarding_status: string
  onboarding_step: number
  timezone: string
  is_active: boolean
}

export interface DashboardData {
  today: string
  today_task: TodayTask | null
  scores: ScoreData
  top_traits: TraitSummary[]
  week_activity: DayActivity[]
  goal: GoalSummary | null
  latest_review: ReviewSummary | null
}

export interface TodayTask {
  id: string
  identity_focus: string
  title: string
  description: string
  time_estimate_minutes: number
  difficulty: number
  status: 'pending' | 'completed' | 'skipped'
  reflection_submitted: boolean
}

export interface ScoreData {
  transformation: number
  consistency: number
  depth: number
  momentum: number
  alignment: number
  momentum_state: 'rising' | 'holding' | 'declining' | 'critical'
  streak: number
  longest_streak: number
  days_active: number
}

export interface TraitSummary {
  name: string
  current_score: number
  target_score: number
  progress_pct: number
  trend: 'growing' | 'stable' | 'declining'
}

export interface DayActivity {
  date: string
  completed: boolean
  reflected: boolean
  score: number | null
}

export interface GoalSummary {
  statement: string
  progress: number
  objectives_total: number
  objectives_done: number
}

export interface ReviewSummary {
  week_start: string
  tasks_completed: number
  tasks_total: number
  consistency_pct: number
  score_delta: number
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────

class ApiClient {
  private getToken(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('access_token')
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    requiresAuth = true,
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    }

    if (requiresAuth) {
      const token = this.getToken()
      if (token) headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
    })

    if (!res.ok) {
      let errorData: any = {}
      try {
        errorData = await res.json()
      } catch {}
      const err: ApiError = {
        error: errorData.error || 'request_failed',
        detail: errorData.detail || res.statusText,
        status: res.status,
      }

      // Auto-refresh on 401
      if (res.status === 401 && requiresAuth) {
        const refreshed = await this.tryRefreshToken()
        if (refreshed) {
          // Retry original request with new token
          return this.request<T>(path, options, requiresAuth)
        }
        // Refresh failed — redirect to login
        if (typeof window !== 'undefined') {
          window.location.href = '/login'
        }
      }

      throw err
    }

    if (res.status === 204) return undefined as T
    return res.json() as T
  }

  private async tryRefreshToken(): Promise<boolean> {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) return false

    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!res.ok) return false

      const data: TokenResponse = await res.json()
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      return true
    } catch {
      return false
    }
  }

  // ── Auth ────────────────────────────────────────────────────

  auth = {
    signup: (data: { email: string; password: string; display_name?: string; timezone?: string }) =>
      this.request<TokenResponse>('/auth/signup', {
        method: 'POST',
        body: JSON.stringify(data),
      }, false),

    login: (email: string, password: string) =>
      this.request<TokenResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }, false),

    logout: () =>
      this.request<void>('/auth/logout', { method: 'POST' }),

    me: () =>
      this.request<UserSummary>('/auth/me'),

    refresh: (refresh_token: string) =>
      this.request<TokenResponse>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token }),
      }, false),
  }

  // ── Onboarding ───────────────────────────────────────────────

  onboarding = {
    status: () =>
      this.request<{ onboarding_status: string; step: number; screen: string; message: string }>('/onboarding/status'),

    sendInterviewMessage: (message: string) =>
      this.request<{
        message: string
        phase: string
        is_complete: boolean
        onboarding_status: string
      }>('/onboarding/interview/message', {
        method: 'POST',
        body: JSON.stringify({ message }),
      }),

    getInterviewState: () =>
      this.request<{ current_phase: string; messages: any[]; is_complete: boolean }>('/onboarding/interview/state'),

    submitGoal: (raw_goal: string) =>
      this.request<{
        goal_id: string | null
        needs_clarification: boolean
        clarifying_questions: string[]
        strategy: any | null
      }>('/onboarding/goal', {
        method: 'POST',
        body: JSON.stringify({ raw_goal }),
      }),

    clarifyGoal: (raw_goal: string, answers: string) =>
      this.request<any>('/onboarding/goal/clarify', {
        method: 'POST',
        body: JSON.stringify({ raw_goal, answers }),
      }),

    previewStrategy: () =>
      this.request<any>('/onboarding/goal/preview'),

    confirmGoal: () =>
      this.request<{ status: string }>('/onboarding/goal/confirm', { method: 'POST' }),

    activate: () =>
      this.request<{ status: string; message: string; tasks_generated: number }>('/onboarding/activate', { method: 'POST' }),
  }

  // ── Goals ────────────────────────────────────────────────────

  goals = {
    getActive: () =>
      this.request<any>('/goals/active'),

    getTraits: () =>
      this.request<{ traits: any[] }>('/goals/traits'),
  }

  // ── Tasks ────────────────────────────────────────────────────

  tasks = {
    getToday: () =>
      this.request<any>('/tasks/today'),

    start: (taskId: string) =>
      this.request<any>(`/tasks/${taskId}/start`, { method: 'POST' }),

    complete: (taskId: string, data?: { execution_notes?: string; actual_duration_minutes?: number }) =>
      this.request<any>(`/tasks/${taskId}/complete`, {
        method: 'POST',
        body: JSON.stringify(data || {}),
      }),

    skip: (taskId: string, reason: string) =>
      this.request<any>(`/tasks/${taskId}/skip`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),

    getHistory: (days = 30) =>
      this.request<any>(`/tasks/history?days=${days}`),
  }

  // ── Reflections ──────────────────────────────────────────────

  reflections = {
    getQuestions: (taskId: string) =>
      this.request<{ task_id: string; questions: any[] }>(`/reflections/questions/${taskId}`),

    submit: (taskId: string, answers: Array<{ question: string; answer: string; question_type: string }>) =>
      this.request<{
        reflection_id: string
        ai_feedback: string
        sentiment: string
        safety_triggered: boolean
      }>('/reflections', {
        method: 'POST',
        body: JSON.stringify({ task_id: taskId, answers }),
      }),

    getToday: () =>
      this.request<any>('/reflections/today'),

    getLatestWeeklyReview: () =>
      this.request<any>('/reflections/weekly-review'),

    getHistory: (days = 30) =>
      this.request<any>(`/reflections/history?days=${days}`),
  }

  // ── Coach ────────────────────────────────────────────────────

  coach = {
    getActiveSession: () =>
      this.request<{ session_id: string; messages: any[] }>('/coach/sessions/active'),

    createSession: () =>
      this.request<{ session_id: string }>('/coach/sessions', { method: 'POST' }),

    // Streaming — returns a ReadableStream, handled separately
    streamMessage: (sessionId: string, content: string) => {
      const token = this.getToken()
      return fetch(`${BASE_URL}/coach/sessions/${sessionId}/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ content }),
      })
    },
  }

  // ── Progress ─────────────────────────────────────────────────

  progress = {
    getDashboard: () =>
      this.request<DashboardData>('/progress/dashboard'),

    getScores: () =>
      this.request<any>('/progress/scores'),

    getTimeline: (days = 30) =>
      this.request<any>(`/progress/timeline?days=${days}`),

    getTraitsTimeline: () =>
      this.request<any>('/progress/traits/timeline'),

    getStreak: () =>
      this.request<any>('/progress/streak'),
  }
}

export const api = new ApiClient()
