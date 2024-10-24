from fastapi import FastAPI, UploadFile
import requests
import cv2
import os
from PIL import ImageFont
import numpy as np
from .utils import draw_results

app = FastAPI()


@app.post("/lens")
async def lens(file: UploadFile) -> bytes:
    data = await file.read()

    # OCR
    ocr_result = await requests.post("http://ocr-app:5000/ocr", files={"file": file})

    # Translation
    translation_result = await requests.post(
        "http://translation-app:9000/translate", texts=ocr_result["texts"]
    )

    # find suitable font size
    bboxes_heights = [bbox[3] - bbox[0] for bbox in ocr_result["bboxes"]]
    font_size = int(np.median(bboxes_heights)) - 5

    # Lens
    fontpath = os.path.join(os.path.dirname(__file__), "./BeVietnam-Light.ttf")
    font = ImageFont.truetype(fontpath, font_size)
    lens_result = draw_results(data, ocr_result["bboxes"], translation_result, font)

    # Encode to bytes
    buffer = cv2.imencode(".jpg", lens_result)[1].tobytes()
    return buffer
