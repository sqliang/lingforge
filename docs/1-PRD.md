# 灵构 LingForge 产品需求文档（PRD）

> 版本：2.0  
> 定位：完整工程型 Atoms Demo 的统一产品、工程与验收基线。

## 1. 文档目标与评分映射

灵构 LingForge 是一个 AI 开发工作台：用户以自然语言创建、审阅、生成、构建、预览、持续修改并回滚 React 应用。本文档约束本次 Demo 的完整能力、接口、状态、质量门槛及交付验收，避免“界面演示”和“真实能力”不一致。

| 题目评估维度 | 本产品的证明方式 |
| --- | --- |
| 完成度 | 从需求到稳定预览、增量修改和版本恢复形成可重复闭环 |
| 工程思维 | 受控生成、隔离构建、稳定版本、真实 Git、可恢复事件流 |
| 用户体验 | 明确的 Contract 审阅、实时可解释进度、失败可诊断、旧版本不丢失 |
| 创新性 | 将“先规划、后生成、可构建验证、可回滚”组合为 AI Coding 的可信工作流 |
| 可交付性 | 公开链接、公开源码、无痕测试、README 与 Eval 结果完整可查 |

### 1.1 产品边界

- 本次生成目标固定为单页 React + TypeScript + Tailwind CSS 应用；不支持服务端业务代码、数据库建模或自定义依赖。
- 平台应用与生成应用是两个独立部署面：平台负责工作流与数据，生成应用仅以受限静态预览产物运行。
- P0/P1 表示实施先后，**不表示是否交付**；本文列出的能力均属于本次完整工程项目范围。

## 2. 用户、角色与核心场景

### 2.1 用户角色

| 角色 | 目标 | 核心诉求 |
| --- | --- | --- |
| Builder 用户 | 快速把产品想法变为可操作应用 | 可控生成、真实预览、可继续修改 |
| 已登录项目所有者 | 长期维护自己的项目 | 数据隔离、历史可查、可恢复版本 |
| 访客评审 | 验证 Demo 是否真实可用 | 无障碍访问、过程透明、结果可复现 |

技术评审和平台开发者属于评审/实现视角，不作为面向产品的用户角色。

### 2.2 核心场景

1. 用户注册或登录，创建“阅读清单”项目并输入需求。
2. Planner 生成 Build Contract；用户编辑范围、组件职责和验收条件后批准。
3. Builder 生成多个 React 源文件；系统完成安全校验、类型检查和 Vite Production Build。
4. 用户在稳定预览中操作生成应用；刷新工作台后项目、对话、源码、事件和预览均可恢复。
5. 用户提出“增加深色模式和按状态筛选”；系统从当前稳定 Commit 增量修改，成功后生成新版本。
6. 用户查看版本 Diff，并恢复任一历史版本；恢复结果以新的 Git Commit 进入历史。

### 2.3 评审标准场景

必须可重复演示：阅读清单、费用记录器、习惯追踪器。每个场景使用固定需求文本和验收步骤，记录首次生成、修改、失败保护和恢复结果。

## 3. 产品范围与优先级

### 3.1 P0：主闭环先完成

- 邮箱注册、登录、登出与项目所有权隔离；提供受控访客演示入口。
- 项目创建、列表、异步标题、项目状态和独立工作目录/Git 仓库。
- Build Contract 的生成、编辑、结构校验、批准、版本化保存与重新编辑。
- Planner、Builder、Validator、Repair、Committer 五阶段 Agent 工作流。
- 多文件 React + TypeScript + Tailwind 源码生成与受控写入。
- SSE 实时事件、断线续传、刷新恢复、停止、失败诊断和重试。
- 临时 worktree 校验、TypeScript 检查、Vite Production Build、稳定产物提升。
- 当前稳定预览、文件树、源码查看、构建日志与增量修改。
- 每次成功构建后的真实 Git Commit；构建失败或取消不得影响稳定版本。
- 项目、Contract、消息、Run、事件、Build、版本和预览元数据持久化。

### 3.2 P1：在 P0 闭环后完成

- 一次定向自动修复；
- 版本列表、文件级 Diff、历史预览与恢复版本；
- 项目 ZIP 导出与 README 生成；
- 运行时预览错误采集与一键发起修复；
- Eval 报告、最小产品指标和运维日志视图。

