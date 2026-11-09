"""The platform fee: seeded from settings, changed only by an admin, never
above the maximum, every change audited."""

import psycopg

from config import settings
from tests.conftest import make_user


def test_only_admins_reach_the_platform_settings(client):
    assert client.get("/api/v1/admin/platform").status_code == 403
    assert client.patch("/api/v1/admin/platform/fee", json={"fee_bps": 100}).status_code == 403


def test_the_first_read_seeds_the_fee_from_settings(client):
    client.sign_in(make_user("Admin", admin=True))
    platform = client.get("/api/v1/admin/platform").json()
    assert (platform["fee_bps"], platform["max_fee_bps"]) == (settings.platform_fee_bps, settings.platform_fee_max_bps)
    assert platform["fee_account"] == settings.near_mainnet_platform_treasury_wallet_address


def test_an_admin_changes_the_fee_and_it_is_audited(client):
    admin = make_user("Admin", admin=True)
    client.sign_in(admin)
    assert client.patch("/api/v1/admin/platform/fee", json={"fee_bps": 350}).json()["fee_bps"] == 350
    with psycopg.connect(settings.database_url) as conn:
        actor, action, before, after = conn.execute(
            "SELECT actor_id, action, before, after FROM admin_audit_log").fetchone()
    assert (actor, action) == (admin.id, "platform.set_fee")
    assert (before["fee_bps"], after["fee_bps"]) == (settings.platform_fee_bps, 350)


def test_the_fee_never_goes_above_the_maximum(client):
    client.sign_in(make_user("Admin", admin=True))
    response = client.patch("/api/v1/admin/platform/fee", json={"fee_bps": settings.platform_fee_max_bps + 1})
    assert response.status_code == 422
    assert client.get("/api/v1/admin/platform").json()["fee_bps"] == settings.platform_fee_bps


def test_me_says_whether_the_user_is_an_admin(client, user):
    assert client.get("/api/v1/me").json() == {"id": str(user.id), "email": user.email, "name": user.name,
                                                "is_admin": False}
