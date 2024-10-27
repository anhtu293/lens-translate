import numpy as np
from PIL import Image, ImageDraw, ImageFont


async def draw_results(img_pil: Image.Image, bboxes: list[list[int]], texts: list[str], font: ImageFont) -> np.ndarray:
    for i in range(len(bboxes)):
        (top_left, top_right, bottom_right, bottom_left) = bboxes[i]
        top_left = (int(top_left[0]), int(top_left[1]))
        bottom_right = (int(bottom_right[0]), int(bottom_right[1]))
        text = texts[i]

        # Create a draw on the original image using the predicted bboxes
        draw = ImageDraw.Draw(img_pil)
        draw.rectangle([top_left, bottom_right], outline="gray", fill="gray")
        draw.text((top_left[0], top_left[1] - 20), text, font=font, fill="white")
        img = np.array(img_pil)

    return img
