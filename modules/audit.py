# managarr/modules/audit.py
from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

TRANSACTIONS_TABLE = "transactions"
DETAILS_COL = "details_json"

# ---------- formatting helpers ----------

def _fmt_date(d):
    if not d:
        return None
    if isinstance(d, (datetime, date)):
        return d.strftime("%m/%d/%Y")
    # allow caller strings like "01/01/2026"
    return str(d)

def _fmt_money(x):
    if x is None:
        return None
    if isinstance(x, Decimal):
        return f"{x:.2f}"
    try:
        return f"{Decimal(str(x)):.2f}"
    except Exception:
        return str(x)

def _kv(k, v):
    if v is None or v == "":
        return None
    return f"{k}: {v}"

def _join_fields(parts):
    return " | ".join(p for p in parts if p)

# ---------- schema helpers (safe for public users) ----------

def _column_exists(db, table: str, column: str) -> bool:
    q = """
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = %s
      AND COLUMN_NAME = %s
    LIMIT 1
    """
    with db.cursor() as cur:
        cur.execute(q, (table, column))
        return cur.fetchone() is not None

def ensure_details_json_column(
    db,
    table: str = TRANSACTIONS_TABLE,
    column: str = DETAILS_COL,
    auto_create: bool = False,
) -> bool:
    """
    Returns True if the column exists after optional creation; False otherwise.
    - If auto_create=False (default), we only check; no ALTER is attempted.
    - If auto_create=True, we try to add a JSON column, and if that fails,
      we fall back to LONGTEXT with utf8mb4_bin collation.
    """
    try:
        if _column_exists(db, table, column):
            return True
        if not auto_create:
            return False

        # Try native JSON first
        try:
            with db.cursor() as cur:
                cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` JSON NULL")
            db.commit()
            return True
        except Exception:
            logger.info("JSON type not available; falling back to LONGTEXT utf8mb4_bin.")
            with db.cursor() as cur:
                cur.execute(
                    f"ALTER TABLE `{table}` "
                    f"ADD COLUMN `{column}` LONGTEXT "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL"
                )
            db.commit()
            return True
    except Exception as e:
        logger.exception("ensure_details_json_column failed: %s", e)
        return False


# ---------- main entry point ----------

def log_transaction(
    db,
    *,
    description: str,
    entity_id: str | int | None = None,
    amount: float | Decimal | None = None,
    payment_method: str | None = None,

    # Structured notes (human-readable, single line)
    server_old: str | None = None,
    server_new: str | None = None,
    fourk_old: str | None = None,   # "Yes"/"No"
    fourk_new: str | None = None,
    length_months: int | None = None,
    old_start: str | date | datetime | None = None,
    old_end:   str | date | datetime | None = None,
    new_start: str | date | datetime | None = None,
    new_end:   str | date | datetime | None = None,

    # Optional JSON payload (machine-readable)
    details: dict | None = None,

    # Behavior flags
    attempt_json_write: bool = True,    # write JSON if column exists
    auto_create_json_col: bool = False, # try to ALTER TABLE to add details_json
) -> None:
    """
    Insert one row into `transactions`:
      - `notes` is a structured, human-readable single line.
      - If `details_json` column exists (or can be added), store `details` JSON there.
      - Will NEVER raise to caller: failures are logged and swallowed.

    Public safety:
      - On databases without `details_json`, JSON write is skipped silently
        (unless auto_create_json_col=True, which will ALTER TABLE once).
    """

    # Build the structured note line (only include provided fields)
    parts = [
        _kv("Server", server_new or server_old),
        _kv("4K", fourk_new if fourk_new is not None else fourk_old),
        _kv("Length", str(length_months) if length_months is not None else None),
        _kv("OldStart", _fmt_date(old_start)),
        _kv("OldEnd",   _fmt_date(old_end)),
        _kv("NewStart", _fmt_date(new_start)),
        _kv("NewEnd",   _fmt_date(new_end)),
    ]
    notes_line = _join_fields(parts) or description  # ensure non-empty

    # 1) Insert the base row (notes are always written)
    last_id = None
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO `{TRANSACTIONS_TABLE}`
                    (`timestamp`, description, entity_id, amount, payment_method, notes)
                VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
                """,
                (
                    description[:255],
                    str(entity_id) if entity_id is not None else None,
                    _fmt_money(amount),
                    payment_method or None,
                    notes_line,
                ),
            )
            cur.execute("SELECT LAST_INSERT_ID()")
            row = cur.fetchone()
            last_id = row[0] if row else None
        db.commit()
    except Exception as e:
        logger.exception("log_transaction: base insert failed (desc=%r, entity_id=%r): %s",
                         description, entity_id, e)
        return  # do not block calling flow

    # 2) Optionally write JSON payload
    if details and attempt_json_write and last_id:
        try:
            if ensure_details_json_column(db, auto_create=auto_create_json_col):
                payload = json.dumps(details, separators=(",", ":"), ensure_ascii=False)
                with db.cursor() as cur:
                    cur.execute(
                        f"UPDATE `{TRANSACTIONS_TABLE}` SET `{DETAILS_COL}`=%s WHERE id=%s",
                        (payload, last_id),
                    )
                db.commit()
        except Exception as e:
            logger.exception("log_transaction: JSON write skipped (id=%s): %s", last_id, e)
            # swallow — never break business logic
