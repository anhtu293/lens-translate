import numpy as np
from PIL import Image, ImageDraw, ImageFont
import textwrap


async def draw_results(img_pil: Image.Image, bboxes: list[list[int]], texts: list[str], font: ImageFont) -> np.ndarray:
    current_y = 0
    draw = ImageDraw.Draw(img_pil)
    for i in range(len(bboxes)):
        (top_left, top_right, bottom_right, bottom_left) = bboxes[i]
        top_left = [int(top_left[0]), int(top_left[1])]
        bottom_right = [int(bottom_right[0]), int(bottom_right[1])]
        width = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        top_left[1] = max(top_left[1], current_y)
        bottom_right[1] = max(top_left[1] + height, current_y + height)
        top_left = tuple(top_left)
        bottom_right = tuple(bottom_right)
        text = texts[i]

        # Calculate max characters per line based on rectangle width
        avg_char_width = font.getsize('x')[0]  # Get average character width
        chars_per_line = max(1, int(width / avg_char_width))

        # Wrap text to fit rectangle width
        wrapped_text = textwrap.fill(text, width=chars_per_line)

        # Create a draw on the original image using the predicted bboxes
        draw.rectangle([top_left, bottom_right], outline="gray", fill="gray")
        y = top_left[1] + 5
        for line in wrapped_text.split('\n'):
            draw.text((top_left[0] + 5, y), line, font=font, fill="white")
            # Move to next line by adding line height
            y += font.getsize(line)[1]
        current_y = y
    img = np.array(img_pil)
    return img
