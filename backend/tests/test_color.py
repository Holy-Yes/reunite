import numpy as np
import pytest

from app import taxonomy
from app.ml.vision import color


def test_ciede2000_reference_pairs():
    # Sharma, Wu and Dalal (2005), supplementary test data
    cases = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ]
    for a, b, expected in cases:
        assert float(color.ciede2000(np.array(a), np.array(b))) == pytest.approx(expected, abs=1e-3)


def test_ciede2000_is_zero_for_identical():
    lab = np.array([[40.0, 10.0, -20.0]])
    assert float(color.ciede2000(lab, lab)[0]) == pytest.approx(0.0, abs=1e-9)


def test_every_palette_color_names_itself():
    for name, spec in taxonomy.palette().items():
        lab = color.rgb_to_lab(np.array([color.hex_to_rgb(spec["hex"])], dtype=np.float32))[0]
        got, de = color.name_color(lab)
        assert got == name and de < 0.5


def test_palette_has_the_17_colors():
    assert len(taxonomy.palette()) == 17


def test_solid_image_names_its_color():
    for rgb, name in (((200, 50, 43), "red"), ((30, 30, 32), "black"), ((62, 142, 82), "green")):
        img = np.full((120, 160, 3), rgb, dtype=np.uint8)
        out = color.dominant_colors(img)
        assert out[0]["name"] == name


def test_two_color_object_gives_two_colors():
    img = np.zeros((160, 160, 3), dtype=np.uint8)
    img[:] = (244, 244, 242)  # near-white background
    img[30:130, 30:80] = (200, 50, 43)   # red half
    img[30:130, 80:130] = (31, 47, 85)   # navy half
    names = {c["name"] for c in color.dominant_colors(img)}
    assert {"red", "navy"} <= names or len(names) == 2
    assert len(color.dominant_colors(img)) <= 2


def test_delta_e_between_palette_colors_orders_sensibly():
    assert color.palette_delta_e("black", "navy") < color.palette_delta_e("black", "yellow")
