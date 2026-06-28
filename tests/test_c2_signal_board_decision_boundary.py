from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_CLIENT = ROOT / "frontend" / "lib" / "api-client.ts"
SIGNALS_PAGE = ROOT / "frontend" / "app" / "signals" / "page.tsx"
SIGNAL_DETAIL_PAGE = ROOT / "frontend" / "app" / "signals" / "[signal_id]" / "page.tsx"


def test_frontend_planned_signal_includes_admission_metadata():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "strategy_revision_id: string | null" in source
    assert "lifecycle_state_at_generation: string | null" in source
    assert "admission_source: string | null" in source
