# Sistema de comunicação: projeto de rádio digital (SDR)

Enlace digital simplex **ADALM-Pluto (TX) → RTL-SDR (RX)** com pacotes numerados e CRC, modulações OOK, 2-FSK e BPSK implementadas em Python, e medição de goodput, PER, BER e banda a 99%.
Projeto Final de SCM22108 Sistemas de Comunicação, Engenharia Eletrônica, IFSC.

## Estado dos blocos

| Bloco | Conteúdo | Estado |
|---|---|---|
| 0 | Ambiente, repositório, portão de qualidade | concluído |
| 1 | Calibração do RTL-SDR (ppm e offset residual) | concluído: 0 ppm, resíduo cerca de −44 Hz ([registro](docs/calibracao_rtl.md)) |
| 2 | Estudo e auditoria da OOK de referência no enlace real | a fazer |

O plano completo, com os requisitos numerados e a matriz de rastreabilidade, está em [docs/00_planejamento_e_auditoria.md](docs/00_planejamento_e_auditoria.md).

## Estrutura

```
docs/            planejamento, padrão de código, ambiente, registro de IA, especificação
referencia/      códigos do professor, sem nenhuma alteração
sdrlink/         pacote Python do projeto
scripts/         programas para rodar (calibrar, transmitir, gravar, processar)
tests/           testes automáticos (pytest)
ferramentas/     portão de qualidade (verificar.py)
configs/         arquivos de configuração dos ensaios
dados/           capturas IQ e logs (fora do git; só o índice é versionado)
```

## Preparar o ambiente

Passo a passo completo (Windows e Fedora) em [docs/ambiente.md](docs/ambiente.md). Resumo no Windows:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install -e .
git config core.hooksPath .githooks
```

## Comandos do dia a dia

```powershell
.venv\Scripts\Activate.ps1               # ativa o ambiente
python scripts/verificar_ambiente.py      # confere bibliotecas, RTL-SDR e Pluto
python ferramentas/verificar.py           # portão de qualidade (roda sozinho a cada commit)
pytest -m hardware                        # testes que precisam do hardware conectado
```

## Como trabalhamos

Regras de código (inspiradas no "Power of 10" da NASA/JPL), fluxo de branches, mensagens de commit e critério de "pronto" em [docs/padrao_de_codigo.md](docs/padrao_de_codigo.md).
O uso de IA de cada etapa fica registrado em [docs/registro_ia.md](docs/registro_ia.md), como o professor exige.