### 3.3 本次不做

- 自定义 npm 依赖、修改构建配置、任意 Shell 命令；
- 后端业务代码、用户自建数据库、支付及第三方业务集成；
- 多页面 Router 项目、多人实时协作、多 Agent Race Mode；
- 将生成应用独立发布为用户自定义域名的生产服务。

## 4. 完整主链路与状态机

### 4.1 主链路

```text
注册/登录
→ 创建项目
→ 输入需求
→ Planner 生成 Build Contract
→ 用户编辑并批准
→ Builder 生成多文件 React 源码
→ 服务端安全校验
→ 临时 worktree TypeScript 检查与 Vite Build
→ Repair Agent（最多一次）
→ 创建真实 Git Commit
→ 上传并提升稳定预览产物
→ 增量修改
→ 查看 Diff / 恢复历史版本
```

### 4.2 Run 类型与状态

`AgentRun.type` 仅允许：`initial`、`update`、`retry`、`restore`。自动修复是原 Run 内最多一次的 `repairing` 阶段，不创建独立 Repair Run。

```text
项目生命周期：provisioning → draft → awaiting_approval → ready → archived

Run 状态：queued → claimed → running → awaiting_approval → queued
                           ↘ cancelling → cancelled
                           ↘ failed

initial Run：queued → claimed → running(planning) → awaiting_approval
          →（批准后重新入队）→ claimed → running(generating)
执行阶段：generating → validating → typechecking → building
          → [repairing → validating]（可选，且最多一次）
          → committing → promoting
```

规则：

- 项目生命周期、Run 状态与执行阶段是三类独立状态；
- 同一项目任意时刻只允许一个写入型 Run；新请求在运行中返回“项目正忙”。
- `initial` Run 先产出草案 Contract 并在 `awaiting_approval` 释放 Worker 租约；批准同一 Contract 后，原 Run 才重新入队进入 `generating`。`update`、`retry` 与 `restore` 必须从已批准 Contract 开始。
- 只有校验、类型检查与构建都成功后才可进入 `committing`。
- 只有 Git Commit、产物上传与稳定指针更新全部成功后才可进入 `completed`。
- `failed` 与 `cancelled` 必须保留 Run、事件和诊断，但不得更新 `stableVersionId`、稳定源码或稳定预览。

### 4.3 停止、重试与恢复

- 停止：取消模型请求、终止构建子进程、清理临时 worktree、写入 `cancelled` 事件；稳定版本保持不变。
- 重试：创建新的 `retry` Run，从当前稳定 Commit 和已批准 Contract 开始；不复用失败 Run 的临时目录。
- 自动修复：仅在 TypeScript 或 Vite Build 失败时使原 Run 进入一次 `repairing` 阶段；Repair 只能改动白名单文件，修复后必须重跑完整校验。
- 恢复：从目标 Commit 创建临时 worktree，重新执行校验与构建；成功后创建新的 `restore` Commit，禁止 `reset --hard`、强推或改写历史。

## 5. 功能需求

### FR-01 鉴权与项目隔离

用户可注册、登录、登出；所有项目、消息、Run、日志与版本仅可由项目所有者访问。访客演示使用隔离的匿名会话及临时项目；它不是任意项目的公开分享链接，不得访问真实用户项目。

**验收：** 未登录用户不能读取私有项目；切换账户后不显示他人项目；登出后清除平台会话。

### FR-02 项目管理

用户输入 10–2000 字需求创建项目。服务端生成不可预测的 `projectId`、初始化独立 Git 仓库和项目目录，并创建项目记录。项目列表展示标题、状态、最后活动时间、当前 Commit 摘要。

**验收：** 刷新后项目仍存在；标题可在 Planner 后异步更新；每个项目的仓库和构建目录相互独立。

### FR-03 Build Contract

Planner 必须输出结构化 Contract，用户可编辑后批准。批准后的 Contract 作为所有生成/增量修改 Run 的输入快照；重新编辑将产生新版本并要求再次批准。

```json
{
  "productGoal": "string",
  "features": ["string"],
  "pageStructure": ["string"],
  "dataModels": [{ "name": "string", "fields": ["name: type"] }],
  "componentPlan": [{ "name": "string", "responsibility": "string" }],
  "statePlan": {
    "owner": "string",
    "persistentState": ["string"],
    "uiState": ["string"],
    "derivedState": ["string"]
  },
  "acceptanceCriteria": ["string"],
  "outOfScope": ["string"]
}
```

