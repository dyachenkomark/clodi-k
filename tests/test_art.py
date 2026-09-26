from clodick.desktop.art import GROUND_ROW, HOUSE, PALETTE, YARD_X


def test_house_is_rectangular_and_uses_palette():
    assert len({len(row) for row in HOUSE}) == 1
    assert {ch for row in HOUSE for ch in row} <= PALETTE.keys()


def test_yard_and_ground_inside_house_art():
    assert 0 < YARD_X < len(HOUSE[0])
    assert set(HOUSE[GROUND_ROW]) == {"L"}
