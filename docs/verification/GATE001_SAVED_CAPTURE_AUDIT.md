# GATE001 Saved Capture Offline Audit

- Audit status: `supplemental_offline_audit_complete`
- Source capture status retained: `mismatch_stop`
- Formal parent: `gate001-b840116400c94e38b1b65ada162f65dd`
- Technical capture: `gate001-techprimary-45281f4864e040b9`
- Scope: saved artifacts and frozen local bars only; no engine/reference backtest, API call, holdout, or parameter search.
- This audit does not establish strategy qualification or alpha.

## Trade and signal linkage

- Canonical economic trades: 7/7 across engine, reference, and original formal result.
- Persisted filled orders: 7/7.
- Entry Signal objects captured: 4/4.
- Exit contexts derived from persisted orders: 3/3. Runtime exit Signal objects were not captured.
- Frozen-bar take-profit evidence: 3/3 exit dates met the saved 10% condition.

## Economics and accounts

- Cost fields and cash flows reconciled: 7/7 trades.
- Daily accounts: 2668 normalized engine rows match 2668 reference rows.
- Duplicate initial anchor preserved as evidence: `2010-01-12`; the first of two identical engine anchors is removed only for comparison.
- Primary metrics match the original formal result: `True`.
- Terminal NAV: CNY 155119.15; cash 12691.15; market value 142428.00; receivable 0.00.

## Input serialization and preserved capture errors

- Sidecar actual disk SHA-256: `304CDA0B663D0C59AFE213FEC9EE11124393796C9313DC2BBFD50858A76C62D3`.
- Capture-embedded sidecar SHA-256: `EDFB6C562F846B346C60E97DD561140E0A89734B71F980A86290D09A799F0D13`; it matches the LF-normalized bytes, while the on-disk CRLF bytes have a different hash.
- Existing capture comparison errors remain recorded unchanged: `captured_signal_link_2, captured_signal_link_4, captured_signal_link_6, complete_seven_leg_capture, reference_trade_missing_7`.
- No capture, sidecar, formal result, or historical ledger line was rewritten.

## Ledger addendum

- Appended record: `gate001-capture-audit-097bdd0bead496c3` (`audit_addendum`; not a research run or technical rerun).
- Counts remain new research 1, technical reruns 4, synthetic validations 3.
