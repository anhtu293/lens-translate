from fastapi import FastAPI
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM


app = FastAPI()


# Init model
model_name = "VietAI/envit5-translation"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

# # Fond for drawing results
# fontpath = os.path.join(os.path.dirname(__file__), "./BeVietnam-Light.ttf")


@app.post("/translate")
async def translate(texts: list[str]) -> list[str]:
    translations = []
    for i, input in enumerate(texts):
        eng_input = f"en: {input}"
        inputs = tokenizer(eng_input, return_tensors="pt", padding=True).input_ids
        outputs = model.generate(inputs, max_length=512)
        translations.append(tokenizer.batch_decode(outputs, skip_special_tokens=True)[0])

    return translations
