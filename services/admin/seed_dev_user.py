
import sys
import os
from sqlalchemy import select
from app.database import SessionLocal
from app.sqlalchemy_models import UserModel, TenantModel, RoleModel, MembershipModel
from app.auth_utils import get_password_hash

def seed_admin():
    db = SessionLocal()
    try:
        print("Checking for existing admin user...")
        user = db.execute(select(UserModel).where(UserModel.email == "admin@example.com")).scalars().first()
        if user:
            print("Admin user already exists.")
            return

        print("Creating Admin Tenant...")
        tenant = db.execute(select(TenantModel).where(TenantModel.slug == "admin-tenant")).scalars().first()
        if not tenant:
            tenant = TenantModel(name="Admin Tenant", slug="admin-tenant")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        
        print("Creating Owner Role...")
        role = db.execute(select(RoleModel).where(RoleModel.name == "Owner", RoleModel.tenant_id.is_(None))).scalars().first()
        if not role:
            role = RoleModel(name="Owner", permissions=["*"], tenant_id=None)
            db.add(role)
            db.commit()
            db.refresh(role)

        print("Creating Admin User...")
        user = UserModel(
            email="admin@example.com",
            password_hash=get_password_hash("password"),
            is_sysadmin=True,
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print("Creating Membership...")
        membership = MembershipModel(
            user_id=user.id,
            tenant_id=tenant.id,
            role_id=role.id,
            is_active=True
        )
        db.add(membership)
        db.commit()
        
        print("Seeding complete. admin@example.com / password created.")
        
    except Exception as e:
        print(f"Error seeding DB: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
