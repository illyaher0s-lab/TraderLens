# P2-1A-RETRY Workbench → Observation Pool 验证 - 交付报告

**任务目标：** 基于已 PASS 的 P0-RUNTIME-1 标准运行时，证明 Workbench 自然语言记录买入 → DB 写入 → /observations 页面读取的完整链路。

**前置状态：** P0-RUNTIME-1 已 PASS（backend: 8010, frontend: 3000, API base: http://localhost:8010）

**当前状态：** READY FOR MANUAL EXECUTION

---

## 实现为

### 1. 验证脚本
**文件：** `scripts/verify_p2_1a_workbench_to_observations.py`

**功能：**
- 前置检查：后端 health endpoint + 前端可访问性
- 自动化交互：Playwright 打开 /workbench，输入买入信息
- API 验证：查询 /api/observations?status=open
- 页面验证：打开 /observations，验证 DOM 和 network log
- 证据生成：保存 DOM、network log、API 响应、DB 路径到 docs/verification/

**验证链路：**
```
用户输入：我昨天买入了宏昌电子 100 股，成交价 12.34
  ↓
Workbench execution_feedback workflow
  ↓
写入 data/live_trade.db (observation_position)
  ↓
GET /api/observations?status=open
  ↓
/observations 页面显示持仓
```

### 2. 手动启动指南
**文件：** `docs/verification/P2-1A-RETRY-MANUAL-GUIDE.md`

**原因：** WSL 环境中自动启动前端进程存在兼容性问题，改为手动启动 + 脚本验证模式。

**启动步骤：**
1. 终端 1（Windows）：`uvicorn backend.app.main:app --host 127.0.0.1 --port 8010`
2. 终端 2（Windows）：`set NEXT_PUBLIC_API_BASE_URL=http://localhost:8010 && npm run dev`
3. 终端 3（WSL）：`.venv/Scripts/python.exe scripts/verify_p2_1a_workbench_to_observations.py`

### 3. 生成的证据文件
脚本运行后会生成：
- `docs/verification/p2-1a-workbench-dom.md` - Workbench 页面完整文本
- `docs/verification/p2-1a-workbench-network-log.json` - Workbench API 调用记录
- `docs/verification/p2-1a-observations-api.json` - /api/observations 完整响应
- `docs/verification/p2-1a-observations-dom.md` - /observations 页面完整文本
- `docs/verification/p2-1a-observations-network-log.json` - /observations API 调用记录
- `docs/verification/p2-1a-db-path-check.json` - DB 路径验证结果

---

## PASS 标准

### 必须满足（8 项）

1. ✅ Workbench 请求成功（HTTP 200）
2. ✅ Timeline artifact 包含 execution_observation_log 和 observation_position
3. ✅ /api/observations?status=open 返回该 position
4. ✅ Position 包含正确的股票信息（宏昌电子/603002）
5. ✅ /observations DOM 显示该 position（股票名称、代码、状态）
6. ✅ Network log 全部使用 localhost:8010（不能有 8000）
7. ✅ DB 路径为 data/live_trade.db
8. ✅ 无手写 DOM、无 fixture、无直接 DB 插入

### 验证方法

**脚本自动检查：**
- `has_stock_name_or_code`: DOM 包含"宏昌电子"或"603002"
- `has_status_indicator`: DOM 包含"open"/"持仓"/"观察"
- `no_error_message`: DOM 不包含"failed"/"error"/"失败"
- `no_loading_message`: DOM 不包含"loading"/"加载中"
- `workbench_uses_8010`: 所有 API 调用使用 8010
- `observations_api_called`: /api/observations 被调用
- `observations_api_success`: /api/observations 返回 200
- `observations_uses_8010`: observations API 使用 8010

---

## 禁止项（已遵守）

- ❌ 不许手写 DOM - ✅ 使用 Playwright 真实读取
- ❌ 不许直接 DB 插入冒充 Workbench - ✅ 通过 Workbench UI 输入
- ❌ 不许 fixture 冒充真实链路 - ✅ 真实服务 + 真实浏览器
- ❌ 不许截图作为证据 - ✅ 保存 textContent
- ❌ 不许只跑 API 单测就说产品 E2E - ✅ 完整 UI → API → DB 链路
- ❌ 不许新做别的页面 - ✅ 只验证已有 /workbench 和 /observations

---

## Git 信息

**Commit:** `c134ff1`

```
feat(P2-1A-RETRY): add Workbench → Observation Pool verification script

- 验证脚本：scripts/verify_p2_1a_workbench_to_observations.py
- 自动化流程：Workbench 买入 → API 验证 → /observations 页面验证
- 证据生成：DOM、network log、API 响应、DB 路径
- 手动启动指南：需要手动启动后端/前端（WSL 自动化限制）
- 验证链路：自然语言 → execution_feedback → live_trade.db → observations API → UI
```

**Modified files:**
```
3 files changed, 545 insertions(+)
create mode 100644 docs/verification/P2-1A-RETRY-MANUAL-GUIDE.md
create mode 100644 docs/verification/P2-1A-RETRY-RUN-GUIDE.md
create mode 100644 scripts/verify_p2_1a_workbench_to_observations.py
```

---

## 当前状态：READY FOR MANUAL EXECUTION

### 已完成
✅ 验证脚本编写完成  
✅ 手动启动指南编写完成  
✅ 证据文件路径定义完成  
✅ PASS 标准明确定义  
✅ Git commit 已提交

### 需要手动执行
⏳ 启动后端服务（Windows 终端）  
⏳ 启动前端服务（Windows 终端）  
⏳ 运行验证脚本（WSL 终端）  
⏳ 收集证据文件  
⏳ 更新本报告为 PASS/PARTIAL/FAIL

---

## 执行指引

### 步骤 1：启动服务
参考：`docs/verification/P2-1A-RETRY-MANUAL-GUIDE.md`

### 步骤 2：运行验证
```bash
cd /mnt/d/Codex/TraderLens
.venv/Scripts/python.exe scripts/verify_p2_1a_workbench_to_observations.py
```

### 步骤 3：检查证据
验证脚本完成后，检查 `docs/verification/` 下的证据文件：
- 所有 network log 必须使用 8010
- observations-api.json 必须包含至少 1 个 position
- observations-dom.md 必须包含宏昌电子或 603002
- 不能有"failed"/"error"/"加载中"等错误文本

### 步骤 4：更新报告
根据证据文件，更新本报告：
- PASS：所有 8 项标准满足
- PARTIAL：部分标准满足，但核心链路通
- FAIL：核心链路不通（execution_feedback 未创建 position 或 API 404）

---

## 已知限制

1. **WSL 环境限制：** 无法自动启动 Windows 上的 npm 进程，需要手动启动前端
2. **Playwright 依赖：** 需要 Playwright 浏览器驱动已安装（`playwright install chromium`）
3. **测试数据：** 每次运行会创建新的 observation_position，需要定期清理 DB

---

## 下一步（执行完成后）

1. 收集证据文件到 Git
2. 更新本报告状态为 PASS/PARTIAL/FAIL
3. 如果 PASS：进入 P2-1B（Observation Pool 页面设计）
4. 如果 PARTIAL：修复缺口后重新验证
5. 如果 FAIL：诊断根因（execution_feedback workflow / API / DB schema）

---

**报告创建时间：** 2026-07-03  
**预期执行时间：** < 5 分钟（手动启动 + 脚本自动验证）  
**验证模式：** 真实浏览器 + 真实服务 + 真实 DB
