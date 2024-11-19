#!/bin/bash

set -e

# Function to deploy a component using helm
deploy_component() {
    local name=$1
    local context=$2
    local args=$3
    echo "Deploying $name..."
    helm upgrade --install $name $context $args
}


# Function to get elasticsearch certificate
copy_elasticsearch_certificate() {
    echo "Copying elasticsearch certificate..."
    CA_CRT=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -ojsonpath='{.data.ca.crt}')
    TLS_CRT=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -ojsonpath='{.data.tls.crt}')
    TLS_KEY=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -ojsonpath='{.data.tls.key}')

    # Replace the certificate in the model-serving elasticsearch-cert.yaml
    sed -i 's|ca.crt:.*|ca.crt: '"$CA_CRT"'|' model-serving/elasticsearch-cert.yaml
    sed -i 's|tls.crt:.*|tls.crt: '"$TLS_CRT"'|' model-serving/elasticsearch-cert.yaml
    sed -i 's|tls.key:.*|tls.key: '"$TLS_KEY"'|' model-serving/elasticsearch-cert.yaml

    # Replace the certificate in the metric-cluster elasticsearch-cert.yaml
    sed -i 's|ca.crt:.*|ca.crt: '"$CA_CRT"'|' metric/elasticsearch-cert.yaml
    sed -i 's|tls.crt:.*|tls.crt: '"$TLS_CRT"'|' metric/elasticsearch-cert.yaml
    sed -i 's|tls.key:.*|tls.key: '"$TLS_KEY"'|' metric/elasticsearch-cert.yaml

    echo "Elasticsearch certificate copied successfully."
}


