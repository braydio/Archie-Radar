from __future__ import annotations

from ..schemas import PetPostIn
from .base import Connector


class PetcoLoveConnector(Connector):
    """Guarded connector for the approved Petco Love Partner API.

    Do not replace this with HTML scraping. Configure it only after an API key is
    issued and map the approved API response shape using the official v2.1 docs.
    """

    source_name = "petco_love"

    def __init__(self, api_key: str, api_base: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")

    async def fetch(self) -> list[PetPostIn]:
        if not self.api_key:
            raise RuntimeError(
                "Petco Love connector requires an approved Partner API key. "
                "See https://api.petcolove.org/v2.1/docs"
            )
        raise NotImplementedError(
            "API key detected, but endpoint mapping is intentionally left disabled "
            "until the approved Partner API response schema is available to this deployment."
        )
