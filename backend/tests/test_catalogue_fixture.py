from app.inventory import ACTIVITIES, HOTELS, SUPPLIERS


def test_tests_run_on_the_small_fixed_catalogue():
    assert len(SUPPLIERS) == 5
    assert len(HOTELS) == 8
    assert len(ACTIVITIES) == 10
    assert {h["destination"] for h in HOTELS.values()} == {"Goa", "Jaipur"}