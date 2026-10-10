# Formal SW2021 PIT Qualification

- status: not_qualified
- scope_hash: 35d996036cc04179
- template_hash: 17a1be7ea3547e7a3cc85ea25e63b43aa2ddb4e8ced50c699db5a1bdd9cec9f0
- guard_config_hash: 16119300ea557f33e6628b905597d7c4d0bbfcd0f6eceaa9c9b318ff85af1829
- data_requirements_hash: e2fff0c75089b88eacc068ce5347d5995ad7cd05b2835906182ac66e5dd709fa
- snapshot_hash: da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e
- guard_state: candidate
- checked_trade_days: 2554
- candidate_stock_days_before_market_scope: 10915023
- out_of_scope_bse_stock_days: 255973
- out_of_scope_other_market_stock_days: 0
- expected_stock_days_after_market_scope: 10659050
- excluded_pre_listing_stock_days: 0
- excluded_no_pit_industry_stock_days: 103348
- lifecycle_unknown_stock_days: 0
- blocking_gap_count: 4413
- gap_counts_by_type: {'daily_basic': {'message_count': 2549, 'stock_day_count': 181903}, 'stk_limit': {'message_count': 1674, 'stock_day_count': 7699}, 'adj_factor': {'message_count': 190, 'stock_day_count': 258}}
- first_gap: 20160104: daily_basic missing 258 expected codes
- first_unexplained_gap: 20160104: daily_basic missing 258 expected codes
- elapsed_seconds: 664.135
- not_authorized_for_b6_oos_promotion_or_signal: True

## Interface statistics
- daily: 2554 partitions, 10901549 rows
- daily_basic: 2554 partitions, 10816742 rows
- stk_limit: 2554 partitions, 13213152 rows
- adj_factor: 2554 partitions, 11313625 rows
- index_daily_000300.SH: 2554 partitions, 2554 rows
- index_daily_000905.SH: 2554 partitions, 2554 rows

Guard remains candidate. This result never authorizes B6, OOS, promotion, or a signal.
