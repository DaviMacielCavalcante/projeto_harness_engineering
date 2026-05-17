# samples/

Documentos de teste para o pipeline (ingestão + query).

## Você precisa adicionar um PDF aqui

O smoke test (`make smoke`) procura, por padrão, um arquivo em
`samples/exemplo.pdf`. Esse PDF **não vem no repositório de propósito**:
os documentos usados nos testes são obras de terceiros (artigos, capítulos,
apostilas) e não podem ser redistribuídos junto com o código.

Antes de rodar a aceitação (Task 15), coloque um PDF curto (1–5 páginas,
de preferência sobre engenharia de software) aqui:

```
samples/exemplo.pdf
```

Ou use outro arquivo passando `--file`:

```
uv run python scripts/smoke_test.py --file samples/o-seu-arquivo.pdf
```

## O que é versionado

- `samples/README.md` (este arquivo) e `samples/.gitkeep`.
- **Nada de `*.pdf`** — o `.gitignore` ignora `samples/*.pdf`. O corpus
  completo (~80 PDFs, B3) fica em `samples/corpus/`, também fora do git.