**校验：** 每个数组至少一项；功能不超过 8 项；组件不超过 12 个；必须有非范围和可验证验收项；字段不得含 HTML、脚本或超长内容。

### FR-04 Agent 代码生成与增量修改

Builder 输入已批准 Contract、当前稳定源码、最近消息摘要、当前 Commit 和用户指令，输出结构化文件集合与变更摘要。初次生成必须包含 `src/App.tsx` 与至少两个独立业务组件；增量修改只返回新增、修改或删除的白名单文件。

**验收：** 输出符合 JSON Schema；生成结果不修改模板文件；修改成功后返回受影响文件、功能摘要与新 Commit SHA；未涉及功能保留。

### FR-05 SSE 事件与可解释进度

前端使用 SSE 接收真实后端事件；每个事件持久化并带单调递增 `sequence`。浏览器通过 `Last-Event-ID` 恢复断开期间事件，刷新后从数据库读取完整历史。

事件最少包括：`run.queued`、`run.claimed`、`stage.started`、`contract.ready`、`run.awaiting_approval`、`agent.file.changed`、`build.diagnostic`、`build.completed`、`repair.started`、`version.promoted`、`run.completed`、`run.failed`、`run.cancelled`。事件信封、重放和过期恢复协议以 [运行时与数据设计](./3-运行时与数据设计.md) 为准。

**验收：** 禁止用定时器伪造进度；事件不可重复排序错乱；错误事件携带阶段、错误码、用户可读信息与是否可重试。

### FR-06 校验、构建与稳定提升

构建流水线固定为：

```text
JSON Schema
→ 文件路径与数量校验
→ AST Import / 危险 API 校验
→ 写入临时 worktree
→ TypeScript Typecheck
→ Vite Production Build
→ 验证 dist/index.html
→ 上传 Preview Artifact
→ Git Commit
→ 更新稳定指针
```

**验收：** 任一失败均不覆盖稳定源码、预览与 `stableVersionId`；构建成功的预览必须来自实际 `dist/` 产物，而不是模拟页面。

### FR-07 预览、源码与日志

工作台展示当前稳定预览、文件树、只读源码、构建状态和截断后的构建日志。预览支持刷新、桌面/移动尺寸切换与新窗口打开；历史版本可打开对应预览。

### FR-08 Git 版本、Diff、恢复与导出

每个项目使用真实 Git 仓库。初始生成、增量修改、自动修复和恢复均在构建成功后生成 Commit；版本页面展示 SHA、消息、来源 Run、时间、变更文件数和 Build 状态。

**验收：** Diff 可按文件查看；恢复不重写历史；导出的 ZIP 包含模板、当前源码、lockfile、README 和可选 `.git` 历史。

## 6. 工程架构与数据契约

### 6.1 职责边界

| 层级 | 职责 |
| --- | --- |
| 前端工作台 | 鉴权、项目 UI、Contract 编辑、SSE 消费、文件/版本/预览展示 |
| Supabase | 用户认证、关系数据、访问控制、预览产物与导出文件的对象存储 |
| Agent/Build 服务 | 模型调用、Contract/源码处理、Git、临时 worktree、校验、构建、SSE 推送 |
| 预览域名 | 仅托管已通过构建的静态产物，与平台主域隔离 |

### 6.2 核心实体

| 实体 | 最小字段 |
| --- | --- |
| Project | `id, ownerId, title, originalPrompt, lifecycleStatus, stableVersionId, templateVersion, createdAt, updatedAt` |
| BuildContract | `id, projectId, version, contentJson, status, approvedAt, createdBy` |
| Message | `id, projectId, runId?, role, content, summary, createdAt` |
| AgentRun | `id, projectId, type, requestId, contractId?, baseVersionId?, threadId?, status, stage?, repairAttempts, agentConfigVersion, modelId?, promptVersion, errorCode?, errorMessage?, startedAt, completedAt` |
| RunEvent | `id, runId, sequence, type, schemaVersion, payloadJson, createdAt` |
| ProjectBuild | `id, projectId, runId, attemptNo, commitSha?, status, diagnosticsRef?, artifactRef?, buildLogRef, runnerImageDigest, durationMs, createdAt` |
| ProjectVersion | `id, projectId, commitSha, parentVersionId?, message, originKind, runId, buildId, templateVersion, restoredFromVersionId?, createdAt` |
| PreviewArtifact | `id, buildId, storageKey, integrityHash, manifestJson, state, createdAt` |

