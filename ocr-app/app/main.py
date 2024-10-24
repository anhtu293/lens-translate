from fastapi import FastAPI, UploadFile
import easyocr
import os
from PIL import Image
import imagehash
from collections import OrderedDict
from io import BytesIO
import numpy as np


CACHE_SIZE = 100
cache = OrderedDict()
app = FastAPI()

# Load model
model_dir = os.path.join(os.path.dirname(__file__), "models")
reader = easyocr.Reader(
    ["en"],
    model_storage_directory=model_dir,
    detect_network="craft",
)


@app.post("/ocr")
async def ocr(file: UploadFile) -> dict[str, list]:
    data = await file.read()
    image = Image.open(BytesIO(data))
    image_hash = imagehash.average_hash(image)

    if image_hash in cache:
        return cache[image_hash]

    detection = reader.readtext(image)

    # Create the final result
    result = {"bboxes": [], "texts": []}
    for bbox, text, prob in detection:
        if prob >= 0.5:
            bbox = np.array(bbox).tolist()
            result["bboxes"].append(bbox)
            result["texts"].append(text)

    if len(cache) >= CACHE_SIZE:
        cache.popitem(last=False)
    cache[image_hash] = result

    return result
