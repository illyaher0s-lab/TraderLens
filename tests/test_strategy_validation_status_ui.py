import ast
import re
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_validation_page_uses_independent_non_actionable_status_card():
    card = (ROOT / "frontend" / "components" / "StrategyValidationStatusCard.tsx").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "StrategyValidationStatusCard" in card
    assert "actionable" in card
    assert "无信号" in card
    assert "不能作为买卖依据" in card
    assert "<button" not in card
    assert "Action Plan" not in card
    assert "StrategyValidationStatusCard" in page


def test_510880_research_links_to_fail_closed_entry_judgement():
    home = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "/strategy-validations?symbol=510880.SH" in home
    assert "收益差不能当跟踪误差" in home
    assert "成本与历史估值判断缺少比较依据" in home
    assert "当前未确认 510880 合格策略" in page
    assert "资格资料不可核" in page
    assert "观察／不交易" in page
    assert "核验日期未知" in page
    assert "自主成交" in page
    assert "/trades/record" in page
    assert "/observations" in page
    assert 'status?.status === "watch"' in page
    assert 'status?.status === "unavailable"' in page
    assert "本页未提供正式入场信号" in page


def test_isolated_browser_mode_labels_old_research_and_synthetic_trades():
    nav = (ROOT / "frontend" / "components" / "TopNav.tsx").read_text(
        encoding="utf-8"
    )

    assert "NEXT_PUBLIC_CARD019_ISOLATED_TEST" in nav
    assert "2026-10-16 历史研究回放，研究待核" in nav
    assert "合成测试成交" in nav
    assert "不代表实时行情" in nav


def test_card020_page_restores_and_displays_safe_provider_timeout_diagnostics():
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "call_diagnostic" in page
    assert "模型调用超时" in page
    assert "response_received" in page
    assert "retry_stop_reason" in page
    assert "duration_ms" in page
    assert "await restoreState()" in page
    assert "sourceTextRef.current === expectedSourceText" in page
    assert "card020SourceMatches(state.latest_parse, expectedSourceText)" in page
    assert "return digest === result.source_sha256.toUpperCase();" in page
    assert "setParseRecord(matchesSubmittedText ? state.latest_parse : null);" in page
    assert "sourceHashVerified: parseSourceVerified" in page
    assert "const parseReady = parseReview.ready;" in page
    assert "const preflightReady = preflightReview.ready;" in page
    assert "const canFreeze = canFreezeCard020({" in page
    workflow = page[page.index("function Card020Workflow"):]
    mount_effect = workflow[workflow.index("useEffect(() =>"):workflow.index("const post = async")]
    assert 'card020Request<Card020Protocol>(`${root}/protocol`)' in mount_effect
    assert 'card020Request<Card020State>(`${root}/state`)' in mount_effect
    assert "handleParse" not in mount_effect
    assert "error.detail = detail" in page
    assert "/parses/${encodeURIComponent(parseId)}" in page
    assert "savedFailure.status === \"provider_error\"" in page
    assert "card020SourceMatches(savedFailure, submittedText)" in page


def test_card020_confirmation_previews_saved_ai_results_in_chinese_before_freeze():
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )
    review = (ROOT / "frontend" / "lib" / "card020-review.ts").read_text(encoding="utf-8")

    assert 'aria-label="卡020 AI 解析摘要"' in page
    assert "模型解析结果摘要" in page
    for group in ("标的与本金", "信号与调仓", "交易与成本", "分红和净值", "样本与比较账户", "评价与研究限制"):
        assert group in review
    assert "模型实际返回值" in page
    assert "原文依据" in page
    assert "不是模型返回值" in page
    assert "validateCard020ParseForReview" in page
    assert "validateCard020PreflightForFreeze" in page
    assert "canFreezeCard020" in page
    assert "以上模型解析的完整策略和预检锁定的输入/执行版本" in page
    assert "重复使用的历史样本，不是独立样本外结果" in page
    assert "不会运行回测或产生真实成交" in page
    assert 'data-card020-full-review="true"' in page
    assert page.index('data-card020-review-summary="true"') < page.index("本人确认并冻结")
    summary_start = page.index('data-card020-review-summary="true"')
    full_review_marker = page.index('data-card020-full-review="true"')
    details_start = page.rfind("<details", summary_start, full_review_marker)
    summary = page[summary_start:details_start]
    assert "<details" not in summary


