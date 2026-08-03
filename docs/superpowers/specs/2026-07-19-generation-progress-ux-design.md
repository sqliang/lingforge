# 生成过程可感知性设计（详情页）

日期：2026-07-19
状态：已确认（auto 模式下按推荐方案决策）

## 背景与目标

详情页在代码生成期间用户感知不足：工作流步骤默认折叠、生成动画消失、无法手动终止、预览区无构建提示、代码要等稳定版本发布后才一次性出现。目标是在不破坏既有信任边界（稳定指针只由成功构建推进）的前提下，让生成过程全程可见、可终止。

## 决策记录

- **代码流式粒度**：Deep Agent 的 `write_source` 是原子工具调用，字符级打字机效果需要改 Agent 架构，成本高、收益低。采用**文件粒度流式**：每写完一个文件即发 SSE 事件，前端实时渲染。
- **流式传输通道**：复用现有 SSE 事件流（事件携带路径 + 内容截断 30 KB），不新增草稿文件 API。事件 payload 在契约中是自由 object，`contracts/sse/v1.schema.json` 无需变更。内容即使用户项目代码、属用户自有数据，无泄露面扩大。
- **取消语义**：严格遵循 `docs/3-运行时与数据设计.md` §3.2 的协作式取消，数据库已有 `cancel_requested_at` 列与 `cancelling/cancelled` 状态，无需迁移。

## 后端改动

### 1. 取消端点（`api/main.py` + `application/repository.py`）

- 新增 `POST /v1/projects/{project_id}/runs/{run_id}/cancel`。
- `repository.request_cancel(...)`：
  - 校验项目所有权与 Run 归属；仅 `queued/claimed/running/awaiting_approval` 可取消，其余 409。
  - `queued` / `awaiting_approval`（Worker 未持有或已释放租约）：直接置 `cancelled`，写 `cancel_requested_at`，追加 `run.cancelled` 事件。
  - `claimed` / `running`：置 `cancelling` + `cancel_requested_at`，由 Worker 在阶段边界完成取消。
- Worker `process_run`：每个阶段边界检查 `cancel_requested_at`（重读数据库），命中抛 `RunCancelled`；单独捕获后置 `cancelled` + `run.cancelled` 事件，走既有 worktree 清理。运行中的单个阶段（如一次模型调用）会执行完毕后才生效——这是 P0 的有意取舍，文档化。
- 稳定指针不变：取消路径不触碰 `stable_version_id`、不提交候选 Commit。

### 2. `builder.file_written` 事件（`agents/service.py` + `worker/main.py`）

- `generate_source(..., on_file_written=None)`：`agents/tools/worktree_files.py` 中 `build_worktree_tools` 的 `write_source` 成功写入后调用回调 `(path, content)`。
- Worker 传入回调，持久化 `builder.file_written` 事件：`{path, content(≤30KB 截断), bytes}`。Repair 阶段复用同一事件类型。

## 前端改动

### 3. 工作流默认展开 + 常驻生成指示（`ChatMessage` / `ChatPanel`）

- `ChatMessage` 新增 `defaultExpanded` prop；活跃 Run 对应的消息默认展开步骤。
- 活跃 Run 期间打字动画常驻消息列表底部（现状保留），并在步骤区尾部追加当前阶段的脉冲指示行。
- `builder.file_written` 映射为文件步骤 `{type:'file', action:'write', file}`，可点击在编辑器打开（命中草稿内容）。

### 4. 发送/终止按钮（`ChatPanel` / `WorkspaceScreen`）

- 活跃 Run 时发送按钮变为终止按钮（Square 图标、destructive 样式），点击调用取消端点；终止请求进行中禁用。
- Run 进入 `cancelling/cancelled` 后按钮恢复为发送。

### 5. 预览区生成中动画（`AppPreview` / `WorkspaceContext`）

- Context 注入 `activeRunStage`；无稳定版本且存在活跃 Run 时，预览区显示旋转动画 + 当前阶段文案；失败/取消后回退为占位提示。已有稳定版本时预览不受影响（继续展示旧稳定版）。

### 6. 代码流式渲染（`WorkspaceScreen` / `WorkspaceContext`）

- SSE 收到 `builder.file_written` 时更新 `draftFiles`（path→content）。
- 展示树 = 稳定文件树合并草稿路径（草稿覆盖同名节点），生成中的文件在树中正常可点。
- `loadFileContent` 优先返回草稿内容；已打开的标签页在收到同路径新事件时通过 `updateTabContent` 增量更新，形成流式效果。
- `version.promoted` 后清空草稿，切回稳定文件树。

## 错误与边界

- 取消已完成/失败/已取消的 Run → 409。
- 取消事件与正常事件同序列持久化，SSE 重放可见 `run.cancelled`。
- 草稿内容仅存在前端内存与 Run 事件中，不影响稳定文件接口 `/files` 的语义。

## 测试

- 后端：取消端点状态机测试（queued 直接取消、running 协作取消、终态 409）；`builder.file_written` 回调触发测试。Ruff + pytest。
- 前端：lint、tsc、build。
- 动态：重建容器后创建项目，观察步骤展开、终止按钮、预览动画、文件流式出现；取消一次运行确认稳定指针不受影响。

## 不在范围

- 字符级代码流式（需 Agent 架构改造）。
- messages 读取接口（本地回显刷新即失）。
