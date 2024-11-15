FROM python:3.10.15-bullseye

RUN apt-get -y  update; apt-get -y install sudo build-essential nano git wget libgl1-mesa-glx

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install easyocr==1.7.0

WORKDIR /app

COPY . /app

ENV PYTHONPATH=$PYTHONPATH:/app

CMD ["python", "-m", "app.main"]
