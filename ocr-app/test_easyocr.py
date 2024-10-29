from PIL import Image, ImageDraw, ImageFont
import easyocr
import os
import numpy as np
import cv2
import textwrap


def get_sentence(raw_result, x_ths=1, y_ths=0.5, mode="ltr"):
    # create basic attributes
    box_group = []
    for box in raw_result:
        all_x = [int(coord[0]) for coord in box[0]]
        all_y = [int(coord[1]) for coord in box[0]]
        min_x = min(all_x)
        max_x = max(all_x)
        min_y = min(all_y)
        max_y = max(all_y)
        height = max_y - min_y
        # last element indicates group
        box_group.append([box[1], min_x, max_x, min_y, max_y, height, 0.5 * (min_y + max_y), 0])

    # arrage order in paragraph
    arranged_result = []
    mean_height = np.mean([box[5] for box in box_group])
    min_gx = min([box[1] for box in box_group])
    max_gx = max([box[2] for box in box_group])
    min_gy = min([box[3] for box in box_group])
    max_gy = max([box[4] for box in box_group])

    while len(box_group) > 0:
        highest = min([box[6] for box in box_group])
        candidates = [box for box in box_group if box[6] < highest + 0.4 * mean_height]
        # get the far left
        if mode == "ltr":
            most_left = min([box[1] for box in candidates])
            for box in candidates:
                if box[1] == most_left:
                    best_box = box
        elif mode == "rtl":
            most_right = max([box[2] for box in candidates])
            for box in candidates:
                if box[2] == most_right:
                    best_box = box
        arranged_result.append(best_box)
        box_group.remove(best_box)

    # cluster boxes into paragraph
    current_group = 1
    while len([box for box in arranged_result if box[7] == 0]) > 0:
        box_group0 = [box for box in arranged_result if box[7] == 0]  # group0 = non-group
        # new group
        if len([box for box in arranged_result if box[7] == current_group]) == 0:
            box_group0[0][7] = current_group  # assign first box to form new group
        # try to add group
        else:
            current_box_group = [box for box in arranged_result if box[7] == current_group]
            mean_height = np.mean([box[5] for box in current_box_group])
            min_gx = min([box[1] for box in current_box_group]) - x_ths * mean_height
            max_gx = max([box[2] for box in current_box_group]) + x_ths * mean_height
            min_gy = min([box[3] for box in current_box_group]) - y_ths * mean_height
            max_gy = max([box[4] for box in current_box_group]) + y_ths * mean_height
            add_box = False
            for box in box_group0:
                same_horizontal_level = (min_gx <= box[1] <= max_gx) or (
                    min_gx <= box[2] <= max_gx
                )
                same_vertical_level = (min_gy <= box[3] <= max_gy) or (
                    min_gy <= box[4] <= max_gy
                )
                has_delimiter = box[0][-1] in [".", "!", "?", ":"]
                if same_horizontal_level and same_vertical_level:
                    box[7] = current_group
                    add_box = True
                    break
            # cannot add more box, go to next group
            if not add_box or has_delimiter:
                current_group += 1

    result = []
    for i in set(box[7] for box in arranged_result):
        current_box_group = [box for box in arranged_result if box[7] == i]
        mean_height = np.mean([box[5] for box in current_box_group])
        min_gx = min([box[1] for box in current_box_group])
        max_gx = max([box[2] for box in current_box_group])
        min_gy = min([box[3] for box in current_box_group])
        max_gy = max([box[4] for box in current_box_group])

        text = ""
        for box in current_box_group:
            text += " " + box[0]

        result.append([[[min_gx, min_gy], [max_gx, min_gy], [max_gx, max_gy], [min_gx, max_gy]], text[1:]])

    return result


model_dir = os.path.join(os.path.dirname(__file__), "models")
img_path = os.path.join(os.path.dirname(__file__), "../images/example.jpeg")
reader = easyocr.Reader(
    ["en"],
    model_storage_directory=model_dir,
    detect_network="craft",
    gpu=False,
)
detection = reader.readtext(img_path, decoder="wordbeamsearch")


sentences = get_sentence(detection)

# print(detection[1])
# if OCR prob is over 0.5, overlay bounding box and text
fontpath = os.path.join(os.path.dirname(__file__), "./BeVietnam-Light.ttf")

bboxes_heights = []
for bbox, text, prob in detection:
    (top_left, top_right, bottom_right, bottom_left) = bbox
    bboxes_heights.append(bottom_right[1] - top_left[1])
font_size = int(np.median(bboxes_heights) / 1.5)

print(font_size)
font = ImageFont.truetype(fontpath, font_size)

img = cv2.imread(img_path)

current_y = 0
# Create a draw on the original image using the predicted bboxes
img_pil = Image.fromarray(img)
draw = ImageDraw.Draw(img_pil)

for bbox, text in sentences:
    # if prob >= 0.5:
    # display
    print(f"Detected text: {text} (Probability: {prob:.2f})")
    # get top-left and bottom-right bbox vertices
    (top_left, top_right, bottom_right, bottom_left) = bbox
    top_left = [int(top_left[0]), int(top_left[1])]
    bottom_right = [int(bottom_right[0]), int(bottom_right[1])]
    width = bottom_right[0] - top_left[0]
    height = bottom_right[1] - top_left[1]

    top_left[1] = max(top_left[1], current_y)
    bottom_right[1] = max(top_left[1] + height, current_y + height)
    top_left = tuple(top_left)
    bottom_right = tuple(bottom_right)

    # Calculate max characters per line based on rectangle width
    avg_char_width = font.getsize('x')[0]  # Get average character width
    chars_per_line = max(1, int(width / avg_char_width))

    # Wrap text to fit rectangle width
    wrapped_text = textwrap.fill(text, width=chars_per_line)

    # Draw rectangle
    print(top_left, bottom_right)
    draw.rectangle([top_left, bottom_right], outline="gray", fill="gray")

    # Draw wrapped text
    y = top_left[1] + 5  # Add small padding from top
    for line in wrapped_text.split('\n'):
        draw.text((top_left[0] + 5, y), line, font=font, fill="white")
        y += font.getsize(line)[1]  # Move to next line by adding line height
    current_y = y

img = np.array(img_pil)

cv2.imwrite(
    os.path.join(
        os.path.dirname(__file__), f"{os.path.basename(img_path)}_overlay.jpg"
    ),
    img,
)