def test_card020_review_values_stay_bound_to_backend_parser_contract():
    backend = (ROOT / "backend" / "services" / "strategy_idea_flow.py").read_text(encoding="utf-8")
    api = (ROOT / "backend" / "api" / "card020.py").read_text(encoding="utf-8")
    review = (ROOT / "frontend" / "lib" / "card020-review.ts").read_text(encoding="utf-8")
    tree = ast.parse(backend)
    expected_fields = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CARD020_EXPECTED_FIELDS" for target in node.targets)
    )
    review_fields = dict(re.findall(r'\{ key: "([^"]+)", label: "[^"]+", expectedValue: "([^"]+)"', review))
    protocol_hash = re.search(r'PROTOCOL_SHA256 = "([A-Fa-f0-9]{64})"', api)
    review_protocol_hash = re.search(r'CARD020_REVIEW_PROTOCOL_SHA256 =\s*"([A-Fa-f0-9]{64})"', review)

    assert len(review_fields) == 44
    assert review_fields == expected_fields
    assert protocol_hash is not None and review_protocol_hash is not None
    assert review_protocol_hash.group(1) == protocol_hash.group(1)


def test_card020_results_lead_with_chinese_economics_and_fold_technical_payload():
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )
    summary = (ROOT / "frontend" / "lib" / "card020-results.ts").read_text(encoding="utf-8")

    assert 'aria-label="卡020模拟结果摘要"' in page
    assert "buildCard020OutcomeSummary" in page
    assert "历史模拟结论" in page
    assert "模拟盈亏" in page
    assert "静态半仓" in page
    assert "正式交易计划或交易信号" in summary
    assert "数据限制" in page
    assert "技术证据（" in page
    assert "技术证据（" in page and 'JSON.stringify(result, null, 2)' in page
    assert "function formatCard020SummaryMoney" in summary
    assert "decision_values" in summary

    summary_start = page.index('aria-label="卡020模拟结果摘要"')
    technical_start = page.index("技术证据（")
    assert "批次状态：" in page
    status_start = page.index("批次状态：")
    visible_result = page[summary_start:technical_start]
    visible_status = page[status_start:technical_start]
    technical_evidence = page[technical_start:]
    assert "result_sha256" not in visible_result
    assert "JSON.stringify(result.reconciliation" not in visible_result
    assert "formatCard020RunStatus(runRecord.status)" in visible_status
    assert "runRecord.run_id" not in visible_status
    assert "typeof runRecord?.run_id" in technical_evidence
    assert "evidence_gap" not in visible_result
    assert "JSON.stringify(result, null, 2)" in technical_evidence


def test_card020_historical_input_section_folds_raw_source_identifiers_and_keeps_limits_visible():
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )
    section_start = page.index('<h3 className="font-semibold text-slate-900">历史输入核验</h3>')
    section_end = page.index('aria-label="卡020 AI 解析摘要"', section_start)
    section = page[section_start:section_end]

    assert 'data-card020-input-source-details="true"' in section
    detail_start = section.index('data-card020-input-source-details="true"')
    detail_end = section.index("</details>", detail_start)
    default_text = section[:detail_start]
    technical_details = section[detail_start:detail_end]

    assert "dataLimitations.map" in default_text
    assert "criticalSourceGaps.map" in default_text
    assert "证据强度为低" in default_text
    assert "2018–2020 区间曾用于此前研究" in default_text
    assert "此项预检不计算历史表现" in default_text
    assert "历史表现尚未计算" not in default_text
    for raw_field in (
        "marketInventory?.snapshot_id",
        "dividendInventory?.snapshot_id",
        "preflight.input_inventory_sha256",
        "marketInventory?.source_status",
        "adapter_validation_status",
        "dividendInventory?.source_status",
        "coverage_record",
        "historical_adapter_note",
    ):
        assert raw_field not in default_text
    for source_field in (
        "marketInventory?.snapshot_id",
        "preflight.input_inventory_sha256",
        "marketInventory?.source_status",
        "dividendInventory?.source_status",
        "coverage_record",
        "historical_adapter_note",
        "JSON.stringify(preflight.input_inventory",
    ):
        assert source_field in technical_details


def test_card020_saved_run_result_is_restored_after_page_reload():
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )
    workflow = page[page.index("function Card020Workflow"):]

    assert '`${root}/runs/${latestRun.run_id}`' in workflow
    assert "setRunResult(saved.result as Card020RunResult)" in workflow
