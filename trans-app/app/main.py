from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import pika
import json
from loguru import logger
import os


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
        task = json.loads(body)
        logger.info(f"Processing translation task: {task['task_id']}")

        translations = []
        for i, input in enumerate(task["texts"]):
            eng_input = f"en: {input}"
            inputs = tokenizer(eng_input, return_tensors="pt", padding=True).input_ids
            outputs = model.generate(inputs, max_length=512)
            result = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
            result = result.replace("vi: ", "")
            translations.append(result)

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