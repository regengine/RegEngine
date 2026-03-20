# DB-First Pattern Implementation Guide

Used across all 5 refactored modules in Sprint 1.

## Template Pattern

### 1. Import & DB Helper
```python
from sqlalchemy import text
import json

def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None
```

### 2. Read Pattern (Regular Tables)
For `fsma.tenant_suppliers` (row-per-record):
```python
def _db_get_suppliers(tenant_id: str) -> Optional[list[SupplierRecord]]:
    """Query suppliers from database."""
    db = _get_db()
    if not db:
        return None
    try:
        rows = db.execute(
            text("SELECT id, name, contact_email, portal_link_id, portal_status, ... FROM fsma.tenant_suppliers WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchall()
        suppliers = []
        for row in rows:
            suppliers.append(SupplierRecord(
                id=row[0],
                name=row[1],
                contact_email=row[2],
                # ... map all columns
                is_sample=False,  # Always false for DB records
            ))
        return suppliers
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()
```

### 3. Read Pattern (JSONB Tables)
For `fsma.tenant_settings` (full object as JSON):
```python
def _db_get_settings(tenant_id: str) -> Optional[SettingsResponse]:
    """Query settings from database."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text("SELECT settings_json FROM fsma.tenant_settings WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not row:
            return None
        settings_data = json.loads(row[0]) if row[0] else {}
        settings_data["tenant_id"] = tenant_id
        return SettingsResponse(**settings_data)
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()
```

### 4. Write Pattern (Regular Tables)
With ON CONFLICT upsert:
```python
def _db_add_supplier(tenant_id: str, supplier: SupplierRecord) -> bool:
    """Insert supplier into database."""
    db = _get_db()
    if not db:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO fsma.tenant_suppliers 
                (id, tenant_id, name, contact_email, portal_link_id, portal_status, ...)
                VALUES (:id, :tid, :name, :email, :plink, :pstatus, ...)
                ON CONFLICT (id) DO UPDATE SET 
                    name = :name, contact_email = :email, portal_link_id = :plink,
                    portal_status = :pstatus, ..., updated_at = now()
            """),
            {
                "id": supplier.id,
                "tid": tenant_id,
                "name": supplier.name,
                "email": supplier.contact_email,
                "plink": supplier.portal_link_id,
                "pstatus": supplier.portal_status,
                # ... all fields
            }
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()
```

### 5. Write Pattern (JSONB Tables)
ON CONFLICT on tenant_id:
```python
def _db_save_settings(tenant_id: str, settings: SettingsResponse) -> bool:
    """Insert or update settings in database."""
    db = _get_db()
    if not db:
        return False
    try:
        settings_json = json.dumps(settings.model_dump(exclude={"tenant_id"}))
        db.execute(
            text("""
                INSERT INTO fsma.tenant_settings (tenant_id, settings_json, created_at, updated_at)
                VALUES (:tid, :json, now(), now())
                ON CONFLICT (tenant_id) DO UPDATE SET settings_json = :json, updated_at = now()
            """),
            {"tid": tenant_id, "json": settings_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()
```

### 6. Endpoint Pattern (DB-First, Memory Fallback)
```python
@router.get("/{tenant_id}")
async def get_suppliers(tenant_id: str, _: None = Depends(_verify_api_key)):
    """Get suppliers."""
    # Try DB first
    suppliers = _db_get_suppliers(tenant_id)
    
    # Fall back to memory if DB unavailable
    if suppliers is None:
        if tenant_id not in _suppliers_store:
            _suppliers_store[tenant_id] = []
        suppliers = _suppliers_store[tenant_id]
    
    return {"suppliers": suppliers}
```

### 7. Update Pattern (Read → Modify → Write)
```python
@router.put("/{tenant_id}/{member_id}/role")
async def update_role(tenant_id: str, member_id: str, role: str, _: None = Depends(_verify_api_key)):
    """Update team member role."""
    # Try DB first
    members = _db_get_team(tenant_id)
    if members is None:
        members = _team_store.get(tenant_id, [])
    
    for member in members:
        if member.id == member_id:
            member.role = role
            
            # Update in DB or memory
            db_success = _db_add_team_member(tenant_id, member)
            if not db_success:
                if tenant_id in _team_store:
                    for mem in _team_store[tenant_id]:
                        if mem.id == member_id:
                            mem.role = role
            
            return {"updated": True}
    
    return {"error": "Member not found"}
```

---

## Key Points

1. **Always filter by tenant_id** — all queries include `WHERE tenant_id = :tid`
2. **Handle None from _get_db()** — DB might be unavailable in dev
3. **Set is_sample=false** on all DB-sourced records
4. **Use ON CONFLICT for upserts** — simplifies create/update logic
5. **Close db in finally block** — prevents connection leaks
6. **Try/except around all DB calls** — log warnings, return None on failure
7. **Memory fallback persists** — `_*_store` dicts keep dev mode working
8. **JSON serialization** — JSONB columns use json.dumps/json.loads
9. **Commit after writes** — don't rely on autocommit
10. **Rollback on error** — clean state for next operation

---

## Testing Strategy

For each module:
1. **DB unavailable scenario**: Confirm fallback to memory works
2. **DB available scenario**: Confirm writes persist and reads retrieve from DB
3. **Conflict handling**: Upserts don't duplicate on repeated writes
4. **Tenant isolation**: Queries filtered by tenant_id return only tenant's data
5. **Error logging**: DB errors logged, don't crash endpoints

---

## Migration Status

Depends on V042 migration which creates all fsma schema tables:
- fsma.tenant_suppliers
- fsma.tenant_team_members
- fsma.tenant_settings (JSONB)
- fsma.tenant_notification_prefs (JSONB)
- fsma.tenant_onboarding (JSONB)

All 5 modules assume these tables exist and are ready to query.
