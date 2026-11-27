from app.modules.agent_auth.service import AgentAuth, hash_key, new_key


def test_env_key_authenticates_without_db(make_settings):
    auth = AgentAuth(make_settings(agent_api_key="k" * 32), None)
    assert auth.authenticate("k" * 32).name == "env" and auth.authenticate("k" * 32).key_id is None
    assert auth.authenticate("wrong") is None and auth.authenticate(None) is None and auth.authenticate("") is None


def test_no_keys_configured_rejects_everything(make_settings):
    assert AgentAuth(make_settings(), None).authenticate("anything") is None


def test_hash_and_new_key():
    k = new_key()
    assert k.startswith("mk_") and len(k) > 40 and new_key() != k
    assert hash_key(k) == hash_key(k) and len(hash_key(k)) == 64 and k not in hash_key(k)


def test_no_database_url_is_503_on_db_endpoint(make_settings):
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    c = TestClient(create_app(make_settings(agent_api_key="k" * 32)), raise_server_exceptions=False)
    r = c.post("/api/v1/agent/links", headers={"Authorization": "Bearer " + "k" * 32},
               json={"shop_id": 1, "item_id": 2, "post_key": "a", "page_code": "p1"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"
    assert "DATABASE_URL" in r.json()["error"]["message"]
