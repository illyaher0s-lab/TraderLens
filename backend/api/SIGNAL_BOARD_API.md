# Signal Board API Reference

**Base URL**: `http://localhost:8000` (dev) or configured via deployment

**Technology**: FastAPI 0.x

**Authentication**: None (M4 v0 is internal tool)

---

## Overview

Signal Board API provides REST endpoints for managing PlannedSignals:
- List signals with filters
- Get single signal detail
- Review signals (update review status)
- Batch review multiple signals
- Get summary statistics

**All endpoints are read-heavy** (list/get) except review operations.

**No write operations for signal content** - signals are immutable after creation, only review_status can be updated.

---

## Data Model

### PlannedSignal

```typescript
interface PlannedSignal {
  // Identity
  signal_id: string;              // SHA256 hash (deterministic)
  strategy_id: string;
  strategy_version: string;       // e.g., "v2.1.0"
  snapshot_hash: string;          // Links to frozen snapshot
  
  // Timing
  signal_date: string;            // ISO date YYYY-MM-DD (when signal generated)
  intended_execution_date: string;// ISO date YYYY-MM-DD (next trading day, T+1)
  
  // Signal Content (IMMUTABLE)
  symbol: string;                 // e.g., "600519.SH"
  direction: "buy" | "sell";      // Data layer only (not for UI display)
  planned_action: "enter" | "exit"; // UI display (入场/离场)
  quantity: number | null;        // null if no sizing yet
  trigger_reason: string;         // Human-readable explanation
  
  // Review State (MUTABLE)
  review_status: "pending" | "ignored" | "watching" | "expired";
  reviewed_at: string | null;     // ISO datetime
  reviewed_by: string | null;
  rejection_reason: string | null;// Required when status=ignored
  
  // Context
  current_price: number | null;   // Close price on signal_date
  position_before: number | null; // Existing position quantity
  
  // Audit
  created_at: string;             // ISO datetime
  metadata: Record<string, any>;  // Strategy params, etc.
}
```

**Key Constraints**:
- `signal_id` is deterministic (same inputs → same ID)
- `direction` (buy/sell) is data layer only
- `planned_action` (enter/exit) is for UI display
- `review_status` CANNOT be set back to "pending"
- `rejection_reason` REQUIRED when `review_status` = "ignored"

---

## Endpoints

### 1. List Signals

**Endpoint**: `GET /api/signals`

**Description**: List signals with optional filters.

**Query Parameters**:
- `signal_date` (optional): Filter by signal generation date (ISO format YYYY-MM-DD)
- `intended_execution_date` (optional): Filter by intended execution date
- `status` (optional): Filter by review status (`pending` | `ignored` | `watching` | `expired`)
- `direction` (optional): Filter by direction (`buy` | `sell`)
- `snapshot_hash` (optional): Filter by snapshot hash
- `strategy_id` (optional): Filter by strategy ID
- `strategy_version` (optional): Filter by strategy version
- `limit` (optional, default: 100): Max results to return (max: 500)
- `offset` (optional, default: 0): Pagination offset

**Response**:
```typescript
{
  items: PlannedSignal[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
```

**Sorting**:
Results are returned in a stable order:
1. `signal_date DESC`
2. `intended_execution_date DESC`
3. `strategy_id ASC`
4. `strategy_version ASC`
5. `symbol ASC`
6. `signal_id ASC`

**Example Request**:
```bash
# Get all pending signals
curl http://localhost:8000/api/signals?status=pending

# Get signals for specific date
curl http://localhost:8000/api/signals?signal_date=2023-12-29

# Get buy signals that are watching
curl http://localhost:8000/api/signals?direction=buy&status=watching

# Pagination
curl http://localhost:8000/api/signals?limit=50&offset=100
```

