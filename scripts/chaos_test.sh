#!/usr/bin/env bash
set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8000}"
OUT_DIR="${OUT_DIR:-data/exp4}"
OUT_FILE="${OUT_FILE:-${OUT_DIR}/chaos.txt}"

mkdir -p "$OUT_DIR"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$OUT_FILE"
}

query_once() {
  local question="${1:-Sobre o que fala o corpus?}"
  curl -sS -X POST "${GATEWAY}/query" \
    -H 'Content-Type: application/json' \
    -d "{\"question\":\"${question}\",\"top_k\":3}" \
    -o /dev/null \
    -w 'status=%{http_code} time=%{time_total}\n'
}

: > "$OUT_FILE"
log "chaos.start gateway=${GATEWAY}"

log "H1 stop rag-ingest-worker-chunk"
docker stop rag-ingest-worker-chunk | tee -a "$OUT_FILE"
sleep 5
docker start rag-ingest-worker-chunk | tee -a "$OUT_FILE"
log "H1 done"

log "H2 stop rag-ollama"
docker stop rag-ollama | tee -a "$OUT_FILE"
set +e
query_once "Teste de resiliencia com Ollama parado" | tee -a "$OUT_FILE"
set -e
docker start rag-ollama | tee -a "$OUT_FILE"
log "H2 done"

log "H3 burst queries"
for i in $(seq 1 10); do
  query_once "Pergunta concorrente ${i} sobre engenharia de software" >> "$OUT_FILE" &
done
wait
log "H3 done"

log "chaos.done out=${OUT_FILE}"
cp "$OUT_FILE" data/b3-chaos.txt
