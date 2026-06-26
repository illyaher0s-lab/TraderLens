"""
Data Source Metadata Contract - M2

Defines stable metadata structure for all data sources.
All data sources MUST implement get_metadata() returning this structure.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class DataSourceMetadata:
    """
    Metadata for data source identification and validation.
    
    M2 Requirement: All data sources MUST provide this metadata.
    """
    # Identification
    source_id: str  # Unique identifier (e.g., "fixed_fixture_20_stocks_2023_2024")
    source_type: Literal["golden_case", "fixed_fixture", "benchmark_fixture"]
    
    # Versioning
    schema_version: str  # Must match contracts.SCHEMA_VERSION
    snapshot_id: str  # Human-readable snapshot identifier (e.g., "mock_v2.1")
    snapshot_hash: str  # Content hash for cache invalidation
    
    # Timestamps
    created_at: datetime  # When snapshot was created
    
    # Data characteristics
    data_mode: Literal["golden_case", "fixed_fixture", "real_data"]
    is_frozen: bool  # True if snapshot is immutable (deterministic backtest)
    
    # Statistics
    symbol_count: int
    trading_days: int
    date_range_start: str  # ISO format "YYYY-MM-DD"
    date_range_end: str    # ISO format "YYYY-MM-DD"


def validate_metadata(metadata: DataSourceMetadata):
    """
    Validate metadata structure and required fields.
    
    Raises:
        ValueError: If metadata is invalid.
    """
    from contracts import SCHEMA_VERSION
    
    # Schema version must match contracts package
    if metadata.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Data source schema_version '{metadata.schema_version}' "
            f"does not match contracts.SCHEMA_VERSION '{SCHEMA_VERSION}'. "
            f"Data source may be incompatible with current strategy_core."
        )
    
    # Snapshot ID and hash must not be empty
    if not metadata.snapshot_id:
        raise ValueError("snapshot_id cannot be empty")
    
    if not metadata.snapshot_hash:
        raise ValueError("snapshot_hash cannot be empty")
    
    # Symbol count and trading days must be positive
    if metadata.symbol_count <= 0:
        raise ValueError(f"symbol_count must be positive, got {metadata.symbol_count}")
    
    if metadata.trading_days <= 0:
        raise ValueError(f"trading_days must be positive, got {metadata.trading_days}")
