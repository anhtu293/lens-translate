FROM python:3.10.15-bullseye

RUN apt-get -y  update; apt-get -y install sudo build-essential nano git wget libgl1-mesa-glx

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .


CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
