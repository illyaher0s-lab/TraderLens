"""ResearchMemoryTool - 历史研究记录检索工具

MVP 占位实现：返回空结果，后续接入 RAG / 向量检索。
"""

import logging
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


def search_research_memory(
    query: str,
    limit: int = 5
) -> dict:
    """检索历史研究记录（MVP 占位）
    
    MVP 阶段返回空结果，后续 Phase 3+ 接入：
    - SQLite research_history 表
    - 向量检索（Embedding + FAISS）
    - RAG 相关记录召回
    
    Args:
        query: 检索关键词（如 "平安银行"、"银行板块"）
        limit: 最大返回数量（默认 5）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"ResearchMemoryTool: searching for '{query}', limit={limit}")
    
    # MVP 占位：返回空结果
    ref_id = f"memory_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    
    result = {
        "tool": "search_research_memory",
        "status": "success",
        "result": {
            "query": query,
            "limit": limit,
            "found_count": 0,
            "records": []  # 空列表，后续接入 RAG
        },
        "summary": f"未找到相关历史记录: {query}",
        "signals": ["no_history"],
        "data_refs": {
            "ref_id": ref_id,
            "source": "placeholder",
            "is_stale": False,
            "last_updated": datetime.now().isoformat()
        },
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    
    logger.info(f"ResearchMemoryTool: returned {result['result']['found_count']} records (placeholder)")
    
    return result
