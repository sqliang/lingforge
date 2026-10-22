"""Short-lived preview ticket signing shared by API and isolated Preview Gateway."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from lingforge.settings import settings


ALGORITHM = "HS256"


def issue_preview_ticket(artifact_id: UUID) -> tuple[str, datetime]:
    """Issue a five-minute, artifact-bound ticket after the API has checked ownership."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode({"artifact_id": str(artifact_id), "exp": expires_at}, settings.preview_ticket_secret, algorithm=ALGORITHM)
    return token, expires_at


def verify_preview_ticket(token: str) -> UUID:
    """Verify ticket integrity/expiry and return only the allowed artifact identifier."""
    try:
        payload = jwt.decode(token, settings.preview_ticket_secret, algorithms=[ALGORITHM])
        return UUID(payload["artifact_id"])
    except (JWTError, KeyError, ValueError) as error:
        raise PermissionError("Invalid or expired preview ticket") from error
