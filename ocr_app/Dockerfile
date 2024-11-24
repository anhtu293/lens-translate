FROM python:3.10.15-slim

RUN apt-get -y  update; apt-get -y install sudo build-essential nano git wget libgl1-mesa-glx

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN rm requirements.txt

RUN pip install torch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install easyocr==1.7.0


COPY ./app .

ENV PYTHONPATH=$PYTHONPATH:/app

CMD ["python", "-m", "main"]
