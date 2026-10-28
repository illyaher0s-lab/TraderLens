export const CARD020_REVIEW_PROTOCOL_SHA256 =
  "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D";

export interface Card020ReviewField {
  key: string;
  label: string;
  expectedValue: string;
  chineseValue: string;
  explanation: string;
  summary: boolean;
}

export interface Card020ReviewSection {
  title: string;
  fields: Card020ReviewField[];
}

// expectedValue is used only to reject an unknown or inconsistent saved model value.
// The page renders the saved parse value, never this validator value.
export const CARD020_REVIEW_SECTIONS: Card020ReviewSection[] = [
  {
    title: "标的与本金",
    fields: [
      { key: "strategy_id", label: "策略版本", expectedValue: "510880-vol-budget-v1", chineseValue: "固定研究候选版本 510880-vol-budget-v1", explanation: "用于识别本次研究的策略版本。", summary: false },
      { key: "symbol", label: "研究标的", expectedValue: "510880.SH", chineseValue: "上证红利 ETF（510880.SH）", explanation: "本次只研究这个 ETF。", summary: true },
      { key: "initial_capital_cny", label: "初始本金", expectedValue: "5000", chineseValue: "人民币 5,000 元", explanation: "各比较账户从相同本金开始。", summary: true },
      { key: "assets", label: "允许持有资产", expectedValue: "510880 and CNY cash only", chineseValue: "只持有 510880 与人民币现金", explanation: "策略可持有资产的范围。", summary: true },
      { key: "leverage_and_shorting", label: "杠杆与做空", expectedValue: "forbidden", chineseValue: "禁止杠杆和做空", explanation: "不允许借款扩大持仓或建立空头。", summary: true },
    ],
  },
  {
    title: "信号与调仓",
    fields: [
      { key: "signal_frequency", label: "信号时间", expectedValue: "SSE month-end close", chineseValue: "每个上交所月末交易日收盘后计算", explanation: "用当时已知数据生成月度目标。", summary: true },
      { key: "volatility_lookback", label: "波动观察期", expectedValue: "60 trading-day returns", chineseValue: "最近 60 个交易日收益", explanation: "使用 61 个有效收盘观察值形成 60 个收益。", summary: true },
      { key: "annualized_volatility_target", label: "年化波动目标", expectedValue: "0.10", chineseValue: "10%", explanation: "策略设定的年化波动目标。", summary: true },
      { key: "target_position_formula", label: "目标仓位公式", expectedValue: "min(1, 0.10 / annualized volatility)", chineseValue: "取 100% 与（10% ÷ 年化波动率）中的较小值", explanation: "波动越高，公式给出的目标仓位越低。", summary: true },
      { key: "zero_volatility_rule", label: "波动为零", expectedValue: "zero volatility means 100% target", chineseValue: "目标仓位为 100%", explanation: "零波动时按固定规则处理。", summary: false },
      { key: "missing_market_data_rule", label: "行情缺失", expectedValue: "stop; do not infer or impute", chineseValue: "停止研究，不推断或填补", explanation: "缺少或无法核实关键信息时不继续计算。", summary: true },
      { key: "maximum_exposure", label: "持仓上限", expectedValue: "1.00", chineseValue: "100%", explanation: "持仓不超过全部账户净值。", summary: true },
      { key: "lot_size_shares", label: "交易单位", expectedValue: "100", chineseValue: "每笔按 100 份整数倍", explanation: "目标份额按整手向下取整。", summary: false },
      { key: "execution_timing", label: "执行时点", expectedValue: "next valid SSE trading day open", chineseValue: "下一个有效上交所交易日开盘尝试", explanation: "收盘信号不会在同一收盘价成交。", summary: true },
      { key: "signal_price", label: "信号价格", expectedValue: "causally valid adjusted close", chineseValue: "使用当时可得且符合因果约束的复权收盘价", explanation: "用于计算历史收益和波动率。", summary: false },
    ],
  },
  {
    title: "交易与成本",
    fields: [
      { key: "execution_price", label: "成交价格", expectedValue: "raw open with adverse slippage and adverse tick rounding", chineseValue: "原始开盘价加不利滑点，并向不利方向取整", explanation: "使用日线开盘代理，不把收盘后信息用于成交。", summary: true },
      { key: "volume_capacity", label: "成交量上限", expectedValue: "10% of prior valid trading-day volume, rounded down to 100 shares", chineseValue: "不超过前一有效交易日成交量的 10%，并向下取整到 100 份", explanation: "单位无法核实时应停止，不猜测成交容量。", summary: true },
      { key: "daily_fill_limit", label: "每日成交次数", expectedValue: "at most one fill per account per trading day", chineseValue: "每个账户每个交易日最多成交一笔", explanation: "模拟账户的单日成交限制。", summary: false },
      { key: "commission_rate", label: "佣金率", expectedValue: "0.0003", chineseValue: "成交金额的 0.03%", explanation: "买入和卖出都按此佣金率计算。", summary: true },
      { key: "minimum_commission_cny", label: "最低佣金", expectedValue: "5", chineseValue: "每笔最低 5 元", explanation: "佣金不足最低金额时仍按最低额计。", summary: true },
      { key: "commission_limit_ratio", label: "佣金比例门槛", expectedValue: "0.005", chineseValue: "成交金额的 0.5%", explanation: "用于判断一笔成交是否超过佣金门槛。", summary: true },
      { key: "commission_filter_action", label: "超过佣金门槛", expectedValue: "cancel remaining monthly adjustment above 0.5%", chineseValue: "取消该月剩余调仓，不拆单绕过", explanation: "超过门槛时不降低门槛或拆单。", summary: false },
      { key: "base_slippage", label: "基础滑点", expectedValue: "0.0005", chineseValue: "单边 0.05%", explanation: "基础成本情景采用的单边滑点。", summary: true },
      { key: "stress_slippage", label: "压力滑点", expectedValue: "0.001", chineseValue: "单边 0.10%", explanation: "压力成本情景采用的单边滑点。", summary: true },
      { key: "t_plus_one_and_market_limits", label: "交易制度约束", expectedValue: "enforced", chineseValue: "执行 T+1、停牌和涨跌停约束", explanation: "继续遵守适用的市场限制。", summary: true },
    ],
  },
  {
    title: "分红和净值",
    fields: [
      { key: "dividend_accounting", label: "分红处理", expectedValue: "Card017 V2 entitlement, receivable, payment and no double count", chineseValue: "沿用卡017 V2权益、应收、到账口径，并防止重复计算", explanation: "未到账分红不能当作可用买入现金。", summary: true },
      { key: "main_end_value", label: "主要期末净值", expectedValue: "settled cash plus raw-close holdings plus confirmed dividend receivable", chineseValue: "已结算现金 + 持仓×原始收盘价 + 已确认分红应收", explanation: "主结果采用账面净值，不虚构期末清仓。", summary: true },
      { key: "realized_volatility", label: "账户实现波动", expectedValue: "daily NAV simple returns, sample standard deviation times sqrt(252), minimum two returns", chineseValue: "每日净值简单收益的样本标准差×√252，至少需要两个收益", explanation: "与 60 日信号波动分开报告。", summary: false },
      { key: "drawdown_method", label: "最大回撤", expectedValue: "amount and ratio independently determine peaks, troughs and recovery", chineseValue: "金额和比例分别确定峰值、谷值与恢复日", explanation: "两种回撤不强行共用同一组峰谷。", summary: false },
    ],
  },
  {
    title: "样本与比较账户",
    fields: [
      { key: "research_start", label: "研究开始日", expectedValue: "2018-01-02", chineseValue: "2018-01-02", explanation: "正式评价区间的开始日期。", summary: true },
      { key: "research_end", label: "研究结束日", expectedValue: "2020-12-31", chineseValue: "2020-12-31", explanation: "正式评价区间的结束日期。", summary: true },
      { key: "preheat_start", label: "预热开始日", expectedValue: "2016-12-23", chineseValue: "2016-12-23", explanation: "预热数据只用于形成首次波动估计。", summary: false },
      { key: "preheat_end", label: "预热结束", expectedValue: "2017 year-end", chineseValue: "2017 年末", explanation: "预热区间不计入正式收益。", summary: false },
      { key: "buy_and_hold", label: "买入持有对照", expectedValue: "one independent initial 5000 CNY buy order, then hold", chineseValue: "窗口首个可执行日尽量用 5,000 元买入整手，此后持有", explanation: "分红到账后保留为现金，不自动再投资。", summary: true },
      { key: "static_half", label: "静态半仓对照", expectedValue: "initial up to 2500 CNY including costs, then no rebalance", chineseValue: "初始最多投入 2,500 元（含费用），之后不再平衡", explanation: "用于比较简单降低初始敞口的效果。", summary: true },
      { key: "segment_normalization", label: "分段比较", expectedValue: "2018-2019 and 2020 each start at 5000 for evaluation only; continuous ledger is not reset", chineseValue: "2018–2019 与 2020 分段各以 5,000 元等值评价；连续账户不重置", explanation: "2020 的归一值只用于评价，实际账户仍连续。", summary: false },
    ],
  },
  {
    title: "评价与研究限制",
    fields: [
      { key: "category_order", label: "评价顺序", expectedValue: "D-C-A-B", chineseValue: "先 D，再 C，再 A，最后 B", explanation: "按固定顺序判定，先命中者为唯一类别。", summary: true },
      { key: "D_rule", label: "D 类：证据不可信", expectedValue: "untrusted critical source data or computation blocks evaluation", chineseValue: "关键来源数据或计算不可信时，停止评价", explanation: "不能用其他类别掩盖关键证据缺失。", summary: true },
      { key: "C_no_dynamic_rule", label: "C 类：没有动态调整", expectedValue: "no executed risk adjustment beyond initial build is C", chineseValue: "初始建仓后没有模拟调仓成交，判为 C 类", explanation: "必须检查模拟账本中实际发生的调仓成交。", summary: false },
      { key: "C_stable_dominance_rule", label: "C 类：稳定被对照支配", expectedValue: "the same simple comparator dominates in both base and stress costs", chineseValue: "同一个简单对照在基础和压力成本下都稳定支配候选时，判为 C 类", explanation: "不能把不同对照在两个成本情景中的优势拼接。", summary: true },
      { key: "dominance_definition", label: "支配定义", expectedValue: "comparator terminal value >= candidate, both drawdowns <= candidate, at least one strict improvement", chineseValue: "对照期末净值不低、两项回撤不高，且至少一项严格更好", explanation: "收益与回撤共同决定是否构成支配。", summary: false },
      { key: "A_full_period_rule", label: "A 类：全期条件", expectedValue: "candidate is no worse than buy-and-hold on terminal value and both drawdowns in base and stress, with one strict improvement per scenario", chineseValue: "基础与压力成本下，全期候选的净值和两项回撤均不差于买入持有，且每种情景至少一项更好", explanation: "A 类只支持继续研究，不代表策略资格。", summary: true },
      { key: "A_segment_rule", label: "A 类：分段条件", expectedValue: "buy-and-hold must not dominate in any 2018-2019 or 2020 segment under base or stress costs", chineseValue: "买入持有不得在 2018–2019 或 2020 的任一基础/压力成本分段支配候选", explanation: "四个分段成本比较都必须满足协议条件。", summary: true },
      { key: "B_rule", label: "B 类：其他有效结果", expectedValue: "all other valid results, with tradeoffs and unclear advantages described", chineseValue: "其他有效结果归为 B 类，并说明收益风险取舍", explanation: "结论优势不清时必须如实描述。", summary: false },
    ],
  },
];

