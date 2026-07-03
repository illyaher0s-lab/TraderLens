# P0-RUNTIME-1 根因审查报告

## 一、启动入口审查

### 问题 1：端口不一致 ⚠️

**标准后端端口：**
- `start-workbench.bat`: **8010** (line 10)
- 设置环境变量: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8010` (line 48)

**前端实际使用：**
- `frontend/app/observations/page.tsx`: 硬编码 **`http://localhost:8000`** (line 67)
- `frontend/app/themes/[theme_id]/page.tsx`: 硬编码 **`http://localhost:8000`** (line 66, 284)
- `frontend/lib/api-client.ts`: 默认 **`http://localhost:8000`** (line 118)
- `frontend/lib/research-api-client.ts`: 默认 **`http://localhost:8000`** (line 78)

**验证脚本：**
- `scripts/verify_p1_3_browser.py`: 硬编码 **`http://localhost:8000`** (line 10)

**结论：**
❌ **端口冲突** - 前端页面和验证脚本使用 8000，但 `start-workbench.bat` 启动后端在 8010

**影响：**
- 用户运行 `start-workbench.bat` 后，前端 `/observations` 请求 8000 端口（无响应）
- P1-3/P2-1A 验证脚本启动后端在 8000，但与生产配置不一致

---

### 问题 2：前端未读取环境变量 ⚠️

`start-workbench.bat` 设置 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8010`，但：

**前端硬编码优先于环境变量：**
- `observations/page.tsx` 直接写死 `http://localhost:8000`，不读 env
- `lib/api-client.ts` 有 fallback，但被页面硬编码绕过

**原因：**
Next.js 环境变量必须在 **构建时** 注入，运行时设置无效。

**解决方案：**
1. 前端必须读取 `process.env.NEXT_PUBLIC_API_BASE_URL`
2. 或者创建 `frontend/.env.local` 文件

---

### 问题 3：验证脚本端口不一致 ⚠️

`scripts/verify_p1_3_browser.py` 启动后端在 8000，但：
- 与 `start-workbench.bat` (8010) 不一致
- 与前端硬编码 (8000) 一致

**结论：**
验证脚本能跑通是因为"凑巧"用了前端硬编码的 8000，而不是标准配置 8010。

---

## 二、import 路径审查

### 从项目根目录 ✅

```bash
$ cd /mnt/d/Codex/TraderLens
$ python -c "import contracts; import backend.app.main; print('IMPORT_OK')"
```

**结果：** (待执行)

### 从 scripts 目录 ❌

```bash
$ cd /mnt/d/Codex/TraderLens/scripts
$ python -c "import contracts; import backend.app.main"
```

**预期：** `ModuleNotFoundError: No module named 'contracts'`

**原因：**
- `cwd` 在 `scripts/` 下
- `contracts/` 在项目根目录
- Python 未将项目根加入 `sys.path`

**影响：**
- 从 `scripts/` 目录直接运行脚本会失败
- 需要 `cd` 到项目根或显式添加 `sys.path`

---

## 三、数据库路径审查

### 硬编码路径问题 ⚠️

**发现硬编码：**
- `backend/api/workbench_execution_feedback.py` line 120:
  ```python
  live_db = LiveTradeDB("live_trade.db")
  ```
- `backend/services/observation_pool.py`:
  ```python
  db = LiveTradeDB("live_trade.db")
  ```
- `scripts/verify_p2_1a_observations_with_fixture.py` line 35:
  ```python
  db = LiveTradeDB("live_trade.db")
  ```

**问题：**
- 相对路径 `"live_trade.db"` 随 `cwd` 变化
- 从项目根运行：写入 `/mnt/d/Codex/TraderLens/live_trade.db`
- 从 `scripts/` 运行：写入 `/mnt/d/Codex/TraderLens/scripts/live_trade.db`
- 从 `backend/` 运行：写入 `/mnt/d/Codex/TraderLens/backend/live_trade.db`

**结论：**
❌ **"测试写 A 库，页面读 B 库"问题存在**

---

### data/ 目录使用情况

**标准路径 (backend/app/main.py):**
```python
db_path = Path("data") / "signal_board.db"  # line 32
initialize_database(Path("data") / "traderlens.sqlite3")  # line 39
research_db_path = Path("data") / "research.db"  # line 104
```

**但 LiveTradeDB 未使用 data/ 目录：**
```python
# workbench_execution_feedback.py 硬编码根目录
LiveTradeDB("live_trade.db")  # ❌ 不在 data/
```

**结论：**
- Signal Board: `data/signal_board.db` ✓
- Research: `data/research.db` ✓
- Live Trade: `live_trade.db` (项目根，❌ 不规范)

---

## 四、前端 API 审查

### /observations 页面 API 调用

**文件：** `frontend/app/observations/page.tsx` line 67

```typescript
const response = await fetch(`http://localhost:8000/api/observations?${params}`);
```

**问题：**
1. 硬编码 8000 端口
2. 未读取 `process.env.NEXT_PUBLIC_API_BASE_URL`
3. 未使用 `lib/api-client.ts` 封装

### 错误处理问题 ⚠️

**当前代码：**
```typescript
const loadPositions = async () => {
  try {
    setLoading(true);
    setError(null);
    const response = await fetch(...);
    if (!response.ok) throw new Error("Failed to load observations");
    const data = await response.json();
    setPositions(data.positions || []);
  } catch (err) {
    setError(err instanceof Error ? err.message : "Unknown error");
  } finally {
    setLoading(false);
  }
};
```

**UI 状态：**
- `loading=true`: 显示"加载中..."
- `error`: 显示错误文本
- **但 error 不显示 API URL 和 HTTP status**

**结论：**
⚠️ 错误提示不够明确，用户看不到是哪个 API 失败

---

## 五、Playwright 脚本审查

**文件：** `scripts/verify_p2_1a_dom_with_playwright.py`

### 问题：

1. ❌ **不启动后端** - 假设后端已运行
2. ❌ **不启动前端** - 假设前端已运行
3. ❌ **不等待后端 health** - 直接访问页面
4. ❌ **不记录 console error**
5. ❌ **不记录 network failed request**
6. ❌ **不保存 API response**
7. ✅ 保存 screenshot

**结论：**
✅ **这是 DOM 抓取脚本，不是运行时诊断脚本** (符合预期)

---

## 根因总结

### 核心问题

1. **端口不一致** - 前端硬编码 8000，bat 启动 8010
2. **DB 路径随 cwd 变化** - `LiveTradeDB("live_trade.db")` 硬编码相对路径
3. **前端未读环境变量** - 运行时设置 `NEXT_PUBLIC_API_BASE_URL` 无效
4. **import 路径依赖 cwd** - 从 scripts/ 运行会失败

### 影响范围

- ❌ 用户运行 `start-workbench.bat` 后前端无法访问 API
- ❌ 验证脚本与生产配置不一致
- ❌ execution_feedback 写入的 DB 可能和页面读取的不同
- ❌ Playwright 脚本无法诊断运行时问题

---

## 下一步

1. 修复端口：统一使用 8010 或 8000
2. 修复 DB 路径：创建 `backend/config/runtime_paths.py`
3. 修复前端 API：使用环境变量或统一封装
4. 创建运行时诊断脚本：`scripts/verify_runtime_smoke.py`
