"""CacheManager - 缓存管理模块

四级缓存：memory → file → API → mock
支持三种模式：mock / live / cache_only
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Literal
import pandas as pd
import json

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器
    
    支持：
    - Memory cache (LRU, 进程内)
    - File cache (Parquet/JSON)
    - TTL (Time To Live)
    - 三种模式切换
    """
    
    def __init__(
        self,
        cache_dir: str = "data/cache",
        mode: Literal["mock", "live", "cache_only"] = "live",
        ttl_hours: int = 24
    ):
        """初始化 CacheManager
        
        Args:
            cache_dir: 缓存目录
            mode: 数据模式
                - mock: 使用本地样例数据
                - live: 优先缓存，缺失时请求 API
                - cache_only: 只读缓存，不请求 API
            ttl_hours: 缓存有效期（小时）
        """
        self.cache_dir = Path(cache_dir)
        self.mode = mode
        self.ttl = timedelta(hours=ttl_hours)
        
        # Memory cache (简单 dict，MVP 不做 LRU)
        self._memory_cache = {}
        
        # 创建缓存目录
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "price").mkdir(exist_ok=True)
        (self.cache_dir / "index").mkdir(exist_ok=True)
        (self.cache_dir / "technical").mkdir(exist_ok=True)
        
        logger.info(f"CacheManager initialized: mode={mode}, ttl={ttl_hours}h, dir={cache_dir}")
    
    def get_price_data(
        self,
        stock_code: str,
        adjust: str = "qfq"
    ) -> Optional[tuple[pd.DataFrame, dict]]:
        """获取价格数据（四级缓存）
        
        Args:
            stock_code: 股票代码
            adjust: 复权方式
        
        Returns:
            (DataFrame, metadata) 或 None
            metadata 包含:
                - source: "memory" | "file_cache" | "api" | "mock"
                - path: 缓存路径
                - is_stale: 是否过期
                - last_updated: 最后更新时间
        """
        cache_key = f"price_{stock_code}_{adjust}"
        
        # 1. Memory cache
        if cache_key in self._memory_cache:
            data, metadata = self._memory_cache[cache_key]
            logger.debug(f"Cache hit (memory): {cache_key}")
            metadata["source"] = "memory"
            return data, metadata
        
        # 2. File cache
        file_path = self.cache_dir / "price" / f"{stock_code}_{adjust}.parquet"
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                metadata = self._read_metadata(file_path)
                
                # 检查是否过期
                if metadata["last_updated"]:
                    last_updated = datetime.fromisoformat(metadata["last_updated"])
                    is_stale = (datetime.now() - last_updated) > self.ttl
                else:
                    is_stale = True
                
                metadata["source"] = "file_cache"
                metadata["is_stale"] = is_stale
                
                # 加载到 memory cache
                self._memory_cache[cache_key] = (df, metadata)
                
                logger.debug(f"Cache hit (file): {cache_key}, stale={is_stale}")
                return df, metadata
            
            except Exception as e:
                logger.warning(f"Failed to read cache file {file_path}: {e}")
        
        # 3. API / Mock (由 DataFetcher 处理)
        logger.debug(f"Cache miss: {cache_key}")
        return None
    
    def set_price_data(
        self,
        stock_code: str,
        adjust: str,
        df: pd.DataFrame,
        source: Literal["api", "mock"] = "api"
    ) -> None:
        """保存价格数据到缓存
        
        Args:
            stock_code: 股票代码
            adjust: 复权方式
            df: DataFrame
            source: 数据来源
        """
        cache_key = f"price_{stock_code}_{adjust}"
        file_path = self.cache_dir / "price" / f"{stock_code}_{adjust}.parquet"
        
        # 保存到文件
        try:
            df.to_parquet(file_path, index=False)
            
            # 保存 metadata
            metadata = {
                "source": source,
                "path": str(file_path),
                "is_stale": False,
                "last_updated": datetime.now().isoformat(),
                "rows": len(df)
            }
            self._write_metadata(file_path, metadata)
            
            # 保存到 memory cache
            self._memory_cache[cache_key] = (df, metadata)
            
            logger.info(f"Cache saved: {cache_key}, {len(df)} rows, source={source}")
        
        except Exception as e:
            logger.error(f"Failed to save cache {file_path}: {e}")
    
    def get_index_data(
        self,
        index_code: str
    ) -> Optional[tuple[pd.DataFrame, dict]]:
        """获取指数数据（复用 get_price_data 逻辑）"""
        cache_key = f"index_{index_code}"
        
        # 1. Memory cache
        if cache_key in self._memory_cache:
            data, metadata = self._memory_cache[cache_key]
            logger.debug(f"Cache hit (memory): {cache_key}")
            metadata["source"] = "memory"
            return data, metadata
        
        # 2. File cache
        file_path = self.cache_dir / "index" / f"{index_code}.parquet"
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                metadata = self._read_metadata(file_path)
                
                # 检查是否过期
                if metadata["last_updated"]:
                    last_updated = datetime.fromisoformat(metadata["last_updated"])
                    is_stale = (datetime.now() - last_updated) > self.ttl
                else:
                    is_stale = True
                
                metadata["source"] = "file_cache"
                metadata["is_stale"] = is_stale
                
                # 加载到 memory cache
                self._memory_cache[cache_key] = (df, metadata)
                
                logger.debug(f"Cache hit (file): {cache_key}, stale={is_stale}")
                return df, metadata
            
            except Exception as e:
                logger.warning(f"Failed to read cache file {file_path}: {e}")
        
        # 3. API / Mock
        logger.debug(f"Cache miss: {cache_key}")
        return None
    
    def set_index_data(
        self,
        index_code: str,
        df: pd.DataFrame,
        source: Literal["api", "mock"] = "api"
    ) -> None:
        """保存指数数据到缓存"""
        cache_key = f"index_{index_code}"
        file_path = self.cache_dir / "index" / f"{index_code}.parquet"
        
        # 保存到文件
        try:
            df.to_parquet(file_path, index=False)
            
            # 保存 metadata
            metadata = {
                "source": source,
                "path": str(file_path),
                "is_stale": False,
                "last_updated": datetime.now().isoformat(),
                "rows": len(df)
            }
            self._write_metadata(file_path, metadata)
            
            # 保存到 memory cache
            self._memory_cache[cache_key] = (df, metadata)
            
            logger.info(f"Cache saved: {cache_key}, {len(df)} rows, source={source}")
        
        except Exception as e:
            logger.error(f"Failed to save cache {file_path}: {e}")
    
    def _read_metadata(self, file_path: Path) -> dict:
        """读取 metadata 文件"""
        metadata_path = file_path.with_suffix(".meta.json")
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read metadata {metadata_path}: {e}")
        
        return {
            "source": "unknown",
            "path": str(file_path),
            "is_stale": True,
            "last_updated": None,
            "rows": 0
        }
    
    def _write_metadata(self, file_path: Path, metadata: dict) -> None:
        """写入 metadata 文件"""
        metadata_path = file_path.with_suffix(".meta.json")
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write metadata {metadata_path}: {e}")
    
    def clear_memory_cache(self) -> None:
        """清空 memory cache"""
        self._memory_cache.clear()
        logger.info("Memory cache cleared")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        price_files = list((self.cache_dir / "price").glob("*.parquet"))
        index_files = list((self.cache_dir / "index").glob("*.parquet"))
        
        return {
            "mode": self.mode,
            "memory_cache_size": len(self._memory_cache),
            "file_cache_price": len(price_files),
            "file_cache_index": len(index_files),
            "cache_dir": str(self.cache_dir)
        }
