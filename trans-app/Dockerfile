FROM python:3.10.15-bullseye

RUN apt-get -y  update; apt-get -y install sudo build-essential nano git wget libgl1-mesa-glx

COPY requirements.txt .
RUN pip install -r requirements.txt

WORKDIR /app

COPY . /app
CMD ["python", "app/main.py"]
