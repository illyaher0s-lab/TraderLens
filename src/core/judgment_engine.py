"""JudgmentEngine - 基本面判断引擎

根据财务数据和策略 Profile，评估股票基本面质量。
"""

import logging
from typing import Literal, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class JudgmentEngine:
    """基本面判断引擎
    
    根据财务指标和行业上下文，评估股票基本面质量。
    支持三种策略：trend（趋势）, growth（成长）, value（价值）
    """
    
    def __init__(self):
        """初始化判断引擎"""
        logger.info("JudgmentEngine initialized")
    
    def evaluate_fundamentals(
        self,
        financial_data: dict,
        industry_context: Optional[dict] = None,
        strategy_profile: Literal["trend", "growth", "value"] = "trend"
    ) -> dict:
        """评估股票基本面
        
        Args:
            financial_data: 财务数据（包含 PE, PB, ROE, 负债率等）
            industry_context: 行业上下文（行业平均 ROE、估值分位等）
            strategy_profile: 策略类型（trend/growth/value）
        
        Returns:
            {
                "absolute_score": float,           # 绝对评分（0-100）
                "industry_relative_score": float,  # 行业相对评分（0-100）
                "combined_score": float,           # 综合评分（0-100）
                "verdict": str,                    # 评级（优秀/良好/一般/差）
                "key_metrics": dict,               # 关键指标
                "strengths": list[str],            # 优势
                "weaknesses": list[str],           # 劣势
                "summary": str                     # 一句话摘要
            }
        """
        logger.info(f"Evaluating fundamentals: strategy={strategy_profile}")
        
        # 1. 提取关键指标
        key_metrics = self._extract_key_metrics(financial_data)
        
        # 2. 计算绝对评分
        absolute_score = self._calculate_absolute_score(key_metrics, strategy_profile)
        
        # 3. 计算行业相对评分（如果有行业上下文）
        industry_relative_score = self._calculate_industry_relative_score(
            key_metrics, industry_context
        ) if industry_context else None
        
        # 4. 综合评分
        if industry_relative_score is not None:
            combined_score = (absolute_score * 0.6 + industry_relative_score * 0.4)
        else:
            combined_score = absolute_score
        
        # 5. 判断评级
        verdict = self._determine_verdict(combined_score)
        
        # 6. 识别优势和劣势
        strengths = self._identify_strengths(key_metrics, strategy_profile)
        weaknesses = self._identify_weaknesses(key_metrics, strategy_profile)
        
        # 7. 生成摘要
        summary = self._generate_summary(verdict, key_metrics, strategy_profile)
        
        result = {
            "absolute_score": round(absolute_score, 2),
            "industry_relative_score": round(industry_relative_score, 2) if industry_relative_score else None,
            "combined_score": round(combined_score, 2),
            "verdict": verdict,
            "key_metrics": key_metrics,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "summary": summary
        }
        
        logger.info(f"Evaluation complete: verdict={verdict}, score={combined_score:.1f}")
        
        return result
    
    def _extract_key_metrics(self, financial_data: dict) -> dict:
        """提取关键指标"""
        return {
            "pe": financial_data.get("pe", None),
            "pb": financial_data.get("pb", None),
            "roe": financial_data.get("roe", None),
            "debt_ratio": financial_data.get("debt_ratio", None),
            "revenue_growth": financial_data.get("revenue_growth", None),
            "profit_growth": financial_data.get("profit_growth", None),
            "gross_margin": financial_data.get("gross_margin", None),
            "net_margin": financial_data.get("net_margin", None),
            "current_ratio": financial_data.get("current_ratio", None),
            "quick_ratio": financial_data.get("quick_ratio", None)
        }
    
    def _calculate_absolute_score(
        self,
        metrics: dict,
        strategy_profile: str
    ) -> float:
        """计算绝对评分（0-100）
        
        根据策略类型调整权重：
        - trend: 平衡型，关注 ROE + 负债率 + 估值
        - growth: 成长型，关注增长率 + 毛利率
        - value: 价值型，关注估值 + ROE + 负债率
        """
        score = 0.0
        
        # 策略权重配置
        if strategy_profile == "trend":
            weights = {
                "roe": 0.25,
                "debt_ratio": 0.20,
                "pe": 0.15,
                "pb": 0.15,
                "revenue_growth": 0.10,
                "profit_growth": 0.10,
                "gross_margin": 0.05
            }
        elif strategy_profile == "growth":
            weights = {
                "revenue_growth": 0.30,
                "profit_growth": 0.25,
                "gross_margin": 0.15,
                "roe": 0.15,
                "pe": 0.10,
                "debt_ratio": 0.05
            }
        else:  # value
            weights = {
                "pe": 0.25,
                "pb": 0.20,
                "roe": 0.20,
                "debt_ratio": 0.15,
                "current_ratio": 0.10,
                "revenue_growth": 0.05,
                "profit_growth": 0.05
            }
        
        # 计算各指标得分
        for metric, weight in weights.items():
            metric_value = metrics.get(metric)
            if metric_value is None:
                continue
            
            metric_score = self._score_metric(metric, metric_value)
            score += metric_score * weight
        
        return min(100.0, max(0.0, score))
    
    def _score_metric(self, metric_name: str, value: float) -> float:
        """给单个指标打分（0-100）"""
        
        if metric_name == "pe":
            # PE 估值：8-15 为优秀，15-25 为良好，25+ 偏贵，<8 可能有问题
            if value <= 0:
                return 0
            elif value < 8:
                return 50
            elif value <= 15:
                return 100
            elif value <= 25:
                return 80 - (value - 15) * 2
            else:
                return max(0, 50 - (value - 25))
        
        elif metric_name == "pb":
            # PB 估值：<1 为低估，1-2 合理，2-4 偏贵，4+ 高估
            if value <= 0:
                return 0
            elif value < 1:
                return 90 + value * 10
            elif value <= 2:
                return 100 - (value - 1) * 10
            elif value <= 4:
                return 80 - (value - 2) * 15
            else:
                return max(0, 50 - (value - 4) * 5)
        
        elif metric_name == "roe":
            # ROE：15%+ 优秀，10-15% 良好，5-10% 一般，<5% 差
            if value < 0:
                return 0
            elif value < 5:
                return value * 10
            elif value < 10:
                return 50 + (value - 5) * 6
            elif value < 15:
                return 80 + (value - 10) * 4
            else:
                return min(100, 100 + (value - 15) * 0.5)
        
        elif metric_name == "debt_ratio":
            # 负债率：<40% 优秀，40-60% 良好，60-80% 一般，80%+ 高风险
            if value < 0:
                return 0
            elif value < 40:
                return 100
            elif value < 60:
                return 90 - (value - 40) * 0.5
            elif value < 80:
                return 70 - (value - 60) * 1.5
            else:
                return max(0, 40 - (value - 80) * 0.5)
        
        elif metric_name in ["revenue_growth", "profit_growth"]:
            # 增长率：20%+ 优秀，10-20% 良好，0-10% 一般，<0 差
            if value < 0:
                return max(0, 50 + value * 2)
            elif value < 10:
                return 60 + value * 2
            elif value < 20:
                return 80 + (value - 10)
            else:
                return min(100, 90 + (value - 20) * 0.5)
        
        elif metric_name == "gross_margin":
            # 毛利率：30%+ 优秀，20-30% 良好，10-20% 一般，<10% 差
            if value < 0:
                return 0
            elif value < 10:
                return value * 4
            elif value < 20:
                return 40 + (value - 10) * 3
            elif value < 30:
                return 70 + (value - 20) * 2
            else:
                return min(100, 90 + (value - 30) * 0.5)
        
        elif metric_name in ["current_ratio", "quick_ratio"]:
            # 流动比率：1.5-2.5 优秀，1-1.5 良好，<1 风险
            if value < 1:
                return value * 50
            elif value < 1.5:
                return 70 + (value - 1) * 20
            elif value < 2.5:
                return 90 + (value - 1.5) * 10
            else:
                return 100
        
        else:
            return 50  # 未知指标默认 50 分
    
    def _calculate_industry_relative_score(
        self,
        metrics: dict,
        industry_context: dict
    ) -> float:
        """计算行业相对评分（0-100）"""
        # MVP: 简化实现，只比较 ROE
        stock_roe = metrics.get("roe")
        industry_avg_roe = industry_context.get("avg_roe")
        
        if stock_roe is None or industry_avg_roe is None:
            return 50  # 无数据时返回中性分
        
        # 相对强度
        if industry_avg_roe <= 0:
            return 50
        
        relative_strength = stock_roe / industry_avg_roe
        
        if relative_strength >= 1.5:
            return 100  # 远超行业平均
        elif relative_strength >= 1.2:
            return 90
        elif relative_strength >= 1.0:
            return 80
        elif relative_strength >= 0.8:
            return 60
        elif relative_strength >= 0.6:
            return 40
        else:
            return 20  # 远低于行业平均
    
    def _determine_verdict(self, score: float) -> Literal["优秀", "良好", "一般", "差"]:
        """判断评级"""
        if score >= 80:
            return "优秀"
        elif score >= 60:
            return "良好"
        elif score >= 40:
            return "一般"
        else:
            return "差"
    
    def _identify_strengths(self, metrics: dict, strategy_profile: str) -> list[str]:
        """识别优势"""
        strengths = []
        
        # ROE
        roe = metrics.get("roe")
        if roe and roe >= 15:
            strengths.append(f"ROE 优秀 ({roe:.1f}%)")
        
        # 负债率
        debt_ratio = metrics.get("debt_ratio")
        if debt_ratio and debt_ratio < 40:
            strengths.append(f"负债率低 ({debt_ratio:.1f}%)")
        
        # 增长率
        if strategy_profile == "growth":
            revenue_growth = metrics.get("revenue_growth")
            if revenue_growth and revenue_growth >= 20:
                strengths.append(f"营收增长快 ({revenue_growth:.1f}%)")
            
            profit_growth = metrics.get("profit_growth")
            if profit_growth and profit_growth >= 20:
                strengths.append(f"利润增长快 ({profit_growth:.1f}%)")
        
        # 估值
        if strategy_profile == "value":
            pe = metrics.get("pe")
            if pe and 8 <= pe <= 15:
                strengths.append(f"估值合理 (PE {pe:.1f})")
            
            pb = metrics.get("pb")
            if pb and pb < 1.5:
                strengths.append(f"PB 低估 ({pb:.2f})")
        
        return strengths
    
    def _identify_weaknesses(self, metrics: dict, strategy_profile: str) -> list[str]:
        """识别劣势"""
        weaknesses = []
        
        # ROE
        roe = metrics.get("roe")
        if roe and roe < 8:
            weaknesses.append(f"ROE 偏低 ({roe:.1f}%)")
        
        # 负债率
        debt_ratio = metrics.get("debt_ratio")
        if debt_ratio and debt_ratio > 70:
            weaknesses.append(f"负债率高 ({debt_ratio:.1f}%)")
        
        # 增长率
        revenue_growth = metrics.get("revenue_growth")
        if revenue_growth and revenue_growth < 0:
            weaknesses.append(f"营收负增长 ({revenue_growth:.1f}%)")
        
        profit_growth = metrics.get("profit_growth")
        if profit_growth and profit_growth < 0:
            weaknesses.append(f"利润负增长 ({profit_growth:.1f}%)")
        
        # 估值
        pe = metrics.get("pe")
        if pe and pe > 30:
            weaknesses.append(f"PE 偏高 ({pe:.1f})")
        
        return weaknesses
    
    def _generate_summary(self, verdict: str, metrics: dict, strategy_profile: str) -> str:
        """生成一句话摘要"""
        pe = metrics.get("pe", 0)
        roe = metrics.get("roe", 0)
        debt_ratio = metrics.get("debt_ratio", 0)
        
        summary_parts = [f"基本面{verdict}"]
        
        if pe:
            summary_parts.append(f"PE {pe:.1f}")
        if roe:
            summary_parts.append(f"ROE {roe:.1f}%")
        if debt_ratio:
            summary_parts.append(f"负债率 {debt_ratio:.1f}%")
        
        return ", ".join(summary_parts)
