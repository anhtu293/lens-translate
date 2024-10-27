from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import pika
import json
from loguru import logger


credentials = pika.PlainCredentials("user", "password")
queue_connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="rabbitmq", credentials=credentials, heartbeat=6000)
)
channel = queue_connection.channel()
channel.queue_declare(queue="translation_tasks", durable=True)
channel.queue_declare(queue="translation_results", durable=True)


# Init model
model_name = "VietAI/envit5-translation"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
logger.info("Translation model loaded")


def process_translation_task(ch, method, properties, body):
    task = json.loads(body)
    logger.info(f"Processing translation task: {task['task_id']}")

    translations = []
    for i, input in enumerate(task["texts"]):
        eng_input = f"en: {input}"
        inputs = tokenizer(eng_input, return_tensors="pt", padding=True).input_ids
        outputs = model.generate(inputs, max_length=512)
        translations.append(tokenizer.batch_decode(outputs, skip_special_tokens=True)[0])

    channel.basic_publish(
        exchange="",
        routing_key="translation_results",
        body=json.dumps({"task_id": task["task_id"], "result": translations}),
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_consume(queue="translation_tasks", on_message_callback=process_translation_task)

logger.info("Waiting for translation tasks...")
channel.start_consuming()
