# To define that we will use GCP
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.80.0" // Provider version
    }
  }
  required_version = "1.9.8" // Terraform version
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_container_cluster" "logging_cluster" {
  name     = "logging-cluster"
  location = var.location

  # It's recommended to seperate the node pools from the cluster definition
  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Enable node auto-provisioning
  cluster_autoscaling {
    enabled = true

    # Optional: Define resource limits for auto-provisioned nodes
    resource_limits {
      resource_type = "cpu"
      minimum       = 1
      maximum       = 1
    }

    resource_limits {
      resource_type = "memory"
      minimum       = 1
      maximum       = 1
    }
  }
}

resource "google_container_node_pool" "logging_cluster_nodes" {
  name       = "logging-cluster-nodes"
  cluster    = google_container_cluster.logging_cluster.id
  node_count = 2

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"
    disk_size_gb = 50
  }

}

resource "google_container_cluster" "model_serving_cluster" {
  name     = "model-serving-cluster"
  location = var.location

  # It's recommended to seperate the node pools from the cluster definition
  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Enable node auto-provisioning
  cluster_autoscaling {
    enabled = true

    # Optional: Define resource limits for auto-provisioned nodes
    resource_limits {
      resource_type = "cpu"
      minimum       = 1
      maximum       = 1
    }

    resource_limits {
      resource_type = "memory"
      minimum       = 1
      maximum       = 1
    }
  }
}

resource "google_container_node_pool" "model_serving_cluster_nodes" {
  name       = "model-serving-cluster-nodes"
  cluster    = google_container_cluster.model_serving_cluster.id
  node_count = 2

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"
    disk_size_gb = 50
  }
}

resource "google_container_cluster" "metrics_cluster" {
  name     = "metrics-cluster"
  location = var.location

  # It's recommended to seperate the node pools from the cluster definition
  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Enable node auto-provisioning
  cluster_autoscaling {
    enabled = true

    # Optional: Define resource limits for auto-provisioned nodes
    resource_limits {
      resource_type = "cpu"
      minimum       = 1
      maximum       = 1
    }

    resource_limits {
      resource_type = "memory"
      minimum       = 1
      maximum       = 1
    }
  }
}

resource "google_container_node_pool" "metrics_cluster_nodes" {
  name       = "metrics-cluster-nodes"
  cluster    = google_container_cluster.metrics_cluster.id
  node_count = 2

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"
    disk_size_gb = 50
  }
}

resource "google_compute_firewall" "allow_lens_app" {
  name    = "allow-lens-app"
  network = "default" // Replace with your network name if different

  allow {
    protocol = "tcp"
    ports    = ["8099", "9100", "9200", "9300", "55000"]
  }

  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]      // Allows traffic from all IPs
  target_tags   = ["allow-lens-app"] // Optional: Use if you want to target specific VMs with this tag
}
