terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

variable "network_name" {
  type = string
}

# Diretório `infra/` na raiz do repo. `path.module` aqui é
# `infra/terraform/modules/observability`; subindo 3 níveis chega em `infra/`.
locals {
  infra_root = abspath("${path.module}/../../..")
}

# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------
resource "docker_image" "prometheus" {
  name = "prom/prometheus:v2.55.1"
}

resource "docker_volume" "prometheus_data" {
  name = "prometheus_data"
}

resource "docker_container" "prometheus" {
  name  = "rag-prometheus"
  image = docker_image.prometheus.image_id
  command = [
    "--config.file=/etc/prometheus/prometheus.yml",
    "--storage.tsdb.retention.time=7d",
    "--storage.tsdb.path=/prometheus",
  ]
  networks_advanced {
    name    = var.network_name
    aliases = ["prometheus"]
  }
  ports {
    internal = 9090
    external = 9090
  }
  volumes {
    host_path      = "${local.infra_root}/prometheus"
    container_path = "/etc/prometheus"
    read_only      = true
  }
  volumes {
    volume_name    = docker_volume.prometheus_data.name
    container_path = "/prometheus"
  }
  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# Loki
# ---------------------------------------------------------------------------
resource "docker_image" "loki" {
  name = "grafana/loki:3.2.0"
}

resource "docker_volume" "loki_data" {
  name = "loki_data"
}

resource "docker_container" "loki" {
  name    = "rag-loki"
  image   = docker_image.loki.image_id
  command = ["-config.file=/etc/loki/loki-config.yml"]
  networks_advanced {
    name    = var.network_name
    aliases = ["loki"]
  }
  ports {
    internal = 3100
    external = 3100
  }
  volumes {
    host_path      = "${local.infra_root}/loki"
    container_path = "/etc/loki"
    read_only      = true
  }
  volumes {
    volume_name    = docker_volume.loki_data.name
    container_path = "/loki"
  }
  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# Grafana
# ---------------------------------------------------------------------------
resource "docker_image" "grafana" {
  name = "grafana/grafana:11.4.0"
}

resource "docker_volume" "grafana_data" {
  name = "grafana_data"
}

resource "docker_container" "grafana" {
  name  = "rag-grafana"
  image = docker_image.grafana.image_id
  env = [
    "GF_SECURITY_ADMIN_PASSWORD=admin",
    "GF_USERS_ALLOW_SIGN_UP=false",
  ]
  networks_advanced {
    name    = var.network_name
    aliases = ["grafana"]
  }
  ports {
    internal = 3000
    external = 3000
  }
  volumes {
    host_path      = "${local.infra_root}/grafana/datasources"
    container_path = "/etc/grafana/provisioning/datasources"
    read_only      = true
  }
  volumes {
    host_path      = "${local.infra_root}/grafana/dashboards"
    container_path = "/etc/grafana/provisioning/dashboards"
    read_only      = true
  }
  volumes {
    volume_name    = docker_volume.grafana_data.name
    container_path = "/var/lib/grafana"
  }
  restart    = "unless-stopped"
  depends_on = [docker_container.prometheus, docker_container.loki]
}

# ---------------------------------------------------------------------------
# Promtail — lê /var/run/docker.sock e bombeia logs JSON pro Loki.
# Sem porta exposta; comunicação interna na rede rag-network.
# ---------------------------------------------------------------------------
resource "docker_image" "promtail" {
  name = "grafana/promtail:3.2.0"
}

resource "docker_container" "promtail" {
  name    = "rag-promtail"
  image   = docker_image.promtail.image_id
  command = ["-config.file=/etc/promtail/promtail-config.yml"]
  networks_advanced {
    name = var.network_name
  }
  volumes {
    host_path      = "${local.infra_root}/promtail"
    container_path = "/etc/promtail"
    read_only      = true
  }
  volumes {
    host_path      = "/var/run/docker.sock"
    container_path = "/var/run/docker.sock"
    read_only      = true
  }
  restart    = "unless-stopped"
  depends_on = [docker_container.loki]
}
