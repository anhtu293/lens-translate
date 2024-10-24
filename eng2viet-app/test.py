from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

model_name = "VietAI/envit5-translation"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
# model.cuda()

inputs = [
    "en: Our teams aspire to make discoveries that impact everyone, and core to our approach is sharing our research and tools to fuel progress in the field.",
    "en: We're on a journey to advance and democratize artificial intelligence through open source and open science."
    ]

outputs = model.generate(tokenizer(inputs, return_tensors="pt", padding=True).input_ids, max_length=512)
output = tokenizer.batch_decode(outputs, skip_special_tokens=True)
print(output)
print(len(output))
print(type(output[0]))
