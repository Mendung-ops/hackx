from datetime import datetime, timedelta

import pytest

from app.services.energy_service import co2_kg, integrate

T0 = datetime(2026, 10, 19, 8, 0, 0)
H = timedelta(hours=1)


def test_tanpa_perintah_pakai_state_sekarang_menyala():
    assert integrate([], True, T0, T0 + 3 * H) == pytest.approx((3, 0))


def test_tanpa_perintah_pakai_state_sekarang_mati():
    assert integrate([], False, T0, T0 + 3 * H) == pytest.approx((0, 0))


def test_rule_turn_off_menghitung_penghematan():
    events = [(T0, False, True)]
    assert integrate(events, False, T0 - H, T0 + 2 * H) == pytest.approx((1, 2))


def test_manual_turn_off_bukan_penghematan():
    events = [(T0, False, False)]
    assert integrate(events, False, T0 - H, T0 + 2 * H) == pytest.approx((1, 0))


def test_rule_off_lalu_manual_on_menghentikan_penghematan():
    events = [(T0, False, True), (T0 + H, True, False)]
    assert integrate(events, True, T0 - H, T0 + 3 * H) == pytest.approx((3, 1))


def test_perintah_sebelum_jendela_tetap_dihitung():
    events = [(T0 - 2 * H, False, True)]
    assert integrate(events, False, T0 - H, T0) == pytest.approx((0, 1))


def test_jendela_tidak_valid_nol():
    assert integrate([], True, T0, T0) == (0.0, 0.0)


def test_co2_memakai_faktor_emisi():
    assert co2_kg(10, factor=0.87) == pytest.approx(8.7)
