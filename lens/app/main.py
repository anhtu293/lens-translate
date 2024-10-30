from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
import cv2
import os
import asyncio
from PIL import Image, ImageFont
from io import BytesIO
from .utils import draw_results
import pika
import json
import uuid
import base64
from loguru import logger


RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials, heartbeat=6000)
)
logger.info("Connected to RabbitMQ")
channel = queue_connection.channel()
# Queue for OCR
channel.exchange_declare(exchange="ocr-dlx", exchange_type="direct")
channel.queue_declare(queue="ocr_tasks_dlq", durable=True)
channel.queue_bind(exchange="ocr-dlx", queue="ocr_tasks_dlq")
channel.queue_declare(
    queue="ocr_tasks",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "ocr-dlx",
        "x-dead-letter-routing-key": "ocr_tasks_dlq",
        "x-message-ttl": 300000,  # 5 minutes in milliseconds
    },
)
channel.queue_declare(queue="ocr_results", durable=True)

# Queue for Translation
channel.exchange_declare(exchange="trans-dlx", exchange_type="direct")
channel.queue_declare(queue="translation_tasks_dlq", durable=True)
channel.queue_bind(exchange="trans-dlx", queue="translation_tasks_dlq")
channel.queue_declare(
    queue="translation_tasks",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "trans-dlx",
        "x-dead-letter-routing-key": "translation_tasks_dlq",
        "x-message-ttl": 300000,  # 5 minutes in milliseconds
    },
)
channel.queue_declare(queue="translation_results", durable=True)

app = FastAPI()

task_results = {}


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
    wait_count = 0
    ocr_ok = True
    while True:
        method_frame, _, body = channel.basic_get("ocr_results")
        if method_frame:
            ocr_result = json.loads(body)
            if ocr_result["task_id"] == task_id:
                ocr_result = ocr_result["result"]
                channel.basic_ack(method_frame.delivery_tag)
                break
        else:
            wait_count += 1
            if wait_count > 10:
                logger.error(f"OCR task {task_id} timeout")
                ocr_ok = False
                break
            await asyncio.sleep(1)

    # Translation
    if ocr_ok:
        logger.info("Sending translation task")
        channel.basic_publish(
            exchange="",
            routing_key="translation_tasks",
            body=json.dumps({"task_id": task_id, "texts": ocr_result["texts"]}),
        )

        # Wait for translation result
        logger.info("Waiting for translation result")
        wait_count = 0
        translation_ok = True
        while True:
            method_frame, _, body = channel.basic_get("translation_results")
            if method_frame:
                translation_result = json.loads(body)
                if translation_result["task_id"] == task_id:
                    translation_result = translation_result["result"]
                    channel.basic_ack(method_frame.delivery_tag)
                    break
            else:
                wait_count += 1
                if wait_count > 10:
                    logger.error(f"Translation task {task_id} timeout")
                    translation_ok = False
                    break
                await asyncio.sleep(1)

    # find suitable font size
    if ocr_ok and translation_ok:
        logger.info("Formatting results")
        font_size = int(ocr_result["bbox_height"] / 1.5)

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
    else:
        task_results[task_id] = None


@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}


@app.post("/translate")
async def translate(file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    data = await file.read()

    logger.info(f"Processing image: {task_id}")
    asyncio.create_task(process_image(data, task_id))

    try:
        while True:
            if task_id in task_results:
                logger.info(f"Sending result: {task_id}")
                result = task_results[task_id]
                if result is not None:
                    return StreamingResponse(BytesIO(result), media_type="image/jpeg")
                else:
                    return {"error": "Error"}
            await asyncio.sleep(1)
    finally:
        task_results.pop(task_id, None)
