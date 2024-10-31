import easyocr
import os
from PIL import Image
import imagehash
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from collections import OrderedDict
from io import BytesIO
import pika
import json
from loguru import logger
import base64
import numpy as np
from .utils import get_sentence


METRIC_SERVICE_NAME = os.getenv("METRIC_SERVICE_NAME")
METRIC_SERVICE_VERSION = os.getenv("METRIC_SERVICE_VERSION")

# Setup Jaeger
JAEGER_AGENT_HOST = os.getenv("JAEGER_AGENT_HOST")
JAEGER_AGENT_PORT = int(os.getenv("JAEGER_AGENT_PORT"))
resource = Resource(attributes={SERVICE_NAME: METRIC_SERVICE_NAME})
set_tracer_provider(TracerProvider(resource=resource))
tracer = get_tracer_provider().get_tracer(METRIC_SERVICE_NAME, METRIC_SERVICE_VERSION)
jaeger_exporter = JaegerExporter(
    agent_host_name=JAEGER_AGENT_HOST,
    agent_port=JAEGER_AGENT_PORT,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
get_tracer_provider().add_span_processor(span_processor)


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
        with tracer.start_as_current_span("ocr-service") as span:
            with tracer.start_as_current_span("load_data", links=[trace.Link(span.get_span_context())]):
                task = json.loads(body)
                logger.info(f"Processing image: {task['task_id']}")
                image = Image.open(BytesIO(base64.b64decode(task["data"].encode("utf-8"))))
                image_hash = imagehash.average_hash(image)

            if image_hash in cache:
                channel.basic_publish(
                    exchange="",
                    routing_key="ocr_results",
                    body=json.dumps({"task_id": task["task_id"], "result": cache[image_hash]}),
                )
                channel.basic_ack(delivery_tag=method.delivery_tag)
                return

            with tracer.start_as_current_span("ocr_detection", links=[trace.Link(span.get_span_context())]):
                detection = reader.readtext(image)

            # Get median height of bboxes
            with tracer.start_as_current_span("ocr_detection_height", links=[trace.Link(span.get_span_context())]):
                bboxes_heights = []
                for bbox, text, prob in detection:
                    (top_left, _, bottom_right, _) = bbox
                    bboxes_heights.append(bottom_right[1] - top_left[1])
                bbox_height = int(np.median(bboxes_heights))

            # Create the final result
            with tracer.start_as_current_span("ocr_merge_sentence", links=[trace.Link(span.get_span_context())]):
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
