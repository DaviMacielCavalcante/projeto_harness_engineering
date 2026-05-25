# Prompts e Ferramentas de Contexto

Este apêndice registra os artefatos versionados usados pelo query-worker.

## Arquivos

| Arquivo | Papel |
|---|---|
| `prompts/system_qa_pt.md` | System prompt em PT-BR, com política de responder apenas pelo contexto e usar `cite_source`. |
| `prompts/system_qa_en.md` | Equivalente em inglês. |
| `prompts/user_qa_template.md` | Template Jinja2 que injeta blocos recuperados e pergunta. |
| `prompts/tools/cite_source.json` | Definição da tool de citação estruturada. |

## Versão atual

Os prompts de sistema estão na versão `0.2.3-b2`, resultado das tentativas de
aumentar aderência ao function calling:

1. Regra híbrida tool + fallback textual.
2. Instrução imperativa para chamar a ferramenta.
3. Separação system/user via `/api/chat`.
4. Remoção do escape textual no prompt.
5. Exemplo few-shot da chamada `cite_source`.

## Política de resposta

O modelo deve:

- responder apenas com base nos blocos de contexto fornecidos;
- declarar ausência de evidência quando o corpus não cobre a pergunta;
- responder no idioma do usuário;
- ser conciso;
- citar fontes por `doc_id`, `page` e `snippet`.

## Achado operacional

A tool `cite_source` está cabeada e funciona em diagnóstico isolado, mas o
modelo não a chama de forma consistente quando recebe contexto RAG denso. Por
isso o query-worker mantém fallback estrutural: quando não há `tool_calls`, as
citações são derivadas diretamente dos chunks reranqueados que entraram no
prompt.

## Montagem de contexto

O query-worker monta mensagens com:

- system prompt por idioma (`pt` ou `en`);
- blocos `[doc_id | source | page]` no template de usuário;
- histórico/resumo de sessão quando `session_id` existe;
- truncamento de cauda quando o orçamento de contexto é excedido.
