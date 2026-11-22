# Sistema de comunicação: projeto de rádio digital (SDR)

Enlace digital simplex **ADALM-Pluto (TX) → RTL-SDR (RX)** com pacotes numerados e CRC-16, modulações OOK, 2-FSK, DBPSK e DQPSK implementadas em Python, código convolucional com Viterbi, e medição de goodput, PER, BER e banda a 99%.
Projeto Final de SCM22108 Sistemas de Comunicação, Engenharia Eletrônica, IFSC.

## Estado dos blocos

| Bloco | Conteúdo | Estado |
|---|---|---|
| 0 | Ambiente, repositório, portão de qualidade | concluído |
| 1 | Calibração do RTL-SDR (ppm e offset residual) | concluído: +84 ppm com o Pluto da equipe ([registro](docs/calibracao_rtl.md)) |
| 2 | Estudo e auditoria da OOK de referência no enlace real | concluído: PER 0% em 698 quadros, achados A17 a A19 ([registro](docs/etapa2_recepcao_ook.md), [auditoria](docs/auditoria_etapas_1_2.md)) |
| 3a | Quadro v2: sequência de 16 bits e CRC-16 (v3 com 24 bits no bloco 10) | concluído ([registro](docs/etapa3_quadro.md)) |
| 3b | OOK, 2-FSK e BPSK em simulação, pulsos RRC e gaussiano, banda a 99% | concluído ([registro](docs/etapa3_modulacoes.md)) |
| 3c | Receptor multiquadro: detecção com limiar, offset e instante por quadro, arquivo de saída | concluído ([registro](docs/etapa3_receptor.md)) |
| 3d | TX de prova: payloads do avaliador, fluxo ao Pluto, log do TX, PER e goodput | concluído em simulação ([registro](docs/etapa3_transmissor.md)) |
| 3e e 3f | Enlace real (bancada) e relatório | a fazer |
| 4 | Simulação do canal: BER × Eb/N0 contra a teoria, fase, offset e temporização | concluído ([registro](docs/etapa4_canal.md)) |
| 5 (software) | BER com sequência conhecida, banda a 99% e Eb/N0 da captura, referência simulada, protocolo de bancada | concluído; medições no ar a fazer ([registro](docs/etapa5_software.md)) |
| 6 | Receptor 3 vezes mais rápido, resultado idêntico | concluído ([registro](docs/etapa3_receptor.md), seção 10) |
| 7 | Prova A: maior taxa em 1 MHz; perfis de configuração | concluído em simulação ([registro](docs/etapa6_prova_a.md)) |
| 8 e 9 | Prova B: DBPSK de baixa taxa e código convolucional K = 7 | concluído em simulação ([prova B](docs/etapa6_prova_b.md), [FEC](docs/etapa6_fec.md)) |
| 10 | DQPSK (perfil `prova-a`, 1,2 Mbit/s de goodput) e quadro v3 | concluído em simulação ([registro](docs/etapa6_dqpsk.md)) |
| 11 e 12 | Viterbi em lote; emenda das caudas do RRC | concluído ([Viterbi](docs/etapa6_viterbi_lote.md), [emenda](docs/etapa6_emenda.md)) |
| 13 | Roteiro da prova e ensaio geral com os perfis finais | concluído ([roteiro](docs/roteiro_da_prova.md)) |
| 14 e 15 | Relatório final; auditoria de conformidade e correções | concluído ([relatório](docs/relatorio_final.md), [auditoria](docs/auditoria_final.md)) |
| bancada | Enlace no ar com o quadro v3, medições da Etapa 5, provas | a fazer ([plano](docs/plano_de_bancada.md)) |

O plano completo, com os requisitos numerados e a matriz de rastreabilidade, está em [docs/00_planejamento_e_auditoria.md](docs/00_planejamento_e_auditoria.md).

## Estrutura

```
docs/            planejamento, padrão de código, ambiente, registro de IA, especificação
referencia/      códigos do professor, sem nenhuma alteração
sdrlink/         pacote Python do projeto
scripts/         programas para rodar (calibrar, transmitir, gravar, processar, avaliar)
ensaios/         scripts dos ensaios de cada etapa, que geram os registros de dados/logs
tests/           testes automáticos (pytest)
ferramentas/     portão de qualidade (verificar.py) e gerador dos relatórios em PDF
configs/         calibração do RTL (rtl.toml) e perfis de enlace (perfis.toml)
dados/           capturas IQ fora do git; registros JSON e logs de ensaio e de calibração versionados
entregas/        relatórios em PDF de cada etapa e o relatório final
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
