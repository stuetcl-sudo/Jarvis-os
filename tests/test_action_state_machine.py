import tempfile
from pathlib import Path
from unittest.mock import patch

from app import config
from app.actions.action import Action
from app.actions.engine import action_engine
from app.actions.history import get_action, initialize_action_tables, insert_action
from app.actions.queue import approve_action, cancel_action, deny_action
from app.actions.state_machine import ActionTransitionConflict, claim_approved_action, transition_action


def reset_db():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    initialize_action_tables()
    return Path(tmp.name)


def make_action(status="waiting_approval", approved=False):
    return insert_action(
        Action(
            requested_by="test",
            source="test",
            asset_id="docker:example-app",
            action_type="docker.start_container",
            reason="test action",
            requires_approval=True,
            status=status,
            approved=approved,
            approved_by="test" if approved else None,
            approved_at="2026-01-01T00:00:00+00:00" if approved else None,
        )
    )


def test_waiting_approval_can_become_approved():
    path = reset_db()
    try:
        action = make_action()
        result = approve_action(action["action_id"])
        assert result.changed is True
        assert result.action["status"] == "approved"
        assert result.action["approved"] is True
    finally:
        path.unlink(missing_ok=True)


def test_approved_cannot_be_approved_again():
    path = reset_db()
    try:
        action = make_action()
        approve_action(action["action_id"])
        try:
            approve_action(action["action_id"])
            raise AssertionError("second approval should fail")
        except ActionTransitionConflict:
            pass
    finally:
        path.unlink(missing_ok=True)


def test_completed_cannot_be_changed():
    path = reset_db()
    try:
        action = make_action(status="approved", approved=True)
        transition_action(action["action_id"], "running")
        transition_action(action["action_id"], "completed")
        try:
            deny_action(action["action_id"])
            raise AssertionError("terminal transition should fail")
        except ActionTransitionConflict:
            pass
        assert get_action(action["action_id"])["status"] == "completed"
    finally:
        path.unlink(missing_ok=True)


def test_running_cannot_be_cancelled_or_denied():
    path = reset_db()
    try:
        action = make_action(status="approved", approved=True)
        transition_action(action["action_id"], "running")
        for fn in (cancel_action, deny_action):
            try:
                fn(action["action_id"])
                raise AssertionError("running transition should fail")
            except ActionTransitionConflict:
                pass
        assert get_action(action["action_id"])["status"] == "running"
    finally:
        path.unlink(missing_ok=True)


def test_two_atomic_claims_result_in_one_winner():
    path = reset_db()
    try:
        action = make_action(status="approved", approved=True)
        first = claim_approved_action(action["action_id"])
        second = claim_approved_action(action["action_id"])
        assert first.changed is True
        assert second.changed is False
        assert get_action(action["action_id"])["status"] == "running"
    finally:
        path.unlink(missing_ok=True)


def test_executor_exception_results_in_failed_status():
    path = reset_db()
    try:
        action = make_action(status="approved", approved=True)
        with patch("app.actions.engine.check_action_safety", return_value=(True, "passed", "test safety passed")):
            with patch("app.actions.engine.execute_action", side_effect=RuntimeError("boom")):
                result = action_engine.run_action(action["action_id"])
        assert result["status"] == "failed"
        assert "boom" in result["result"].get("error", "")
        assert get_action(action["action_id"])["status"] == "failed"
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    for test in [
        test_waiting_approval_can_become_approved,
        test_approved_cannot_be_approved_again,
        test_completed_cannot_be_changed,
        test_running_cannot_be_cancelled_or_denied,
        test_two_atomic_claims_result_in_one_winner,
        test_executor_exception_results_in_failed_status,
    ]:
        test()
    print("Action state machine tests OK")
