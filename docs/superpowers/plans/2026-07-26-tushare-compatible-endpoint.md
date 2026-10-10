# Tushare-Compatible Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the local TraderLens runtime at the newly purchased Tushare-compatible endpoint without changing production client code.

**Architecture:** Reuse `TushareConfig.from_env()` and `TushareClient`, which already support an environment-provided token and API URL. Change only the ignored local environment file, then verify configuration, existing client behavior, and one real read-only request.

**Tech Stack:** Python, Tushare SDK, pytest, local `.env.local`.

---

### Task 1: Update and verify the local endpoint

**Files:**
- Modify: `.env.local`
- Test: `tests/test_tushare_config.py`
- Test: `tests/test_tushare_client_query_parameters.py`

- [x] **Step 1: Record the baseline**

Verify `.env.local` is ignored and untracked:

```powershell
git check-ignore -v .env.local
git ls-files --error-unmatch .env.local
```

Expected: the first command identifies `.gitignore`; the second reports that
the file is not tracked.

- [x] **Step 2: Update the local settings**

Preserve every unrelated setting in `.env.local`. Replace only:

```text
TUSHARE_TOKEN=<the owner-supplied token from this task>
TUSHARE_API_URL=https://ts.gyzcloud.top/api
```

Do not add the token to source code, tests, documentation, or command output.

- [x] **Step 3: Run the focused regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/test_tushare_config.py `
  tests/test_tushare_client_query_parameters.py -q
```

Expected: exit code 0 with no failures, skips, or warnings.

- [x] **Step 4: Verify environment loading**

Load `.env.local` through the repository's existing environment-loading
pattern, then call `TushareConfig.from_env()`.

Expected:

```text
token_configured=True
api_url=https://ts.gyzcloud.top/api
```

Never print the token value.

- [x] **Step 5: Run one real read-only smoke request**

Use `TushareClient` to request:

```python
client.query("stock_st", trade_date="20210601")
```

Expected:

- the request succeeds through the configured endpoint;
- the response contains `ts_code`, `name`, `trade_date`, and `type`;
- every returned `trade_date` equals `20210601`;
- only status, columns, row count, and date consistency are printed.

- [x] **Step 6: Confirm scope boundaries**

Verify `.env.local` remains ignored/untracked and no formal artifact or data
directory changed. Do not collect the 172 gap dates or publish any Task 3
artifact in this task.
