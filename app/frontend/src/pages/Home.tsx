/**
 * @file Home.tsx
 * @description 首页 - 项目列表与新建项目入口
 *
 * 该页面是用户登录后的主界面，包含以下核心功能：
 * 1. 左侧边栏：展示用户历史项目列表（从 Supabase 实时查询）
 * 2. 主区域：项目需求输入框，用户描述需求后创建新项目
 * 3. 底部用户信息：显示当前登录用户邮箱和登出入口
 *
 * 核心业务流程（Session 预生成）：
 * - 用户输入构建需求 → 点击"开始构建"
 * - 前端经 FastAPI 创建项目并获得项目 UUID
 * - 携带项目 UUID 跳转到工作台页面 /project/:sessionId
 *
 * 数据表结构参考：
 * Project 事实数据由 FastAPI 读取；Supabase 客户端只维持用户认证。
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Sparkles, ArrowRight, Layers, Clock, ChevronRight, LogOut, User, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ModeSelect, type RunMode } from '@/shared/ui/ModeSelect';
import { useAuth } from '@/context/AuthContext';
import { apiRequest, ApiError } from '@/shared/api/client';
import { toast } from 'sonner';

/**
 * 项目列表项数据结构
 * @property id - 项目 UUID，用于 URL 路由
 * @property original_prompt - 用户最初输入的需求
 */
interface Project {
  id: string;
  title: string;
  original_prompt: string;
  lifecycle_status: string;
  /** 最新一次 Run 的状态，用于列表级进度标识 */
  latest_run_status: string | null;
}

/** 仍在推进中的 Run 状态，列表需要持续轮询以更新标识 */
const ACTIVE_RUN_STATUSES = new Set(['queued', 'claimed', 'running', 'awaiting_approval', 'cancelling']);

/** 项目状态标识：优先展示最新 Run 的进展，其次展示项目生命周期状态 */
function ProjectStatusBadge({ project }: { project: Project }) {
  const runStatus = project.latest_run_status;
  if (runStatus && ACTIVE_RUN_STATUSES.has(runStatus)) {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] text-primary">
        <Loader2 className="w-2.5 h-2.5 animate-spin" />
        生成中
      </span>
    );
  }
  if (runStatus === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] text-destructive">
        <AlertCircle className="w-2.5 h-2.5" />
        生成失败
      </span>
    );
  }
  if (runStatus === 'cancelled') {
    return <span className="text-[9px] text-muted-foreground/60">已取消</span>;
  }
  const lifecycleLabels: Record<string, string> = { ready: '已就绪', draft: '草稿', awaiting_approval: '待确认' };
  return (
    <span className="inline-flex items-center gap-1 text-[9px] text-muted-foreground/40">
      <Clock className="w-2.5 h-2.5" />
      {lifecycleLabels[project.lifecycle_status] ?? project.lifecycle_status}
    </span>
  );
}

