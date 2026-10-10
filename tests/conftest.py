"""
Pytest fixtures for TrustCheck test suite.
Uses an isolated in-memory SQLite database.
"""
import os

# Ensure tests run against isolated in-memory SQLite and never connect to remote databases
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.db import Base, get_db
from app.main import app
from app.models import SellerProfile, SellerReferralCode, User

# In-memory SQLite test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Create fresh tables for every test function."""
    import app.models  # ensure models registered
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with DB override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session):
    """Create a default test user with profile and referral code."""
    user = User(
        email="test_seller@trustcheck.com",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    profile = SellerProfile(
        user_id=user.id,
        business_name="Test Crafts Co",
        contact_name="Aarav Sharma",
        upi_id="testcrafts@okhdfcbank",
    )
    db_session.add(profile)

    ref_code = SellerReferralCode(
        seller_id=user.id,
        code="SL-7K9M-4Q2X",
    )
    db_session.add(ref_code)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user):
    """Valid JWT Bearer token headers for test_user."""
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}
