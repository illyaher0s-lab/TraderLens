# P2-1A-RETRY 运行指南

## 前置准备

### 1. 启动后端（终端 1）
```bash
cd D:\Codex\TraderLens
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

等待看到：
```
INFO:     Uvicorn running on http://127.0.0.1:8010
```

### 2. 启动前端（终端 2）
```cmd
cd D:\Codex\TraderLens\frontend
set NEXT_PUBLIC_API_BASE_URL=http://localhost:8010
npm run dev
```

等待看到：
```
ready - started server on 0.0.0.0:3000
```

### 3. 运行验证脚本（终端 3，WSL）
```bash
cd /mnt/d/Codex/TraderLens
.venv/Scripts/python.exe scripts/verify_p2_1a_workbench_to_observations.py
```

## 验证流程

脚本会自动：
1. 打开浏览器访问 /workbench
2. 输入："我昨天买入了宏昌电子 100 股，成交价 12.34"
3. 等待 Agent 响应
4. 查询 /api/observations?status=open
5. 打开 /observations 页面
6. 验证 DOM 和 network log
7. 生成证据文件到 docs/verification/

## 预期结果

- ✅ Workbench 记录买入
- ✅ /api/observations 返回该持仓
- ✅ /observations 页面显示宏昌电子
- ✅ 所有 API 使用 localhost:8010
- ✅ DB 路径正确

## 故障排查

### 前端请求 8000 而非 8010
- 删除 frontend/.next 缓存
- 重启前端 dev server
- 确认环境变量已设置

### Workbench 无响应
- 检查后端日志是否有错误
- 检查 DB 文件是否存在
- 检查 Tushare token 是否配置

### /observations 空白
- 检查 execution_feedback workflow 是否正确创建 position
- 查看 data/live_trade.db 是否有记录
- 检查 API 响应内容
