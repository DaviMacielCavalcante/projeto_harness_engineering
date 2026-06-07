host_role = "server"
image_tag = "0.1.0-b3"

# Exp 3 (bônus): descomente para subir o vLLM e mover o Ollama p/ CPU (libera a
# GPU de 8GB inteira). Aplique, espere o vLLM responder em :8002, e só então
# aplique o pc2.tfvars com inference_backend="vllm". Reverta (comente) depois.
# enable_vllm = true
