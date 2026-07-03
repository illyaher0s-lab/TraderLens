"""
启动后端服务 (用于 P2-1A DOM 验证)
"""
import os
import sys

# 设置环境变量
os.environ["RESEARCH_CONVERSATION_MODE"] = "deterministic"
os.environ["SERENITY_EXECUTION_MODE"] = "stub"

# 启动 uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
