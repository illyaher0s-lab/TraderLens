const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

export interface PositionMarketState {
  position_id: string;
  symbol: string;
  trade_type: "actual" | "simulated" | "unknown";
  status: "ok" | "stale" | "unavailable";
  message: string;
  expected_trade_date: string | null;
  trade_date: string | null;
  close: number | null;
  fetched_at: string | null;
  source: string | null;
  api: string | null;
  unrealized_pnl: number | null;
  unrealized_pnl_state: "known_gross" | "unknown_before_entry";
  target_price: number | null;
  stop_price: number | null;
  distance_to_target_pct: number | null;
  distance_to_stop_pct: number | null;
  alerts: string[];
}

interface PositionMarketCheckResponse {
  session_id: string;
  items: PositionMarketState[];
}

type MarketWindow = Window & {
  __traderLensMarketSessionId?: string;
  __traderLensMarketCheck?: Promise<PositionMarketCheckResponse>;
};

function getPageSessionId(target: MarketWindow): string {
  if (!target.__traderLensMarketSessionId) {
    target.__traderLensMarketSessionId = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  }
  return target.__traderLensMarketSessionId;
}

/** Share one market freshness action across the home and positions pages. */
export function ensurePositionMarketCheck(): Promise<PositionMarketCheckResponse> {
  const target = window as MarketWindow;
  if (!target.__traderLensMarketCheck) {
    const sessionId = getPageSessionId(target);
    target.__traderLensMarketCheck = fetch(`${API_BASE_URL}/api/observations/market-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    }).then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `持仓行情检查失败：HTTP ${response.status}`);
      }
      return response.json();
    });
  }
  return target.__traderLensMarketCheck;
}
