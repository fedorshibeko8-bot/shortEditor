from enum import Enum


class ClipStatus(str, Enum):
    NEW = "new"
    SENT_TO_ADMIN = "sent_to_admin"
    APPROVED = "approved"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    RENDERING = "rendering"
    SENT_FOR_REVIEW = "sent_for_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REVISION = "revision"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[ClipStatus, frozenset[ClipStatus]] = {
    ClipStatus.NEW: frozenset({ClipStatus.SENT_TO_ADMIN, ClipStatus.REJECTED}),
    ClipStatus.SENT_TO_ADMIN: frozenset({
        ClipStatus.APPROVED,
        ClipStatus.REJECTED,
    }),
    ClipStatus.APPROVED: frozenset({ClipStatus.DOWNLOADING, ClipStatus.FAILED, ClipStatus.REJECTED}),
    ClipStatus.DOWNLOADING: frozenset({ClipStatus.TRANSCRIBING, ClipStatus.FAILED}),
    ClipStatus.TRANSCRIBING: frozenset({ClipStatus.RENDERING, ClipStatus.FAILED}),
    ClipStatus.RENDERING: frozenset({
        ClipStatus.SENT_FOR_REVIEW,
        ClipStatus.REVISION,
        ClipStatus.FAILED,
    }),
    ClipStatus.SENT_FOR_REVIEW: frozenset({
        ClipStatus.PUBLISHED,
        ClipStatus.REVISION,
        ClipStatus.REJECTED,
        ClipStatus.FAILED,
    }),
    ClipStatus.REVISION: frozenset({ClipStatus.RENDERING, ClipStatus.FAILED}),
    ClipStatus.PUBLISHED: frozenset(),
    ClipStatus.REJECTED: frozenset(),
    ClipStatus.FAILED: frozenset(),
}


class InvalidStatusTransitionError(ValueError):
    pass


def assert_transition(current: ClipStatus | str, target: ClipStatus | str) -> None:
    current_status = ClipStatus(current)
    target_status = ClipStatus(target)
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        raise InvalidStatusTransitionError(
            f"Invalid clip status transition: {current_status.value} -> {target_status.value}"
        )
