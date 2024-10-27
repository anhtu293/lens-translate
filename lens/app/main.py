from fastapi import FastAPI, WebSocket, BackgroundTasks
import cv2
import os
import asyncio
from PIL import Image, ImageFont
import numpy as np
from io import BytesIO
from .utils import draw_results
import pika
import json
import uuid
import base64
from loguru import logger

credentials = pika.PlainCredentials("user", "password")
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="rabbitmq", credentials=credentials, heartbeat=6000)
)
logger.info("Connected to RabbitMQ")
channel = queue_connection.channel()
channel.queue_declare(queue="ocr_tasks", durable=True)
channel.queue_declare(queue="ocr_results", durable=True)
channel.queue_declare(queue="translation_tasks", durable=True)
channel.queue_declare(queue="translation_results", durable=True)

app = FastAPI()

task_results = {}
websocket_connections = {}
background_tasks = BackgroundTasks()


async def process_image(data: bytes, task_id: str) -> None:
    # Wait for OCR result
    logger.info("Sending OCR task")
    channel.basic_publish(
        exchange="",
        routing_key="ocr_tasks",
        body=json.dumps({"task_id": task_id, "data": base64.b64encode(data).decode("utf-8")}),
    )

    # Wait for OCR result
    logger.info("Waiting for OCR result")
    while True:
        method_frame, _, body = channel.basic_get("ocr_results")
        if method_frame:
            ocr_result = json.loads(body)
            if ocr_result["task_id"] == task_id:
                ocr_result = ocr_result["result"]
                channel.basic_ack(method_frame.delivery_tag)
                break
        else:
            await asyncio.sleep(1)

    # Translation
    logger.info("Sending translation task")
    channel.basic_publish(
        exchange="",
        routing_key="translation_tasks",
        body=json.dumps({"task_id": task_id, "texts": ocr_result["texts"]}),
    )

    # Wait for translation result
    logger.info("Waiting for translation result")
    while True:
        method_frame, _, body = channel.basic_get("translation_results")
        if method_frame:
            translation_result = json.loads(body)
            if translation_result["task_id"] == task_id:
                translation_result = translation_result["result"]
                channel.basic_ack(method_frame.delivery_tag)
                break
        else:
            await asyncio.sleep(1)

    # find suitable font size
    ocr_result["bboxes"] = np.array(ocr_result["bboxes"])
    logger.info("Formatting results")
    bboxes_heights = [bbox[3] - bbox[0] for bbox in ocr_result["bboxes"]]
    font_size = int(np.median(bboxes_heights)) - 5

    # Lens
    fontpath = os.path.join(os.path.dirname(__file__), "./BeVietnam-Light.ttf")
    font = ImageFont.truetype(fontpath, font_size)
    image = Image.open(BytesIO(data))
    lens_result = await draw_results(
        image, ocr_result["bboxes"], translation_result, font
    )

    # Encode to bytes
    buffer = cv2.imencode(".jpg", lens_result)[1].tobytes()
    task_results[task_id] = buffer


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    task_id = str(uuid.uuid4())
    logger.info(f"New connection: {task_id}")

    websocket_connections[task_id] = websocket
    data = await websocket.receive()

    logger.info(f"Processing image: {task_id}")
    # background_tasks.add_task(process_image, data, task_id)
    asyncio.create_task(process_image(data["bytes"], task_id))

    try:
        while True:
            if task_id in task_results:
                logger.info(f"Sending result: {task_id}")
                result = task_results[task_id]
                await websocket.send({"type": "websocket.send", "bytes": result})
                break
            await asyncio.sleep(1)
    finally:
        del websocket_connections[task_id]
        task_results.pop(task_id, None)
        logger.info(f"Connection closed: {task_id}")
