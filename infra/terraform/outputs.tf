output "host_role" {
  value = var.host_role
}

output "network_name" {
  value = docker_network.rag_net.name
}
