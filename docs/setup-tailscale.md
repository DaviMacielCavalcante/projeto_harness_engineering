# Runbook — Tailscale (rede do projeto, Modo 2)

Procedimento manual para colocar os 3 PCs do trio no mesmo tailnet privado,
que é a base do **Modo 2 distribuído** (PC2/PC3 rodam workers que falam com o
PC1 via Tailscale).

- **Pré-condição rastreada:** `[C]` do B1 no [`TODO.md`](../TODO.md) — *"Tailscale instalado e autenticado nos 3 PCs"*.
- **Spec relacionada:** [§9.1 Modos de execução](superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md) e §16 (risco "Tailscale flaky").
- **Automação futura:** este manual é a especificação da role Ansible `tailscale` do B3 (ver [`b3-tolerancia-iac-modo2.md`](superpowers/plans/2026-05-09-tema5-b3-tolerancia-iac-modo2.md)). Tudo que está aqui como passo manual deve virar task idempotente da role.

---

## 0. Decisão de tailnet — a pegadinha do domínio CESUPA

> ⚠️ **Leia isto antes de qualquer comando.** Foi o erro que custou tempo na primeira tentativa.

Contas Google `@aluno.cesupa.br` são de um **Google Workspace de domínio único**. O
Tailscale agrupa automaticamente **todo usuário do mesmo domínio no mesmo tailnet**.
Resultado da primeira tentativa: ao logar com a conta CESUPA, o PC1 caiu num
tailnet **compartilhado da turma** (~10 devices de ~7 alunos), com exposição
indevida dos serviços sem-auth do PC1 (Redis, RabbitMQ `guest:guest`, Qdrant, Ollama).

**Decisão adotada (trio):** tailnet **dedicado**, criado/possuído por uma
**identidade fora do domínio cesupa** (Gmail/GitHub pessoal). Quem dá `logout`
e loga de novo com a conta CESUPA **volta ao tailnet da turma** — não funciona.

| Item | Valor |
|---|---|
| Modelo | Tailnet dedicado do trio (plano grátis Personal: 3 usuários / 100 devices) |
| Owner | `DaviMacielCavalcante@` (identidade pessoal, **não** `@aluno.cesupa.br`) |
| Onboarding PC2/PC3 | Auth key reutilizável (sem conta/navegador por colega) |
| Nome estável do servidor | `pc1-davi` via **MagicDNS** (o IP muda ao trocar de tailnet — não confiar em IP) |

---

## 1. Pré-requisitos

- [ ] Owner tem uma identidade **não-CESUPA** (Gmail ou GitHub pessoal).
- [ ] Cada PC com acesso de admin/sudo.
- [ ] Colegas do PC2/PC3 são Windows 11 (confirmado nesta turma). Linux coberto como alternativa.

---

## 2. Procedimento — PC1 (servidor, owner)

1. **Criar/entrar no tailnet dedicado** em janela anônima: `https://login.tailscale.com`, autenticar com a identidade **pessoal**.
2. **Migrar o PC1** (se ele já esteve em outro tailnet, ex. o da turma):
   ```bash
   sudo tailscale logout
   sudo tailscale up --hostname=pc1-davi
   ```
   Na URL de auth impressa no terminal (o comando **bloqueia de propósito** até concluir no navegador), logar com a conta **pessoal**, não a CESUPA.
3. **Confirmar tailnet limpo:**
   ```bash
   tailscale status     # deve listar SÓ pc1-davi
   tailscale ip -4
   ```

## 3. Procedimento — PC2/PC3 (workers, colegas)

1. **Owner gera auth key reutilizável:** `https://login.tailscale.com/admin/settings/keys` → *Generate auth key* → **Reusable** ✓, *Ephemeral* off. Enviar no privado (é credencial).

### Windows 11
```powershell
winget install --id tailscale.tailscale -e
# PowerShell COMO ADMINISTRADOR:
tailscale up --authkey=<TSKEY> --hostname=pc2-<colega>
# se "comando não reconhecido" (PATH não atualizou):
& "C:\Program Files\Tailscale\tailscale.exe" up --authkey=<TSKEY> --hostname=pc2-<colega>
tailscale status
```

