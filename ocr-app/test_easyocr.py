from PIL import Image, ImageDraw, ImageFont
import easyocr
import os
import numpy as np
import cv2

model_dir = os.path.join(os.path.dirname(__file__), "models")
img_path = os.path.join(os.path.dirname(__file__), "../images/example.jpeg")
reader = easyocr.Reader(
    ["en"],
    model_storage_directory=model_dir,
    detect_network="craft",
)
detection = reader.readtext(img_path)

# if OCR prob is over 0.5, overlay bounding box and text
fontpath = os.path.join(os.path.dirname(__file__), "./BeVietnam-Light.ttf")
font = ImageFont.truetype(fontpath, 40)

img = cv2.imread(img_path)

for bbox, text, prob in detection:
    if prob >= 0.5:
        # display
        print(f"Detected text: {text} (Probability: {prob:.2f})")
        # get top-left and bottom-right bbox vertices
        (top_left, top_right, bottom_right, bottom_left) = bbox
        top_left = (int(top_left[0]), int(top_left[1]))
        bottom_right = (int(bottom_right[0]), int(bottom_right[1]))

        # Create a draw on the original image using the predicted bboxes
        img_pil = Image.fromarray(img)
        draw = ImageDraw.Draw(img_pil)
        draw.rectangle([top_left, bottom_right], outline="gray", fill="gray")
        draw.text((top_left[0], top_left[1] - 20), text, font=font, fill="white")
        img = np.array(img_pil)

cv2.imwrite(
    os.path.join(
        os.path.dirname(__file__), f"{os.path.basename(img_path)}_overlay.jpg"
    ),
    img,
)
