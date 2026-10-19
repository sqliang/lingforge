# PC 客户端（Electron 壳 + 本地优先演进）设计

- 日期：2026-10-20
- 分支：`feature/pc-client`
- 状态：已评审（用户确认方案 A + 本地优先 Coding Agent 方向）

## 1. 目标与边界

**远期目标**：Lite Atoms 的本地优先 Coding Agent PC 客户端（类似 Codex 桌面端）——本地运行 Agent、本地持久化，云端服务按需使用。

**本迭代范围**：

- 在 `app/` 下引入 pnpm workspace，新增 `desktop` Electron 壳包
- 壳完整复用现有 Web 前端 UI 与远端 API，零行为分叉
- 建立两级扩展缝（平台适配层 + API 网关接口），为后续 PC 专属 UI / API / 本地数据库提供落点

**明确不做（本迭代）**：本地 Agent 运行时、SQLite、离线模式、安装包打包分发。

## 2. 现状前提

- 仓库根无 workspace（无根 `package.json` / `pnpm-workspace.yaml`）
- `app/frontend` 为独立 Vite + React 应用（pnpm 10，`@vitejs/plugin-react-swc`），`src` 按 `features/`、`shared/`、`pages/` 组织
- 所有后端请求统一收口在 `@/shared/api/client`，SSE 经 `features/runs/api/sse-transport.ts`
- Auth：Supabase，renderer 侧现有机制

## 3. 目录结构

```
app/
├── pnpm-workspace.yaml              # 新增：声明 frontend + desktop 两个包
├── frontend/                        # 现有 Web 应用，结构与构建不动
│   └── src/shared/
│       ├── platform/                # 新增：Tier 1 平台适配层
│       │   ├── types.ts             # PlatformAdapter 接口
│       │   ├── web.ts               # Web 实现（能力均不支持）
│       │   ├── desktop.ts           # 桌面实现（经 preload 桥）
│       │   └── index.ts             # 运行时探测，导出当前平台实例
│       └── api/
│           └── gateway.ts           # 新增：Tier 2 BackendGateway 接口，HTTP 实现收口现有 client
└── desktop/                         # 新增：Electron 壳（包名 @lite-atoms/desktop）
    ├── package.json
    ├── tsconfig.json
    └── electron/
        ├── main.ts                  # 窗口、生命周期、本地回环代理；未来 SQLite 与本地 Agent 的宿主
        └── preload.ts               # contextBridge 白名单 IPC
```

## 4. Tier 1：平台适配层（本迭代实现）

```ts
interface PlatformAdapter {
  kind: 'web' | 'desktop';
  capabilities: { localAgent: boolean; localDatabase: boolean; fileSystem: boolean };
  window?: { minimize(): void; maximize(): void; close(): void };
  info(): { appVersion: string; platform: NodeJS.Platform };
}
```

- renderer 通过 preload 暴露的 `window.liteAtoms` 调用桌面能力
- `web.ts` 所有能力返回不支持，`window` 为 `undefined`
- 运行时探测：`window.liteAtoms` 存在则为 desktop，否则 web
- 将来 PC 专属 UI 通过 `platform.kind === 'desktop'` 条件渲染或路由级覆盖

## 5. Tier 2：API 网关缝（本迭代只收口，不替换）

- 将现有 `shared/api/client` 收口为 `BackendGateway` 接口，HTTP 实现即现状行为；feature 代码不改动
- 未来桌面端提供 `LocalGateway`（IPC → 主进程 SQLite / 本地 Agent），切换点只在 `shared/api` 一处
- 本迭代不产生任何行为变化

## 6. Electron 壳行为与安全基线

- dev：加载 Vite dev server URL；prod：`loadFile(frontend/dist/index.html)`，`apiBaseUrl` 由配置指向远端 API
- 安全基线：`contextIsolation: true`、`nodeIntegration: false`、sandbox；preload 仅暴露白名单方法
- Auth：沿用 Supabase 现有 renderer 机制；后续迭代再迁到 `safeStorage`
- **CORS 已知问题与对策**：`file://` 源请求 API 会触发 CORS，且 SSE 需要稳定直连。对策是在主进程内置本地回环代理（loopback proxy）转发 `/api` 与 SSE 请求，renderer 始终访问 `http://127.0.0.1:<port>`，这也是壳的组成部分

## 7. 本地优先演进路径（仅文档化，不在本迭代实现）

- **阶段 2**：主进程 SQLite（better-sqlite3），以 `LocalGateway` 实现项目/消息/Run 的本地持久化子集
- **阶段 3**：本地 Agent 运行时——开放决策：TS 重实现 agent loop vs 打包 Python sidecar，届时单独评审
- **阶段 4**：云端按需——LLM 网关、云端构建、数据同步

## 8. 构建与质量

- `desktop` 包独立 `lint` / `tsc` / `vitest`（主进程逻辑单元测试）
- Playwright Electron 冒烟测试（启动窗口并加载 UI）后置
- electron-builder 打包配置后置
- Web 端 Docker / compose 部署与构建产物完全不受影响；CI 仅需追加 desktop 包的静态检查

## 9. 不变量（继承 AGENTS.md）

- 浏览器（含 Electron renderer）代码只持身份令牌；Service Role key、Docker socket 等仍属服务端
- 现有 Run 生命周期、SSE 契约、stable 版本保护不变
- 本迭代不新增任何生产 mock 写路径
