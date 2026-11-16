import pytest

from backend.app.results import status_for


@pytest.mark.parametrize("code,valid,pages,killed,expected", [
    (0, True, 1, None, "success"),
    (0, True, 0, None, "failed"),
    (0, False, 2, None, "failed"),
    (10, True, 2, None, "partial"),
    (10, False, 2, None, "failed"),
    (2, True, 1, None, "failed"),
    (3, True, 1, None, "failed"),
    (4, False, 0, None, "failed"),
    (5, True, 0, None, "failed"),
    (1, False, 0, None, "failed"),
    (-15, True, 2, "cancelled", "partial"),
    (0, True, 1, "cancelled", "partial"),
    (-9, False, 0, "timeout", "failed"),
])
def test_status_rules(code, valid, pages, killed, expected):
    assert status_for(code, valid, pages, killed) == expected
