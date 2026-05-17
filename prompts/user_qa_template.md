---
version: 0.1.0-b1
model_target: qwen2.5:7b-instruct
last_changed: 2026-05-09
---

# Contexto

{% for c in context_blocks -%}
[source: {{ c.source }}, page: {{ c.page or "n/a" }}]
{{ c.text }}

{% endfor %}
# Pergunta

{{ question }}

# Resposta
