from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import pika
import json
from loguru import logger
import os
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import get_tracer_provider, set_tracer_provider


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
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials, heartbeat=6000)
)
channel = queue_connection.channel()


# Init model
model_name = "VietAI/envit5-translation"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
logger.info("Translation model loaded")


def process_translation_task(ch, method, properties, body):
    try:
        with tracer.start_as_current_span("translation-service") as span:
            with tracer.start_as_current_span("load_data", links=[trace.Link(span.get_span_context())]):
                task = json.loads(body)
                logger.info(f"Processing translation task: {task['task_id']}")

            translations = []

            with tracer.start_as_current_span("translation-service-translate", links=[trace.Link(span.get_span_context())]):
                for i, input in enumerate(task["texts"]):
                    eng_input = f"en: {input}"
                    inputs = tokenizer(eng_input, return_tensors="pt", padding=True).input_ids
                    outputs = model.generate(inputs, max_length=512)
                    result = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
                    result = result.replace("vi: ", "")
                    translations.append(result)

            with tracer.start_as_current_span("translation-service-publish", links=[trace.Link(span.get_span_context())]):
                channel.basic_publish(
                    exchange="",
                    routing_key="translation_results",
                    body=json.dumps({"task_id": task["task_id"], "result": translations}),
                )
                channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing translation task: {e}")
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)


channel.basic_consume(queue="translation_tasks", on_message_callback=process_translation_task)

logger.info("Waiting for translation tasks...")
channel.start_consuming()
