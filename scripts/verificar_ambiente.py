"""Mostra o diagnóstico do ambiente: Python, bibliotecas, RTL-SDR e Pluto.

Uso (com o .venv ativo, na raiz do repositório):
    python scripts/verificar_ambiente.py

Sai com código 0 se tudo estiver pronto e 1 se faltar alguma coisa.
"""

import sys

from sdrlink.ambiente import diagnosticar, formatar


def main() -> int:
    """Executa o diagnóstico e imprime a tabela."""
    itens = diagnosticar()
    print(formatar(itens))
    faltando = [item.nome for item in itens if not item.ok]
    if faltando:
        print(f"\nFalta preparar: {', '.join(faltando)}")
        return 1
    print("\nAmbiente 100% pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
