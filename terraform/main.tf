terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "2.25.2"
    }
  }
  backend "local" {
    path = "/tmp/terraform-lab9.tfstate"
  }
}

provider "kubernetes" {
  config_path = "/tmp/microk8s-config.yaml"
}

resource "kubernetes_namespace" "lab9" {
  metadata {
    name = "lab9"
    labels = {
      environment = "lab"
      managed-by  = "terraform"
      team        = "platform"
    }
  }
}

resource "kubernetes_resource_quota" "lab9" {
  metadata {
    name      = "lab9-quota"
    namespace = kubernetes_namespace.lab9.metadata[0].name
    labels    = { managed-by = "terraform" }
  }
  spec {
    hard = {
      "requests.cpu"    = "500m"
      "requests.memory" = "512Mi"
      "limits.cpu"      = "1000m"
      "limits.memory"   = "1Gi"
      "pods"            = "10"
    }
  }
}

output "lab9_namespace" {
  value = kubernetes_namespace.lab9.metadata[0].name
}