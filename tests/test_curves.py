import numpy as np
import pytest

from optimum.curves import ZeroCurve, implied_forward, year_fraction


@pytest.fixture
def curve():
    return ZeroCurve(
        "PEN", np.array([0, 1, 3, 5, 10, 20.0]), np.array([0.04, 0.041, 0.043, 0.047, 0.053, 0.06])
    )


def test_interp_hits_nodes(curve):
    assert np.allclose(curve.zero(curve.tenors), curve.rates)


def test_linear_between_nodes(curve):
    assert curve.zero(2.0) == pytest.approx((0.041 + 0.043) / 2)


def test_flat_extrapolation(curve):
    assert curve.zero(30.0) == pytest.approx(0.06)


def test_discount_zero_coupon_by_hand(curve):
    # 1 año, 4.1 % efectiva: DF = 1/1.041
    assert curve.discount(1.0) == pytest.approx(1 / 1.041)
    assert curve.discount(1.0, spread=0.01) == pytest.approx(1 / 1.051)


def test_forward_1y_equals_spot_1y(curve):
    """Nota del Excel: con t0 = 0, f(0,1Y) = z(1Y)."""
    assert implied_forward(curve, 1e-9, 1.0) == pytest.approx(0.041, abs=1e-6)


def test_act365():
    assert year_fraction("2025-12-31", "2026-12-31") == pytest.approx(1.0)
