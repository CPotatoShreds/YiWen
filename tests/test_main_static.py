"""静态托管与 SPA 回退：文件工作全部委托 StaticFiles，回退层不解析文件路径。

回归背景：旧版 catch-all 自写「URL 拼路径 + is_file」判断，%2e%2e 穿越可读 static/ 外
任意文件（同类业内事故：Apache CVE-2021-41773、starlette StaticFiles CVE-2023-29159）。
现架构下越界防护由 StaticFiles（realpath + commonpath）负责；本测试用手工构造的 ASGI
scope 直接驱动 SPAStaticFiles（绕开测试客户端对 URL 的规范化），验证：
1) 正常文件服务；2) 穿越请求 404（双层防护 + 回退白名单）；3) 回退只对前端路由形态生效。
"""
import asyncio
from pathlib import Path

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app import main as app_main
from app.main import SPAStaticFiles

FALLBACK_HTML = "<html>SPA</html>"


@pytest.fixture()
def spa(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "secret.txt").write_text("secret", encoding="utf-8")
    (static / "index.html").write_text(FALLBACK_HTML, encoding="utf-8")
    # 回退层读取 app.main.INDEX_HTML 模块全局；测试环境无镜像内 static，注入测试值（测后自动还原）。
    # dev 环境本无 static/index.html，该全局尚不存在，故 raising=False 允许新建。
    monkeypatch.setattr(app_main, "INDEX_HTML", FALLBACK_HTML, raising=False)
    return SPAStaticFiles(directory=str(static), html=True)


def _scope(path: str, method: str = "GET") -> dict:
    return {"type": "http", "method": method, "path": path, "headers": []}


def _serve(spa: SPAStaticFiles, scope: dict) -> Response:
    """以 StaticFiles.__call__ 的同等路径计算驱动 get_response，返回响应对象。"""
    return asyncio.run(spa.get_response(spa.get_path(scope), scope))


def test_serves_real_file(spa):
    resp = _serve(spa, _scope("/app.js"))
    assert resp.status_code == 200


def test_client_route_falls_back_to_index_html(spa):
    resp = _serve(spa, _scope("/scenarios/123"))
    assert resp.status_code == 200
    assert FALLBACK_HTML.encode() in resp.body


def test_root_serves_index_html(spa):
    """html=True 模式下 / 直接命中磁盘上的 index.html（FileResponse，支持 ETag/304）。"""
    resp = _serve(spa, _scope("/"))
    assert resp.status_code == 200


def test_missing_asset_with_extension_returns_404(spa):
    with pytest.raises(StarletteHTTPException) as exc:
        _serve(spa, _scope("/assets/nope.js"))
    assert exc.value.status_code == 404


def test_parent_traversal_blocked(spa):
    """../ 穿越双层防护：StaticFiles 拒绝 + 回退白名单拒绝，一律 404。

    scope["path"] 是服务器解码后的路径（%2f 到达时已是 /），故按解码形态构造；
    双重编码变体（%252e%252e → 字面 %2e%2e）由白名单的扩展名检查兜住。
    """
    for path in ("/../secret.txt", "/%2e%2e/secret.txt"):
        with pytest.raises(StarletteHTTPException) as exc:
            _serve(spa, _scope(path))
        assert exc.value.status_code == 404


def test_backslash_traversal_blocked(spa):
    """%5C 解码出的反斜杠路径：白名单拒绝；Windows 上 StaticFiles 亦拒绝。"""
    with pytest.raises(StarletteHTTPException) as exc:
        _serve(spa, _scope("/..\\secret.txt"))
    assert exc.value.status_code == 404


def test_api_unknown_path_keeps_json_404(spa):
    """未匹配的 /api/** 不得回退成 HTML 200。"""
    with pytest.raises(StarletteHTTPException) as exc:
        _serve(spa, _scope("/api/unknown"))
    assert exc.value.status_code == 404


def test_wrong_method_returns_405(spa):
    with pytest.raises(StarletteHTTPException) as exc:
        _serve(spa, _scope("/scenarios/123", method="POST"))
    assert exc.value.status_code == 405


def test_fallback_policy_rejects_suspicious_shapes(spa):
    """回退白名单本身的单元断言：畸形形态一律不算前端路由。"""
    assert spa._is_client_route(_scope("/scenarios/123")) is True
    assert spa._is_client_route(_scope("/")) is True
    assert spa._is_client_route(_scope("/api/scenarios/1")) is False
    assert spa._is_client_route(_scope("/../secret.txt")) is False
    assert spa._is_client_route(_scope("/a/./b")) is False
    assert spa._is_client_route(_scope("/a\\b")) is False
    assert spa._is_client_route(_scope("/assets/app.js")) is False
