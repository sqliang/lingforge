"""Builder and Repair roles: capability-minimized Deep Agents over the worktree.

The agents reason over a Build Contract and source files, but all effectful platform
operations (validation, Docker, Git, artifact upload and database promotion) remain in
the Worker. This keeps a model mistake from becoming a stable product version.

Collaborators: prompts live in `agents/prompts/builder.py`, the worktree write boundary
in `agents/tools/worktree_files.py`, and model/abort plumbing in `agents/model.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from lite_atoms.agents.model import agent_session
from lite_atoms.agents.prompts.builder import render_builder_prompt
from lite_atoms.agents.tools.worktree_files import build_reference_excerpts, build_worktree_tools


def generate_source(
    worktree: Path,
    contract: dict[str, Any],
    diagnostics: str | None = None,
    on_file_written: Callable[[str, str], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
    instruction: str | None = None,
    references: list[dict[str, Any]] | None = None,
) -> str:
    """Run Builder or Repair with a capability-minimized Deep Agent.

    The returned text is an auditable summary only. All source mutation has to pass through
    the constrained worktree tools, and later deterministic validation decides promotion.
    `on_file_written` is invoked after each successful write so the workspace can stream
    generated files before promotion. `should_abort` is polled between tool calls; when it
    fires, AgentAborted unwinds the session and propagates to the Worker. `instruction`
    carries the owner's update request for incremental Runs.
    """
    from deepagents import create_deep_agent

    # ── Step 1: compose the system prompt ───────────────────────────────────
    # The prompt is the advisory half of capability minimization; the tools in
    # Step 2 enforce the same boundary mechanically. `render_builder_prompt`
    # picks the Builder or Repair persona based on whether diagnostics exist.
    system_prompt = render_builder_prompt(diagnostics)

    # ── Step 2: build the constrained worktree file tools ────────────────────
    # Exactly three tools — read_source, list_sources, write_source — each bound
    # to this Run's worktree, its write-streaming callback, and its cancellation
    # check. These are the only tools whose writes land on disk.
    file_tools = build_worktree_tools(worktree, on_file_written, should_abort)

    # ── Step 3: assemble the Deep Agent inside an abort-watched session ──────
    # `agent_session` yields the shared ChatOpenAI adapter and arms the watcher
    # thread that force-closes the model's HTTP client the moment the Run is
    # cancelled, so a blocking in-flight request fails immediately. Together
    # with the per-tool abort check in Step 2, cancellation works both between
    # agent steps and during a single long model call.
    with agent_session(should_abort=should_abort, watcher_name="agent-abort-watcher") as model:
        # `create_deep_agent` builds a LangGraph ReAct-style agent graph: the model
        # proposes a tool call, the graph executes it, feeds the result back, and
        # loops until the model answers in plain text.
        #   model:         the reasoning engine driving the loop.
        #   tools:         our allowlisted file tools — see the Chinese note below.
        #   subagents=[]:  an empty list removes the built-in `task` delegation
        #                  tool entirely, keeping the session single-agent and
        #                  fully auditable.
        #   system_prompt: the fixed persona/boundary text from Step 1.
        #
        # 已知行为说明(刻意保留,暂不修复):
        # deepagents 的 `tools` 参数是追加式的 —— 官方文档明确 "Passing tools here
        # is additive — it never removes a built-in"。除我们传入的 3 个工具外,默认
        # middleware 还会注入 `write_todos` 以及 `ls / read_file / write_file /
        # edit_file / glob / grep` 六个内置文件工具。这些内置文件工具默认落在
        # StateBackend(LangGraph 临时状态)上:不写入 worktree、不触发
        # `on_file_written` 流式回调、也不受 allowlist / 文件预算约束 —— 模型若
        # 调用内置 `write_file`,内容会随会话结束静默丢失。目前依赖 system prompt
        # 中的 "Work only through the provided source tools" 引导模型只使用我们的
        # 3 个落盘工具。
        # 这是有意接受的过渡状态:后续计划主动启用 deepagents 的内置能力(任务
        # 规划、子代理、持久化 backend 等)来增强代码生成 Agent,届时应把这些工具
        # 纳入正式的能力边界设计,而不是继续只靠 prompt 规避。若届时需要彻底剔除
        # 内置工具,可使用 `register_harness_profile` +
        # `HarnessProfile(excluded_middleware=...)`(beta API)。
        agent = create_deep_agent(
            model=model,
            tools=file_tools,
            subagents=[],
            system_prompt=system_prompt,
        )

        # ── Step 4: build the single user message that kicks off the session ──
        # The payload is structured JSON instead of prose so the contract arrives
        # unambiguous. Optional fields are added only when present.
        payload: dict[str, Any] = {"contract": contract}
        if instruction:
            # Incremental Runs: the owner's instruction steers a minimal edit, the
            # approved Contract remains the product boundary.
            payload["instruction"] = instruction
            payload["note"] = (
                "Modify the existing source minimally to satisfy the instruction; "
                "keep unrelated features and files intact."
            )
        excerpts = build_reference_excerpts(worktree, references or [])
        if excerpts:
            # User-pinned excerpts give the agent precise local context for the edit.
            payload["references"] = excerpts
        user_message = {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}

        # ── Step 5: run the agent to completion ──────────────────────────────
        # `invoke` executes the whole LangGraph synchronously and returns the
        # final graph state: a dict whose "messages" list holds the full
        # conversation (user message, interleaved tool calls/results, and the
        # closing assistant reply). AgentAborted raised by any tool call or by
        # the watcher's client close propagates out of here to the Worker.
        result = agent.invoke({"messages": [user_message]})

        # ── Step 6: return the closing assistant message as the Run summary ──
        # The last message is the model's own report of what it changed; it is
        # audit text only, never trusted as an effect. Capped at 4 000 chars to
        # keep it a summary, not a transcript.
        final_message = result["messages"][-1]
        return str(final_message.content)[:4_000]
