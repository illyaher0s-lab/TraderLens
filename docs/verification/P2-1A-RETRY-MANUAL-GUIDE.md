# P2-1A-RETRY 手动验证流程

## 当前状态
- ✅ 验证脚本已就绪：`scripts/verify_p2_1a_workbench_to_observations.py`
- ⚠️ 需要手动启动后端和前端服务

## 手动启动步骤

### 终端 1：启动后端（Windows PowerShell 或 CMD）
```powershell
cd D:\Codex\TraderLens
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

**等待看到：**
```
INFO:     Uvicorn running on http://127.0.0.1:8010
INFO:     Application startup complete.
```

### 终端 2：启动前端（Windows PowerShell 或 CMD）
```powershell
cd D:\Codex\TraderLens\frontend
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8010"
npm run dev
```

**或使用 CMD：**
```cmd
cd D:\Codex\TraderLens\frontend
set NEXT_PUBLIC_API_BASE_URL=http://localhost:8010
npm run dev
```

**等待看到：**
```
ready - started server on 0.0.0.0:3000, url: http://localhost:3000
```

### 终端 3：运行验证脚本（WSL）
```bash
cd /mnt/d/Codex/TraderLens
.venv/Scripts/python.exe scripts/verify_p2_1a_workbench_to_observations.py
```

## 验证流程

脚本会自动：
1. ✅ 检查后端 health endpoint
2. ✅ 检查前端可访问
3. 🌐 打开浏览器访问 /workbench
4. ⌨️ 输入测试消息："我昨天买入了宏昌电子 100 股，成交价 12.34"
5. ⏳ 等待 Agent 响应（最多 60 秒）
6. 📊 查询 /api/observations?status=open
7. 🌐 打开 /observations 页面
8. ✔️ 验证 DOM 和 network log
9. 💾 生成证据文件

## 生成的证据文件

所有证据保存到 `docs/verification/`：
- `p2-1a-workbench-dom.md` - Workbench 页面文本
- `p2-1a-workbench-network-log.json` - Workbench API 调用
- `p2-1a-observations-api.json` - /api/observations 响应
- `p2-1a-observations-dom.md` - Observations 页面文本
- `p2-1a-observations-network-log.json` - Observations API 调用
- `p2-1a-db-path-check.json` - DB 路径验证

## PASS 标准

1. ✅ Workbench API 使用 localhost:8010
2. ✅ Agent 响应包含"已记录"或"执行反馈"
3. ✅ /api/observations 返回至少 1 个 position
4. ✅ Position 包含宏昌电子（603002）
5. ✅ /observations 页面显示股票名称/代码
6. ✅ /observations 页面无错误提示
7. ✅ Observations API 使用 localhost:8010
8. ✅ DB 路径为 data/live_trade.db

## 故障排查

### 后端启动失败
- 检查端口 8010 是否被占用：`netstat -ano | findstr :8010`
- 检查 Python 虚拟环境是否激活
- 查看后端日志错误信息

### 前端启动失败
- 检查端口 3000 是否被占用：`netstat -ano | findstr :3000`
- 删除 `.next` 缓存：`rmdir /s /q .next`
- 确认 `node_modules` 已安装：`npm install`

### 环境变量未生效
- 前端仍请求 8000：删除 `.next` 并重启
- 浏览器显示 404：确认环境变量已设置
- 创建 `frontend/.env.local`：
  ```
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8010
  ```

### Workbench 无响应
- 检查后端日志是否有错误
- 检查浏览器 console 是否有 CORS 错误
- 确认 Tushare token 已配置（deterministic 模式不需要）

### /observations 空白
- 检查 API 响应是否为空
- 查看 `data/live_trade.db` 是否有 observation_positions 表
- 确认 execution_feedback workflow 是否正确执行

## 下一步

验证完成后，提交：
- Git commit 验证脚本
- 创建 `docs/verification/P2_1A_RETRY_DELIVERY.md`
- 总结 PASS/PARTIAL/FAIL 结论