**Example Response**:
```json
{
  "items": [
    {
      "signal_id": "a1b2c3d4e5f6...",
      "strategy_id": "momentum_v2",
      "strategy_version": "v2.1.0",
      "snapshot_hash": "abc123...",
      "signal_date": "2023-12-29",
      "intended_execution_date": "2024-01-02",
      "symbol": "600519.SH",
      "direction": "buy",
      "planned_action": "enter",
      "quantity": 100,
      "trigger_reason": "Price broke above 5-day high AND Volume surge 2.5x",
      "review_status": "pending",
      "reviewed_at": null,
      "reviewed_by": null,
      "rejection_reason": null,
      "current_price": 1850.0,
      "position_before": null,
      "created_at": "2023-12-29T16:30:00Z",
      "metadata": {}
    }
  ],
  "total": 123,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

**Error Responses**:
- `400 Bad Request`: Invalid date format, `limit > 500`, `limit <= 0`, or `offset < 0`.
- `422 Unprocessable Entity`: Non-integer `limit` or `offset`.

---

### 2. Get Single Signal

**Endpoint**: `GET /api/signals/{signal_id}`

**Description**: Get detailed information for a single signal.

**Path Parameters**:
- `signal_id` (required): Signal ID (SHA256 hash, 64 chars)

**Response**: `PlannedSignal`

**Example Request**:
```bash
curl http://localhost:8000/api/signals/a1b2c3d4e5f6...
```

**Example Response**: Same as single item in list response.

**Error Responses**:
- `404 Not Found`: Signal ID not found

---

### 3. Review Signal

**Endpoint**: `POST /api/signals/{signal_id}/review`

**Description**: Update review status of a signal.

**Path Parameters**:
- `signal_id` (required): Signal ID

**Request Body**:
```typescript
{
  review_status: "ignored" | "watching" | "expired";  // CANNOT set to "pending"
  reviewed_by: string;                                // Username
  rejection_reason?: string;                          // Required when status=ignored
}
```

**Response**: `PlannedSignal` (updated)

**Example Requests**:
```bash
# Mark as watching
curl -X POST http://localhost:8000/api/signals/{signal_id}/review \
  -H "Content-Type: application/json" \
  -d '{
    "review_status": "watching",
    "reviewed_by": "trader1"
  }'

# Ignore with reason
curl -X POST http://localhost:8000/api/signals/{signal_id}/review \
  -H "Content-Type: application/json" \
  -d '{
    "review_status": "ignored",
    "reviewed_by": "trader1",
    "rejection_reason": "Low liquidity"
  }'

# Mark as expired
curl -X POST http://localhost:8000/api/signals/{signal_id}/review \
  -H "Content-Type: application/json" \
  -d '{
    "review_status": "expired",
    "reviewed_by": "trader1"
  }'
```

**Error Responses**:
- `400 Bad Request`: Invalid review_status or missing rejection_reason
- `404 Not Found`: Signal ID not found
- `422 Unprocessable Entity`: Validation error

**Validation Rules**:
- `review_status` CANNOT be "pending" (use POST to create new signal instead)
- `rejection_reason` REQUIRED when `review_status` = "ignored"
- `reviewed_by` REQUIRED (cannot be empty)

---

### 4. Batch Review Signals

**Endpoint**: `POST /api/signals/batch-review`

**Description**: Update review status for multiple signals at once.

**Request Body**:
```typescript
{
  signal_ids: string[];                              // List of signal IDs
  review_status: "ignored" | "watching" | "expired"; // Same status for all
  reviewed_by: string;                               // Username
  rejection_reason?: string;                         // Required when status=ignored
}
```

**Response**:
```typescript
{
  updated_count: number;    // How many signals were updated
  signal_ids: string[];     // IDs that were updated
}
```

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/signals/batch-review \
  -H "Content-Type: application/json" \
  -d '{
    "signal_ids": ["signal_1", "signal_2", "signal_3"],
    "review_status": "watching",
    "reviewed_by": "trader1"
  }'
```

