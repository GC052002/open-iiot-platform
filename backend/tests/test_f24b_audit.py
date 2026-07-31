"""F2.4b: audit log en el historiador SQLite."""

import pytest

from app.storage import SQLiteHistorian


async def test_audit_record_and_query(tmp_path):
    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    try:
        await repo.record_audit({"action": "login", "username": "ana", "project_id": "P"})
        await repo.record_audit({"action": "tag:write", "username": "ana", "project_id": "P",
                                 "detail": "t0", "old_value": 1, "new_value": 2})
        rows = await repo.query_audit("P")
        assert len(rows) == 2
        w = next(r for r in rows if r["action"] == "tag:write")
        assert w["old_value"] == "1" and w["new_value"] == "2" and w["username"] == "ana"
    finally:
        await repo.close()