export default function HomePage() {
  /** 用户输入的项目构建需求文本 */
  const [input, setInput] = useState('');
  /** 控制用户菜单弹窗的显示/隐藏 */
  const [showUserMenu, setShowUserMenu] = useState(false);
  /** 执行模式：build 自动批准计划，plan 需人工审阅批准后生成 */
  const [mode, setMode] = useState<RunMode>('build');
  /** 项目创建中的加载状态，防止重复提交 */
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiRequest<Project[]>('/v1/projects'),
    enabled: Boolean(user),
    // 有项目处于生成中时低频轮询，让列表标识随 Run 状态推进自动更新
    refetchInterval: (query) =>
      query.state.data?.some((project) => project.latest_run_status && ACTIVE_RUN_STATUSES.has(project.latest_run_status))
        ? 3_000
        : false,
  });
  const projects = projectsQuery.data ?? [];

  /** 用户登出并重定向到登录页 */
  const handleSignOut = async () => {
    await signOut();
    navigate('/login', { replace: true });
  };

  /**
   * 开始构建新项目
   *
   * 业务流程：
   * 1. 校验输入非空且用户已登录
   * 2. 向 FastAPI 创建受认证保护的项目记录
   * 3. 获取数据库返回的 project UUID
   * 4. 携带用户输入的 prompt 跳转到工作台页面
   *
   * 注意：此处不携带任何 AI 逻辑，纯粹是数据库插入 + 路由跳转
   */
  const handleStartBuild = async () => {
    if (!input.trim() || !user || creating) return;
    const trimmedInput = input.trim();
    // 服务端要求需求描述 10~2000 字，前端提前拦截并给出明确提示
    if (trimmedInput.length < 10) {
      toast.error('需求描述太短了，请至少输入 10 个字，描述得越具体生成效果越好');
      return;
    }
    setCreating(true);

    try {
      const data = await apiRequest<Project>('/v1/projects', { method: 'POST', body: JSON.stringify({ prompt: trimmedInput }) });
      const run = await apiRequest<{ id: string }>(`/v1/projects/${data.id}/runs`, {
        method: 'POST',
        body: JSON.stringify({ kind: 'initial', request_id: crypto.randomUUID(), instruction: trimmedInput, mode }),
      });
      navigate(`/project/${data.id}`, { state: { prompt: trimmedInput, runId: run.id, mode } });
    } catch (error) {
      toast.error(error instanceof ApiError ? `创建失败：${error.message}` : '创建失败，请稍后重试');
      setCreating(false);
    }
  };

  /**
   * 键盘事件处理
   * Enter 键触发构建（等同于点击按钮），Shift+Enter 换行
   */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleStartBuild();
    }
  };

  /** 点击项目列表项，跳转到对应工作台 */
  const handleProjectClick = (projectId: string) => {
    navigate(`/project/${projectId}`);
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-background flex">
      {/* 左侧边栏 - 项目列表 */}
      <aside className="w-[280px] h-full border-r border-border/60 flex flex-col bg-card/50 flex-shrink-0">
        {/* 侧边栏顶部 - 品牌标识 */}
        <div className="flex items-center justify-between px-4 h-12 border-b border-border/40 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center">
              <Layers className="w-3.5 h-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold text-foreground">灵构 LingForge</span>
          </div>
        </div>

        {/* 项目列表区域 - 可滚动 */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider font-medium px-2 mb-2">
            最近项目
          </p>
          <div className="space-y-0.5">
            {/* 加载中：骨架屏避免列表空白让用户误以为页面异常 */}
            {projectsQuery.isLoading &&
              Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="px-3 py-2.5 space-y-1.5">
                  <Skeleton className="h-3.5 w-3/4" />
                  <Skeleton className="h-2.5 w-full" />
                  <Skeleton className="h-2 w-1/3" />
                </div>
              ))}
            {!projectsQuery.isLoading && projects.length === 0 && (
              <p className="px-3 py-4 text-[11px] text-muted-foreground/60 leading-relaxed">
                还没有项目，从右侧输入你的第一个想法吧。
              </p>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => handleProjectClick(project.id)}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-secondary/60 transition-colors duration-150 group cursor-pointer"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-medium text-foreground/90 truncate">
                    {project.title}
                  </span>
                  <ChevronRight className="w-3 h-3 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <p className="text-[10px] text-muted-foreground/60 truncate mt-0.5">
                  {project.original_prompt}
                </p>
                <div className="flex items-center gap-1 mt-1">
                  <ProjectStatusBadge project={project} />
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 底部用户信息区域 */}
        <div className="flex-shrink-0 border-t border-border/40 px-3 py-3">
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-secondary/60 transition-colors cursor-pointer"
            >
              <div className="w-7 h-7 rounded-full bg-secondary border border-border/60 flex items-center justify-center flex-shrink-0">
                <User className="w-3.5 h-3.5 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-xs text-foreground/90 truncate">{user?.email}</p>
              </div>
            </button>
            {/* 用户操作弹窗菜单 */}
            {showUserMenu && (
              <div className="absolute left-0 bottom-full mb-1 w-full bg-card border border-border/80 rounded-lg shadow-lg py-1 z-50">
                <button
                  onClick={handleSignOut}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  退出登录
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* 主内容区域 - 项目需求输入 */}
      <main className="flex-1 flex flex-col items-center justify-center px-8">
        <div className="w-full max-w-[640px] space-y-8">
          {/* 引导区域 - 标题和描述 */}
          <div className="text-center space-y-3">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 border border-border/40 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-7 h-7 text-primary/70" />
            </div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">
              描述你想构建的项目
            </h1>
            <p className="text-sm text-muted-foreground/70 max-w-md mx-auto leading-relaxed">
              使用自然语言描述你的想法，AI 将帮助你生成代码并构建应用
            </p>
          </div>

          {/* 需求输入区域 */}
          <div className="relative">
            <div className="rounded-2xl border border-border/80 bg-card shadow-sm focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-primary/10 transition-all duration-300">
              <textarea
                id="project-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="例如：帮我创建一个待办事项应用...（至少 10 个字，描述越具体生成效果越好）"
                rows={4}
                className="w-full resize-none bg-transparent px-5 pt-4 pb-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none leading-relaxed"
              />
              <div className="flex items-center justify-between px-4 pb-3">
                <p className="text-[10px] text-muted-foreground/40">
                  按 Enter 开始构建，Shift+Enter 换行
                </p>
                <div className="flex items-center gap-1.5">
                  <ModeSelect mode={mode} onChange={setMode} />
                  <Button
                    onClick={handleStartBuild}
                    disabled={input.trim().length < 10 || creating}
                    size="sm"
                    className="h-8 px-4 gap-2 rounded-lg cursor-pointer transition-all duration-200 disabled:opacity-30"
                  >
                    {creating ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        创建中...
                      </>
                    ) : (
                      <>
                        开始构建
                        <ArrowRight className="w-3.5 h-3.5" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* 快速开始建议标签 */}
          <div className="space-y-2">
            <p className="text-[10px] text-muted-foreground/50 text-center uppercase tracking-wider">
              快速开始
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {[
                '数据仪表盘',
                '博客系统',
                '电商平台',
                '任务管理工具',
                '聊天应用',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(`帮我创建一个${suggestion}`)}
                  className="px-3 py-1.5 rounded-full border border-border/60 text-[11px] text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-secondary/40 transition-all duration-200 cursor-pointer"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
