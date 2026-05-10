"""Configuração compartilhada de testes.

Adiciona a raiz do projeto ao sys.path para que `import src.*` funcione
sem precisar instalar o projeto como pacote (alinhado com `[tool.uv] package = false`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
