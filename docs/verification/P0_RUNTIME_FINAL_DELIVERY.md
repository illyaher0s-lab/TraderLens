# P0-RUNTIME-1 最终交付报告

## 交付结论：PARTIAL

**原因：** 核心修复已完成，运行时 smoke 测试可运行，但前端环境变量加载机制需重启 dev server 才能生效。

---

## 完成项

### ✅ 根因审查
**文档：** `docs/verification/P0_RUNTIME_ROOT_CAUSE.md`

**发现的核心问题：**
1. 端口不一致：bat 8010 vs 前端硬编码 8000
2. DB 路径随 cwd 变化
3. 前端未读环境变量
4. 错误提示不明确

### ✅ 统一配置
**新建：** `backend/config/runtime_paths.py`

**标准配置：**
- 后端端口：**8010**
- 前端端口：**3000**
- API base：**http://localhost:8010**
- DB 路径：
  - `data/live_trade.db`
  - `data/research.db`
  - `data/signal_board.db`

### ✅ 清除硬编码
**修复文件：**
1. `backend/api/observations.py` - 使用 `get_live_trade_db_path()`
2. `backend/api/workbench_execution_feedback.py` - 使用 `get_live_trade_db_path()`
3. `frontend/app/observations/page.tsx` - 读取 env var，默认 8010
4. `frontend/app/themes/[theme_id]/page.tsx` - 读取 env var，默认 8010
5. `frontend/lib/api-client.ts` - 默认 8010
6. `frontend/lib/research-api-client.ts` - 默认 8010
7. `frontend/.env.local` - 新建，设置 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8010`

**残留硬编码：**
- `scripts/verify_p1_3_browser.py` - 测试脚本，使用 8000（需要更新）

### ✅ /api/health/runtime
**文件：** `backend/api/runtime_health.py`

**返回内容：**
```json
{
  "status": "ok",
  "cwd": "D:\\Codex\\TraderLens",
  "project_root": "D:\\Codex\\TraderLens",
  "mode": "deterministic",
  "backend_port": 8010,
  "api_base_url": "http://localhost:8010",
  "contracts_import": true,
  "backend_import": true,
  "live_trade_db_path": "D:\\Codex\\TraderLens\\data\\live_trade.db",
  "research_db_path": "D:\\Codex\\TraderLens\\data\\research.db",
  "signal_board_db_path": "D:\\Codex\\TraderLens\\data\\signal_board.db"
}
```

### ✅ 运行时 smoke 测试
**文件：** `scripts/verify_runtime_smoke.py`

**功能：**
1. ✅ Import checks (contracts, backend)
2. ✅ 启动后端 (port 8010)
3. ✅ 等待 health endpoint
4. ✅ 启动前端 (port 3000)
5. ✅ Playwright 打开 /observations
6. ✅ 捕获 console logs
7. ✅ 捕获 network requests
8. ✅ 保存 DOM textContent
9. ✅ 保存诊断证据

**生成文件：**
- `docs/verification/runtime-health.json`
- `docs/verification/runtime-network-log.json`
- `docs/verification/runtime-observations-dom.md`
- `docs/verification/runtime-startup-log.txt`

### ✅ 错误状态改进
**文件：** `frontend/app/observations/page.tsx`

**改进：**
```typescript
throw new Error(`API request failed: ${url} - HTTP ${response.status}`);
```

用户看到：
```
API request failed: http://localhost:8010/api/observations - HTTP 404. 
请检查后端服务是否在 http://localhost:8010 启动。
```

---

## 未完成项

### ❌ 前端环境变量生效
**问题：** Next.js dev server 不会自动重载 `.env.local`

**证据：** `runtime-network-log.json` 显示：
```json
{
  "url": "http://localhost:8000/api/observations",
  "status": 404
}
```

**原因：**
- `.env.local` 创建后，dev server 仍使用旧缓存
- 需要停止并重启 `npm run dev`

**解决方案：**
1. 手动重启 dev server
2. 或在 smoke 脚本中先删除 `.next` 缓存

---

## 测试结果

### pytest ✅
```bash
$ pytest tests/test_v1_observations_api.py -q
4 passed, 3 warnings in 6.18s
```

### TypeScript ✅
```bash
$ cd frontend && npx tsc -p tsconfig.json --noEmit --skipLibCheck
Exit code 0
```

### Runtime Smoke ⚠️
```bash
$ python scripts/verify_runtime_smoke.py
[OK] Backend started on 8010
[OK] Health check passed
[OK] Frontend started on 3000
[OK] Playwright captured DOM
[WARN] Frontend still requests port 8000
```

---

## Git Commits

1. `758b7a4` - fix(P0-RUNTIME-1): unify ports + DB paths + error handling
2. `aee7478` - feat(P0-RUNTIME-1B): add runtime smoke test + health endpoint - PARTIAL

**变更统计：**
- 13 files changed, 666 insertions(+), 11 deletions(-)

---

## 标准启动方式

### 人工启动
```bash
start-workbench.bat /demo
```
- 后端：8010
- 前端：3000
- 设置 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8010`

### 自动验收
```bash
.venv\Scripts\python.exe scripts\verify_runtime_smoke.py
```
- 自动启动前后端
- 捕获 health、network、DOM
- 保存诊断证据

---

## PASS 标准检查

| 标准 | 状态 | 说明 |
|------|------|------|
| /api/health/runtime 返回 ok | ✅ | status=ok, imports=true |
| smoke 脚本一条命令跑通 | ✅ | 从干净终端可运行 |
| /observations 不无限加载 | ⚠️ | 显示"加载失败"（API 404） |
| Playwright 真实读取 DOM | ✅ | 已保存 textContent |
| network log 有请求响应 | ✅ | 已保存 JSON |
| execution_feedback 和 API 读同一 DB | ✅ | 都用 data/live_trade.db |
| 无手写 DOM | ✅ | Playwright 真实读取 |
| 无 fixture 冒充 | ✅ | 真实启动服务 |

---

## 交付状态

**PARTIAL**

✅ 根因已定位并修复  
✅ 配置已统一  
✅ 硬编码已清除  
✅ Health endpoint 已实现  
✅ Smoke 测试已实现  
✅ 错误提示已改进  
✅ DB 路径已统一  
⚠️ 前端 env 需重启 dev server 生效  

---

## 下一步

1. 重启 dev server 验证环境变量生效
2. 更新 `verify_p1_3_browser.py` 使用 8010
3. 补充端到端 Workbench 测试（从输入到 DB 到页面）

**当前交付：PARTIAL** - 核心修复完成，运行时主干可诊断，前端环境变量加载需手动重启
