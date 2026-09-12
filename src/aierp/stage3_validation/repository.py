import uuid

from sqlalchemy.orm import Session

from aierp.stage3_validation.codes import ValidationResult
from aierp.stage3_validation.models import ValidationResultRecord, ValidationRun


def persist_validation_run(
    session: Session,
    *,
    document_id: uuid.UUID,
    canonical_invoice_id: uuid.UUID,
    results: list[ValidationResult],
) -> ValidationRun:
    run = ValidationRun(document_id=document_id, canonical_invoice_id=canonical_invoice_id)
    session.add(run)
    session.flush()

    for result in results:
        session.add(
            ValidationResultRecord(
                run_id=run.id,
                code=result.code,
                severity=result.severity,
                message_nl=result.message_nl,
                params=result.params,
            )
        )
    session.flush()
    return run
