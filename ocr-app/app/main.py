import easyocr
import os
from PIL import Image
import imagehash
from collections import OrderedDict
from io import BytesIO
import numpy as np
import pika
import json
from loguru import logger
import base64

CACHE_SIZE = 100
cache = OrderedDict()

credentials = pika.PlainCredentials("user", "password")
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="rabbitmq", credentials=credentials, heartbeat=6000)
)
channel = queue_connection.channel()
channel.queue_declare(queue="ocr_tasks", durable=True)
channel.queue_declare(queue="ocr_results", durable=True)

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
    task = json.loads(body)
    logger.info(f"Processing image: {task['task_id']}")
    image = Image.open(BytesIO(base64.b64decode(task["data"].encode("utf-8"))))
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

    channel.basic_publish(
        exchange="",
        routing_key="ocr_results",
        body=json.dumps({"task_id": task["task_id"], "result": result}),
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_consume(queue="ocr_tasks", on_message_callback=process_ocr_task)

logger.info("Waiting for OCR tasks...")
channel.start_consuming()