### 6.3 API 边界

| 接口 | 行为 |
| --- | --- |
| `POST /projects` | 创建项目与 Git 仓库 |
| `POST /projects/:id/contracts:plan` | 创建进入 `planning` 阶段的 `initial` Run |
| `PATCH /contracts/:id` | 保存未批准 Contract 新版本 |
| `POST /contracts/:id/approve` | 锁定 Contract，并将对应等待批准的 `initial` Run 重新入队 |
| `POST /projects/:id/runs` | 发起 `initial`、`update`、`retry` 或 `restore` Run；请求携带幂等 `requestId` |
| `GET /runs/:id/events` | SSE 事件流，支持 `Last-Event-ID` |
| `POST /runs/:id/cancel` | 协作式取消运行任务 |
| `GET /projects/:id/files` | 读取指定稳定或历史 Commit 文件树 |
| `GET /projects/:id/builds/:buildId/logs` | 读取脱敏且截断的构建日志 |
| `GET /projects/:id/versions` | 版本列表 |
| `GET /projects/:id/versions/:sha/diff` | 文件级 Diff |
| `POST /projects/:id/versions/:sha/restore` | 发起恢复 Run |
| `POST /projects/:id/export` | 生成并返回 ZIP 下载地址 |

所有写接口校验身份、项目所有权、运行锁和幂等键；服务端返回的错误统一包含 `code`、`message`、`retryable`、`runId?`。

## 7. 生成、构建与安全边界

### 7.1 固定模板与可写范围

模板固定提供 `package.json`、lockfile、Vite/TypeScript/Tailwind 配置、`src/main.tsx` 和基础样式。Agent 仅可写：

```text
src/App.tsx
src/components/**/*.tsx
src/hooks/**/*.ts
src/lib/**/*.ts
src/types/**/*.ts
```

限制：业务文件 3–12 个；单文件不超过 30KB；总业务源码不超过 200KB；禁止绝对路径、`..` 路径、根目录写入、`public/` 写入、配置修改与 `.git/` 写入。

### 7.2 依赖与 AST 校验

只允许 `react`、`react-dom`、`lucide-react`、`clsx` 和项目内相对路径。服务端以 AST 而非字符串匹配校验：

- 禁止动态 `import()`、`require()`、Node 内置模块与未安装包；
- 禁止远程脚本、远程模块、`eval`、`Function`、`Worker`、`WebSocket`、`XMLHttpRequest`；
- 默认禁止 `fetch`，如后续开放则仅允许显式白名单域名；
- 禁止内联脚本、危险 URL 协议和未经批准的 iframe；
- 生成文件需通过 JSON Schema、路径规则、Import 规则和大小规则。

### 7.3 隔离与资源限制

- 每次 Run 由独立临时 worktree 执行，完成或失败后清理。
- 构建服务设置模型、校验和构建阶段超时；限制单项目并发、CPU、内存、磁盘和日志总量。
- 预览使用独立 Origin、严格 CSP 与 iframe sandbox；平台 Cookie、Token 和内部 API 不可被生成应用访问。
- SSE、构建日志、模型 Prompt 和错误信息不得输出密钥、认证头、服务角色凭据或完整敏感配置。

## 8. 页面与交互

### 8.1 首页与项目列表

首页包含产品价值说明、示例 Prompt、项目列表与新项目输入区。创建后立即跳转工作台；列表分别展示项目生命周期（草稿、待批准、就绪、已归档）与最近 Run 状态（运行中、成功、失败、已取消），不得将二者混为一个字段。

### 8.2 工作台

左侧：会话、修改指令、运行状态、停止/重试、版本列表。  
右侧：Contract、Activity、Files、Build、Diff 与 Live Preview 标签页。

关键交互：

- `awaiting_approval` 时仅允许编辑/批准 Contract，不显示“生成完成”；
- 运行中持续显示真实阶段和最新事件，旧预览保持可用；
- 失败时聚焦错误摘要、日志入口和重试/编辑入口；
- 版本恢复必须展示目标 Commit、变更影响和“恢复将产生新 Commit”的确认文案；
- 预览打开失败时展示稳定 Build 标识、产物状态和重新加载操作。

