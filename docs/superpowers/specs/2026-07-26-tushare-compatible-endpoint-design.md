# Tushare-Compatible Endpoint Configuration Design

## Goal

Switch the local TraderLens runtime to the newly purchased Tushare-compatible
endpoint without changing application behavior or committing private account
configuration.

## Existing Capability

- `TushareConfig.from_env()` already reads `TUSHARE_TOKEN` and
  `TUSHARE_API_URL`.
- `TushareClient` already initializes the official Tushare SDK and assigns the
  configured URL to the SDK HTTP endpoint.
- `.env.local` is excluded by Git and already contains both settings.

No new client, provider abstraction, MCP integration, or HTTP wrapper is
required.

## Design

Update only these values in the local `.env.local` file:

- `TUSHARE_TOKEN`: the new account token.
- `TUSHARE_API_URL`: `https://ts.gyzcloud.top/api`.

Keep the existing conservative client limit of 60 requests per minute. The
account permits 150 requests per minute, but using less capacity reduces
throttling risk and is sufficient for the current targeted data checks.

Do not change the repository default endpoint. Other environments continue to
control their endpoint through environment variables.

## Verification

1. Confirm `.env.local` remains ignored and untracked.
2. Run the focused configuration and client tests.
3. Load `TushareConfig.from_env()` and verify the configured URL without
   printing the token.
4. Make one real `stock_st(trade_date=...)` request through `TushareClient`.
5. Report only the response status, columns, row count, and date consistency.

The smoke request is read-only and does not write formal data or consume any
Task 3 publication ID.

## Failure Handling

- Missing token or endpoint: stop without modifying production code.
- Authentication, permission, schema, or date mismatch: report the exact
  provider error and keep `stock_st_collection_provenance_unavailable`.
- No retry loop beyond the existing client's configured retry behavior.

## Scope Boundary

This configuration change does not collect the 172 missing dates, publish a
provenance artifact, modify B3 package `_001`, create `_002`, or authorize
B6/OOS/Gate/Promotion/Signal. Global status remains
`validation_unavailable`.
