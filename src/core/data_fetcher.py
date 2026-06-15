"""DataFetcher - 数据获取模块

Phase 2A+: 集成缓存管理器，支持四级读取
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Literal
import pandas as pd

from src.core.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class DataFetcher:
    """数据获取器
    
    Phase 2A+: 四级缓存架构
    - memory cache → file cache → API → mock fallback
    
    支持三种模式：
    - mock: 使用本地样例数据
    - live: 优先缓存，缺失时请求 API
    - cache_only: 只读缓存，不请求 API
    """
    
    def __init__(
        self,
        mode: Optional[Literal["mock", "live", "cache_only"]] = None
    ):
        """初始化 DataFetcher
        
        Args:
            mode: 数据模式，默认从环境变量读取
        """
        # 从环境变量读取模式
        if mode is None:
            mode = os.getenv("TRADERLENS_DATA_MODE", "live")
        
        self.mode = mode
        self.cache_manager = CacheManager(mode=mode)
        
        logger.info(f"DataFetcher initialized: mode={mode}")
    
    def get_stock_daily_kline(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "qfq",
        period: Optional[str] = None
    ) -> tuple[pd.DataFrame, dict]:
        """获取股票日线数据（四级缓存）
        
        Args:
            stock_code: 股票代码（6 位数字，如 "000001"）
            start_date: 开始日期（YYYY-MM-DD），默认 1 年前
            end_date: 结束日期（YYYY-MM-DD），默认今天
            adjust: 复权方式（"qfq"=前复权, "hfq"=后复权, ""=不复权）
            period: 时间周期简写（"1m"=1个月, "3m"=3个月, "6m"=6个月, "1y"=1年, "2y"=2年）
        
        Returns:
            (DataFrame, metadata)
            DataFrame 包含列：date, open, close, high, low, volume, ...
            metadata 包含：source, path, is_stale, last_updated
        
        Raises:
            ValueError: 股票代码格式错误
            Exception: 数据拉取失败（仅 live 模式 + 无缓存时）
        """
        # 参数校验
        if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            raise ValueError(f"Invalid stock_code: {stock_code}. Must be 6-digit string.")
        
        # 如果提供了 period，转换为 start_date
        if period:
            days_map = {
                "1m": 30,
                "3m": 90,
                "6m": 180,
                "1y": 365,
                "2y": 730
            }
            days = days_map.get(period, 365)
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        logger.info(f"Fetching daily kline for {stock_code}, adjust={adjust}, mode={self.mode}")
        
        # === 模式判断 ===
        if self.mode == "mock":
            return self._get_mock_data(stock_code, adjust)
        
        # === 1. 尝试从缓存读取 ===
        cached = self.cache_manager.get_price_data(stock_code, adjust)
        
        if cached:
            df, metadata = cached
            
            # cache_only 模式：只返回缓存，不请求 API
            if self.mode == "cache_only":
                logger.info(f"Cache only mode: returning cached data for {stock_code}")
                return df, metadata
            
            # live 模式：如果缓存新鲜，直接返回
            if not metadata.get("is_stale", True):
                logger.info(f"Cache hit (fresh): {stock_code}")
                return df, metadata
            
            # live 模式 + 缓存过期：尝试刷新，失败则返回旧缓存
            logger.info(f"Cache stale, attempting to refresh: {stock_code}")
        
        # === 2. live 模式：尝试从 API 拉取 ===
        if self.mode == "live":
            try:
                df_api = self._fetch_from_api(stock_code, start_date, end_date, adjust)
                
                # 保存到缓存
                self.cache_manager.set_price_data(stock_code, adjust, df_api, source="api")
                
                metadata = {
                    "source": "api",
                    "path": None,
                    "is_stale": False,
                    "last_updated": datetime.now().isoformat()
                }
                
                logger.info(f"API fetch success: {stock_code}, {len(df_api)} rows")
                return df_api, metadata
            
            except Exception as e:
                logger.error(f"API fetch failed for {stock_code}: {e}")
                
                # 如果有旧缓存，返回旧缓存（partial 状态）
                if cached:
                    df, metadata = cached
                    metadata["source"] = "file_cache"
                    metadata["is_stale"] = True
                    logger.warning(f"Returning stale cache for {stock_code}")
                    return df, metadata
                
                # 如果没有缓存，则抛出异常
                raise
        
        # === cache_only 模式但无缓存 ===
        raise Exception(f"No cache available for {stock_code} in cache_only mode")
    
    def get_index_daily_kline(
        self,
        index_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> tuple[pd.DataFrame, dict]:
        """获取指数日线数据（复用 get_stock_daily_kline 逻辑）
        
        指数不需要复权，所以 adjust=""
        """
        # 参数校验
        if not index_code or len(index_code) != 6 or not index_code.isdigit():
            raise ValueError(f"Invalid index_code: {index_code}. Must be 6-digit string.")
        
        logger.info(f"Fetching index kline for {index_code}, mode={self.mode}")
        
        # === 模式判断 ===
        if self.mode == "mock":
            return self._get_mock_data(index_code, adjust="")
        
        # === 1. 尝试从缓存读取 ===
        cached = self.cache_manager.get_index_data(index_code)
        
        if cached:
            df, metadata = cached
            
            # cache_only 模式：只返回缓存
            if self.mode == "cache_only":
                logger.info(f"Cache only mode: returning cached index data for {index_code}")
                return df, metadata
            
            # live 模式：缓存新鲜则返回
            if not metadata.get("is_stale", True):
                logger.info(f"Cache hit (fresh): {index_code}")
                return df, metadata
            
            logger.info(f"Cache stale, attempting to refresh: {index_code}")
        
        # === 2. live 模式：从 API 拉取 ===
        if self.mode == "live":
            try:
                df_api = self._fetch_from_api(index_code, start_date, end_date, adjust="")
                
                # 保存到缓存
                self.cache_manager.set_index_data(index_code, df_api, source="api")
                
                metadata = {
                    "source": "api",
                    "path": None,
                    "is_stale": False,
                    "last_updated": datetime.now().isoformat()
                }
                
                logger.info(f"API fetch success: {index_code}, {len(df_api)} rows")
                return df_api, metadata
            
            except Exception as e:
                logger.error(f"API fetch failed for {index_code}: {e}")
                
                # 返回旧缓存
                if cached:
                    df, metadata = cached
                    metadata["source"] = "file_cache"
                    metadata["is_stale"] = True
                    logger.warning(f"Returning stale cache for {index_code}")
                    return df, metadata
                
                raise
        
        # cache_only 模式但无缓存
        raise Exception(f"No cache available for {index_code} in cache_only mode")
    
    def _fetch_from_api(
        self,
        stock_code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        adjust: str
    ) -> pd.DataFrame:
        """从 AKShare API 拉取数据（带重试机制）"""
        # 默认时间范围：过去 1 年
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        else:
            start_date = start_date.replace("-", "")
        
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        else:
            end_date = end_date.replace("-", "")
        
        logger.info(f"API fetch: {stock_code}, period={start_date}-{end_date}, adjust={adjust}")
        
        try:
            import akshare as ak
        except ImportError:
            logger.error("AKShare not installed. Run: pip install akshare")
            raise
        
        # 重试机制（最多 3 次）
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # AKShare 接口
                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                
                if df is None or df.empty:
                    raise Exception(f"No data returned for {stock_code}")
                
                # 成功获取数据，跳出重试循环
                break
            
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} attempts failed for {stock_code}")
                    raise last_error
        
        # 列名标准化（AKShare 返回中文列名）
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "change_pct",
            "涨跌额": "change_amount",
            "换手率": "turnover_rate"
        })
        
        # 日期转换
        df["date"] = pd.to_datetime(df["date"])
        
        # 按日期排序
        df = df.sort_values("date").reset_index(drop=True)
        
        logger.info(f"Fetched {len(df)} rows for {stock_code}")
        
        return df
    
    def _get_mock_data(self, stock_code: str, adjust: str) -> tuple[pd.DataFrame, dict]:
        """返回 mock 数据（用于测试）"""
        logger.info(f"Mock mode: generating mock data for {stock_code}")
        
        # 生成简单的上涨趋势数据
        import numpy as np
        
        days = 250
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        base_price = 10.0
        trend = np.linspace(0, 5, days)
        noise = np.random.normal(0, 0.3, days)
        close_prices = base_price + trend + noise
        
        open_prices = close_prices + np.random.normal(0, 0.1, days)
        high_prices = np.maximum(open_prices, close_prices) + np.abs(np.random.normal(0, 0.1, days))
        low_prices = np.minimum(open_prices, close_prices) - np.abs(np.random.normal(0, 0.1, days))
        
        volume = np.random.randint(10000000, 50000000, days).astype(float)
        volume[-5:] = volume[-5:] * 1.8
        
        df = pd.DataFrame({
            'date': dates,
            'open': open_prices,
            'close': close_prices,
            'high': high_prices,
            'low': low_prices,
            'volume': volume,
            'amount': volume * close_prices,
            'amplitude': ((high_prices - low_prices) / close_prices * 100).round(2),
            'change_pct': (np.concatenate([[0], np.diff(close_prices) / close_prices[:-1] * 100])).round(2),
            'change_amount': np.concatenate([[0], np.diff(close_prices)]).round(2),
            'turnover_rate': (volume / 1000000000 * 100).round(2)
        })
        
        metadata = {
            "source": "mock",
            "path": None,
            "is_stale": False,
            "last_updated": datetime.now().isoformat()
        }
        
        return df, metadata
    
    def get_stock_sector(self, stock_code: str) -> Optional[dict]:
        """获取股票所属板块/行业信息
        
        Args:
            stock_code: 股票代码（6 位数字）
        
        Returns:
            {
                "sector": str,    # 板块名称（如 "银行"）
                "industry": str   # 行业名称（如 "金融"）
            }
            如果无法识别则返回 None
        """
        logger.info(f"Fetching sector info for {stock_code}")
        
        # Mock 模式：返回固定值
        if self.mode == "mock":
            return {
                "sector": "银行",
                "industry": "金融"
            }
        
        # 真实模式：调用 AKShare API
        try:
            import akshare as ak
            
            # 获取股票行业分类（申万一级）
            df = ak.stock_individual_info_em(symbol=stock_code)
            
            if df is None or df.empty:
                logger.warning(f"No sector info found for {stock_code}")
                return None
            
            # 从返回的 DataFrame 中提取行业信息
            sector = df.loc[df['item'] == '行业', 'value'].values
            industry = df.loc[df['item'] == '所属行业', 'value'].values
            
            return {
                "sector": sector[0] if len(sector) > 0 else "未知板块",
                "industry": industry[0] if len(industry) > 0 else "未知行业"
            }
        
        except Exception as e:
            logger.error(f"Failed to get sector info for {stock_code}: {e}")
            return None
    
    def get_sector_constituents(self, sector_name: str) -> Optional[list]:
        """获取板块内所有股票列表
        
        Args:
            sector_name: 板块名称（如 "银行"）
        
        Returns:
            [
                {"code": "000001", "name": "平安银行"},
                {"code": "600000", "name": "浦发银行"},
                ...
            ]
            如果无法获取则返回 None
        """
        logger.info(f"Fetching constituents for sector {sector_name}")
        
        # Mock 模式：返回固定列表
        if self.mode == "mock":
            return [
                {"code": "000001", "name": "平安银行"},
                {"code": "600000", "name": "浦发银行"},
                {"code": "600036", "name": "招商银行"},
                {"code": "601166", "name": "兴业银行"},
                {"code": "601288", "name": "农业银行"}
            ]
        
        # 真实模式：调用 AKShare API
        try:
            import akshare as ak
            
            # 获取申万行业成分股
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
            
            if df is None or df.empty:
                logger.warning(f"No constituents found for sector {sector_name}")
                return None
            
            # 转换为标准格式
            constituents = [
                {
                    "code": row["代码"],
                    "name": row["名称"]
                }
                for _, row in df.iterrows()
            ]
            
            logger.info(f"Found {len(constituents)} stocks in sector {sector_name}")
            return constituents
        
        except Exception as e:
            logger.error(f"Failed to get constituents for {sector_name}: {e}")
            return None
    
    def get_financial_data(self, stock_code: str) -> Optional[dict]:
        """获取股票财务数据
        
        Args:
            stock_code: 股票代码（6 位数字）
        
        Returns:
            {
                "pe": float,              # 市盈率（TTM）
                "pb": float,              # 市净率
                "roe": float,             # 净资产收益率（%）
                "debt_ratio": float,      # 资产负债率（%）
                "revenue_growth": float,  # 营收增长率（%）
                "profit_growth": float,   # 净利润增长率（%）
                "gross_margin": float,    # 毛利率（%）
                "net_margin": float,      # 净利率（%）
                "current_ratio": float,   # 流动比率
                "quick_ratio": float      # 速动比率
            }
            如果无法获取则返回 None
        """
        logger.info(f"Fetching financial data for {stock_code}")
        
        # Mock 模式：返回固定值
        if self.mode == "mock":
            return {
                "pe": 12.5,
                "pb": 1.8,
                "roe": 15.2,
                "debt_ratio": 45.0,
                "revenue_growth": 18.5,
                "profit_growth": 22.3,
                "gross_margin": 32.5,
                "net_margin": 12.8,
                "current_ratio": 1.6,
                "quick_ratio": 1.2
            }
        
        # 真实模式：调用 AKShare API
        try:
            import akshare as ak
            
            # 获取财务指标（AKShare 提供汇总指标）
            df = ak.stock_financial_analysis_indicator(symbol=stock_code)
            
            if df is None or df.empty:
                logger.warning(f"No financial data found for {stock_code}")
                return None
            
            # 提取最新一期数据（最后一行）
            latest = df.iloc[-1]
            
            return {
                "pe": float(latest.get("市盈率", 0)),
                "pb": float(latest.get("市净率", 0)),
                "roe": float(latest.get("净资产收益率", 0)),
                "debt_ratio": float(latest.get("资产负债率", 0)),
                "revenue_growth": float(latest.get("营业总收入同比增长", 0)),
                "profit_growth": float(latest.get("净利润同比增长", 0)),
                "gross_margin": float(latest.get("销售毛利率", 0)),
                "net_margin": float(latest.get("销售净利率", 0)),
                "current_ratio": float(latest.get("流动比率", 0)),
                "quick_ratio": float(latest.get("速动比率", 0))
            }
        
        except Exception as e:
            logger.error(f"Failed to get financial data for {stock_code}: {e}")
            return None
    
    def get_industry_context(self, sector_name: str) -> Optional[dict]:
        """获取行业上下文（行业平均指标）
        
        Args:
            sector_name: 板块名称（如 "银行"）
        
        Returns:
            {
                "avg_roe": float,    # 行业平均 ROE（%）
                "avg_pe": float,     # 行业平均 PE
                "avg_pb": float      # 行业平均 PB
            }
            如果无法获取则返回 None
        """
        logger.info(f"Fetching industry context for {sector_name}")
        
        # Mock 模式：返回固定值
        if self.mode == "mock":
            return {
                "avg_roe": 12.5,
                "avg_pe": 10.8,
                "avg_pb": 1.5
            }
        
        # 真实模式：计算行业平均值
        try:
            # 获取板块成分股
            constituents = self.get_sector_constituents(sector_name)
            
            if not constituents or len(constituents) == 0:
                logger.warning(f"No constituents for sector {sector_name}")
                return None
            
            # 计算行业平均（取前 20 只股票）
            roe_list = []
            pe_list = []
            pb_list = []
            
            for stock in constituents[:20]:
                try:
                    financial_data = self.get_financial_data(stock["code"])
                    if financial_data:
                        if financial_data.get("roe"):
                            roe_list.append(financial_data["roe"])
                        if financial_data.get("pe"):
                            pe_list.append(financial_data["pe"])
                        if financial_data.get("pb"):
                            pb_list.append(financial_data["pb"])
                except Exception as e:
                    logger.warning(f"Failed to get data for {stock['code']}: {e}")
                    continue
            
            # 计算平均值
            avg_roe = sum(roe_list) / len(roe_list) if roe_list else None
            avg_pe = sum(pe_list) / len(pe_list) if pe_list else None
            avg_pb = sum(pb_list) / len(pb_list) if pb_list else None
            
            if avg_roe is None and avg_pe is None and avg_pb is None:
                return None
            
            return {
                "avg_roe": avg_roe,
                "avg_pe": avg_pe,
                "avg_pb": avg_pb
            }
        
        except Exception as e:
            logger.error(f"Failed to get industry context for {sector_name}: {e}")
            return None
