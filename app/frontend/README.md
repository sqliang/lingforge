# 灵构 LingForge

一个基于 AI 的开发者工作台，左侧为 AI 对话面板，右侧为代码编辑器/预览区域。深色主题，IDE 风格界面。

## 前端技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: shadcn/ui
- **样式**: Tailwind CSS
- **路由**: React Router v6
- **后端服务**: Supabase（认证 + 数据库）
- **面板布局**: react-resizable-panels
- **代码高亮**: highlight.js

## 前端项目结构

```
src/
├── pages/
│   ├── Home.tsx              # 首页 - 项目列表与新建入口
│   ├── Workspace.tsx         # 工作台 - AI 对话 + 编辑器分屏
│   ├── Login.tsx             # 登录/注册页
│   ├── Index.tsx             # 根路由重定向
│   ├── AuthCallback.tsx      # OAuth 回调处理
│   └── AuthError.tsx         # 认证错误页
├── components/
│   ├── ChatPanel.tsx         # AI 对话面板
│   ├── ChatMessage.tsx       # 单条消息组件
│   ├── WorkspacePanel.tsx    # 编辑器/预览标签页
│   ├── FileTree.tsx          # 文件目录树
│   ├── ProtectedRoute.tsx    # 路由守卫
│   ├── editors/              # 编辑器组件
│   │   ├── CodeEditor.tsx    # 代码编辑器
│   │   ├── ImageViewer.tsx   # 图片预览
│   │   └── DocumentViewer.tsx # 文档预览
│   └── ui/                   # shadcn/ui 组件库
├── context/
│   ├── AuthContext.tsx       # 认证状态管理
│   └── WorkspaceContext.tsx  # 工作区标签页状态
├── lib/
│   └── supabase.ts           # Supabase 客户端配置
├── App.tsx                   # 路由配置
├── main.tsx                  # 应用入口
└── index.css                 # 全局样式与主题变量
```

## 环境要求

- Node.js >= 18
- pnpm >= 8

## 快速启动

### 1. 安装依赖

```bash
pnpm install
```

### 2. 配置环境变量

在项目根目录创建 `.env.local` 文件，填入 Supabase 配置：

```env
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

> 注意：如果在 Atoms 平台上运行，环境变量已自动配置，无需手动设置。

### 3. 启动开发服务器

```bash
pnpm run dev
```

开发服务器默认运行在 `http://localhost:5173`。

### 4. 构建生产版本

```bash
pnpm run build
```

构建产物输出到 `dist/` 目录。

### 5. 代码检查

```bash
pnpm run lint
```

## 开发说明

- `@/` 路径别名指向 `src/` 目录
- 所有 shadcn/ui 组件已预下载至 `@/components/ui`
- 使用 Tailwind CSS 语义化变量（如 `bg-primary`、`text-foreground`）
- 请勿修改 `index.html` 中的 title、description 和 logo（由平台系统管理）

## 常用命令

| 命令 | 说明 |
|------|------|
| `pnpm install` | 安装依赖 |
| `pnpm run dev` | 启动开发服务器 |
| `pnpm run build` | 构建生产版本 |
| `pnpm run lint` | ESLint 代码检查 |
| `pnpm run preview` | 预览构建产物 |