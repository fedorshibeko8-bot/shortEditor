import pytest

from shorteditor.core.statuses import (
    ClipStatus,
    InvalidStatusTransitionError,
    assert_transition,
)


@pytest.mark.parametrize(
    ("current", "allowed"),
    [
        (ClipStatus.NEW, {ClipStatus.SENT_TO_ADMIN, ClipStatus.REJECTED}),
        (ClipStatus.SENT_TO_ADMIN, {ClipStatus.APPROVED, ClipStatus.REJECTED}),
        (ClipStatus.APPROVED, {ClipStatus.DOWNLOADING, ClipStatus.FAILED, ClipStatus.REJECTED}),
        (ClipStatus.DOWNLOADING, {ClipStatus.TRANSCRIBING, ClipStatus.FAILED}),
        (ClipStatus.TRANSCRIBING, {ClipStatus.RENDERING, ClipStatus.FAILED}),
        (
            ClipStatus.RENDERING,
            {ClipStatus.SENT_FOR_REVIEW, ClipStatus.REVISION, ClipStatus.FAILED},
        ),
        (
            ClipStatus.SENT_FOR_REVIEW,
            {ClipStatus.PUBLISHED, ClipStatus.REVISION, ClipStatus.REJECTED, ClipStatus.FAILED},
        ),
        (ClipStatus.REVISION, {ClipStatus.RENDERING, ClipStatus.FAILED}),
        (ClipStatus.PUBLISHED, set()),
        (ClipStatus.REJECTED, set()),
        (ClipStatus.FAILED, set()),
    ],
)
def test_status_transition_matrix(current: ClipStatus, allowed: set[ClipStatus]) -> None:
    for target in ClipStatus:
        if target in allowed:
            assert_transition(current, target)
        else:
            with pytest.raises(InvalidStatusTransitionError):
                assert_transition(current, target)
