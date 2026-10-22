"""Plan/Build mode branching: only plan mode pauses the initial Run for approval."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

from lingforge.worker import main as worker


def _run(mode: str) -> dict:
    return {"id": uuid4(), "project_id": uuid4(), "kind": "initial", "stage": "planning", "mode": mode}


def _persist_plan_patches(run: dict):
    """Patch every collaborator of _persist_plan; yields the repository mock."""
    repository = MagicMock()
    repository.cancel_requested.return_value = False
    repository.create_draft_contract.return_value = {"id": uuid4(), "version": 1}
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = {
        "original_prompt": "build a todo app",
        "owner_id": "user-1",
        "title": "TaskFlow",  # already named: skip the title model call
    }

    @contextmanager
    def fake_transaction():
        yield connection

    return (
        patch.object(worker, "repository", repository),
        patch.object(worker, "transaction", fake_transaction),
        patch.object(worker, "plan_contract", return_value={"title": "T"}),
        patch.object(worker, "_event", lambda *_args, **_kwargs: None),
        repository,
    )


def test_build_mode_auto_approves_contract() -> None:
    run = _run("build")
    repository_patch, transaction_patch, planner_patch, event_patch, repository = _persist_plan_patches(run)
    with repository_patch, transaction_patch, planner_patch, event_patch:
        worker._persist_plan(run)
    repository.auto_approve_contract.assert_called_once()
    # build 模式不得把 Run 暂停在待审批状态
    statuses = [call.kwargs.get("status") for call in repository.update_run.call_args_list]
    assert "awaiting_approval" not in statuses


def test_plan_mode_pauses_for_manual_approval() -> None:
    run = _run("plan")
    repository_patch, transaction_patch, planner_patch, event_patch, repository = _persist_plan_patches(run)
    with repository_patch, transaction_patch, planner_patch, event_patch:
        worker._persist_plan(run)
    repository.auto_approve_contract.assert_not_called()
    statuses = [call.kwargs.get("status") for call in repository.update_run.call_args_list]
    assert "awaiting_approval" in statuses
