#!/usr/bin/env python3
"""TraderLens UI 启动脚本"""

import subprocess
import sys
import os

# 确保在项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

# 启动 Streamlit
subprocess.run([
    sys.executable,
    "-m",
    "streamlit",
    "run",
    "src/ui/app.py",
    "--server.port=8501",
    "--server.address=0.0.0.0",
    "--theme.base=light",
    "--theme.primaryColor=#171717",
    "--theme.backgroundColor=#ffffff",
    "--theme.secondaryBackgroundColor=#fafafa",
    "--theme.textColor=#171717"
])
