from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ExternalLead:
    external_id: str
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    notes: str = ""
    attributes: dict[str, Any] | None = None

class LeadSourceAdapter(ABC):
    @abstractmethod
    def pull_leads(self, *, cursor: str | None = None) -> tuple[list[ExternalLead], str | None]:
        raise NotImplementedError

class CRMAdapter(LeadSourceAdapter):
    @abstractmethod
    def write_qualification(
        self,
        *,
        external_id: str,
        score: int,
        status: str,
        next_action: str,
        reason: str,
    ) -> None:
        raise NotImplementedError

class IdentityProviderAdapter(ABC):
    @abstractmethod
    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def exchange_code(self, *, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError
