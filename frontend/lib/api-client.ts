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
  strategy_revision_id: string | null;
  lifecycle_state_at_generation: string | null;
  admission_source: string | null;
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

// C3 Action Plan types
export interface ActionCheck {
  check_id: string;
  label: string;
  source: "strategy_core" | "signal_metadata" | "risk_flag" | "system_rule";
  status: "pass" | "warning" | "blocked" | "unknown";
  blocking: boolean;
  detail: string;
}

export interface UserActionDecision {
  decision: "execute" | "skip" | "partial" | "expired";
  decided_at: string; // ISO datetime
  decided_by: string;
  reason: string | null;
  manual_notes: string | null;
}

export interface ExecutionWindow {
  planned_date: string; // ISO date
  valid_for_date: string; // ISO date
  expires_after_date: string; // ISO date
}

export interface ActionPlan {
  action_plan_id: string;
  signal_id: string;
  strategy_id: string;
  strategy_version: string;
  strategy_revision_id: string | null;
  snapshot_hash: string;
  symbol: string;
  planned_action: "enter" | "exit";
  signal_date: string; // ISO date
  intended_execution_date: string; // ISO date
  action_plan_date: string; // ISO date
  status: "draft" | "ready_for_human" | "user_marked_execute" | "user_marked_skip" | "user_marked_partial" | "expired";
  freshness_status: "fresh" | "stale" | "expired";
  execution_window: ExecutionWindow;
  pre_action_checks: ActionCheck[];
  invalidation_checks: ActionCheck[];
  risk_warnings: string[];
  user_decision: UserActionDecision | null;
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}

export interface ActionPlanDecisionRequest {
  decision: "execute" | "skip" | "partial" | "expired";
  decided_by: string;
  reason?: string;
  manual_notes?: string;
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

/**
 * Get Action Plan for a signal.
 */
export async function getActionPlan(signalId: string): Promise<ActionPlan> {
  const url = `${API_BASE_URL}/api/signals/${signalId}/action-plan`;
  const response = await fetch(url);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Action Plan not available for signal: ${signalId}`);
    }
    throw new Error(`Failed to get action plan: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Submit Action Plan decision.
 */
export async function submitActionDecision(
  signalId: string,
  request: ActionPlanDecisionRequest
): Promise<ActionPlan> {
  const url = `${API_BASE_URL}/api/signals/${signalId}/action-plan/decision`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to submit decision: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// Agent Workbench API (Task 13/14)
// ============================================================================

export interface WorkbenchMessageRequest {
  conversation_id?: string;
  message: string;
  context?: Record<string, any>;
}

export interface WorkbenchMessageResponse {
  conversation_id: string;
  workflow_type: string;
  stage: string;
  agent_reply: string;
  approval_card: ApprovalCardData | null;
  artifact_ids: string[];
  next_required_user_action: string;
}

export interface ApprovalCardData {
  approval_card_id: string;
  workflow_id: string;
  stage: string;
  title: string;
  plain_language_summary: string;
  allowed_decisions: string[];
  blocked_technical_decisions: string[];
  artifact_ids: string[];
  created_at: string;
  decided_at: string | null;
  decision: string | null;
  decided_by: string | null;
}

export interface WorkbenchSession {
  session: {
    session_id: string;
    workflow_kind: string;
    workflow_state: string;
    title: string;
    created_at: string;
    updated_at: string;
  };
  timeline: Array<{
    type: string;
    content: any;
  }>;
}

export interface ApprovalDecisionRequest {
  decision: string;
  decided_by: string;
}

export interface ApprovalDecisionResponse {
  approval_card_id: string;
  decision: string;
  decided_by: string;
  decided_at: string | null;
}

/**
 * Send message to agent workbench.
 */
export async function sendWorkbenchMessage(
  request: WorkbenchMessageRequest
): Promise<WorkbenchMessageResponse> {
  const url = `${API_BASE_URL}/api/agent/workbench/message`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to send message: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get workbench session with timeline.
 */
export async function getWorkbenchSession(
  conversationId: string
): Promise<WorkbenchSession> {
  const url = `${API_BASE_URL}/api/agent/workbench/${conversationId}`;
  const response = await fetch(url);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Session not found: ${conversationId}`);
    }
    throw new Error(`Failed to get session: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Decide on approval card.
 */
export async function decideApprovalCard(
  conversationId: string,
  cardId: string,
  request: ApprovalDecisionRequest
): Promise<ApprovalDecisionResponse> {
  const url = `${API_BASE_URL}/api/agent/workbench/${conversationId}/approval-cards/${cardId}/decide`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to decide: ${response.statusText}`);
  }

  return response.json();
}
