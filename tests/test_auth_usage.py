import os
import importlib
from pathlib import Path

def test_password_hash_roundtrip():
    from app.security import hash_password, verify_password
    encoded = hash_password("a-very-good-password")
    assert "a-very-good-password" not in encoded
    assert verify_password("a-very-good-password", encoded)
    assert not verify_password("wrong-password", encoded)

def test_plan_limits_present():
    from app.config import PLAN_LIMITS
    assert PLAN_LIMITS["free"] < PLAN_LIMITS["starter"] < PLAN_LIMITS["growth"]

def test_integration_interfaces_import():
    from app.integrations.base import CRMAdapter, IdentityProviderAdapter, LeadSourceAdapter
    assert CRMAdapter
    assert IdentityProviderAdapter
    assert LeadSourceAdapter
