# 灵构 LingForge

一个 AI 驱动的 React 应用生成工作台。用户用自然语言描述需求，系统经过「计划 → 审批 → 生成 → 校验 → 构建 → 提交 → 预览」的受控闭环，最终产出可运行的单页 React + TypeScript + Tailwind CSS 应用。

---

## 1. 项目能做什么

- **自然语言创建项目**：输入需求后，Planner Agent 生成结构化 Build Contract。
- **Contract 审阅与批准**：用户可编辑 Contract，批准后进入代码生成阶段。
- **多文件源码生成**：Builder Agent 在受控范围内生成 `src/` 和 `public/` 下的业务代码。
- **自动校验与构建**：服务端进行 AST 校验、TypeScript 类型检查、Vite 生产构建。
- **失败自动修复**：构建失败时自动进入一次 Repair 阶段，尝试修复类型/构建错误。
- **真实 Git 版本**：每次成功构建都会生成真实 Git Commit，并提升为稳定版本。
- **实时 SSE 进度**：前端通过 SSE 接收持久化事件，支持断线续传和刷新恢复。
- **隔离预览**：生成应用在独立 Origin 下通过短时票据访问，与平台会话隔离。

---

## 2. 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端工作台 | React + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| 前端状态 | TanStack Query + Zustand |
| 后端 API | Python 3.11 + FastAPI |
| Agent | Deep Agents + LangChain + LangGraph |
| 数据与身份 | Supabase Auth + PostgreSQL + Storage |
| 源码版本 | Git（真实 Commit） |
| 隔离构建 | Rootless Docker Build Runner |
| 部署 | Docker Compose |

---

## 3. 前置条件

在本地运行前，请确保已准备：

