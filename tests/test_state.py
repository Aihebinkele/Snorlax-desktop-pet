import datetime
import time

from desktop_pet.state import StateMachine, EVENT_TO_STATE, STATE_CONFIG, CLICK_RESPONSES, AUTO_RECOVERY


def test_event_to_state_mapping():
    assert EVENT_TO_STATE["task_start"] == "thinking"
    assert EVENT_TO_STATE["tool_start"] == "thinking"
    assert EVENT_TO_STATE["reading_start"] == "reading"
    assert EVENT_TO_STATE["step_complete"] == "step_done"
    assert EVENT_TO_STATE["task_complete"] == "happy"
    assert EVENT_TO_STATE["user_confirmation_needed"] == "waiting"
    assert EVENT_TO_STATE["error"] == "sad"


def test_all_states_have_config():
    for state in EVENT_TO_STATE.values():
        assert state in STATE_CONFIG
        assert "emoji" in STATE_CONFIG[state]
        assert "label" in STATE_CONFIG[state]
        assert "bg" in STATE_CONFIG[state]
        assert "fg" in STATE_CONFIG[state]


def test_all_states_have_click_response():
    for state in STATE_CONFIG:
        assert state in CLICK_RESPONSES, f"Missing CLICK_RESPONSES for state: {state}"


def test_state_machine_initial_state():
    sm = StateMachine()
    assert sm.current_state == "idle"
    assert sm.current_message == ""


def test_state_machine_process_event():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("task_start", "test")
    assert sm.current_state == "thinking"
    assert changes[-1] == ("thinking", "test")


def test_state_machine_tool_start():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("tool_start", "Write")
    assert sm.current_state == "thinking"


def test_state_machine_reading_start():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("reading_start", "Read")
    assert sm.current_state == "reading"


def test_set_callback():
    changes = []
    sm = StateMachine()
    sm.set_callback(lambda s, m: changes.append((s, m)))
    sm.process_event("task_complete", "done")
    assert sm.current_state == "happy"
    assert changes == [("happy", "done")]


def test_auto_recovery_step_done():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("step_complete", "Write")
    assert sm.current_state == "step_done"
    target, duration = sm.get_auto_recovery("step_done", {"state_durations": {"step_done": 1500}})
    assert target == "thinking"
    assert duration == 1500


def test_auto_recovery_reading():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("reading_start", "Read")
    assert sm.current_state == "reading"
    target, duration = sm.get_auto_recovery("reading", {"state_durations": {"reading": 2000}})
    assert target == "thinking"
    assert duration == 2000


def test_auto_recovery_happy():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("task_complete", "done")
    assert sm.current_state == "happy"
    target, duration = sm.get_auto_recovery("happy", {"state_durations": {"happy": 5000}})
    assert target == "idle"
    assert duration == 5000


def test_auto_recovery_no_duration():
    target, duration = StateMachine.get_auto_recovery(None, "tired", {"state_durations": {"tired": 0}})
    assert target is None
    assert duration == 0


def test_step_done_timeout():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("step_complete", "Write")
    assert sm.current_state == "step_done"

    sm._last_event_at = datetime.datetime.now() - datetime.timedelta(seconds=10)
    sm.check_timeouts({"step_done_timeout_ms": 5000, "thinking_tired_timeout_ms": 180000, "idle_sleeping_timeout_ms": 600000})
    assert sm.current_state == "thinking"


def test_thinking_tired_transition():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.process_event("task_start", "test")
    assert sm.current_state == "thinking"

    sm._state_entered_at = datetime.datetime.now() - datetime.timedelta(seconds=200)
    sm._last_event_at = datetime.datetime.now()
    sm.check_timeouts({"step_done_timeout_ms": 5000, "thinking_tired_timeout_ms": 180000, "idle_sleeping_timeout_ms": 600000})
    assert sm.current_state == "tired"


def test_idle_sleeping_transition():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    assert sm.current_state == "idle"

    sm._state_entered_at = datetime.datetime.now() - datetime.timedelta(seconds=700)
    sm.check_timeouts({"step_done_timeout_ms": 5000, "thinking_tired_timeout_ms": 180000, "idle_sleeping_timeout_ms": 600000})
    assert sm.current_state == "sleeping"


def test_wake_up_from_sleeping():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.transition("sleeping", "")
    assert sm.current_state == "sleeping"
    sm.wake_up()
    assert sm.current_state == "idle"


def test_wake_up_from_non_sleeping():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.transition("thinking", "")
    sm.wake_up()
    assert sm.current_state == "thinking"


def test_reset_to_idle():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))
    sm.transition("thinking", "")
    sm.reset_to_idle()
    assert sm.current_state == "idle"


def test_thinking_vs_reading():
    changes = []
    sm = StateMachine(on_state_change=lambda s, m: changes.append((s, m)))

    sm.process_event("task_start", "user prompt")
    assert sm.current_state == "thinking"

    sm.process_event("reading_start", "Read")
    assert sm.current_state == "reading"


def test_no_working_in_state_config():
    assert "working" not in STATE_CONFIG
    assert "working" not in EVENT_TO_STATE.values()
    assert "working" not in CLICK_RESPONSES
    assert "working" not in AUTO_RECOVERY