**Example Response**:
```json
{
  "updated_count": 3,
  "signal_ids": ["signal_1", "signal_2", "signal_3"]
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request body
- `422 Unprocessable Entity`: Validation error

---

### 5. Get Summary Statistics

**Endpoint**: `GET /api/signals/summary`

**Description**: Get aggregated statistics for signals on a given date.

**Query Parameters**:
- `signal_date` (required): Date to summarize (ISO format YYYY-MM-DD)

**Response**:
```typescript
{
  signal_date: string;                     // ISO date
  total_count: number;                     // Total signals
  by_status: Record<string, number>;       // Count by review_status
  by_direction: Record<string, number>;    // Count by direction
  pending_count: number;                   // Shortcut for by_status.pending
}
```

**Example Request**:
```bash
curl http://localhost:8000/api/signals/summary?signal_date=2023-12-29
```

**Example Response**:
```json
{
  "signal_date": "2023-12-29",
  "total_count": 15,
  "by_status": {
    "pending": 10,
    "watching": 3,
    "ignored": 2,
    "expired": 0
  },
  "by_direction": {
    "buy": 8,
    "sell": 7
  },
  "pending_count": 10
}
```

---

## Important Design Notes

### 1. `direction` vs. `planned_action`

**`direction` (buy/sell)**:
- Data layer field (contracts, database, API)
- NOT for UI display
- Used for filtering, aggregation

**`planned_action` (enter/exit)**:
- UI display field
- Shows as "入场" (enter) / "离场" (exit) in Chinese UI
- Avoids regulatory implications of "买入建议" / "卖出建议"

**Mapping**:
```
buy  → enter (入场)
sell → exit (离场)
```

**Frontend should display `planned_action`, NOT `direction`.**

---

### 2. Review Status Flow

**Valid Status Values**:
- `pending`: Default after signal generation (未审核)
- `ignored`: User decided not to act (已忽略，需填写原因)
- `watching`: User wants to monitor (已加入观察)
- `expired`: Signal expired, missed execution window (已过期)

**NOT ALLOWED**:
- ❌ `reviewed`: Removed (ambiguous, "看过但没决定" has no value)
- ❌ `approved_for_watch`: Simplified to `watching`
- ❌ `approved_for_execution`: M4 doesn't execute trades

**State Transitions** (enforced by frontend, not API):
```
pending → ignored
pending → watching
pending → expired
```

**Cannot Go Back**:
- Once reviewed (ignored/watching/expired), CANNOT set back to `pending`
- Frontend ReviewForm does NOT offer "pending" option
- API technically allows it (no DB constraint), but frontend prevents

---

### 3. Immutability

**IMMUTABLE after creation**:
- signal_id, strategy_id, strategy_version, snapshot_hash
- signal_date, intended_execution_date
- symbol, direction, planned_action, quantity, trigger_reason
- current_price, position_before
- created_at, metadata

**MUTABLE** (via review operations):
- review_status
- reviewed_at (auto-set on review)
- reviewed_by
- rejection_reason

**No edit endpoint** - signals are audit records, not editable documents.

---

### 4. Deterministic signal_id

**Computed as**:
```
signal_id = sha256(
    strategy_id +
    strategy_version +
    snapshot_hash +
    signal_date +
    intended_execution_date +
    symbol +
    direction +
    trigger_reason
)
```

**Why**:
- Same inputs → same signal_id
- Prevents duplicate imports
- Enables upsert logic (skip existing signals)
- Traceable to exact data + strategy version

---

## Error Codes

### 400 Bad Request
```json
{
  "detail": "rejection_reason is required when review_status is 'ignored'"
}
```

### 404 Not Found
```json
{
  "detail": "Signal not found: {signal_id}"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["body", "review_status"],
      "msg": "Input should be 'ignored', 'watching' or 'expired'",
      "input": "pending"
    }
  ]
}
```

---

## OpenAPI / Swagger UI

Interactive API documentation available at:

**URL**: http://localhost:8000/docs

**Features**:
- Try out endpoints in browser
- See request/response schemas
- Test authentication (when added)

---

## Rate Limiting

**M4 v0**: No rate limiting (internal tool)

**M5+**: Add rate limiting for production (e.g., 100 req/min per IP)

---

## Authentication

**M4 v0**: No authentication (internal tool, localhost only)

**M5+**: Add JWT tokens or API keys for production

---

**Last Updated**: 2026-06-23 (M4 Phase 4)  
**API Version**: Signal Board v0  
**Maintainer**: TraderLens Team
