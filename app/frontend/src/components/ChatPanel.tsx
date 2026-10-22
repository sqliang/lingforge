/**
 * @file ChatPanel.tsx
 * @description AI 对话面板组件
 *
 * 该组件实现了工作台左侧的 AI 聊天界面，包含：
 * - 顶部导航栏：返回首页按钮、项目名称、Run 历史
 * - 消息列表区域：用户消息和 AI 回复（工作流步骤来自持久化的 SSE Run 事件）
 * - 底部输入区域：发送新的生成指令（创建 update Run）
 *
 * 数据边界：消息内容来自服务端事实——首条用户消息是项目原始需求，
 * AI 回复的步骤是最新 Run 的持久化事件流；本组件不构造任何模拟回复。
 *
 * 核心交互：
 * - Enter 发送消息，Shift+Enter 换行
 * - 滚动到底部按钮（当用户向上滚动时显示）
 * - Run 历史下拉菜单
 * - Run 等待审批时内嵌 Build Contract 确认卡片
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Send, Square, Sparkles, History, ArrowDown, Home, RefreshCw, CheckCircle2, LoaderCircle, X, FileCode2 } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import ChatMessage, { ChatMessageData, StepItem } from './ChatMessage';
import { PlanCard } from '@/features/contracts/ui/PlanCard';
import { ModeSelect, type RunMode } from '@/shared/ui/ModeSelect';
import { useWorkspace } from '@/context/WorkspaceContext';
import { collectFilePaths } from '@/features/workspace/model/project-files';
import type { ChatMessageRecord, ProjectVersion, Run, StreamEvent } from '@/features/workspace/ui/WorkspaceScreen';

/** 随指令发送的代码引用（选区引用带行区间，@ 引用仅路径） */
export interface RunReferenceInput {
  path: string;
  start_line?: number;
  end_line?: number;
}

/** SSE 事件类型到工作流步骤文案的映射（与 Worker 状态机一一对应） */
const EVENT_STEP_LABELS: Record<string, string> = {
  'run.queued': '任务已排队，等待 Worker 接管…',
  'run.claimed': 'Worker 已接管任务',
  'planner.started': '正在分析需求并规划 Build Contract…',
  'contract.ready': 'Build Contract 已生成，等待确认',
  'builder.started': '正在生成项目代码…',
  'validation.started': '正在校验生成的代码…',
  'build.started': '正在执行 TypeScript 检查与 Vite 构建…',
  'repair.started': '构建未通过，正在自动修复…',
  'build.retry_started': '修复完成，重新构建…',
  'commit.started': '构建成功，正在提交版本…',
  'preview.uploaded': '正在发布预览产物…',
  'version.promoted': '稳定版本已发布',
};

const RUN_KIND_LABELS: Record<Run['kind'], string> = {
  initial: '初始生成',
  update: '需求更新',
  retry: '失败重试',
  restore: '版本恢复',
};

const ACTIVE_RUN_STATUSES = new Set<Run['status']>(['queued', 'claimed', 'running']);

/** 根据 Run 状态生成 AI 回复的摘要文案 */
function runSummary(run: Run): string {
  switch (run.status) {
    case 'completed':
      return '已完成代码生成并通过受限校验与真实构建，稳定版本已发布。';
    case 'failed':
      return `运行失败：${run.error_message ?? run.error_code ?? '未知错误'}`;
    case 'cancelled':
      return '本次运行已取消，稳定版本未受影响。';
    case 'awaiting_approval':
      return '已生成 Build Contract，请在右上角确认后开始生成代码。';
    default:
      return '正在处理你的需求，生成过程见下方工作流步骤…';
  }
}

/**
 * ChatPanel 组件 Props
 * @property projectId - 当前项目 ID（用于 Build Contract 确认卡片）
 * @property projectName - 项目名称
 * @property originalPrompt - 项目原始需求（历史为空时的首条用户消息兜底）
 * @property runs - 项目的 Run 列表（新→旧）
 * @property events - 最新 Run 的持久化 SSE 事件
 * @property history - 服务端持久化的对话历史（用户指令 + assistant 摘要）
 * @property versions - 已提升的版本列表（新→旧），用于版本切换
 * @property selectedVersionId - 当前查看的历史版本；null 为最新稳定版
 * @property onSelectVersion - 切换查看的版本（null 回到最新）
 * @property buildDiagnostics - 失败 Run 的构建诊断（可折叠展示）
 * @property onSend - 发送新指令（创建 update Run，可附代码引用）
 * @property onRetry - 重试失败的 Run（无契约时重新规划，有契约时重试构建）
 * @property onCancel - 请求协作式终止当前活跃 Run
 * @property isSending - 指令提交中
 * @property isCancelling - 终止请求进行中或 Run 正在终止
 */
