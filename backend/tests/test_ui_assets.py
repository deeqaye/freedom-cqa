import re

from fastapi.testclient import TestClient

from app.main import app


def test_index_points_at_content_versioned_assets():
    with TestClient(app) as c:
        r = c.get("/ui/")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
        v = re.search(r'src="v/([0-9a-f]{12})/js/app.js"', r.text).group(1)
        assert f'href="v/{v}/css/app.css"' in r.text
        for path in ("js/app.js", "js/views/help.js", "css/app.css"):
            a = c.get(f"/ui/v/{v}/{path}")
            assert a.status_code == 200 and "immutable" in a.headers["cache-control"], path
        assert c.get("/ui/js/app.js").headers["cache-control"] == "no-cache"  # old unversioned path still works
