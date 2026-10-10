/**
 * Research API client.
 * 
 * Typed client for research module API endpoints.
 */

export interface Theme {
  theme_id: string;
  theme_name: string;
  background: string;
  source_type: string;
  research_mode: string;
  urgency: string;
  notes: string;
  status: string;
  board_version: number;
  created_at: string;
  updated_at: string;
}

export interface Candidate {
  candidate_id: string;
  theme_id: string;
  symbol: string;
  company_name: string | null;
  source_type: string;
  chain_layer: string | null;
  match_reason: string;
  match_confidence: string;
  status: string;
  hard_filter_flags: string[];
  override_reason: string | null;
  created_at: string;
}

export interface ConversationMessage {
  message_id: string;
  theme_id: string;
  role: string;
  content: string;
  linked_proposed_action_ids: string[];
  created_at: string;
}

export interface ProposedAction {
  action_id: string;
  action: string;
  target_id: string;
  args: Record<string, any>;
  rationale: string;
  proposed_by: string;
  proposed_at: string;
  expires_at: string | null;
  board_version: number | null;
}

export interface ConfirmedCandidate {
  confirmed_id: string;
  theme_id: string;
  candidate_id: string;
  source_serenity_run_id: string | null;
  source_evidence_run_id: string | null;
  symbol: string;
  company_name: string;
  chain_layer: string | null;
  thesis_snapshot: string;
  invalidation_rules: any[];
  price_snapshot: Record<string, any>;
  benchmark_snapshot: Record<string, any>;
  confirmation_reason: string;
  evidence_level: string;
  confirmed_by: string;
  confirmed_at: string;
  pool_snapshot_date: string;
  forward_only: true;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010';

export const researchApi = {
  // Themes
  async createTheme(data: {
    theme_name: string;
    background: string;
    source_type: string;
    research_mode?: string;
    urgency?: string;
    notes?: string;
  }): Promise<{ theme_id: string; status: string }> {
    const response = await fetch(`${API_BASE}/api/research/themes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to create theme');
    return response.json();
  },

  async listThemes(): Promise<Theme[]> {
    const response = await fetch(`${API_BASE}/api/research/themes`);
    if (!response.ok) throw new Error('Failed to list themes');
    return response.json();
  },

  async getTheme(themeId: string): Promise<Theme> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}`);
    if (!response.ok) throw new Error('Failed to get theme');
    return response.json();
  },

  // Candidates
  async addCandidate(themeId: string, data: {
    symbol: string;
    verification_id: string;
    match_reason: string;
    source_type: string;
  }): Promise<{ candidate_id: string; status: string }> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/candidates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to add candidate');
    return response.json();
  },

  // Analysis
  async runSerenity(themeId: string): Promise<any> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/run-serenity`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to run Serenity');
    return response.json();
  },

  async runEvidence(candidateIds: string[]): Promise<any> {
    const response = await fetch(`${API_BASE}/api/research/candidates/run-evidence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(candidateIds),
    });
    if (!response.ok) throw new Error('Failed to run Evidence');
    return response.json();
  },

  // Conversation
  async sendMessage(themeId: string, content: string): Promise<{
    user_message: ConversationMessage;
    agent_message: ConversationMessage;
    proposed_actions: ProposedAction[];
  }> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/conversation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) throw new Error('Failed to send message');
    return response.json();
  },

  async getConversation(themeId: string): Promise<ConversationMessage[]> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/conversation`);
    if (!response.ok) throw new Error('Failed to get conversation');
    return response.json();
  },

  // Actions
  async applyAction(actionId: string, appliedBy: string): Promise<{
    action_id: string;
    applied: boolean;
    rejection_reason: string | null;
  }> {
    const response = await fetch(`${API_BASE}/api/research/actions/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId, applied_by: appliedBy }),
    });
    if (!response.ok) throw new Error('Failed to apply action');
    return response.json();
  },

  async getPendingActions(themeId: string): Promise<ProposedAction[]> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/pending-actions`);
    if (!response.ok) throw new Error('Failed to get pending actions');
    return response.json();
  },

  // Confirmation
  async confirmCandidate(candidateId: string, data: {
    approval_card_id: string;
    confirmation_reason: string;
    evidence_level: string;
    confirmed_by: string;
    pool_snapshot_date: string;
    thesis_snapshot: string;
    invalidation_rules: any[];
    price_snapshot: Record<string, any>;
    benchmark_snapshot: Record<string, any>;
    override_reason?: string;
  }): Promise<{ confirmed_id: string; status: string }> {
    const response = await fetch(`${API_BASE}/api/research/candidates/${candidateId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to confirm candidate');
    return response.json();
  },

  async listConfirmedCandidates(themeId: string): Promise<ConfirmedCandidate[]> {
    const response = await fetch(`${API_BASE}/api/research/themes/${themeId}/confirmed-candidates`);
    if (!response.ok) throw new Error('Failed to list confirmed candidates');
    return response.json();
  },
};
