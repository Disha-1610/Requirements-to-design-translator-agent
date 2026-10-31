"""Fail-closed control flow. Every gate failure is a Stop with an exact message."""


class Stop(Exception):  # noqa: N818 - name mirrors the STOP output contract
    """Halt the run. `message` is the exact STOP line(s) emitted to the user."""

    def __init__(self, message: str, stage: str = "unknown") -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
