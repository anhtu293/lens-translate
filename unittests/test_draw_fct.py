import os
import numpy as np
from PIL import Image, ImageFont

from lens.app.utils import draw_results


def test_draw_results():
    file_path = os.path.join(os.path.dirname(__file__), "../images/example.jpeg")
    font_path = os.path.join(os.path.dirname(__file__), "../lens/app/BeVietnam-Light.ttf")
    img_pil = Image.open(file_path)
    bboxes = [[[100, 100], [200, 200], [300, 300], [400, 400]]]
    texts = ["Hello World"]
    font = ImageFont.truetype(font_path, 16)
    result = draw_results(img_pil, bboxes, texts, font)
    assert isinstance(result, np.ndarray)