# Deploy logging cluster
deploy_logging_cluster() {
    echo "****************************************************"
    echo "********** DEPLOY LOGGING CLUSTER... ***************"
    echo "****************************************************"

    gcloud container clusters get-credentials logging-cluster --zone $ZONE --project $PROJECT_ID

    kubectl create namespace logging && kubens logging
    kubectl apply -f logging/secret.yaml
    deploy_component "elasticsearch" "./logging/elasticsearch" ""

    # Deploy filebeat, cadvisor, node-exporter
    deploy_component "filebeat" "./logging/filebeat" ""
    echo "Filebeat is launched."
    deploy_component "cadvisor" "./logging/cadvisor" ""
    echo "Cadvisor is launched."
    deploy_component "node-exporter" "./logging/node-exporter" ""
    echo "Node exporter is launched."

    # To deploy kibana and jaeger, we need to make sure that elasticsearch is ready
    echo "Waiting for elasticsearch to be ready..."
    kubectl wait --for=condition=ready pod -l app=elasticsearch -n logging --timeout=300s

    # Deploy kibana and jaeger
    echo "Elasticsearch is ready. Deploying kibana and jaeger..."
    deploy_component "kibana" "./logging/kibana" ""
    deploy_component "jaeger" "./logging/jaeger" ""

    # Get elasticsearch certificate and assign to model-serving filebeat and metric-server filebeat
    copy_elasticsearch_certificate

    # Get elasticsearch load balancer IP
    ELASTICSEARCH_IP=$(kubectl get svc elasticsearch-master --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Elasticsearch load balancer IP: $ELASTICSEARCH_IP"
    echo "--------------------------------------------------"

    # Get kibana load balancer IP
    KIBANA_IP=$(kubectl get svc kibana-kibana --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
    KIBANA_PASSWORD=$(kubectl get secrets --namespace=logging elasticsearch-master-credentials -ojsonpath='{.data.password}' | base64 -d)
    echo "Kibana Address: http://$KIBANA_IP"
    echo "Kibana Username: elastic"
    echo "Kibana Password: $KIBANA_PASSWORD"
    echo "--------------------------------------------------"

    # Get jaeger info
    JAEGER_COLLECTOR_HOST=$(kubectl get svc jaeger-collector --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
    JAEGER_QUERY_HOST=$(kubectl get svc jaeger-query --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Jaeger Collector Host Port: $JAEGER_COLLECTOR_HOST:14250"
    echo "Jaeger Query Host: $JAEGER_QUERY_HOST"
    echo "--------------------------------------------------"

    # Get IP of 1 node to scrape metrics
    LOGGING_NODE_IP=$(kubectl get nodes -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
    echo "Logging Node IP: $LOGGING_NODE_IP"
    echo "--------------------------------------------------"

    echo "Logging cluster deployed successfully."
}


deploy_model_serving_cluster() {
    echo "****************************************************"
    echo "********* DEPLOY MODEL SERVING CLUSTER... **********"
    echo "****************************************************"

    gcloud container clusters get-credentials model-serving-cluster --zone $ZONE --project $PROJECT_ID
    kubectl create namespace model-serving && kubens model-serving
    kubectl apply -f model-serving/secret.yaml -f model-serving/elasticsearch-cert.yaml

    # Deploy rabbitmq
    deploy_component "rabbitmq" "./model-serving/rabbitmq"
    RABBITMQ_PASSWORD=$(kubectl get secret --namespace model-serving rabbitmq-credentials -o jsonpath="{.data.rabbitmq-password}" | base64 -d)
    echo "--------------------------------------------------"
    echo "You can log into the RabbitMQ UI by forwarding its Service port to localhost:"
    echo "kubectl port-forward svc/rabbitmq-rabbitmq 15672:15672"
    echo "Then, use the following credentials to log in:"
    echo "Username: rabbitmq"
    echo "Password: $RABBITMQ_PASSWORD"
    echo "--------------------------------------------------"

    # nginx-ingress
    deploy_component "nginx-ingress" "./model-serving/nginx-ingress"
    echo "Nginx ingress is launched."
    # filebeat
    deploy_component "filebeat" "./model-serving/filebeat" "-set daemonset.extraEnvs[0].value=$ELASTICSEARCH_IP:9200"
    echo "Filebeat is launched."

    # cadvisor
    deploy_component "cadvisor" "./model-serving/cadvisor" ""
    echo "Cadvisor is launched."

    # node-exporter
    deploy_component "node-exporter" "./model-serving/node-exporter" ""
    echo "Node exporter is launched."

    # jaeger
    deploy_component "jaeger" "./model-serving/jaeger" "-set agent.extraEnv[0].value=$JAEGER_COLLECTOR_HOST:14250"
    echo "Jaeger is launched."

    # lens-app
    deploy_component "lens-app" "./model-serving/lens" ""
    echo "Lens app is launched."
    APP_IP=$(kubectl get ingress app-nginx-ingress -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Lens app address: $APP_IP"
    echo "Add this to your /etc/hosts file:"
    echo "$APP_IP app.example.com"
    echo "--------------------------------------------------"

    # Get IP of 1 node to scrape metrics
    MODEL_SERVING_NODE_IP=$(kubectl get nodes -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
    echo "Model serving node IP: $MODEL_SERVING_NODE_IP"

    APP_METRIC_HOST=$(kubectl get svc app-lens-app-metrics -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Lens app metric host: $APP_METRIC_HOST"
    echo "--------------------------------------------------"

    echo "Model serving cluster deployed successfully."
}

deploy_metrics_cluster() {
    echo "****************************************************"
    echo "********** DEPLOY METRICS CLUSTER... **************"
    echo "****************************************************"

    gcloud container clusters get-credentials metrics-cluster --zone $ZONE --project $PROJECT_ID
    kubectl create namespace metrics && kubens metrics
    kubectl apply -f metric/elasticsearch-cert.yaml -f metric/secret.yaml

    # Deploy filebeat
    deploy_component "filebeat" "./metric/filebeat" "-set daemonset.extraEnvs[0].value=$ELASTICSEARCH_IP:9200"
    echo "Filebeat is launched."

    # Deploy prometheus
    deploy_component "prometheus" "./metric/prometheus" "--set serverFiles.prometheus.yml.scrape_configs[10].static_configs.targets[0]=$LOGGING_NODE_IP:9100 --set serverFiles.prometheus.yml.scrape_configs[11].static_configs.targets[0]=$LOGGING_NODE_IP:55000 --set serverFiles.prometheus.yml.scrape_configs[12].static_configs.targets[0]=$MODEL_SERVING_NODE_IP:9100 --set serverFiles.prometheus.yml.scrape_configs[13].static_configs.targets[0]=$MODEL_SERVING_NODE_IP:55000 --set serverFiles.prometheus.yml.scrape_configs[14].static_configs.targets[0]=$APP_METRIC_HOST:8099"
    echo "Prometheus is launched."
    PROMETHEUS_IP=$(kubectl get svc prometheus-server -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Prometheus address: $PROMETHEUS_IP"
    echo "--------------------------------------------------"

    # Deploy grafana
    deploy_component "grafana" "./metric/grafana" ""
    echo "Grafana is launched."
    GRAFANA_IP=$(kubectl get svc grafana -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
    echo "Grafana address: $GRAFANA_IP"
    echo "Username: admin"
    echo "Password: $(kubectl get secret --namespace metrics grafana -o jsonpath="{.data.admin-password}" | base64 --decode)"
    echo "--------------------------------------------------"

    echo "Metrics cluster deployed successfully."
}
