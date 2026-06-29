from datetime import datetime

from sqlmodel import Session

from .. import db as _db
from ..models import NotificationLog


class DatabaseChannel:
    def send(
        self,
        *,
        kind: str,
        title: str,
        message: str,
        product_id: int | None,
        url: str | None,
        tags: list[str],
        recorded_at: datetime | None = None,
    ) -> None:
        with Session(_db.engine) as session:
            session.add(
                NotificationLog(
                    product_id=product_id,
                    kind=kind,
                    title=title,
                    message=message,
                    product_url=url,
                    sent_at=recorded_at or datetime.utcnow(),
                )
            )
            session.commit()