### Linux (alternativa)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=<TSKEY> --hostname=pc2-<colega>
tailscale status
```

> O hostname que o colega escolher (ex.: `pc2-jm`) é indiferente: o `.env.distributed`
> aponta para o **servidor `pc1-davi`**, nunca para os workers.

## 4. Endurecimento (owner, no admin console)

- [ ] **MagicDNS ON** — `admin/dns`. Sem isso `pc1-davi` não resolve por nome.
- [ ] **Disable key expiry** nos 3 devices — `admin/machines` → ⋯. Evita logout no meio do sprint/demo.
- [ ] ACL default já é trio-fechado (nada da turma) — fecha a limitação de exposição do §17 do spec.

---

## 5. Verificação (critério de aceite da pré-condição `[C]`)

De **cada** PC, contra os outros dois:
```bash
tailscale status                 # 3 peers, todos online
tailscale ping pc1-davi          # e ping recíproco entre todos
```
Sucesso = rota **`direct`** (`pong ... via 100.x.y.z:porta`).
Relay (`via DERP(...)`) funciona mas é lento e **contamina os experimentos de
latência/throughput do B4** — tratar como falha a investigar.

---

## 6. Estado atual

> Atualizar conforme o trio conecta.

| PC | Papel | Hostname | Online | Ping recíproco | Resultado |
|---|---|---|---|---|---|
| PC1 | servidor (GPU, owner) | `pc1-davi` | ✅ | — | IP `100.117.1.33` (instável — usar MagicDNS) |
| PC2 | worker | `pc2-jm` | ✅ | ✅ (PC1↔PC2) | **direct** (`via [IPv6]:porta`, não DERP) — ~113ms em 2026-05-18 |
| PC3 | worker | `pc3-<colega>` | ⏳ pendente | ⏳ | ⬜ A PREENCHER: colega não pôde em 2026-05-18; data real de entrada |

`[C]` do B1 só fecha com os **3** online e ping **direct** recíproco.

> **Piso de latência (achado real, 2026-05-18):** o ping PC1↔PC2 é *direct*,
> mas sai por **IPv6 público** (prefixo `2804::/16`, BR/LACNIC) — os PCs não
> estão na mesma LAN, e sim em locais físicos distintos via internet. RTT
> observado ~113ms (primeiro ping; confirmar regime estável). Não é relay, não
> é bug: é a topologia real. **Consequência:** todo round trip worker→PC1
> (embed Ollama, `search` Qdrant, hop RabbitMQ) paga esse piso. Carregar para
> o doc técnico §8 (limitações) e usar como contexto dos experimentos do B4
> (latência/throughput terão esse floor embutido).
> ⬜ A PREENCHER: RTT de regime estável após múltiplos pings; idem PC1↔PC3.

---

## 7. `.env.distributed` (consumido por PC2/PC3)

Arquivo **gitignored** (só `.env.example` vai pro repo). Nos workers, usar o
**nome MagicDNS**, não IP:

```bash
RABBITMQ_URL=amqp://guest:guest@pc1-davi:5672/
OLLAMA_URL=http://pc1-davi:11434
GENERATION_MODEL=qwen2.5:7b-instruct
EMBEDDING_MODEL=nomic-embed-text
QDRANT_URL=http://pc1-davi:6333
QDRANT_COLLECTION=se_corpus
REDIS_URL=redis://pc1-davi:6379/0
RERANK_URL=http://pc1-davi:8081
LOG_LEVEL=INFO
SERVICE_NAME=unset
```
O PC1 **não** usa `.env.distributed` no lado servidor — `docker compose --profile server up` usa o DNS interno do compose.

---

## 8. Plano B (spec §16 — Tailscale flaky)

Se algum colega ficar preso em `relay` ou sem rota:
1. Túnel reverso `ssh -R` PC_worker → PC1 expondo as portas dos serviços.
2. Pior caso: demo só com containers no PC1 (ainda atende req 4.1, com nota nas limitações).

> ⬜ A PREENCHER: se acionado, registrar aqui qual rede travou e o que resolveu.

---

## 9. Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `status` mostra dezenas de devices de outros alunos | Logou com conta `@aluno.cesupa.br` (tailnet de domínio da turma) | `tailscale logout` e relogar com identidade **pessoal** (§0) |
| Terminal "travado" na URL após `tailscale up` | Comportamento normal: bloqueia até auth no navegador | Abrir a URL impressa, autenticar; **não** dar Ctrl+C |
| IP do PC1 mudou e quebrou config | Trocou de tailnet → nova alocação de IP | Usar nome MagicDNS `pc1-davi`, nunca IP cru (§7) |
| Windows: `tailscale` não reconhecido | PATH não atualizou pós-install | Caminho completo `C:\Program Files\Tailscale\tailscale.exe` (§3) |
| Ping responde mas `via DERP(...)` | NAT/firewall na rede do peer impede hole punching | Investigar firewall/UPnP do roteador do colega; senão Plano B (§8) |

---

## 10. Mapeamento para a role Ansible `tailscale` (B3)

A automação deve reproduzir, idempotente:
- instalar Tailscale (apt no Linux dos hosts gerenciados);
- `tailscale up` com auth key vinda do Ansible vault (`--authkey`), `--hostname` por host do inventory;
- garantir MagicDNS/expiry via API do admin (ou documentar como passo manual one-time do owner);
- só no PC1: nada extra de Tailscale (GPU/NVIDIA é outra role).

> ⬜ A PREENCHER pelo trio durante o B3 conforme a role for escrita.