1. **Docker Desktop** 或已安装 Docker + Docker Compose 的 Linux/macOS 环境；
2. **Python 3.11+** 和 [`uv`](https://docs.astral.sh/uv/)（用于本地非容器检查）；
3. **Node.js 20+** 和 `pnpm`（用于前端本地开发和构建）；
4. **一个 Supabase 项目**：
   - 启用 Auth（邮箱验证）；
   - 在 SQL Editor 中执行 `supabase/migrations/20260719_0001_lingforge.sql`；
   - 准备两个已验证邮箱的测试用户；
5. **一个支持 tool calling 的 OpenAI 兼容 API**：
   - OpenAI 官方 API；
   - 或任何兼容 OpenAI SDK 的第三方端点。

---

## 4. 本地运行步骤

### 4.1 克隆仓库并进入目录

```bash
git clone <你的仓库地址>
cd lingforge
```

### 4.2 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入以下关键值：

```bash
# Supabase 项目配置（必须使用一个独立开发/测试项目）
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<你的 anon key>
SUPABASE_SERVICE_ROLE_KEY=<你的 service role key>
DATABASE_URL=postgresql://postgres:<密码>@db.<project-ref>.supabase.co:5432/postgres

# 模型配置（OpenAI 兼容端点）
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=<你的 API key>
MODEL_NAME=gpt-4.1-mini

# 本地平台地址（保持默认即可）
PLATFORM_ORIGIN=http://localhost:3000
API_ORIGIN=http://localhost:8000
PREVIEW_ORIGIN=http://localhost:8081
PROJECTS_ROOT=/var/lib/lingforge/projects
ARTIFACTS_ROOT=/var/lib/lingforge/artifacts
BUILD_RUNNER_IMAGE=lingforge-build-runner:local
PREVIEW_TICKET_SECRET=<随机长字符串，用于签发预览票据>

# 前端构建时注入的变量
VITE_SUPABASE_URL=$SUPABASE_URL
VITE_SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
VITE_API_BASE_URL=http://localhost:8000
```

### 4.3 应用数据库迁移

### 4.3 应用数据库迁移

本地开发无需手动迁移：compose 的 `db` 服务（postgres:16-alpine）首次启动时自动执行
`infra/local-db-init/` 下的 shim 与 `supabase/migrations/20260719_0001_lingforge.sql`。
本地运行时产品状态（项目、Run、事件等）写入该本地数据库（volume `infra_db-data`），
Supabase 仅用于 Auth 身份验证；如需改回云端 Postgres，把 compose 中 api/worker 的
`DATABASE_URL` 覆盖项移除并在 Supabase 项目的 SQL Editor 中执行上述迁移文件即可。

> **安全提示**：`SUPABASE_SERVICE_ROLE_KEY` 和 `MODEL_API_KEY` 拥有较高权限，只应保存在 `.env` 中，**不要提交到 Git**。

### 4.4 启动所有服务

```bash
docker compose --env-file .env -f infra/compose.local.yml up --build
```

首次启动会构建三个镜像：

- `lingforge-build-runner:local`：构建运行器镜像；
- `lingforge-api`：FastAPI 控制面；
- `lingforge-frontend`：React 工作台。

### 4.5 访问本地服务

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端工作台 | http://localhost:3000 | 用户主要操作界面 |
| API 健康检查 | http://localhost:8000/health | 验证后端是否启动 |
| 隔离预览 | http://localhost:8081 | 通过票据访问生成应用预览 |

### 4.6 停止服务

```bash
# 在前台运行终端按 Ctrl+C
docker compose --env-file .env -f infra/compose.local.yml down
```

如需完全清理数据卷（会删除本地项目目录和构建产物）：

```bash
docker compose --env-file .env -f infra/compose.local.yml down -v
```

---

## 5. 本地开发（非容器方式）

如果你只想修改前端或后端代码，可以单独启动本地开发服务器。

### 5.1 前端开发

```bash
cd app/frontend
pnpm install
pnpm run dev
```

前端开发服务器默认运行在 http://localhost:5173，会通过 `VITE_API_BASE_URL` 连接本地 API。

### 5.2 后端开发

```bash
cd app/backend
uv sync
uv run python -m lingforge.api.main
```

API 默认运行在 http://localhost:8000。Worker 需要 Docker socket 才能执行构建，建议在容器中运行：

```bash
docker compose --env-file .env -f infra/compose.local.yml up worker
```

### 5.3 运行静态检查

```bash
# 前端 lint + 生产构建
pnpm --dir app/frontend run lint
pnpm --dir app/frontend run build

# 后端 lint + 单元测试
cd app/backend
uv run ruff check src tests
uv run pytest
```

也可以使用项目提供的脚本：

```bash
./scripts/verify-local.sh
```

---

## 6. 部署说明

当前版本面向单台云主机的 Docker Compose 部署，适合 Demo 和小规模使用。

### 6.1 准备服务器

- 一台 Linux 云主机（建议 4 核 8G 以上，预留 Docker 构建所需的 CPU/内存）；
- 安装 Docker 和 Docker Compose；
- 开放端口：`3000`（前端）、`8000`（API）、`8081`（预览）。

### 6.2 域名与 DNS（推荐）

为三个服务分别配置 DNS：

| 服务 | 示例域名 |
| --- | --- |
| 前端 | `app.yourdomain.com` |
| API | `api.yourdomain.com` |
| 预览 | `preview.yourdomain.com` |

然后在 `.env` 中更新 Origin：

```bash
PLATFORM_ORIGIN=https://app.yourdomain.com
API_ORIGIN=https://api.yourdomain.com
PREVIEW_ORIGIN=https://preview.yourdomain.com
VITE_API_BASE_URL=https://api.yourdomain.com
```

### 6.3 配置 SSL/TLS

Compose 文件本身不包含 HTTPS。推荐在前端增加反向代理（如 Nginx 或 Caddy）：

```nginx
server {
    listen 443 ssl;
    server_name app.yourdomain.com;
    # ssl_certificate / ssl_certificate_key 配置省略

    location / {
        proxy_pass http://localhost:3000;
    }
}

server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE 需要禁用缓冲
        proxy_buffering off;
        proxy_cache off;
    }
}

server {
    listen 443 ssl;
    server_name preview.yourdomain.com;

    location / {
        proxy_pass http://localhost:8081;
    }
}
```

### 6.4 部署步骤

```bash
# 1. 上传代码到服务器
git clone <你的仓库地址>
cd lingforge

# 2. 配置生产环境变量
cp .env.example .env
# 编辑 .env，填入生产 Supabase 和模型配置

# 3. 启动服务
docker compose --env-file .env -f infra/compose.local.yml up -d --build

# 4. 验证
curl https://api.yourdomain.com/health
```

### 6.5 更新部署

```bash
cd lingforge
git pull
docker compose --env-file .env -f infra/compose.local.yml up -d --build
```

### 6.6 生产注意事项

- 使用独立的 Supabase 生产项目，并启用 RLS；
- `PREVIEW_TICKET_SECRET` 必须替换为强随机字符串；
- 定期清理失败的孤儿 Artifact 和临时 worktree（脚本待补充）；
- 模型调用可能产生费用，建议设置单用户/单项目配额；
- 当前预览产物存储在本地 Docker volume，生产环境建议迁移到 Supabase Storage（P1 能力）。

---

## 7. 使用流程

1. 打开 `http://localhost:3000`，注册或登录测试用户 A；
2. 在首页输入需求，例如：「创建一个阅读清单应用，可以添加、删除、搜索书籍，并标记阅读状态」；
3. 等待 Planner 生成 Build Contract，查看并批准；
4. 观察 SSE 事件流：Builder → 校验 → TypeScript 检查 → Vite 构建 → Git Commit → 稳定预览；
5. 在右侧面板查看生成的源码、文件树和实时预览；
6. 在左侧聊天框输入增量需求，例如：「增加深色模式和按状态筛选」；
7. 登出，用测试用户 B 登录，确认无法访问用户 A 的项目。

---

## 8. 当前能力边界

### 已支持（P0）

- 注册/登录/项目所有权隔离
- 自然语言 → Build Contract → 批准 → 源码生成
- AST/路径/危险 API 校验
- TypeScript + Vite 生产构建
- 一次自动 Repair
- 真实 Git Commit 和稳定版本提升
- SSE 实时事件、断线续传、取消运行
- 工作台文件树、源码查看、预览

### 暂未支持（P1 / 后续）

- 版本 Diff、版本恢复、导出 ZIP
- 访客 Demo 模式
- 运行时预览错误采集与一键修复
- 完整 Eval 报告（三个标准场景）
- Supabase Storage Artifact 存储
- 多 Agent 分角色协作（Planner/Architect/Builder/Reviewer/Repair）
- 输入框 `@文件`、编辑器行级选中上下文

---

## 9. 常见问题

**Q：启动时提示 `lingforge-build-runner:local` 镜像不存在？**

A：Compose 文件中的 `build-runner` 服务会在 `up` 时构建该镜像。如果仍失败，可手动构建：

```bash
docker build -t lingforge-build-runner:local -f infra/build-runner/Dockerfile .
```

**Q：模型调用报错或生成失败？**

A：检查 `.env` 中的 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` 是否正确，并确认该模型支持 tool calling。

**Q：预览 iframe 无法加载？**

A：确保 `PREVIEW_ORIGIN` 与浏览器访问地址一致，且预览服务已启动。跨域问题通常是因为 Origin 配置错误。

---

## 10. 许可证

MIT
