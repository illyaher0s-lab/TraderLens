# Gate001 runner connection freeze

Status: frozen for independent acceptance. Formal historical performance remains locked.

## Scope and result

- Mainline step: 4 — deterministic strategy validation for an executable plan.
- Synthetic CLI: `synthetic_verified`; all 9 scenario paths reconciled against the independent reference.
- Terminal boundary: open position and CNY 1,110.00 receivable at 2020-12-31; T+1 unlock metadata is 2021-01-04; no post-window bar was requested or present.
- Formal result flag: `false`; separate controller authorization: `not_authorized`.
- The previous `GATE001_SYNTHETIC_PREFLIGHT.json` remains byte-for-byte unchanged.

## Verification

- `python -m py_compile scripts/run_gate001_once.py scripts/gate001_reference.py` — passed.
- Final focused dependency batch, excluding the raw market-adapter test: 148 passed.
- Synthetic CLI produced JSON, Markdown, and a two-phase JSONL trial with one trial ID; `market_sample=false`, `counts_as_new_research=false`.
- The public formal guard test confirms the loader is not called and no trial is written while the lock is closed.
- A broader earlier dependency batch included `tests/test_gate001_market_adapter.py`; those tests loaded the pinned local 2009–2020 market snapshot to validate its mapping. They did not calculate MA signals, backtest returns, or a verdict. No Holdout data was read.

## Recoverable preimage

Checkpoint: `.codex_snapshots/gate001_formal_connection_20261005_210343/checkpoint.json`  
Checkpoint SHA-256: `2BFF2B8212E5D377D8ED93CB853A9652C732845BA1740DEC14C1E2E5062F17F2`  
All five checkpoint snapshots were re-hashed and matched their recorded pre-change digests.

## Frozen file hashes

| File | SHA-256 |
|---|---|
| `scripts/run_gate001_once.py` | `59BE76180D0CA391A45C56EFBCD0BB7AA401CFEF8D16E40FC8EF5E58320D24EB` |
| `scripts/gate001_reference.py` | `5973E802218C038592414988202556AD2892CB6C5FF3A29890731E4DFCB79E83` |
| `tests/test_gate001_runner.py` | `FACDAEFC0A1FF4DE1622D563A9B4ACD08B4ED1CF8FEF7A0F156943F84419B689` |
| `data/alpha_gate_001/GATE001_PROTOCOL_V1_20261005_a94b1e3f6d6a46af87894e0269777a32.json` | `4E5D9FF76FF9F42ED9B2CD3ADF5B2D06A64BBDA2181F4227471359E44C2BE378` |
| `docs/verification/GATE001_FORMAL_CONNECTION.json` | `ED839DE31715FCC89FD28624B216C97B8F6F8A7259EB022201E8A8E1DD6608E4` |
| `docs/verification/GATE001_FORMAL_CONNECTION.md` | `2917865926B7C40770C2DDBAF9BD37D9F48CE08A548AF7482322CD7E732BB286` |
| `docs/verification/GATE001_TRIALS.jsonl` | `87498CD057E5434AEE465587967106A8DCA00A482C52B425553981D6C7510E9E` |
| `docs/verification/GATE001_SYNTHETIC_PREFLIGHT.json` (preserved) | `D70490FA80D14D81776A1200DD23F0AC60EE0A7C9631D238785562C5BA7ECBF8` |

## Unchanged frozen execution roots

| File | SHA-256 |
|---|---|
| `strategy_core/fill_simulator.py` | `3919DF33872789E9AED892852DF0C18ABE5C8C7CFCA9EA4706C326D0D0756050` |
| `strategy_core/gate001_market_adapter.py` | `F1A342A3CFD7B9E56C2DB15EF32F1325CDC54C31C45BFE936929BCFAE5E0DF05` |
| `strategy_core/signals.py` | `C3C87F738CD3AA1D75A5156D79D8DB782590E6DD1E9F1A7DCDA93209B36427E6` |
| `strategy_core/validator.py` | `B764BD28E937009CE71E3958729FA16DE111419382CA01737DAC238BBE31D08E` |
| `strategy_core/orders.py` | `5C489E6BC6625426BCB97A3E6D9B99792666373E451A6BB1A3C015CBD4BE9117` |
| `strategy_core/backtest_engine.py` | `6886EB726308DC64009D57E78904F268B122273D1C9032B4A9667960865ABACB` |

## One blocker

A separate controller instruction must authorize one historical Gate001 run. Until then, keep `formal_performance_result_allowed=false`; do not load the formal inputs or publish a historical verdict.
