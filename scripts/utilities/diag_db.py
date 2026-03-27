import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ADMIN_DATABASE_URL = "postgresql://regengine:regengine@localhost:5433/regengine_admin"
engine = create_engine(ADMIN_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def test_insert():
    db = SessionLocal()
    # SECURITY: set_admin_context(true) sets the session variable, but RLS bypass
    # only works if connected as the 'regengine_sysadmin' role. With the standard
    # 'regengine' role, this call is a no-op for bypass purposes.
    # For full sysadmin access, use ADMIN_DATABASE_URL with regengine_sysadmin credentials.
    db.execute(text("SELECT set_admin_context(true)"))
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@example.com"
    print(f"Inserting user {user_id} with email {email}")
    
    # Use raw SQL to avoid model dependency issues for this diagnostic
    db.execute(text("INSERT INTO users (id, email, password_hash, status, is_sysadmin) VALUES (:id, :email, :pw, :status, :is_sysadmin)"),
               {"id": user_id, "email": email, "pw": "hash", "status": "active", "is_sysadmin": True})
    db.commit()
    db.close()
    print("Done")

if __name__ == "__main__":
    test_insert()
