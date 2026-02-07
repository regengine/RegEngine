import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add services/admin to path
sys.path.append(os.path.abspath("services/admin"))

try:
    from app.sqlalchemy_models import Base, TenantModel, UserModel, RoleModel, MembershipModel, AuditLogModel
    print("Successfully imported models.")
except ImportError as e:
    print(f"Failed to import models: {e}")
    sys.exit(1)

# Create in-memory SQLite db
engine = create_engine("sqlite:///:memory:")

try:
    Base.metadata.create_all(engine)
    print("Successfully created tables.")
except Exception as e:
    print(f"Failed to create tables: {e}")
    sys.exit(1)

print("Verification complete.")