export interface Card020ReviewAssessment {
  ready: boolean;
  issues: string[];
  missingFields: string[];
  unknownFields: string[];
}

const REVIEW_FIELDS = CARD020_REVIEW_SECTIONS.flatMap((section) => section.fields);
const REVIEW_FIELD_BY_KEY = new Map(REVIEW_FIELDS.map((field) => [field.key, field]));
const SHA256_PATTERN = /^[A-Fa-f0-9]{64}$/;
const LINE_CLASSIFICATIONS = new Set([
  "mapped_rule", "context", "unsupported", "ambiguous", "contradiction", "unmapped",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function valueText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return String(value);
}

function isMarkdownTableSeparator(line: string): boolean {
  let formatted = line.trim();
  if (!formatted || !formatted.includes("|")) return false;
  if (formatted.startsWith("|")) formatted = formatted.slice(1);
  if (formatted.endsWith("|")) formatted = formatted.slice(0, -1);
  const cells = formatted.split("|");
  return cells.length > 0 && cells.every((rawCell) => {
    let cell = rawCell.trim();
    if (cell.startsWith(":")) cell = cell.slice(1);
    if (cell.endsWith(":")) cell = cell.slice(0, -1);
    return cell.length >= 3 && /^-+$/.test(cell);
  });
}

export function formatCard020ModelValue(fieldKey: string, actualValue: unknown): { known: boolean; text: string } {
  const field = REVIEW_FIELD_BY_KEY.get(fieldKey);
  const rawValue = valueText(actualValue);
  if (!field) return { known: false, text: rawValue ? `未知字段的模型返回值：${rawValue}` : "未知字段未返回值" };
  if (!rawValue.trim()) return { known: false, text: "模型未返回该字段值" };
  if (rawValue !== field.expectedValue) {
    return { known: false, text: `模型返回值无法对应固定修订3规则：${rawValue}` };
  }
  return { known: true, text: field.chineseValue };
}

export function validateCard020ParseForReview({
  record,
  sourceText,
  protocolSha256,
  sourceHashVerified,
}: {
  record: unknown;
  sourceText: string;
  protocolSha256: string;
  sourceHashVerified: boolean;
}): Card020ReviewAssessment {
  const issues: string[] = [];
  const missingFields: string[] = [];
  const unknownFields = new Set<string>();
  const parse = asRecord(record);
  const result = asRecord(parse?.result);

  if (!parse || !result) {
    return { ready: false, issues: ["没有与当前固定原文对应的已保存解析结果。"], missingFields: [], unknownFields: [] };
  }
  if (sourceHashVerified !== true) issues.push("保存解析的原文哈希尚未与当前固定策略原文匹配。");
  if (protocolSha256 !== CARD020_REVIEW_PROTOCOL_SHA256 || parse.protocol_sha256 !== protocolSha256) {
    issues.push("解析记录的协议版本与当前固定修订3不一致。");
  }
  if (parse.status !== "ready_for_confirmation" || result.status !== "ready_for_confirmation") {
    issues.push("解析状态未通过，不能确认冻结。");
  }
  if (!Array.isArray(result.blocking_reasons) || result.blocking_reasons.length > 0) {
    issues.push("解析记录包含阻断原因或缺少阻断检查结果。");
  }
  if (!Array.isArray(result.blocking_fields) || result.blocking_fields.length > 0) {
    issues.push("解析记录包含未通过的字段或缺少字段检查结果。");
  }
  const sourceSha = parse.source_sha256;
  if (typeof sourceSha !== "string" || !SHA256_PATTERN.test(sourceSha)
    || result.source_sha256 !== sourceSha) {
    issues.push("解析记录原文哈希缺失或互相不一致。");
  }
  const parserSha = result.parser_sha256;
  if (typeof parserSha !== "string" || !SHA256_PATTERN.test(parserSha)) {
    issues.push("解析器版本指纹缺失或无效。");
  }

  const fieldValues = asRecord(result.fields);
  if (!fieldValues) {
    issues.push("模型解析字段集合缺失。");
  } else {
    for (const key of Object.keys(fieldValues)) {
      if (!REVIEW_FIELD_BY_KEY.has(key)) unknownFields.add(key);
    }
    for (const field of REVIEW_FIELDS) {
      const rawValue = fieldValues[field.key];
      if (typeof rawValue !== "string" || rawValue.trim() === "") {
        missingFields.push(field.key);
        continue;
      }
      if (rawValue !== field.expectedValue) {
        issues.push(`${field.label}的模型返回值与固定修订3规则不一致。`);
      }
    }
  }

  const rawMappings = result.source_mappings;
  const mappingByKey = new Map<string, Record<string, unknown>>();
  const citedLines = new Set<number>();
  const sourceLines = sourceText.split(/\r\n|\n|\r/);
  const nonemptyLineNumbers = new Set<number>();
  sourceLines.forEach((line, index) => { if (line.trim()) nonemptyLineNumbers.add(index + 1); });
  if (!Array.isArray(rawMappings)) {
    issues.push("模型来源映射列表缺失。");
  } else {
    for (const rawMapping of rawMappings) {
      const mapping = asRecord(rawMapping);
      if (!mapping) {
        unknownFields.add("（映射格式无效）");
        issues.push("存在格式无效的字段来源映射。");
        continue;
      }
      const key = typeof mapping?.field === "string" ? mapping.field : "";
      if (!key || !REVIEW_FIELD_BY_KEY.has(key)) {
        unknownFields.add(key || "（字段名无效）");
        continue;
      }
      if (mappingByKey.has(key)) issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}出现重复映射。`);
      mappingByKey.set(key, mapping);
      if (typeof mapping.value !== "string" || mapping.value !== fieldValues?.[key]) {
        issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}的模型映射值与字段记录不一致。`);
      }
      if (mapping.value !== REVIEW_FIELD_BY_KEY.get(key)?.expectedValue) {
        issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}的映射值与固定修订3规则不一致。`);
      }
      const lineNumbers = mapping.source_line_numbers;
      const quotes = mapping.source_quotes;
      if (!Array.isArray(lineNumbers) || lineNumbers.length === 0
        || !Array.isArray(quotes) || quotes.length !== lineNumbers.length) {
        issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}缺少逐条对应的原文行和引文。`);
        continue;
      }
      lineNumbers.forEach((lineNumber, index) => {
        const quote = quotes[index];
        if (!Number.isInteger(lineNumber) || !nonemptyLineNumbers.has(lineNumber as number)
          || typeof quote !== "string" || quote.trim() === ""
          || !sourceLines[(lineNumber as number) - 1]?.includes(quote)) {
          issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}的原文行号或引文不正确。`);
          return;
        }
        const sourceLine = sourceLines[(lineNumber as number) - 1];
        if (isMarkdownTableSeparator(sourceLine)) {
          issues.push(`${REVIEW_FIELD_BY_KEY.get(key)?.label}引用了格式分隔行。`);
          return;
        }
        citedLines.add(lineNumber as number);
      });
    }
  }

  for (const field of REVIEW_FIELDS) {
    if (!mappingByKey.has(field.key)) missingFields.push(field.key);
  }
  if (fieldValues && Object.keys(fieldValues).length !== REVIEW_FIELDS.length) {
    issues.push("解析字段数量与固定规则清单不一致。");
  }
  if (Array.isArray(rawMappings) && rawMappings.length !== REVIEW_FIELDS.length) {
    issues.push("来源映射数量与固定规则清单不一致。");
  }

  if (unknownFields.size > 0) {
    issues.push(`存在未识别字段：${Array.from(unknownFields).join("、")}。`);
  }

  const rawCoverage = result.line_coverage;
  const coverageByLine = new Map<number, string>();
  if (!Array.isArray(rawCoverage)) {
    issues.push("逐行覆盖记录缺失。");
  } else {
    for (const rawEntry of rawCoverage) {
      const entry = asRecord(rawEntry);
      const number = entry?.line_number;
      const classification = entry?.classification;
      if (!Number.isInteger(number) || !nonemptyLineNumbers.has(number as number)
        || typeof classification !== "string" || !LINE_CLASSIFICATIONS.has(classification)) {
        issues.push("逐行覆盖包含无效行号或类别。");
        continue;
      }
      if (coverageByLine.has(number as number)) issues.push(`原文第 ${number} 行被重复分类。`);
      coverageByLine.set(number as number, classification);
      if (classification === "mapped_rule" && !citedLines.has(number as number)) {
        issues.push(`原文第 ${number} 行标为规则，但没有字段引用。`);
      }
      if (["unsupported", "ambiguous", "contradiction", "unmapped"].includes(classification)) {
        issues.push(`原文第 ${number} 行仍有未解决内容。`);
      }
    }
  }
  for (const number of Array.from(nonemptyLineNumbers)) {
    if (!coverageByLine.has(number)) issues.push(`原文第 ${number} 行未分类。`);
  }
  for (const number of Array.from(citedLines)) {
    if (coverageByLine.get(number) !== "mapped_rule") issues.push(`原文第 ${number} 行被引用但未标为规则。`);
  }

  const dividerLines = Array.from(nonemptyLineNumbers).filter((number) => isMarkdownTableSeparator(sourceLines[number - 1]));
  for (const number of dividerLines) {
    if (coverageByLine.get(number) !== "context") issues.push(`表格格式行第 ${number} 行必须标为 context。`);
  }
  const rawFormatLines = result.deterministic_format_lines;
  if (!Array.isArray(rawFormatLines)) {
    issues.push("程序补记的格式行记录缺失。");
  } else {
    const seenFormatLines = new Set<number>();
    for (const number of rawFormatLines) {
      if (!Number.isInteger(number) || !dividerLines.includes(number as number)
        || coverageByLine.get(number as number) !== "context") {
        issues.push("程序补记行与原文格式行记录不一致。");
      }
      if (seenFormatLines.has(number as number)) issues.push("程序补记行存在重复记录。");
      seenFormatLines.add(number as number);
    }
  }

  const uniqueIssues = Array.from(new Set(issues));
  return {
    ready: uniqueIssues.length === 0 && missingFields.length === 0,
    issues: uniqueIssues,
    missingFields: Array.from(new Set(missingFields)),
    unknownFields: Array.from(unknownFields),
  };
}

export function validateCard020PreflightForFreeze({
  preflight,
  protocolSha256,
  parserSha256,
}: {
  preflight: unknown;
  protocolSha256: string;
  parserSha256: unknown;
}): Card020ReviewAssessment {
  const issues: string[] = [];
  const record = asRecord(preflight);
  if (!record) return { ready: false, issues: ["固定输入预检记录缺失。"], missingFields: [], unknownFields: [] };
  if (record.preflight_id === undefined || record.preflight_id === null || record.preflight_id === "") {
    issues.push("预检记录编号缺失。");
  }
  if (record.status !== "passed_with_disclosed_data_limits") issues.push("预检未通过，不能冻结。");
  if (record.protocol_sha256 !== protocolSha256 || protocolSha256 !== CARD020_REVIEW_PROTOCOL_SHA256) {
    issues.push("预检协议哈希与当前固定修订3不一致。");
  }
  if (typeof record.input_inventory_sha256 !== "string" || !SHA256_PATTERN.test(record.input_inventory_sha256)) {
    issues.push("预检输入清单版本指纹缺失或无效。");
  }
  if (!asRecord(record.input_inventory)) issues.push("预检输入清单内容缺失。");
  const fingerprint = asRecord(record.execution_fingerprint);
  const files = asRecord(fingerprint?.files);
  if (typeof fingerprint?.executor_version !== "string" || !fingerprint.executor_version.trim()
    || typeof fingerprint.bundle_sha256 !== "string" || !SHA256_PATTERN.test(fingerprint.bundle_sha256)) {
    issues.push("执行版本指纹缺失或无效。");
  }
  const parserFingerprint = files?.["backend/services/strategy_idea_flow.py"];
  if (typeof parserSha256 !== "string" || !SHA256_PATTERN.test(parserSha256)
    || parserFingerprint !== parserSha256) {
    issues.push("解析器指纹与预检执行版本不一致。");
  }
  if (!Array.isArray(record.critical_source_gaps) || record.critical_source_gaps.length > 0) {
    issues.push("预检存在关键来源缺口或未提供缺口检查结果。");
  }
  if (!Array.isArray(record.data_limitations) || record.data_limitations.length === 0) {
    issues.push("预检的数据限制未披露。");
  }
  const inventory = asRecord(record.input_inventory);
  const market = asRecord(inventory?.market);
  const dividends = asRecord(inventory?.dividends);
  if (!market || typeof market.snapshot_id !== "string" || !market.snapshot_id.trim()
    || typeof market.manifest_sha256 !== "string" || !SHA256_PATTERN.test(market.manifest_sha256)
    || market.source_status !== "downloaded_unverified_for_research_use"
    || market.adapter_validation_status !== "degraded"
    || market.provider_origin_authenticated !== false) {
    issues.push("行情来源状态、验证状态或来源认证限制缺失。");
  }
  if (!dividends || typeof dividends.snapshot_id !== "string" || !dividends.snapshot_id.trim()
    || typeof dividends.manifest_sha256 !== "string" || !SHA256_PATTERN.test(dividends.manifest_sha256)
    || typeof dividends.source_status !== "string" || !dividends.source_status.includes("raw_unverified")
    || !Array.isArray(dividends.official_spotcheck_dates) || dividends.official_spotcheck_dates.length === 0
    || typeof dividends.coverage_record !== "string" || !dividends.coverage_record.includes("closed")
    || typeof dividends.historical_adapter_note !== "string" || !dividends.historical_adapter_note.includes("raw_unverified")) {
    issues.push("分红来源、抽查范围或未验证限制缺失。");
  }
  const disclosures = Array.isArray(record.data_limitations)
    ? record.data_limitations.filter((item): item is string => typeof item === "string")
    : [];
  const hasDisclosure = (...terms: string[]) => disclosures.some((line) => terms.every((term) => line.includes(term)));
  if (!hasDisclosure("不认证提供方来源")) issues.push("行情提供方来源未认证的限制未披露。");
  if (!hasDisclosure("未获交易所认证", "排队优先级")) issues.push("开盘可交易状态的限制未披露。");
  if (!hasDisclosure("成交量与成交额单位", "没有把该文档绑定")) issues.push("成交量和成交额单位的限制未披露。");
  if (!hasDisclosure("分红快照", "未验证标记", "有限官方抽查")) issues.push("分红快照未验证和有限抽查的限制未披露。");
  if (record.evidence_level !== "low") issues.push("预检证据强度缺失或不符合固定研究边界。");
  if (record.historical_metrics_computed !== false) issues.push("预检阶段不得计算历史表现指标。");
  const uniqueIssues = Array.from(new Set(issues));
  return { ready: uniqueIssues.length === 0, issues: uniqueIssues, missingFields: [], unknownFields: [] };
}

export function canFreezeCard020({
  parseReady,
  preflightReady,
  confirmationChecked,
  busy,
  frozen,
}: {
  parseReady: boolean;
  preflightReady: boolean;
  confirmationChecked: boolean;
  busy: boolean;
  frozen: boolean;
}): boolean {
  return parseReady && preflightReady && confirmationChecked && !busy && !frozen;
}
