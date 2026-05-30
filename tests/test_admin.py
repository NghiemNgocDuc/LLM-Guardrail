import pytest
from fastapi import HTTPException

from app.routers.admin import require_org_admin


class FakeUser:
    def __init__(self, is_admin=True, org_id="org-1"):
        self.is_admin = is_admin
        self.org_id = org_id


def test_require_org_admin_allows_org_admin():
    require_org_admin(FakeUser())


def test_require_org_admin_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        require_org_admin(FakeUser(is_admin=False))

    assert exc.value.status_code == 403


def test_require_org_admin_rejects_user_without_org():
    with pytest.raises(HTTPException) as exc:
        require_org_admin(FakeUser(org_id=None))

    assert exc.value.status_code == 403