## 9. 测试、Eval 与验收

### 9.1 P0 总验收

| ID | 验收条件 |
| --- | --- |
| AC-01 | 用户可注册、登录并仅访问自己的项目 |
| AC-02 | 自然语言需求可生成、编辑并批准合法 Build Contract |
| AC-03 | 批准后生成多个受限 React 业务文件并可查看源码 |
| AC-04 | 代码通过 Schema、路径、AST Import 与危险 API 校验 |
| AC-05 | 临时 worktree 的 TypeScript 与 Vite Production Build 成功 |
| AC-06 | 预览加载真实稳定 `dist/` 产物，核心交互可操作 |
| AC-07 | SSE 显示真实事件，刷新或重连后不丢失历史事件 |
| AC-08 | 项目、消息、Contract、源码、Build 和版本可恢复 |
| AC-09 | 增量修改基于当前稳定 Commit，并在成功后生成新 Commit |
| AC-10 | 失败、取消与修复失败均不覆盖稳定预览和稳定源码 |
| AC-11 | 可查看版本、Diff，并以新 Commit 恢复历史版本 |
| AC-12 | 公开链接可在无痕窗口完成受控 Demo 测试 |

### 9.2 关键测试用例

| 用例 | 操作 | 预期 |
| --- | --- | --- |
| TC-01 首次生成 | 创建阅读清单并批准 Contract | 多文件应用构建成功并可预览 |
| TC-02 核心交互 | 新增、删除、搜索、切换阅读状态 | 交互结果正确 |
| TC-03 刷新恢复 | 刷新工作台与预览 | 项目和稳定版本可恢复 |
| TC-04 增量修改 | 增加深色模式和状态筛选 | 保留已有能力，产生新 Commit |
| TC-05 构建失败 | 注入类型错误 | 显示诊断，旧预览不变 |
| TC-06 非法源码 | 注入路径穿越、动态 import 或 `fetch` | 服务端拒绝且不创建稳定版本 |
| TC-07 断线重连 | 中途断开 SSE 再连接 | 按 sequence 补齐事件且不重复 |
| TC-08 自动修复 | 制造可修复类型错误 | 最多一次修复后完整重建 |
| TC-09 版本恢复 | 恢复初始 Commit | 重新构建成功并创建 restore Commit |
| TC-10 权限隔离 | 使用另一账户访问项目 URL | 返回无权限，不泄露项目内容 |

### 9.3 Eval 记录

对阅读清单、费用记录器、习惯追踪器分别记录：Contract 合法性、文件数、首次生成耗时、类型检查结果、构建结果、核心功能通过数、修复次数、增量修改结果、恢复结果与最终 Commit SHA。

## 10. 可观测性、风险与交付

### 10.1 最小指标

记录 `project.created`、`contract.generated`、`contract.approved`、`run.started`、`build.diagnostic`、`build.typecheck.completed`、`build.production.completed`、`repair.started`、`version.promoted`、`run.failed`、`version.restored`。所有事件带项目、Run、耗时和结果，不记录敏感 Prompt 或密钥。

### 10.2 主要风险与应对

| 风险 | 应对 |
| --- | --- |
| 模型输出不稳定 | 结构化输出、固定模板、Schema/AST 校验、一次定向修复 |
| 构建破坏旧版本 | 临时 worktree、成功后提升、稳定指针原子更新 |
| 代码执行风险 | 独立构建环境、资源配额、独立预览 Origin、CSP/sandbox |
| SSE 中断 | 事件持久化、sequence、`Last-Event-ID` 回放 |
| Git 与数据库不一致 | Commit 成功后才写版本元数据；失败任务标记待清理并可审计 |
| 成本或超时失控 | 每阶段超时、并发限制、源码体积限制、单次自动修复 |

### 10.3 最终交付清单

- 公开可测试的在线链接；
- 公开 GitHub 源码链接；
- README：架构、运行方式、环境变量、完成能力、未做能力、已知限制和后续优先级；
- 无痕窗口验收记录；
- 三个标准 Eval 场景及结果；
- 可选：AI Coding 工具链与实现过程说明。
