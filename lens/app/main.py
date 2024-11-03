import os
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from prometheus_client import start_http_server
import cv2
import asyncio
from PIL import Image, ImageFont
from io import BytesIO
from .utils import draw_results
import pika
import json
import uuid
import base64
from loguru import logger
from time import time


METRIC_SERVICE_NAME = os.getenv("METRIC_SERVICE_NAME")
METRIC_SERVICE_VERSION = os.getenv("METRIC_SERVICE_VERSION")

# Start Prometheus metrics server
start_http_server(8099, addr="0.0.0.0")
resource = Resource(attributes={SERVICE_NAME: METRIC_SERVICE_NAME})
reader = PrometheusMetricReader()
provider = MeterProvider(resource=resource, metric_readers=[reader])
set_meter_provider(provider)
meter = metrics.get_meter(METRIC_SERVICE_NAME, METRIC_SERVICE_VERSION)
# Create your first counter
counter = meter.create_counter(
    name="lens_request_counter",
    description="Number of lens requests"
)
histogram = meter.create_histogram(
    name="lens_response_histogram",
    description="Lens response histogram",
    unit="seconds",
)

# Setup Jaeger
JAEGER_AGENT_HOST = os.getenv("JAEGER_AGENT_HOST")
JAEGER_AGENT_PORT = int(os.getenv("JAEGER_AGENT_PORT"))
set_tracer_provider(TracerProvider(resource=resource))
tracer = get_tracer_provider().get_tracer(METRIC_SERVICE_NAME, METRIC_SERVICE_VERSION)
jaeger_exporter = JaegerExporter(
    agent_host_name=JAEGER_AGENT_HOST,
    agent_port=JAEGER_AGENT_PORT,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
get_tracer_provider().add_span_processor(span_processor)

# RabbitMQ
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
task_start_time = {}


async def process_image(data: bytes, task_id: str) -> None:
    with tracer.start_as_current_span("process_image") as span:
        # Wait for OCR result
        logger.info("Sending OCR task")
        with tracer.start_as_current_span("send_ocr_task", links=[trace.Link(span.get_span_context())]):
            channel.basic_publish(
                exchange="",
                routing_key="ocr_tasks",
                body=json.dumps({"task_id": task_id, "data": base64.b64encode(data).decode("utf-8")}),
            )

        # Wait for OCR result
        logger.info("Waiting for OCR result")
        with tracer.start_as_current_span("wait_ocr_result", links=[trace.Link(span.get_span_context())]):
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
            with tracer.start_as_current_span("send_translation_task", links=[trace.Link(span.get_span_context())]):
                channel.basic_publish(
                    exchange="",
                    routing_key="translation_tasks",
                    body=json.dumps({"task_id": task_id, "texts": ocr_result["texts"]}),
                )

            # Wait for translation result
            logger.info("Waiting for translation result")
            with tracer.start_as_current_span("wait_translation_result", links=[trace.Link(span.get_span_context())]):
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
            with tracer.start_as_current_span("format_results", links=[trace.Link(span.get_span_context())]):
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
    task_start_time[task_id] = time()
    asyncio.create_task(process_image(data, task_id))

    try:
        while True:
            if task_id in task_results:
                logger.info(f"Sending result: {task_id}")
                result = task_results[task_id]
                if result is not None:
                    histogram.record(time() - task_start_time[task_id], {"api": "/lens"})
                    counter.add(1, {"api": "/lens"})
                    task_start_time.pop(task_id)
                    return StreamingResponse(BytesIO(result), media_type="image/jpeg")
                else:
                    histogram.record(time() - task_start_time[task_id], {"api": "/lens"})
                    counter.add(1, {"api": "/lens"})
                    task_start_time.pop(task_id)
                    return {"error": "Error"}
            await asyncio.sleep(1)
    finally:
        task_results.pop(task_id, None)
