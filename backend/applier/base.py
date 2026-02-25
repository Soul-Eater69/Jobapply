import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class BaseApplier:
    """Base class for all job appliers."""

    async def apply(self, job: dict) -> Tuple[bool, str]:
        """
        Apply to a job.
        Returns (success: bool, reason: str)
        """
        raise NotImplementedError

    async def login(self, page) -> bool:
        """Log into the job platform. Returns True on success."""
        raise NotImplementedError
