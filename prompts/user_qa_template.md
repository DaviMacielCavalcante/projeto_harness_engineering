---
version: 0.2.0-b2
model_target: qwen2.5:7b-instruct
last_changed: 2026-05-21
---
# Contexto

{% for c in context_blocks -%}
[doc_id: {{ c.doc_id }} | source: {{ c.source }} | page: {{ c.page or "n/a" }}]
{{ c.text }}

{% endfor %}
# Pergunta

{{ question }}

# Resposta
