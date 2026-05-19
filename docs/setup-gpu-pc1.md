# Runbook — GPU NVIDIA no PC1 (driver + Container Toolkit)

Procedimento manual para habilitar a GPU do PC1 dentro de containers Docker, que
é a pré-condição para o **Ollama servir `qwen2.5:7b` + `nomic-embed-text` acelerado**
no Modo 1 e no Modo 2.

- **Pré-condição rastreada:** `[A]` do B1 no [`TODO.md`](../TODO.md) — *"GPU NVIDIA + nvidia-container-toolkit no PC1"*.
- **Spec relacionada:** [§2 / §16](superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md) — GPU é só do PC1; PC2/PC3 chamam o Ollama do PC1 via Tailscale.
- **Doc irmão:** [`setup-tailscale.md`](setup-tailscale.md) — mesma filosofia de runbook (spec-antes-de-código).
- **Automação futura:** este manual é a especificação da role Ansible `nvidia` do B3 (só PC1).

> **Por que este runbook existe:** sem a GPU, a stack subia só pela metade —
> infra (redis/qdrant/rabbitmq) OK, mas `ollama`/`gateway`/workers não iniciavam,
> e a **Task 15 (smoke ponta-a-ponta) do B1 ficou bloqueada**. Habilitar a GPU
> destravou o smoke (122 chunks, 3 citações).

---

## 0. Ambiente alvo (fatos reais deste PC1)

| Item | Valor |
|---|---|
| OS | Linux Mint 22.3 (base Ubuntu `noble` = 24.04 LTS) |
| GPU | NVIDIA GeForce RTX 4060 Ti |
| Driver instalado | `595.58.03` (proprietário) |
| nvidia-container-toolkit | `1.19.0-1` (+ `-base` `1.19.0-1`) |
| Ollama (compose) | `ollama/ollama:0.23.2`, container `rag-ollama`, profiles `all`/`server` |

Como Mint 22.3 é base **noble**, todos os repositórios/pacotes são os de
**Ubuntu 24.04** — usar os repos `noble` da NVIDIA, não os de Mint.

---

## 1. Pré-requisitos

- [ ] Docker e Docker Compose v2 já instalados e funcionando (`docker run hello-world`).
- [ ] Acesso `sudo`.
- [ ] GPU NVIDIA fisicamente presente (`lspci | grep -i nvidia`).

---

## 2. Driver proprietário NVIDIA

> ⬜ A PREENCHER: confirmar o caminho usado neste PC1 — *Gerenciador de Drivers*
> do Mint (GUI `mintdrivers`) **ou** `ubuntu-drivers` por CLI. O resultado final
> verificado foi driver **595.58.03**.

Caminho CLI (Ubuntu 24.04 / noble):
```bash
ubuntu-drivers devices              # lista drivers recomendados
sudo ubuntu-drivers autoinstall     # ou: sudo apt install nvidia-driver-<versão>
sudo reboot
```
Validar no host após reboot:
```bash
nvidia-smi    # deve listar a RTX 4060 Ti e o driver 595.58.03
```

---

## 3. NVIDIA Container Toolkit

Repositório oficial (libnvidia-container) — vale para Ubuntu 24.04/noble:
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit       # alvo verificado: 1.19.0-1

# Liga o runtime nvidia no Docker e reinicia o daemon
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Validar o toolkit isolado (fora do projeto):
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu24.04 nvidia-smi
```
Deve imprimir a mesma tabela do `nvidia-smi` do host, **de dentro do container**.

---

## 4. Verificação no contexto do projeto

O serviço `ollama` no [`docker-compose.yml`](../docker-compose.yml) **já declara**
o acesso à GPU (não precisa editar):

```yaml
  ollama:
    image: ollama/ollama:0.23.2
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Subir só o Ollama e confirmar que ele enxerga a GPU:
```bash
docker compose --profile server up -d ollama
docker exec rag-ollama nvidia-smi      # deve listar a RTX 4060 Ti
docker logs rag-ollama | grep -i "gpu\|cuda"   # Ollama loga detecção da GPU no boot
```

Critério de aceite da pré-condição `[A]` — smoke ponta-a-ponta:
```bash
make dev && make pull-models && make smoke
```
Esperado (resultado real de 2026-05-18): resposta fundamentada, 3 citações,
122 chunks indexados.

---

## 5. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `nvidia-smi` falha no host pós-install | Driver não carregou / faltou reboot | `sudo reboot`; checar Secure Boot (driver não-assinado bloqueado pelo MOK) |
| `docker run --gpus all` → `could not select device driver` | Toolkit instalado mas runtime não configurado | `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| `rag-ollama` sobe mas usa CPU (lento) | Container sem acesso à GPU | Confirmar bloco `deploy.resources.reservations.devices` no compose e toolkit OK (§3) |
| Stack sobe infra mas `ollama`/`gateway`/workers não | Exatamente o bug que motivou este runbook | Seguir §2→§4 na ordem |
| Secure Boot bloqueia o módulo NVIDIA | UEFI Secure Boot ativo | Enrolar a chave MOK no install do driver **ou** desabilitar Secure Boot na UEFI |

> ⬜ A PREENCHER: se algo travou neste PC1 especificamente (ex.: MOK/Secure Boot,
> conflito com driver `nouveau`), registrar aqui o sintoma e a solução real.

---

## 6. Mapeamento para a role Ansible `nvidia` (B3, só PC1)

A automação deve reproduzir, idempotente e **apenas no host PC1**:
- instalar driver proprietário (versão pinada ou recomendada);
- adicionar repo + instalar `nvidia-container-toolkit`;
- `nvidia-ctk runtime configure --runtime=docker` + restart do Docker;
- task de verificação: `docker run --rm --gpus all ... nvidia-smi` como gate pós-deploy.

> ⬜ A PREENCHER pelo trio durante o B3 conforme a role for escrita.
