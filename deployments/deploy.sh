#!/bin/bash

# set -e

# Define variables
export ELASTICSEARCH_IP=$ELASTICSEARCH_IP
export KIBANA_IP=$KIBANA_IP
export KIBANA_PASSWORD=$KIBANA_PASSWORD
export JAEGER_COLLECTOR_HOST=$JAEGER_COLLECTOR_HOST
export JAEGER_QUERY_HOST=$JAEGER_QUERY_HOST
export LOGGING_NODE_IP=$LOGGING_NODE_IP
export RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD
export MODEL_SERVING_NODE_IP=$MODEL_SERVING_NODE_IP
export APP_METRIC_HOST=$APP_METRIC_HOST
export APP_IP=$APP_IP
export PROMETHEUS_IP=$PROMETHEUS_IP
export GRAFANA_IP=$GRAFANA_IP
export GRAFANA_PASSWORD=$GRAFANA_PASSWORD


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
    CA_CRT=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -o json | jq -r '.data["ca.crt"]')
    TLS_CRT=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -o json | jq -r '.data["tls.crt"]')
    TLS_KEY=$(kubectl get secrets --namespace=logging elasticsearch-master-certs -o json | jq -r '.data["tls.key"]')

    # Replace the certificate in the model-serving elasticsearch-cert.yaml
    sed -i 's|ca.crt:.*|ca.crt: '"$CA_CRT"'|' model-serving/elasticsearch-cert.yaml
    sed -i 's|tls.crt:.*|tls.crt: '"$TLS_CRT"'|' model-serving/elasticsearch-cert.yaml
    sed -i 's|tls.key:.*|tls.key: '"$TLS_KEY"'|' model-serving/elasticsearch-cert.yaml

    # Replace the certificate in the metric-cluster elasticsearch-cert.yaml
    sed -i 's|ca.crt:.*|ca.crt: '"$CA_CRT"'|' metrics/elasticsearch-cert.yaml
    sed -i 's|tls.crt:.*|tls.crt: '"$TLS_CRT"'|' metrics/elasticsearch-cert.yaml
    sed -i 's|tls.key:.*|tls.key: '"$TLS_KEY"'|' metrics/elasticsearch-cert.yaml

    echo "Elasticsearch certificate copied successfully."
}


