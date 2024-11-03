# lens-translate

This application can directly translate English text from images into Vietnamese.
The purpose of this project is to develop and deploy a machine learning application at scale.

## 1. Application Design
The application consists of the following components:
![text](images/pipeline.png)
- **OCR Service** and **Translation Service** are separated services to improve scalability and overall application throughput.

### Architecture Flow
1. User uploads an image. Image is then sent to **lens-app**
2. Image is sent to **OCR Service** for text detection via `OCR Queue`
3. **OCR Service** detects text in images and sends results to `OCR Results Queue`
4. **lens-app** receives results (bounding boxes and text) from `OCR Results` and forwards text to **Translation Service** via `Trans Queue`
5. **Translation Service** processes the text and returns results to **lens-app** via `Trans Results` queue
6. **lens-app** overlays translated text onto the original image using the bounding boxes and sends the result back to the user

## 2. Local Deployment with docker compose

- Create `.env` file
```
RABBITMQ_USER=user
RABBITMQ_PASSWORD=password
```

- Launch docker compose
```bash
docker compose up -d
```

- Open `localhost:8000` in web browser and you should have the following **FastAPI** doc.
![](images/fastapi_doc.png)

- You can supervise the queue (**RabbitMQ**) from `localhost:15672`


## 3. Local deployment K8S with minikube

### 3.0 Prerequisites
- Setup minikube
```bash
minikube start
minikube addons enable ingress
minikube tunnel
```

- Create namespace
```bash
kubectl create namespace model-serving
```

- Set your [secret](deployments/secret.yaml). You must encode your password using `base64` to be able to use with K8S Secret: `echo -n "YOUR PASSWORD" | base64`.
Set your password in secret. Then execute the following command to apply secret
```bash
cd deployments
kubectl apply -f secret.yaml
```

- Setup `jaeger` host for collecting tracing
```bash
cd deployments/monitoring/metrics/jaeger
helm upgrade --install jaeger .
```

### 3.1 RabbitMQ

```bash
cd deployments/rabbitmq
helm upgrade --install rabbitmq .
```

### 3.2 Nginx-ingress
```bash
cd deployments/nginx-ingress
helm upgrade --install nginx-ingress .
```

### 3.3 lens
- Get ClusterIP of `rabbitmq`
```bash
k get svc rabbitmq
```

- Get jaeger host and modify in `values.yaml`

- Copy ClusterIP to `deployments/lens/values.yaml`: `rabbitmq.host`
```bash
cd deployments/lens
helm upgrade --install lens .
```


### 3.4 Test
- Get Minikube IP
```bash
minikube ip
```

- Use web broser to access `minikubeIP/docs`. You should have the **FastAPI** doc.

### 3.5 Monitoring
```bash
kubectl create namespace monitoring
```
- Setup secret
```bash
kubectl apply -f secret.yaml
```

- Elasticsearch
```bash
cd deployments/elasticsearch
helm upgrade --install elasticsearch .
```
- Export Elasticsearch certificate for collecting log & apply this secret in model-serving cluster for deploying `filebeat`.
```
kubectl get secret elasticsearch -o yaml > elasticsearch-cert.yaml
```
- Kibana
```bash
cd deployments/kibana
helm upgrade --install kibana .
````
- Filebeat
```bash
cd deployments/filebeat
helm upgrade --install filebeat .
```

### 3.4 Metric

- Grafana
```bash
cd deployments/monitoring/metrics/grafana
helm upgrade --install grafana .
```

- Prometheus
```bash
cd deployments/monitoring/metrics/prometheus
helm upgrade --install prometheus .
```
