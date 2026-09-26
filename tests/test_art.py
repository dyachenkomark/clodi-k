import pytest

from clodick.desktop.art import HOUSE, PALETTE, RACCOON


def all_frames():
    for mode, frames in RACCOON.items():
        for index, frame in enumerate(frames):
            yield f"{mode}[{index}]", frame
    yield "house", HOUSE


@pytest.mark.parametrize(("name", "rows"), list(all_frames()))
def test_frame_is_rectangular_and_uses_palette(name, rows):
    widths = {len(row) for row in rows}
    assert len(widths) == 1, f"{name}: строки разной длины {widths}"
    unknown = {ch for row in rows for ch in row} - PALETTE.keys()
    assert not unknown, f"{name}: неизвестные цвета {unknown}"


def test_raccoon_frames_same_size():
    sizes = {(len(f[0]), len(f)) for frames in RACCOON.values() for f in frames}
    assert len(sizes) == 1
