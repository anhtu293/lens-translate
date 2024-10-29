import easyocr
import os
from PIL import Image
import imagehash
from collections import OrderedDict
from io import BytesIO
import pika
import json
from loguru import logger
import base64
import numpy as np
from .utils import get_sentence


RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
CACHE_SIZE = 100
cache = OrderedDict()

credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials, heartbeat=6000)
)
channel = queue_connection.channel()
logger.info("OCR channel initialized")


# Load model
model_dir = os.path.join(os.path.dirname(__file__), "models")
reader = easyocr.Reader(
    ["en"],
    model_storage_directory=model_dir,
    detect_network="craft",
    gpu=False,
)
logger.info("OCR model loaded")


def process_ocr_task(ch, method, properties, body):
    try:
        task = json.loads(body)
        logger.info(f"Processing image: {task['task_id']}")
        image = Image.open(BytesIO(base64.b64decode(task["data"].encode("utf-8"))))
        image_hash = imagehash.average_hash(image)

        if image_hash in cache:
            return cache[image_hash]

        detection = reader.readtext(image)

        # Get median height of bboxes
        bboxes_heights = []
        for bbox, text, prob in detection:
            (top_left, _, bottom_right, _) = bbox
            bboxes_heights.append(bottom_right[1] - top_left[1])
        bbox_height = int(np.median(bboxes_heights))

        # Create the final result
        result = get_sentence(detection)

        bboxes = [box[0] for box in result]
        texts = [box[1] for box in result]
        result = {"bboxes": bboxes, "texts": texts, "bbox_height": bbox_height}

        if len(cache) >= CACHE_SIZE:
            cache.popitem(last=False)
        cache[image_hash] = result

        channel.basic_publish(
            exchange="",
            routing_key="ocr_results",
            body=json.dumps({"task_id": task["task_id"], "result": result}),
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing OCR task: {e}")
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)


channel.basic_consume(queue="ocr_tasks", on_message_callback=process_ocr_task)
logger.info("Waiting for OCR tasks...")
channel.start_consuming()
