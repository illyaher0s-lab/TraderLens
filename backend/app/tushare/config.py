"""
Tushare Configuration - M3.1

Configuration for Tushare API access and snapshot storage.
Token loaded from environment variable only when needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TushareConfig:
    """
    Configuration for Tushare data source.
    
    M3.1 Design:
    - Token loaded from environment variable (TUSHARE_TOKEN)
    - Snapshot storage paths configurable
    - Rate limits set conservatively to avoid API throttling
    - Missing token only fails at API call time, not at import
    """
    
    # API Configuration
    token: str | None = None  # Loaded from env var or passed explicitly
    api_url: str = "http://8.163.90.143:8686/"  # Custom endpoint
    
    # Rate Limiting (conservative defaults)
    requests_per_minute: int = 60  # 1 request per second
    retry_attempts: int = 3
    retry_delay_seconds: float = 2.0
    
    # Snapshot Storage
    snapshot_root: Path | None = None  # Defaults to data/tushare_snapshots
    
    @property
    def metadata_dir(self) -> Path:
        """Directory for snapshot metadata (manifest, stock list, calendar)."""
        root = self.snapshot_root or self._default_snapshot_root()
        return root / "metadata"
    
    @property
    def data_dir(self) -> Path:
        """Directory for Parquet data files."""
        root = self.snapshot_root or self._default_snapshot_root()
        return root / "data"
    
    @staticmethod
    def _default_snapshot_root() -> Path:
        """Default snapshot root: data/tushare_snapshots relative to project root."""
        # Assuming backend/app/tushare/config.py location
        project_root = Path(__file__).parent.parent.parent.parent
        return project_root / "data" / "tushare_snapshots"
    
    @classmethod
    def from_env(cls) -> TushareConfig:
        """
        Load configuration from environment variables.
        
        Environment variables:
        - TUSHARE_TOKEN: API token (required for API calls)
        - TUSHARE_API_URL: Override the API endpoint
        - TUSHARE_SNAPSHOT_ROOT: Override default snapshot directory
        
        Returns:
            TushareConfig instance
        
        Note: Missing TUSHARE_TOKEN does not raise error here.
              Error raised only when API calls are attempted.
        """
        token = os.getenv("TUSHARE_TOKEN")
        api_url = os.getenv("TUSHARE_API_URL") or cls().api_url
        snapshot_root_str = os.getenv("TUSHARE_SNAPSHOT_ROOT")
        
        snapshot_root = Path(snapshot_root_str) if snapshot_root_str else None
        
        return cls(
            token=token,
            api_url=api_url,
            snapshot_root=snapshot_root,
        )
    
    def ensure_token(self) -> str:
        """
        Get token or raise error if missing.
        
        Returns:
            Token string
        
        Raises:
            ValueError: If token is not configured
        
        Called by: API client when making requests
        """
        if not self.token:
            raise ValueError(
                "Tushare token not configured. "
                "Set TUSHARE_TOKEN environment variable or pass token explicitly to TushareConfig."
            )
        return self.token
    
    def ensure_directories(self) -> None:
        """
        Create snapshot directories if they don't exist.
        
        Called by: snapshot generator before writing files
        """
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
