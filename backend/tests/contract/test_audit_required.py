"""Ép bắt buộc audit_ctx: hàm service đổi tiền/dữ liệu admin KHÔNG thể được gọi mà thiếu ngữ cảnh audit, và route ghi/admin
phải có dependency tạo ngữ cảnh đó. Thêm hàm mới mà quên `@audited` thì test này đỏ."""
import inspect

import pytest

from app.main_api import create_app
from app.modules.audit.errors import InvalidAudit
from app.modules.audit.service import Actor, AuditContext, audited
from app.modules.auth.mfa_service import MfaService
from app.modules.orders.admin_service import OrphanAdmin
from app.modules.payout import api as payout_api
from app.modules.payout.service import PayoutService
from app.modules.platform_settings.service import PlatformSettings
from app.modules.wallet.money import WalletMoney

# Mọi lớp service tiền/payout: (lớp, tập hàm chỉ-đọc được miễn)
GUARDED = [(PayoutService, PayoutService.READ_ONLY), (WalletMoney, WalletMoney.READ_ONLY), (MfaService, MfaService.READ_ONLY),
           (OrphanAdmin, OrphanAdmin.READ_ONLY)]


def public_callables(cls):
    for name, member in inspect.getmembers(cls):
        if name.startswith("_") or name in ("READ_ONLY",):
            continue
        fn = member
        if inspect.isfunction(fn) or inspect.ismethod(fn):
            yield name, fn


@pytest.mark.parametrize("cls,read_only", GUARDED)
def test_every_public_mutating_function_is_audited_with_a_required_keyword(cls, read_only):
    seen = 0
    for name, fn in public_callables(cls):
        seen += 1
        if name in read_only or name == "cipher":
            continue
        assert getattr(fn, "__audited__", False), f"{cls.__name__}.{name} đổi dữ liệu nhưng thiếu @audited (hoặc thêm vào READ_ONLY nếu chỉ đọc)"
        p = inspect.signature(fn).parameters["audit"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty, f"{cls.__name__}.{name}: audit phải bắt buộc"
    assert seen >= 2


def test_read_only_lists_contain_only_real_functions():
    for cls, read_only in GUARDED:
        names = {n for n, _ in public_callables(cls)}
        assert read_only <= names, f"READ_ONLY có tên không tồn tại trong {cls.__name__}: {read_only - names}"


def test_decorator_rejects_missing_or_defaulted_audit_parameter_at_definition_time():
    with pytest.raises(TypeError):
        @audited
        def a(x): ...
    with pytest.raises(TypeError):
        @audited
        def b(x, *, audit=None): ...                           # có mặc định: cấm
    with pytest.raises(TypeError):
        @audited
        def c(x, audit): ...                                   # không phải keyword-only: cấm


def test_calling_without_a_real_audit_context_fails_at_runtime(make_settings):
    @audited
    def act(x, *, audit): return x

    ctx = AuditContext(make_settings(), Actor(1, "admin"), None)
    assert act(1, audit=ctx) == 1
    for bad in (None, {"actor": 1}, "admin"):
        with pytest.raises(InvalidAudit):
            act(1, audit=bad)
    with pytest.raises(InvalidAudit):
        act(1)
    svc = PayoutService.__new__(PayoutService)
    with pytest.raises(InvalidAudit):
        svc.approve(1, audit=None)
    with pytest.raises(InvalidAudit):
        WalletMoney.hold(None, 1, 1, 100, audit=None)


def test_platform_settings_set_int_accepts_audit_ctx_keyword_only():
    p = inspect.signature(PlatformSettings.set_int).parameters["audit_ctx"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY


def all_routes(router):
    """FastAPI mới gói router con thành `_IncludedRouter` (lười): duỗi ra qua `original_router`."""
    for r in router.routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from all_routes(inner)
        else:
            yield r


def _deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _deps(d)


# Route admin CHỈ-ĐỌC không lộ dữ liệu nhạy cảm được miễn audit (vẫn bắt buộc require_admin). Thêm route khác vào đây là quyết định có chủ ý.
ADMIN_READ_ONLY_PATHS = {"/api/v1/admin/withdrawals", "/api/v1/admin/orphans"}


def test_every_write_or_admin_route_has_the_required_dependencies(make_settings):
    from app.modules.auth.api import require_admin
    app = create_app(make_settings())
    checked = 0
    for r in all_routes(app):
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", set()) or set()
        is_admin = path.startswith("/api/v1/admin/")
        is_money_write = path.startswith(("/api/v1/me/withdrawals", "/api/v1/me/bank-accounts")) and (methods - {"GET", "HEAD", "OPTIONS"})
        if not (is_admin or is_money_write):
            continue
        calls = set(_deps(r.dependant))
        if is_admin:
            assert require_admin in calls, f"{path}: route admin phải có require_admin (staff không đủ)"
            if path not in ADMIN_READ_ONLY_PATHS:
                assert payout_api.admin_audit_context in calls, f"{path}: route admin phải dùng admin_audit_context"
        else:
            assert payout_api.audit_context in calls, f"{sorted(methods)} {path} thiếu dependency audit_context"
        checked += 1
    assert checked >= 8                                        # 7 route admin + 2 route ghi của người dùng
