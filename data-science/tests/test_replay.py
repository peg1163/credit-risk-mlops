import pytest
from credit_risk import replay
def test_replay_is_sequential_and_idempotent():
    replay.reset(); first=replay.release("1998-01")
    assert first["rows"]>0
    with pytest.raises(ValueError,match="already released"): replay.release("1998-01")
    second=replay.release("1998-02"); assert second["period"]=="1998-02"
    replay.reset()

