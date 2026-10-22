import pytest

from app.core.state_machine import (
    ALL_STATES, EVENTS, TRANSITIONS,
    IllegalTranstition, next_status,
)

LEGAL = list(TRANSITIONS.items())
ILLEGAL = [(s,e) for s in ALL_STATES for e in EVENTS if (s,e) not in TRANSITIONS]

def test_counts():
    """护栏: 转移表改了但数字没同步, 这里先红。"""
    assert len(ALL_STATES) == 9
    assert len(EVENTS) == 15
    assert len(LEGAL) == 16
    assert len(LEGAL) + len(ILLEGAL) == 135

@pytest.mark.parametrize(("pair", "target"), LEGAL)
def test_legal(pair, target):
    assert next_status(*pair) == target

@pytest.mark.parametrize(("state", "event"), ILLEGAL)
def test_illegal(state, event):
    with pytest.raises(IllegalTranstition):
        next_status(state, event)