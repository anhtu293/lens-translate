#!/bin/bash

# Define input and output files
INPUT_FILE="cert.json"
OUTPUT_FILE="elasticsearch-cert.yaml"

# Extract and decode the certificates
CA_CRT=$(jq -r '.["ca.crt"]' $INPUT_FILE | base64 --decode)
TLS_CRT=$(jq -r '.["tls.crt"]' $INPUT_FILE | base64 --decode)
TLS_KEY=$(jq -r '.["tls.key"]' $INPUT_FILE | base64 --decode)

# Write to the YAML file
cat <<EOF > $OUTPUT_FILE
apiVersion: v1
data:
  ca.crt: $(echo -n "$CA_CRT" | base64)
  tls.crt: $(echo -n "$TLS_CRT" | base64)
  tls.key: $(echo -n "$TLS_KEY" | base64)
kind: Secret
metadata:
  annotations:
    meta.helm.sh/release-namespace: model-serving
  labels:
    app: elasticsearch-master
    app.kubernetes.io/managed-by: Helm
    chart: elasticsearch
    heritage: Helm
    release: elasticsearch
  name: elasticsearch-master-certs
  namespace: model-serving
type: kubernetes.io/tls
EOF

echo "Certificates have been extracted and written to $OUTPUT_FILE"
