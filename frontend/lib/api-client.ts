/**
 * Signal Board API Client
 * 
 * Type-safe client for Signal Board REST API.
 * All types match backend contracts (PlannedSignal, etc.)
 */

// Types matching backend contracts
export interface PlannedSignal {
  signal_id: string;
  strategy_id: string;
  strategy_version: string;
  snapshot_hash: string;
  signal_date: string; // ISO date
  intended_execution_date: string; // ISO date
  symbol: string;
  direction: "buy" | "sell";
  planned_action: "enter" | "exit";
  quantity: number | null;
  trigger_reason: string;
  review_status: "pending" | "ignored" | "watching" | "expired";
  reviewed_at: string | null; // ISO datetime
  reviewed_by: string | null;
  rejection_reason: string | null;
  current_price: number | null;
  position_before: number | null;
  created_at: string; // ISO datetime
  metadata: Record<string, any>;
}

export interface SignalSummary {
  signal_date: string;
  total_count: number;
  by_status: Record<string, number>;
  by_direction: Record<string, number>;
  pending_count: number;
}

export interface SignalReviewRequest {
  review_status: "ignored" | "watching" | "expired";
  reviewed_by: string;
  rejection_reason?: string;
}

export interface StrategyInfo {
  strategy_id: string;
  strategy_version: string;
  signal_count: number;
  latest_signal_date: string;
}

export interface SignalListResponse {
  items: PlannedSignal[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

// API Base URL (configurable)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/**
 * List signals with optional filters.
 */
export async function listSignals(params?: {
  signal_date?: string;
  intended_execution_date?: string;
  status?: string;
  direction?: string;
  snapshot_hash?: string;
  strategy_id?: string;
  strategy_version?: string;
  limit?: number;
  offset?: number;
}): Promise<SignalListResponse> {
  const searchParams = new URLSearchParams();
  
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        searchParams.append(key, String(value));
      }
    });
  }
  
  const url = `${API_BASE_URL}/api/signals?${searchParams}`;
  const response = await fetch(url);
  
  if (!response.ok) {
    throw new Error(`Failed to list signals: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Get a single signal by ID.
 */
export async function getSignal(signalId: string): Promise<PlannedSignal> {
  const url = `${API_BASE_URL}/api/signals/${signalId}`;
  const response = await fetch(url);
  
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Signal not found: ${signalId}`);
    }
    throw new Error(`Failed to get signal: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Review a signal (update review status).
 */
export async function reviewSignal(
  signalId: string,
  request: SignalReviewRequest
): Promise<PlannedSignal> {
  const url = `${API_BASE_URL}/api/signals/${signalId}/review`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to review signal: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Get summary statistics for a given date.
 */
export async function getSignalSummary(signalDate: string): Promise<SignalSummary> {
  const url = `${API_BASE_URL}/api/signals/summary?signal_date=${signalDate}`;
  const response = await fetch(url);
  
  if (!response.ok) {
    throw new Error(`Failed to get summary: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * List all strategies (strategy_id + strategy_version combinations).
 */
export async function listStrategies(): Promise<StrategyInfo[]> {
  const url = `${API_BASE_URL}/api/signals/strategies`;
  const response = await fetch(url);
  
  if (!response.ok) {
    throw new Error(`Failed to list strategies: ${response.statusText}`);
  }
  
  return response.json();
}