# DEPLOY LOGGING CLUSTER
deploy_logging_cluster() {
    echo "****************************************************"
    echo "********** DEPLOY LOGGING CLUSTER... ***************"
    echo "****************************************************"

    export ELASTICSEARCH_IP=""
    export KIBANA_IP=""
    export KIBANA_PASSWORD=""
    export JAEGER_COLLECTOR_HOST=""
    export JAEGER_QUERY_HOST=""
    export LOGGING_NODE_IP=""

    gcloud container clusters get-credentials logging-cluster --zone $ZONE --project $PROJECT_ID

    if ! kubectl get namespace logging > /dev/null 2>&1; then
        kubectl create namespace logging
    fi
    kubens logging
    kubectl apply -f logging/secret.yaml
    deploy_component "elasticsearch" "./logging/elasticsearch" ""

    # Deploy cadvisor, node-exporter
    deploy_component "cadvisor" "./logging/cadvisor" ""
    echo "Cadvisor is launched."
    deploy_component "node-exporter" "./logging/node-exporter" ""
    echo "Node exporter is launched."

    # To deploy kibana and jaeger, we need to make sure that elasticsearch is ready
    echo "Waiting for elasticsearch to be ready..."
    kubectl wait --for=condition=ready pod -l app=elasticsearch-master -n logging --timeout=300s

    # Deploy kibana and jaeger
    echo "Elasticsearch is ready. Deploying filebeat, kibana and jaeger..."
    deploy_component "filebeat" "./logging/filebeat" ""
    echo "Filebeat is launched."
    deploy_component "kibana" "./logging/kibana" ""
    deploy_component "jaeger" "./logging/jaeger" ""

    # Get elasticsearch certificate and assign to model-serving filebeat and metric-server filebeat
    copy_elasticsearch_certificate

    # Get elasticsearch load balancer IP
    while [ -z $ELASTICSEARCH_IP ]; do
        echo "Waiting for elasticsearch load balancer IP..."
        ELASTICSEARCH_IP=$(kubectl get svc elasticsearch-master --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$ELASTICSEARCH_IP" ] && sleep 2
    done
    echo "--------------------------------------------------"
    echo "Elasticsearch load balancer IP: $ELASTICSEARCH_IP"
    echo "--------------------------------------------------"

    # Get kibana load balancer IP
    while [ -z $KIBANA_IP ]; do
        echo "Waiting for kibana endpoint..."
        KIBANA_IP=$(kubectl get svc kibana-kibana --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$KIBANA_IP" ] && sleep 2
    done
    KIBANA_PASSWORD=$(kubectl get secrets --namespace=logging elasticsearch-master-credentials -ojsonpath='{.data.password}' | base64 -d)
    echo "Kibana Address: http://$KIBANA_IP:5601"
    echo "Kibana Username: elastic"
    echo "Kibana Password: $KIBANA_PASSWORD"
    echo "--------------------------------------------------"

    # Get jaeger info
    while [ -z $JAEGER_COLLECTOR_HOST ]; do
        echo "Waiting for jaeger collector endpoint..."
        JAEGER_COLLECTOR_HOST=$(kubectl get svc jaeger-collector --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$JAEGER_COLLECTOR_HOST" ] && sleep 2
    done
    while [ -z $JAEGER_QUERY_HOST ]; do
        echo "Waiting for jaeger query endpoint..."
        JAEGER_QUERY_HOST=$(kubectl get svc jaeger-query --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$JAEGER_QUERY_HOST" ] && sleep 2
    done
    echo "Jaeger Collector Host Port: $JAEGER_COLLECTOR_HOST:14250"
    echo "Jaeger Query Host: $JAEGER_QUERY_HOST"
    echo "--------------------------------------------------"

    # Get IP of 1 node to scrape metrics
    while [ -z $LOGGING_NODE_IP ]; do
        echo "Waiting for logging node IP..."
        LOGGING_NODE_IP=$(kubectl get nodes -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
        [ -z "$LOGGING_NODE_IP" ] && sleep 2
    done
    echo "Logging Node IP: $LOGGING_NODE_IP"
    echo "--------------------------------------------------"

    echo "Logging cluster deployed successfully."
}

# DEPLOY MODEL SERVING CLUSTER
deploy_model_serving_cluster() {
    echo "****************************************************"
    echo "********* DEPLOY MODEL SERVING CLUSTER... **********"
    echo "****************************************************"

    export RABBITMQ_PASSWORD=""
    export MODEL_SERVING_NODE_IP=""
    export APP_METRIC_HOST=""
    export APP_IP=""

    gcloud container clusters get-credentials model-serving-cluster --zone $ZONE --project $PROJECT_ID
    if ! kubectl get namespace model-serving > /dev/null 2>&1; then
        kubectl create namespace model-serving
    fi
    kubens model-serving
    kubectl apply -f model-serving/secret.yaml -f model-serving/elasticsearch-cert.yaml

    # Deploy rabbitmq
    deploy_component "rabbitmq" "./model-serving/rabbitmq"
    echo "Waiting for rabbitmq to be ready..."
    kubectl wait --for=condition=ready pod -l app=rabbitmq -n model-serving --timeout=300s
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
    yq eval ".daemonset.extraEnvs[] |= select(.name == \"ELASTICSEARCH_HOSTS\").value = \"$ELASTICSEARCH_IP:9200\"" -i model-serving/filebeat/values.yaml
    deploy_component "filebeat" "./model-serving/filebeat" ""
    echo "Filebeat is launched."

    # cadvisor
    deploy_component "cadvisor" "./model-serving/cadvisor" ""
    echo "Cadvisor is launched."

    # node-exporter
    deploy_component "node-exporter" "./model-serving/node-exporter" ""
    echo "Node exporter is launched."

    # jaeger
    yq eval ".agent.extraEnv[] |= select(.name == \"REPORTER_GRPC_HOST_PORT\").value = \"$JAEGER_COLLECTOR_HOST:14250\"" -i model-serving/jaeger/values.yaml
    deploy_component "jaeger" "./model-serving/jaeger" ""
    echo "Jaeger is launched."

    # lens-app
    deploy_component "app" "./model-serving/lens" ""
    echo "Aapp is launched."
    while [ -z $APP_IP ]; do
        echo "Waiting for app IP..."
        APP_IP=$(kubectl get ingress app-nginx-ingress -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$APP_IP" ] && sleep 2
    done
    echo "Lens app address: $APP_IP"
    echo "Add this to your /etc/hosts file:"
    echo "$APP_IP app.example.com"
    echo "--------------------------------------------------"

    # Get IP of 1 node to scrape metrics
    while [ -z $MODEL_SERVING_NODE_IP ]; do
        echo "Waiting for model serving node IP..."
        MODEL_SERVING_NODE_IP=$(kubectl get nodes -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
        [ -z "$MODEL_SERVING_NODE_IP" ] && sleep 2
    done
    echo "Model serving node IP: $MODEL_SERVING_NODE_IP"

    while [ -z $APP_METRIC_HOST ]; do
        echo "Waiting for app metric host..."
        APP_METRIC_HOST=$(kubectl get svc app-lens-app-metrics -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$APP_METRIC_HOST" ] && sleep 2
    done
    echo "Lens app metric host: $APP_METRIC_HOST"
    echo "--------------------------------------------------"

    echo "Model serving cluster deployed successfully."
}

# DEPLOY METRICS CLUSTER
deploy_metrics_cluster() {
    echo "****************************************************"
    echo "********** DEPLOY METRICS CLUSTER... **************"
    echo "****************************************************"

    export PROMETHEUS_IP=""
    export GRAFANA_IP=""
    export GRAFANA_PASSWORD=""

    gcloud container clusters get-credentials metrics-cluster --zone $ZONE --project $PROJECT_ID
    if ! kubectl get namespace metrics > /dev/null 2>&1; then
        kubectl create namespace metrics
    fi
    kubens metrics
    kubectl apply -f metrics/elasticsearch-cert.yaml -f metrics/secret.yaml

    # Deploy filebeat
    yq eval ".daemonset.extraEnvs[] |= select(.name == \"ELASTICSEARCH_HOSTS\").value = \"$ELASTICSEARCH_IP:9200\"" -i metrics/filebeat/values.yaml
    deploy_component "filebeat" "./metrics/filebeat" ""
    echo "Filebeat is launched."

    # Deploy prometheus
    yq eval ".serverFiles.prometheus.yml.scrape_configs[10].static_configs.targets[0] = \"$LOGGING_NODE_IP:9100\"" -i metrics/prometheus/values.yaml
    yq eval ".serverFiles.prometheus.yml.scrape_configs[11].static_configs.targets[0] = \"$LOGGING_NODE_IP:55000\"" -i metrics/prometheus/values.yaml
    yq eval ".serverFiles.prometheus.yml.scrape_configs[12].static_configs.targets[0] = \"$MODEL_SERVING_NODE_IP:9100\"" -i metrics/prometheus/values.yaml
    yq eval ".serverFiles.prometheus.yml.scrape_configs[13].static_configs.targets[0] = \"$MODEL_SERVING_NODE_IP:55000\"" -i metrics/prometheus/values.yaml
    yq eval ".serverFiles.prometheus.yml.scrape_configs[14].static_configs.targets[0] = \"$APP_METRIC_HOST:8099\"" -i metrics/prometheus/values.yaml
    deploy_component "prometheus" "./metrics/prometheus" ""
    # wait for prometheus to be ready
    echo "Waiting for prometheus to be ready..."
    kubectl wait --for=condition=ready pod -l app=prometheus-server -n metrics --timeout=300s
    echo "Prometheus is launched."
    while [ -z $PROMETHEUS_IP ]; do
        echo "Waiting for prometheus IP..."
        PROMETHEUS_IP=$(kubectl get nodes -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
        [ -z "$PROMETHEUS_IP" ] && sleep 2
    done
    echo "Prometheus address: $PROMETHEUS_IP"
    echo "--------------------------------------------------"

    # Deploy grafana
    deploy_component "grafana" "./metrics/grafana" ""
    echo "Waiting for grafana to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n metrics --timeout=300s
    echo "Grafana is launched."
    while [ -z $GRAFANA_IP ]; do
        echo "Waiting for grafana IP..."

        GRAFANA_IP=$(kubectl get svc grafana -ojsonpath='{.status.loadBalancer.ingress[0].ip}')
        [ -z "$GRAFANA_IP" ] && sleep 2
    done
    GRAFANA_PASSWORD=$(kubectl get secret --namespace metrics grafana -o jsonpath="{.data.admin-password}" | base64 --decode)
    echo "Grafana address: $GRAFANA_IP"
    echo "Username: admin"
    echo "Password: $GRAFANA_PASSWORD"
    echo "--------------------------------------------------"

    echo "Metrics cluster deployed successfully."
}


# SUMMARY
create_summary() {
    # Write all the information to a summary file
    echo "Writing summary to variables.sh..."
    # overwrite the file
    echo "export ELASTICSEARCH_IP=$ELASTICSEARCH_IP" > variables.sh
    echo "export KIBANA_IP=$KIBANA_IP" >> variables.sh
    echo "export KIBANA_PASSWORD=$KIBANA_PASSWORD" >> variables.sh
    echo "export JAEGER_COLLECTOR_HOST=$JAEGER_COLLECTOR_HOST" >> variables.sh
    echo "export JAEGER_QUERY_HOST=$JAEGER_QUERY_HOST" >> variables.sh
    echo "export LOGGING_NODE_IP=$LOGGING_NODE_IP" >> variables.sh
    echo "export RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD" >> variables.sh
    echo "export MODEL_SERVING_NODE_IP=$MODEL_SERVING_NODE_IP" >> variables.sh
    echo "export APP_METRIC_HOST=$APP_METRIC_HOST" >> variables.sh
    echo "export APP_IP=$APP_IP" >> variables.sh
    echo "export PROMETHEUS_IP=$PROMETHEUS_IP" >> variables.sh
    echo "export GRAFANA_IP=$GRAFANA_IP" >> variables.sh
    echo "export GRAFANA_PASSWORD=$GRAFANA_PASSWORD" >> variables.sh
}


# install jq and yq if not installed
if ! command -v jq &> /dev/null; then
    echo "jq could not be found, installing..."
    sudo apt-get install -y jq
fi

# install yq if not installed
if ! command -v yq &> /dev/null; then
    echo "yq could not be found, installing..."
    sudo wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq
    sudo chmod +x /usr/local/bin/yq
fi


if [ "$1" = "logging" ]; then
    deploy_logging_cluster
    create_summary
elif [ "$1" = "model-serving" ]; then
    deploy_model_serving_cluster
    create_summary
elif [ "$1" = "metrics" ]; then
    deploy_metrics_cluster
    create_summary
elif [ "$1" = "all" ]; then
    deploy_logging_cluster
    deploy_model_serving_cluster
    deploy_metrics_cluster
    create_summary
fi
