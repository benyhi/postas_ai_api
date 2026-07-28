from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.arca.models import ArcaInvoice
from app.arca.service import InvoiceService, utc_now
from app.core.config import get_settings
from app.db.session import SessionLocal, engine


logger = logging.getLogger(__name__)


class ArcaInvoiceWorker:
    def __init__(self, session_factory=SessionLocal, *, batch_size: int = 20) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size

    def run_once(self) -> int:
        processed = 0
        seen: set[int] = set()
        while processed < self.batch_size:
            with self.session_factory() as db:
                query = (
                    select(ArcaInvoice)
                    .where(
                        ArcaInvoice.status.in_(["pending", "processing", "retrying"]),
                        ArcaInvoice.next_retry_at.is_not(None),
                        ArcaInvoice.next_retry_at <= utc_now(),
                    )
                    .order_by(ArcaInvoice.next_retry_at, ArcaInvoice.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if seen:
                    query = query.where(ArcaInvoice.id.not_in(seen))
                record = db.scalar(query)
                if record is None:
                    break
                seen.add(record.id)
                try:
                    InvoiceService(db).process(record)
                except Exception as exc:
                    db.rollback()
                    quarantined = db.get(ArcaInvoice, record.id, with_for_update=True)
                    if quarantined is not None:
                        quarantined.status = "quarantined"
                        quarantined.next_retry_at = None
                        quarantined.last_error_code = "worker_unexpected_error"
                        quarantined.last_error_message = "La factura fue puesta en cuarentena por un error interno."
                        db.commit()
                    logger.exception("ARCA invoice quarantined invoice_id=%s error=%s", record.id, type(exc).__name__)
                processed += 1
        return processed

    def run_forever(self, poll_seconds: float) -> None:
        logger.info("ARCA invoice worker started")
        while True:
            if self.run_once() == 0:
                time.sleep(poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("El worker ARCA requiere PostgreSQL para locks y correlatividad segura.")
    settings = get_settings()
    ArcaInvoiceWorker(batch_size=settings.arca_worker_batch_size).run_forever(
        settings.arca_worker_poll_seconds
    )


if __name__ == "__main__":
    main()