interface ChatPanelProps {
  projectId: string;
  projectName?: string;
  originalPrompt: string;
  runs: Run[];
  events: StreamEvent[];
  history: ChatMessageRecord[];
  versions: ProjectVersion[];
  selectedVersionId: string | null;
  onSelectVersion: (versionId: string | null) => void;
  buildDiagnostics: string | null;
  onSend: (instruction: string, references: RunReferenceInput[], mode: RunMode) => void;
  onRetry: () => void;
  onCancel: () => void;
  isSending: boolean;
  isCancelling: boolean;
}

export default function ChatPanel({
  projectId,
  projectName: propProjectName,
  originalPrompt,
  runs,
  events,
  history,
  versions,
  selectedVersionId,
  onSelectVersion,
  buildDiagnostics,
  onSend,
  onRetry,
  onCancel,
  isSending,
  isCancelling,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  /** Run 历史下拉菜单的显示状态 */
  const [showVersions, setShowVersions] = useState(false);
  /** 滚动到底部按钮的显示状态 */
  const [showScrollButton, setShowScrollButton] = useState(false);
  /** @ 引用：手动添加的文件 chips 与当前候选下拉状态 */
  const [mentionRefs, setMentionRefs] = useState<string[]>([]);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  /**
   * 执行模式：build 自动批准计划，plan 需人工审阅批准后生成。
   * 初始值优先级：首页路由传入 > 本项目 localStorage 记忆 > 默认 build。
   */
  const [mode, setModeState] = useState<RunMode>(() => {
    const fromRoute = (location.state as { mode?: RunMode } | null)?.mode;
    if (fromRoute === 'build' || fromRoute === 'plan') return fromRoute;
    const remembered = localStorage.getItem(`lingforge:mode:${projectId}`);
    return remembered === 'plan' ? 'plan' : 'build';
  });
  /** 切换模式并记忆到本项目，作用于下一次发送 */
  const setMode = (next: RunMode) => {
    setModeState(next);
    localStorage.setItem(`lingforge:mode:${projectId}`, next);
  };
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const versionsMenuRef = useRef<HTMLDivElement>(null);
  const { selectionReference, setSelectionReference, projectFiles } = useWorkspace();

  const allFilePaths = useMemo(() => collectFilePaths(projectFiles), [projectFiles]);
  /** @ 候选文件列表：按输入片段模糊过滤 */
  const mentionCandidates = useMemo(() => {
    if (mentionQuery === null) return [];
    const query = mentionQuery.toLowerCase();
    return allFilePaths.filter((path) => path.toLowerCase().includes(query)).slice(0, 8);
  }, [mentionQuery, allFilePaths]);

  /** 版本下拉菜单：点击菜单外任意位置自动收起 */
  useEffect(() => {
    if (!showVersions) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!versionsMenuRef.current?.contains(event.target as Node)) {
        setShowVersions(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [showVersions]);

  /** 项目名称：加载中时显示占位文本 */
  const projectName = propProjectName || '加载中…';

  const currentRun = runs[0];
  /** AI 正在生成回复的状态：最新 Run 仍处于活跃或正在终止的阶段 */
  const isTyping = Boolean(
    currentRun && (ACTIVE_RUN_STATUSES.has(currentRun.status) || currentRun.status === 'cancelling'),
  );
  /** 当前阶段文案：跟随最新 SSE 事件，文件写入时直接展示正在写哪个文件 */
  const currentStageLabel = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const { type, event } = events[index];
      if (type === 'builder.file_written') {
        return `正在写入 ${String(event.payload.path ?? '源文件')}…`;
      }
      const label = EVENT_STEP_LABELS[type];
      if (label) return label;
    }
    return null;
  }, [events]);

  /**
   * 构建阶段状态条：代码生成结束后进入校验/构建/提交/发布阶段时持续可见，
   * 让用户知道预览为何还没刷新；完成后短暂展示新版本 Commit。
   */
  const buildStatus = useMemo(() => {
    if (!currentRun) return null;
    const stageLabels: Record<string, string> = {
      validating: '代码生成完成，正在校验…',
      typechecking: '正在构建（TypeScript 检查 + Vite Build）…',
      building: '正在构建（TypeScript 检查 + Vite Build）…',
      repairing: '构建未通过，正在自动修复…',
      committing: '构建成功，正在提交新版本…',
      promoting: '正在发布预览…',
    };
    if (ACTIVE_RUN_STATUSES.has(currentRun.status) && currentRun.stage && stageLabels[currentRun.stage]) {
      return { kind: 'running' as const, label: stageLabels[currentRun.stage] };
    }
    if (currentRun.status === 'completed') {
      const sha = versions[0]?.commit_sha;
      return { kind: 'done' as const, label: `构建完成，预览已更新${sha ? ` · 新版本 ${sha.slice(0, 7)}` : ''}` };
    }
    return null;
  }, [currentRun, versions]);

  /** 组装消息列表：持久化历史 + 最新 Run 的实时工作流（若历史尚未覆盖它） */
  const messages = useMemo<ChatMessageData[]>(() => {
    const result: ChatMessageData[] = [];
    if (history.length === 0) {
      // 历史尚未加载或老项目缺少首条记录时，用原始需求兜底。
      result.push({ id: 'original-prompt', role: 'user', content: originalPrompt, timestamp: new Date() });
    }
    for (const record of history) {
      if (record.role === 'system') continue;
      result.push({
        id: record.id,
        role: record.role === 'user' ? 'user' : 'assistant',
        content: record.visible_content,
        timestamp: new Date(record.created_at),
      });
    }
    if (currentRun) {
      const hasAssistantRecord = history.some((record) => record.run_id === currentRun.id && record.role === 'assistant');
      const isLive = ACTIVE_RUN_STATUSES.has(currentRun.status) || currentRun.status === 'cancelling';
      // 活跃 Run 始终展示实时工作流；刚结束的 Run 在 assistant 摘要落库前也保留实时视图。
      if (isLive || !hasAssistantRecord) {
        const steps: StepItem[] = events.flatMap(({ type, event }) => {
          if (type === 'builder.file_written') {
            // 生成中的文件写入：以文件步骤呈现，点击可在编辑器中流式查看内容
            return [{ type: 'file', action: 'write', file: String(event.payload.path ?? '') }];
          }
          const label = EVENT_STEP_LABELS[type];
          return label ? [label] : [];
        });
        result.push({
          id: `run-${currentRun.id}`,
          role: 'assistant',
          content: `【${RUN_KIND_LABELS[currentRun.kind]}】${runSummary(currentRun)}`,
          steps,
          timestamp: new Date(),
          version:
            currentRun.status === 'completed'
              ? { label: '稳定版本', description: '已通过校验、构建并发布' }
              : undefined,
        });
      }
    }
    return result;
  }, [originalPrompt, runs, events, history, currentRun]);

  /** 新消息到达时自动滚动到底部 */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  /**
   * 监听消息列表滚动位置
   * 当用户向上滚动超过 80px 时显示"滚动到底部"按钮
   */
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 80;
    setShowScrollButton(!isNearBottom);
  }, []);

  /** 平滑滚动到消息列表底部 */
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  /** 发送用户指令：创建 update Run（附选区/@ 代码引用），后续进展由 SSE 事件驱动 */
  const handleSend = () => {
    const instruction = input.trim();
    if (instruction.length < 10 || isSending) return;
    const references: RunReferenceInput[] = [
      ...mentionRefs.map((path) => ({ path })),
      ...(selectionReference
        ? [{ path: selectionReference.path, start_line: selectionReference.startLine, end_line: selectionReference.endLine }]
        : []),
    ];
    onSend(instruction, references, mode);
    setInput('');
    setMentionRefs([]);
    setSelectionReference(null);
    setMentionQuery(null);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  };

  /** 输入变化：检测光标前最后一个 @ 片段，驱动文件候选下拉 */
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    setInput(el.value);
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    const beforeCursor = el.value.slice(0, el.selectionStart ?? el.value.length);
    const atIndex = beforeCursor.lastIndexOf('@');
    if (atIndex >= 0 && !/[\s@]/.test(beforeCursor.slice(atIndex + 1))) {
      setMentionQuery(beforeCursor.slice(atIndex + 1));
      setMentionIndex(0);
    } else {
      setMentionQuery(null);
    }
  };

  /** 选中一个 @ 候选文件：移除 @片段，加入引用 chips */
  const pickMention = (path: string) => {
    const el = inputRef.current;
    const cursor = el?.selectionStart ?? input.length;
    const atIndex = input.slice(0, cursor).lastIndexOf('@');
    if (atIndex >= 0) {
      setInput(input.slice(0, atIndex) + input.slice(cursor));
    }
    setMentionRefs((previous) => (previous.includes(path) ? previous : [...previous, path]));
    setMentionQuery(null);
    inputRef.current?.focus();
  };

  /**
   * 键盘事件处理
   * @ 下拉打开时：上下键选择、Enter 确认、Esc 关闭；否则 Enter 发送，Shift+Enter 换行
   */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (mentionQuery !== null && mentionCandidates.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionIndex((index) => Math.min(index + 1, mentionCandidates.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionIndex((index) => Math.max(index - 1, 0));
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        pickMention(mentionCandidates[mentionIndex]);
        return;
      }
      if (e.key === 'Escape') {
        setMentionQuery(null);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-background relative">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-between px-4 h-12 border-b border-border/60 flex-shrink-0">
        <div className="flex items-center gap-2">
          {/* 返回首页按钮 */}
          <Button
            variant="ghost"
            size="icon"
            className="w-7 h-7 cursor-pointer"
            onClick={() => navigate('/')}
            title="返回首页"
          >
            <Home className="w-4 h-4" />
          </Button>
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5 text-primary-foreground" />
          </div>
          <span className="text-sm font-semibold text-foreground">{projectName}</span>
        </div>
        {/* 版本历史按钮 */}
        <div className="relative" ref={versionsMenuRef}>
          <Button
            variant="ghost"
            size="icon"
            className="w-7 h-7 cursor-pointer"
            onClick={() => setShowVersions(!showVersions)}
            title="Run 历史"
          >
            <History className="w-4 h-4" />
          </Button>

          {/* 版本历史下拉菜单：切换到任一已提升版本的只读视图 */}
          {showVersions && (
            <div className="absolute right-0 top-9 w-56 bg-card border border-border rounded-lg shadow-lg z-50 py-1 animate-in fade-in slide-in-from-top-1 duration-200 max-h-72 overflow-y-auto">
              <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider font-medium px-3 py-1.5">
                版本历史
              </p>
              {versions.length === 0 && (
                <p className="px-3 py-2 text-xs text-muted-foreground">暂无已发布版本</p>
              )}
              {versions.map((version) => {
                const isSelected = selectedVersionId ? version.id === selectedVersionId : version.is_stable;
                return (
                  <button
                    key={version.id}
                    className={`w-full text-left px-3 py-2 transition-colors text-xs cursor-pointer ${
                      isSelected ? 'bg-primary/10' : 'hover:bg-secondary/60'
                    }`}
                    onClick={() => {
                      onSelectVersion(version.is_stable ? null : version.id);
                      setShowVersions(false);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground/90 font-mono">{version.commit_sha.slice(0, 7)}</span>
                      {version.is_stable && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600">当前</span>
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-[10px] text-muted-foreground truncate">
                        {RUN_KIND_LABELS[version.origin_kind as Run['kind']] ?? version.origin_kind} · {version.message}
                      </span>
                      <span className="text-[10px] text-muted-foreground/60 flex-shrink-0 ml-2">
                        {new Date(version.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 消息列表区域 */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto relative"
        onScroll={handleScroll}
      >
        <div className="py-2">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              defaultExpanded={isTyping && msg.id === `run-${currentRun?.id}`}
            />
          ))}
          {/* Plan 模式：Run 暂停在待审批时，在会话流中展示完整构建计划 */}
          {currentRun?.status === 'awaiting_approval' && <PlanCard projectId={projectId} />}
          {/* AI 正在生成的动画指示器（代码生成阶段常驻；构建阶段由下方状态条接管） */}
          {isTyping && !buildStatus && (
            <div className="flex gap-3 px-4 py-3">
              <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-primary animate-pulse" />
              </div>
              <div className="flex flex-col justify-center gap-1">
                <div className="flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:0ms]" />
                  <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:150ms]" />
                  <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:300ms]" />
                </div>
                <span className="text-[11px] text-muted-foreground animate-pulse">
                  {currentRun?.status === 'cancelling' ? '正在终止生成…' : currentStageLabel ?? '正在处理…'}
                </span>
              </div>
            </div>
          )}
          {/* 最新 Run 失败：诊断面板 + 恢复入口（无契约则重新规划，有契约则重试构建） */}
          {currentRun?.status === 'failed' && (
            <div className="px-4 py-2 space-y-2">
              {buildDiagnostics && (
                <details className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                  <summary className="cursor-pointer text-xs font-medium text-destructive">
                    构建诊断（点击展开）
                  </summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-muted-foreground">
                    {buildDiagnostics}
                  </pre>
                </details>
              )}
              <Button
                variant="outline"
                size="sm"
                className="gap-2 text-xs cursor-pointer"
                disabled={isSending}
                onClick={onRetry}
              >
                <RefreshCw className="w-3.5 h-3.5" />
                重试生成
              </Button>
            </div>
          )}
          {/* 最新一轮会话的构建状态：代码生成完成后的校验/构建/提交/发布进度，
              以及完成时的新版本 Commit。跟随当前 Run，新一轮会话开始后自然更新。 */}
          {buildStatus && (
            <div className="px-4 py-2">
              <div
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                  buildStatus.kind === 'done'
                    ? 'border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400'
                    : 'border-border/70 bg-secondary/40 text-foreground/80'
                }`}
              >
                {buildStatus.kind === 'done' ? (
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                ) : (
                  <LoaderCircle className="w-3.5 h-3.5 flex-shrink-0 animate-spin" />
                )}
                <span>{buildStatus.label}</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 滚动到底部浮动按钮 */}
      {showScrollButton && (
        <div className="absolute bottom-[120px] left-1/2 -translate-x-1/2 z-40">
          <Button
            variant="secondary"
            size="icon"
            className="w-8 h-8 rounded-full shadow-lg border border-border/60 cursor-pointer hover:bg-primary/10 transition-all duration-200"
            onClick={scrollToBottom}
          >
            <ArrowDown className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* 底部消息输入区域 */}
      <div className="p-3 border-t border-border/60 flex-shrink-0 relative">
        {/* @ 文件候选下拉 */}
        {mentionQuery !== null && mentionCandidates.length > 0 && (
          <div className="absolute bottom-full mb-2 left-3 right-3 bg-card border border-border rounded-lg shadow-lg z-50 py-1 max-h-56 overflow-y-auto">
            <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider font-medium px-3 py-1.5">
              引用文件
            </p>
            {mentionCandidates.map((path, index) => (
              <button
                key={path}
                className={`w-full text-left px-3 py-1.5 text-xs font-mono cursor-pointer transition-colors ${
                  index === mentionIndex ? 'bg-primary/10 text-foreground' : 'text-muted-foreground hover:bg-secondary/60'
                }`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pickMention(path);
                }}
              >
                {path}
              </button>
            ))}
          </div>
        )}
        <div className="rounded-xl border border-border/80 bg-secondary/30 focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20 transition-all duration-200">
          {/* 代码引用 chips：编辑器选区（带行号）与 @ 引用 */}
          {(selectionReference || mentionRefs.length > 0) && (
            <div className="flex flex-wrap gap-1.5 px-3 pt-2.5">
              {selectionReference && (
                <span className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 border border-primary/25 px-2 py-1 text-[11px] text-foreground/90">
                  <FileCode2 className="w-3 h-3 text-primary" />
                  {selectionReference.path.split('/').pop()} · L{selectionReference.startLine}-{selectionReference.endLine}
                  <button
                    className="text-muted-foreground hover:text-foreground cursor-pointer"
                    onClick={() => setSelectionReference(null)}
                    title="移除引用"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {mentionRefs.map((path) => (
                <span
                  key={path}
                  className="inline-flex items-center gap-1.5 rounded-md bg-secondary border border-border/60 px-2 py-1 text-[11px] text-foreground/90"
                >
                  <FileCode2 className="w-3 h-3 text-muted-foreground" />
                  {path.split('/').pop()}
                  <button
                    className="text-muted-foreground hover:text-foreground cursor-pointer"
                    onClick={() => setMentionRefs((previous) => previous.filter((candidate) => candidate !== path))}
                    title="移除引用"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          {/* 多行文本输入框，支持自动高度调整；输入 @ 可引用项目文件 */}
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="描述你的需求（至少 10 个字）... 输入 @ 可引用文件"
            rows={2}
            className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none overflow-y-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent"
            style={{ minHeight: '56px', maxHeight: '200px' }}
          />
          {/* 工具栏 - 模式选择器紧贴发送按钮，生成期间为终止按钮 */}
          <div className="flex items-center justify-end gap-1.5 px-3 pb-2">
            <ModeSelect mode={mode} onChange={setMode} disabled={isTyping} />
            {isTyping ? (
              <Button
                onClick={onCancel}
                disabled={isCancelling}
                size="icon"
                variant="destructive"
                className="w-8 h-8 rounded-lg disabled:opacity-30 cursor-pointer transition-all duration-200"
                title="终止生成"
              >
                <Square className="w-3.5 h-3.5" />
              </Button>
            ) : (
              <Button
                onClick={handleSend}
                disabled={input.trim().length < 10 || isSending || isTyping}
                size="icon"
                className="w-8 h-8 rounded-lg bg-primary hover:bg-primary/90 disabled:opacity-30 cursor-pointer transition-all duration-200"
                title="发送"
              >
                <Send className="w-3.5 h-3.5 text-primary-foreground" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
