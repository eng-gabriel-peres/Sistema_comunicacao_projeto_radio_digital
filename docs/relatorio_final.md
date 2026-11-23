# Relatório final: enlace digital ADALM-Pluto → RTL-SDR

SCM22108, Sistemas de Comunicação (IFSC). Gabriel de Oliveira Peres, matrícula 201920800001.

Estado em 22/11/2026, depois do bloco 18: **tudo o que dá para fazer sem hardware está feito e validado em simulação**, e o projeto passou por uma auditoria completa contra o enunciado ([auditoria_final.md](auditoria_final.md)). Falta a bancada: o enlace com o quadro novo no ar, as medições da Etapa 5 e as provas. Este documento junta todos os blocos: o que cada um fez, o que funcionou, o que falhou e como foi corrigido, e o que dá para melhorar. Os detalhes de cada bloco estão nos documentos que vêm depois deste, no mesmo relatório.

## 1. Resumo

| Item | Resultado |
|---|---|
| Prova A (maior goodput) | perfil `prova-a`: **DQPSK, RRC β = 0,25, 1 365 kbit/s no ar**, caudas emendadas. Na prova de 60 s simulada com os comandos da prova: **1 217,8 kbit/s de goodput**, PER de 0,003%, banda a 99% de 748,6 kHz, RX em 75 s |
| Reservas da prova A | `prova-a-fec` (DQPSK com FEC: 626 kbit/s com 12,9 dB de margem estimada na bancada) e `prova-a-dbpsk` (625 kbit/s, 9,6 dB); regra de troca objetiva no roteiro |
| Perfis experimentais | `prova-a-8psk`: **8-PSK coerente, 1 778,5 kbit/s** na prova de 60 s simulada (+46%), na mesma banda; pede 2,8 dB a mais de C/N0 e tolera 100 vezes menos ruído de fase que a DQPSK, por isso depende da bancada ([etapa6_8psk.md](etapa6_8psk.md)). `prova-a-24`: DQPSK com o RTL a 2,4 MS/s, **1 427 kbit/s** (+17%); depende de dois testes de bancada ([etapa6_taxa_24.md](etapa6_taxa_24.md)) |
| Robustez | todos os perfis aguentam **±50 ppm** de diferença de relógio entre o Pluto e o RTL (esperado depois da calibração: cerca de 2 ppm); opção `--pre-gerar` contra o risco de o Python não alimentar o Pluto a tempo ([etapa6_robustez.md](etapa6_robustez.md)); o ruído de fase real do par Pluto + RTL, medido nos tons de 04/11, não tem efeito detectável em nenhum perfil, e o ADC de 8 bits não custa nada de −30 a −6 dBFS ([etapa6_imperfeicoes.md](etapa6_imperfeicoes.md)) |
| Prova B (maior alcance) | perfil `prova-b`: **DBPSK com código convolucional K = 7, 25,6 kbit/s no ar**: goodput de 11,8 kbit/s, 500 pacotes em 43 s, **C/N0 necessário de 48,2 dB-Hz** com o limiar de detecção de 0,4 (bloco 19), cerca de 25 dB menos que o `prova-a` com DQPSK (cerca de 20 dB menos que o `prova-a-dbpsk`): cerca de 18 vezes a distância no espaço livre |
| Comparação com a OOK de referência | a referência entrega **7,3 kbit/s** no ar (21 bytes por quadro, 10 kbit/s, pulso retangular; captura real de 04/11). O `prova-a` chega a **1 218 kbit/s em simulação**, na mesma banda de 1 MHz. **Os dois números não vêm das mesmas condições** (um é medido, o outro simulado), e o enunciado pede a melhoria medida nas mesmas condições: essa medição é da bancada |
| Simulação × teoria | BER de BPSK, DBPSK, DQPSK e 2-FSK a menos de 0,08 dB das fórmulas; a DQPSK bate com a fórmula exata (Marcum) a 0,5% |
| Qualidade | 246 testes automáticos; portão (ruff, mypy --strict, regras NASA, pytest) em todo commit; testes de mutante em cada decisão; 25 tags, uma ou mais por bloco (de `bloco-00` a `bloco-18`); toda evidência com a versão do código que a gerou |
| Falta | bancada: o enlace no ar com o quadro v3, as medições da Etapa 5 e as provas; **10 a 13 h em 4 sessões** ([plano_de_bancada.md](plano_de_bancada.md)); e o registro de uso de IA |

## 2. O sistema

```
arquivo do avaliador ─► transmitir.py ─► Pluto ─► ar ─► RTL ─► gravar_iq.py ─► captura IQ
     (128 bytes)          │  quadro v3                        2,048 MS/s          │
                          │  FEC (opcional)                   +84 ppm             ▼
                          │  DQPSK / DBPSK / OOK / 2-FSK                   receber.py ─► saída
                          │  RRC ou gaussiano                                  │       (sequência,
                          ▼                                                    │        payload)
                    log do TX ──────────────────► avaliar.py ◄─────────────────┘
                                                  PER e goodput (seção 7)
```

| Bloco do sistema | O que faz | Módulo |
|---|---|---|
| Quadro v3 | preâmbulo de 16 bits, Barker-13, comprimento (8), **sequência (24)**, payload, CRC-16/CCITT sobre comprimento, sequência e payload, guarda de 16 bits: 1 117 bits para 128 bytes | `sdrlink/quadro.py` |
| Código | convolucional K = 7, taxa 1/2 (171, 133), Viterbi com decisão suave, em lote | `sdrlink/codigo.py` |
| Modulação | OOK, BPSK, DBPSK, **DQPSK** (corpo com 2 bits por símbolo) e 2-FSK de fase contínua; pulsos RRC e gaussiano | `sdrlink/modem.py`, `sdrlink/pulsos.py` |
| TX | payloads do avaliador, numeração, fluxo em blocos para o Pluto, caudas emendadas, log do TX, conferência da faixa de 915 a 928 MHz | `sdrlink/transmissor.py`, `sdrlink/hw/pluto_tx.py` |
| RX | gravação sem perda de amostras; detecção pela correlação coerente do prefixo numa grade de offsets; offset e instante por quadro; demodulação; FEC em lote; arquivo de saída | `sdrlink/hw/rtl_rx.py`, `sdrlink/receptor.py` |
| Medição | PER e goodput (seção 7), BER com sequência conhecida, banda a 99% (com marcação de confiança) e Eb/N0 da captura, faixa plana do RTL | `sdrlink/metricas.py`, `sdrlink/medicao.py` |
| Configuração | perfis com nome, os mesmos no TX, na gravação e no RX | `configs/perfis.toml`, `sdrlink/config.py` |

## 3. Linha do tempo

| Bloco | Tag | O que entregou | Documento |
|---|---|---|---|
| 0 e 1 | `bloco-01` | ambiente, repositório, portão de qualidade, calibração do RTL (+77 ppm com o Pluto do professor) | [calibracao_rtl.md](calibracao_rtl.md) |
| 2 | `bloco-02` | recalibração com o Pluto da equipe (**+84 ppm**); OOK de referência no ar: **698 de 698 quadros**; leitura assíncrona sem perda (A17) | [etapa2_recepcao_ook.md](etapa2_recepcao_ook.md), [auditoria_etapas_1_2.md](auditoria_etapas_1_2.md) |
| 3a | `bloco-03a` | quadro v2: sequência e CRC-16, com a escolha do CRC justificada | [etapa3_quadro.md](etapa3_quadro.md) |
| 3b | `bloco-03b` | OOK, BPSK, DBPSK e 2-FSK em simulação; RRC e gaussiano escolhidos pela banda | [etapa3_modulacoes.md](etapa3_modulacoes.md) |
| 3c | `bloco-03c` | receptor multiquadro: 698/698 na captura real, perda de implementação de 0 a 0,3 dB | [etapa3_receptor.md](etapa3_receptor.md) |
| 3d | `bloco-03d` | transmissor de prova, log do TX, PER e goodput pela regra do enunciado | [etapa3_transmissor.md](etapa3_transmissor.md) |
| 4 | `bloco-04` | canal: AWGN, fase, offset e temporização contra a teoria; a BPSK do projeto é a DBPSK | [etapa4_canal.md](etapa4_canal.md) |
| 5 (software) | `bloco-05-software` | BER com sequência conhecida, banda e Eb/N0 da captura, protocolo de bancada; A22 e A23 | [etapa5_software.md](etapa5_software.md) |
| 6 | `bloco-06` | receptor 3 vezes mais rápido, resultado idêntico | [etapa3_receptor.md](etapa3_receptor.md), seção 10 |
| 7 | `bloco-07` | prova A: maior taxa que cabe em 1 MHz (682,7 kbit/s); perfis de configuração | [etapa6_prova_a.md](etapa6_prova_a.md) |
| 8 | `bloco-08` | prova B sem código: DBPSK a 12,8 kbit/s, 17,3 dB mais sensível | [etapa6_prova_b.md](etapa6_prova_b.md) |
| 9 | `bloco-09` | FEC convolucional: prova B com 2,9 dB a menos de C/N0 | [etapa6_fec.md](etapa6_fec.md) |
| 10 | `bloco-10` | DQPSK: 1,93 vez o goodput; **quadro v3** (sequência de 24 bits) | [etapa6_dqpsk.md](etapa6_dqpsk.md) |
| 11 | `bloco-11` | Viterbi em lote, 8 vezes mais rápido; DQPSK com FEC como reserva | [etapa6_viterbi_lote.md](etapa6_viterbi_lote.md) |
| 12 | `bloco-12` | caudas do RRC emendadas: +2,1% de goodput na DQPSK | [etapa6_emenda.md](etapa6_emenda.md) |
| 13 | `bloco-13` | roteiro da prova e ensaio geral com os quatro perfis finais | [roteiro_da_prova.md](roteiro_da_prova.md) |
| 14 | `bloco-14-rev2` | este relatório final consolidado | este documento |
| 15 | `bloco-15` | auditoria completa contra o enunciado, do código e dos documentos; correções; plano de bancada | [auditoria_final.md](auditoria_final.md), [plano_de_bancada.md](plano_de_bancada.md) |
| 16 | `bloco-16` | diferença de relógio de amostragem (±50 ppm sem perda em todos os perfis) e opção de gerar o sinal todo antes de transmitir (risco R1) | [etapa6_robustez.md](etapa6_robustez.md) |
| 17 | `bloco-17` | perfil experimental a 2,4 MS/s: 1 427 kbit/s (+17%) em simulação; ferramenta da faixa plana do RTL | [etapa6_taxa_24.md](etapa6_taxa_24.md) |
| 18 | `bloco-18` | fechamento: relatório final e PDFs atualizados | este documento |
| 19 | `bloco-19` | limiar de detecção de 0,4 na prova B com FEC: de 0,4 a 1 dB a mais de alcance | [etapa6_limiar.md](etapa6_limiar.md) |
| 20 | `bloco-20` | análise automática da sessão de bancada: tabela, gráfico e perda do enlace; sessão simulada com os scripts da bancada (perda mediana de +0,07 dB) | [etapa5_analise_bancada.md](etapa5_analise_bancada.md) |
| 21 | `bloco-21` | imperfeições do hardware: ruído de fase real do par sem efeito detectável (folga de 16 a 31 vezes), janela do ADC de 8 bits (−30 a −6 dBFS) com aviso no `gravar_iq.py` e no `receber.py`, medida do tom na bancada | [etapa6_imperfeicoes.md](etapa6_imperfeicoes.md) |
| 22 | `bloco-22` | revisão dos documentos pelos blocos 19 a 21; a fase real dentro de um quadro (números corrigidos no bloco 23) | este documento |
| 23 | `bloco-23` | viabilidade da 8-PSK coerente na prova A (+48% de goodput, 2,8 dB a mais de C/N0); defeito na trajetória de fase achado e corrigido, ensaios dos blocos 21 e 22 refeitos | [etapa6_8psk.md](etapa6_8psk.md) |
| 24 | `bloco-24` | 8-PSK coerente no receptor (malha de fase, mapa de Gray corrigido) e perfil experimental `prova-a-8psk`: 1 778,5 kbit/s na prova de 60 s simulada | [etapa6_8psk.md](etapa6_8psk.md) |

## 4. Resultados finais (ensaio geral, sem hardware)

A prova de 60 s simulada com cada perfil final, pelos comandos da prova, no canal com os defeitos medidos do enlace real (offset de −1,4 kHz, atraso fracionário, DC, imagem IQ a −45 dBc), de 1,5 a 2 dB acima do Eb/N0 necessário:

| Perfil | Certos / transmitidos | PER | Goodput | Banda medida | RX para 61,5 s |
|---|---|---|---|---|---|
| `prova-a` (DQPSK) | 71 357 / 71 359 | 0,003% | **1 217,8 kbit/s** | 748,6 kHz | 74,5 s |
| `prova-a-fec` (DQPSK com FEC) | 36 703 / 36 703 | 0 | 626,4 kbit/s | 750,0 kHz | 89,1 s |
| `prova-a-dbpsk` (DBPSK) | 36 631 / 36 637 | 0,016% | 625,2 kbit/s | 749,2 kHz | 65,6 s |
| `prova-b` (DBPSK com FEC) | 694 / 694 | 0 | 11,8 kbit/s | 30 kHz no TX (a medida da captura não vale com sinal tão fraco, seção 6) | 25,2 s |

**Sensibilidade de cada configuração** (C/N0 necessário para PER de 1%, receptor completo):

| Configuração | C/N0 necessário | Margem pela bancada de 04/11 (78,3 dB-Hz) |
|---|---|---|
| 8-PSK coerente 2 048 kbit/s (`prova-a-8psk`) | 76,2 dB-Hz | 2,1 dB |
| DQPSK 1 365 kbit/s (`prova-a`) | 73,4 dB-Hz | 4,9 dB |
| DBPSK 682,7 kbit/s (`prova-a-dbpsk`) | 68,7 dB-Hz | 9,6 dB |
| DQPSK com FEC (`prova-a-fec`) | 65,4 dB-Hz | 12,9 dB |
| DBPSK 12,8 kbit/s sem código (`prova-b-sem-fec`) | 51,3 dB-Hz | |
| **DBPSK com FEC, 25,6 kbit/s no ar (`prova-b`)** | **48,2 dB-Hz** (limiar 0,4; 48,4 com o limiar 0,5 no bloco 09) | |

## 5. O que funcionou

1. **Simulação, teoria e a captura real concordam.** A BER simulada ficou a menos de 0,08 dB da teoria; o receptor perdeu de 0 a 0,3 dB em relação à demodulação ideal; e o mesmo receptor recebeu 698 de 698 quadros da captura real de 04/11.
2. **Medir antes de decidir.** Cada escolha veio de um ensaio: o pulso pela banda (3b), a DBPSK pelo offset medido (Etapa 4), a taxa da prova A pela banda e pela margem (bloco 07), a modulação da prova B pelo C/N0 necessário (bloco 08), o FEC (bloco 09), a DQPSK (bloco 10), a emenda das caudas (bloco 12).
3. **O receptor estima tudo por quadro** (instante, offset, fase, limiar da OOK), a partir do prefixo de 29 bits conhecidos. A deriva de offset medida no ar (A18) deixa de ser problema.
4. **Os perfis** garantem os mesmos parâmetros no TX, na gravação e no RX, e registram a configuração em cada JSON, como a prova B pede.
5. **O processo pegou os defeitos.** Quase todos os defeitos da seção 6 foram achados por um teste, um mutante sobrevivente, um ensaio que não bateu com a teoria, ou uma prova simulada de ponta a ponta. Nenhum chegou a uma conclusão publicada sem ser corrigido.

## 6. O que falhou e como foi corrigido

### 6.1 Na referência do professor (auditoria das Etapas 1 e 2)

| # | Achado | Correção |
|---|---|---|
| A1, A2 | o RX decodificava **um quadro só** por captura, sem limiar | receptor multiquadro com limiar medido (3c) |
| A3, A9 | sem número de sequência; CRC-8 fraco; payload de no máximo 64 bytes | quadro v2 e depois v3, com CRC-16 (3a, bloco 10) |
| A4 | TX repetia o mesmo quadro em buffer cíclico, sem log | transmissor de prova com log (3d) |
| A5 a A7, A15, A16 | calibração com correção perdida, FFT de 500 Hz por bin, tom de teste com espectro em pente, RTL com −68 ppm e espúrios | nova calibração com resolução de 10 Hz; registro de calibração (Etapa 1) |
| A8, A17 | leitura síncrona do RTL **perdia de 2 a 5 mil amostras a cada 128 ms** (12 quadros com CRC falho em 107) | leitura assíncrona sem perda: 698/698 (Etapa 2) |
| A10, A18 | sem recuperação de relógio; offset residual que deriva até 35 Hz/s | instante e offset estimados em cada quadro (3c) |
| A11 a A14, A19 | instalação só no Fedora, IP do Pluto, parâmetros espalhados, erro de I2C no fechamento | `requirements.txt`, perfis (bloco 07), erro de I2C sob observação |
| A20, A21 | LO na borda da faixa autorizada; banda subestimada nas bordas do RTL | LO em 919,5 MHz conferido pelo TX; banda medida só com RRC e gaussiano |

### 6.2 No nosso próprio código

| # | Bloco | O que aconteceu | Como apareceu | Correção |
|---|---|---|---|---|
| A22 | 5 | janela da 2-FSK 1,5 amostra adiantada desde a 3c: BER da GFSK 2,6 vezes maior | ensaio contra a Etapa 4 | janela corrigida; números refeitos |
| A23 | 5 | correlator da 2-FSK sem filtro de banda: um pico de DC multiplicava a BER por 25 | ensaio com pico de DC | 2-FSK demodula depois do filtro |
| B1 | 6 | **0/0 na métrica** com zeros exatos antes do quadro: 51 detecções falsas | teste novo do comprimento corrompido | piso de energia relativo |
| B2 | 7 | conta do goodput com 1 109 bits por quadro, sem a cauda do RRC: 1,2% a mais | a prova de 60 s mandou menos quadros que a conta previa | goodput pelo período real do quadro |
| B3 | 8 | o ensaio cortava a captura na última amostra não nula e **perdia o último quadro da OOK** | piso de PER de 0,25% que não melhorava com o sinal | ruído também depois dos quadros |
| B4 | 9 | com FEC, um quadro curto no fim da captura era perdido | teste com captura curta | a janela de leitura encolhe perto do fim |
| B5 | 10 | **a sequência de 16 bits dava a volta em 60 s** na DQPSK: 4 839 pacotes com "conteúdo diferente", PER de 6,9% (desclassificação) | prova de 60 s simulada | **quadro v3, sequência de 24 bits** |
| B6 | 10 | o ensaio gerava 60 000 payloads, menos do que a DQPSK manda em 60 s | prova de 60 s simulada | 100 000 payloads; o TX passou a **avisar** quando o arquivo não enche a janela |
| B7 | 10 | quatro testes passavam pela semente (offset a 300 Hz por quadro, centro da banda, GFSK com DC, instante com FEC) | mudança de formato que trocou todos os bits | testes reescritos a partir da distribuição em várias sementes |
| B8 | 13 | **banda medida de 266 kHz** num sinal de 30 kHz, com SNR de −13 dB na captura; na mesma condição, com outras sementes, de 27 a 1 884 kHz | ensaio geral da prova B; depois o ensaio `banda_snr` (bloco 15) | a medida marca "não confiável" abaixo de −5 dB; medir na posição mais próxima |
| B9 | 15 | os testes e um ensaio da DQPSK passavam ao `canal.awgn` as amostras **por símbolo**: ruído 3 dB acima do declarado | auditoria do código | amostras por bit, fracionárias |
| B10 | 15 | **o roteiro mandava instalar só o `requirements.txt`**: sem o `pip install -e .` os scripts não rodariam no dia da prova | auditoria dos documentos | roteiro igual ao README |
| B11 | 15 | "20,2 dB a menos que o `prova-a`" ficou de quando o `prova-a` era a DBPSK (com a DQPSK, 25,0 dB); matriz de rastreabilidade parada em 04/11 | auditoria dos documentos | números e matriz atualizados |
| B12 | 15 | o registro do RX não tinha o ganho do receptor, que a seção 7 do enunciado pede | auditoria contra o enunciado | o `receber.py` junta os metadados da gravação e avisa divergências |
| B13 | 17 | a primeira versão da faixa plana confundia a elevação de +1 dB da resposta do RTL com a queda do filtro | captura real de 04/11 | critério só da queda |

E falhas de processo, registradas nos blocos: um commit intermediário feito sem o portão (bloco 10, corrigido no commit seguinte); dois ensaios disparados sem aviso de término e vigiados depois; o computador desligou no meio de uma varredura (bloco 08), refeita com pico de memória de 1,1 GB. No bloco 14 uma cadeia de comandos seguiu depois de o lint barrar o commit, e a tag `bloco-14` foi criada e publicada no commit do bloco 13; como tag publicada não se move, a do bloco 14 é a `bloco-14-rev2` (a mesma convenção de `bloco-01-rev2` e `bloco-02-rev3`). Depois, a pedido, a `bloco-14` errada foi apagada, junto com a `bloco-06-rx-rapido` (uma tag leve do bloco 06, que o `git describe` ignorava; a anotada é a `bloco-06`).

## 7. O que dá para melhorar

| Melhoria | Ganho | Situação |
|---|---|---|
| Detecção coerente da DBPSK (fase pela média de z²) | 0,8 dB sem código; 0,3 dB com FEC | medida com sincronismo ideal (bloco 09); não adotada: a fase real, sem o offset, anda 0,11 a 0,12 rad (p95) num quadro de 86 ms da prova B, uma perda de 0,06 dB (0,12 dB no pior quadro); o ganho líquido seria de cerca de 0,2 dB, pequeno demais pelo risco (blocos 22 e 23, [etapa6_imperfeicoes.md](etapa6_imperfeicoes.md)) |
| Prefixo mais longo nos quadros com FEC | cerca de 0,5 dB na prova B (a detecção vira o gargalo) | estimado (bloco 09) |
| Modelo do prefixo que leve em conta a cauda do quadro anterior | recupera os 0,1 a 0,2 dB que a emenda custa na parte íngreme da curva | estimado (bloco 12) |
| `xo_correction` do Pluto (erro de cerca de −9,5 ppm) | offset residual menor e mais estável | pendência P3 da bancada |
| Taxa de 2,4 MS/s | +17% de goodput na prova A (1 427 kbit/s em simulação) | perfil `prova-a-24` pronto (bloco 17); depende de dois testes de bancada |

## 8. Pendências com hardware

| Pendência | Para quê | Plano |
|---|---|---|
| Enlace no ar com o quadro v3, nas três modulações (3e) | MOD-02, MOD-03, CMP-01 | protocolo da Etapa 5, com os perfis `dbpsk-256k`, `gfsk-128k` e `ook-128k` |
| Medições da Etapa 5: PER, goodput, BER, banda e Eb/N0, varrendo ganho, taxa e distância | MET-01 a MET-05, CMP-04 | [etapa5_software.md](etapa5_software.md), seção 6 |
| TX e RX em computadores distintos (P2) | PLT-02 | roteiro, seção 1 |
| Banda dos perfis medida no RTL; DQPSK no ar; Pluto alimentado por 60 s sem buraco | CMP-A | roteiro, seção 6 |
| Ensaio da prova B na sala, posição a posição | CMP-B | roteiro, seção 4 |
| **Registro de uso de IA** das Etapas 1 a 7 (P1) | PRC-02 (critério de processo) | **vazio**: o texto tem de ser da equipe |
| Tag da prova (CMP-C) | regra da competição | criar antes da prova |

## 9. Critérios de avaliação (seção 9 do enunciado)

| Critério (peso) | O que existe | Falta |
|---|---|---|
| Implementação e comparação das modulações (20%) | OOK, 2-FSK, DBPSK e DQPSK implementadas; simulação × teoria a menos de 0,08 dB; BPSK coerente comparada e justificada | a **medição** de cada uma no ar e a comparação simulação × teoria × medição |
| Confiabilidade da recepção e desafios do enlace (15%) | offset, fase e instante estimados por quadro; calibração registrada; 31 defeitos diagnosticados com evidência (seção 6) | confirmar no ar |
| Caracterização experimental e métricas (20%) | ferramentas de PER, goodput, BER, banda e Eb/N0 validadas contra o valor verdadeiro; protocolo pronto | as medições |
| Otimização e desempenho (15%) | 1 218 kbit/s contra 7,3 kbit/s da referência em simulação; prova B com 25 dB a menos de C/N0 que a prova A; limites de banda e de tempo atendidos | a melhoria **medida** nas mesmas condições da referência |
| Processo e entregas (10%) | entregas por etapa com relatório; 246 testes, portão e mutantes; tags por bloco; auditoria completa | **registro de IA vazio**; Etapas 1, 2 e 3 entregues fora do prazo |
| Relatório técnico e análise de falhas (10%) | este documento e os de cada bloco, com as falhas e as correções | a parte medida |
| Defesa oral individual (10%) | cada documento explica o porquê de cada escolha | estudar os blocos (seção 10) |

## 10. Para a defesa

Perguntas prováveis, com o ponto central da resposta e onde está o detalhe:

| Pergunta | Ponto central | Onde |
|---|---|---|
| Por que DBPSK e não BPSK coerente? | o offset residual (até 1,6 kHz, deriva de 35 Hz/s) gira a fase dentro do quadro; a BPSK coerente aguenta 7,7 Hz a 100 kbit/s | Etapa 4 |
| Por que RRC? | pulso retangular espalha a BPSK por 20 vezes a taxa; com RRC β = 0,25 cabem 682,7 ksímbolos/s em 749 kHz | 3b, bloco 07 |
| Como o RX acha os quadros? | correlação coerente do prefixo de 29 bits numa grade de offsets, métrica de Pearson com limiar de 0,5 (0,4 na prova B), supressão de não-máximos | 3c, bloco 19 |
| Por que o limiar da prova B é 0,4? | com FEC o prefixo, que não é codificado, fica 3 dB mais fraco e a detecção vira o gargalo; 0,4 dá de 0,4 a 1 dB; nenhuma detecção em 30 s só de ruído, e o CRC rejeita as falsas | bloco 19 |
| E se os relógios do Pluto e do RTL forem diferentes? | todos os perfis aguentam ±50 ppm sem perder quadro; depois da calibração sobram cerca de 2 ppm | bloco 16 |
| O ruído de fase dos osciladores atrapalha? | medido no tom real: não aparece no tamanho de um símbolo (folga de 16 a 31 vezes); a fase real anda menos de 0,01 rad num quadro da prova A e 0,11 a 0,12 rad (p95) num quadro de 86 ms da prova B | blocos 21 a 23 |
| Como você escolheu o ganho do RX? | pela janela do ADC de 8 bits: sem perda de −30 a −6 dBFS, alvo de −20 a −12; o `gravar_iq.py` mostra o nível; as gravações de 04/11 ficaram entre −17 e −19 dBFS | bloco 21 |
| Por que não usar uma modulação de ordem maior na prova A? | a 8-PSK coerente leva 46% a mais na mesma banda, mas pede 2,8 dB a mais de C/N0 e tolera 100 vezes menos ruído de fase (10 a 30 Hz contra 1 kHz); ela fica como primeira opção só se a bancada mostrar as duas folgas | bloco 24 |
| Como você compara medição e teoria? | perda do enlace: quantos dB a mais que a curva teórica cada ponto precisou para a BER medida, só sem FEC e com 10 erros ou mais; na sessão simulada, +0,07 dB | bloco 20 |
| Por que CRC-16 e por que ele cobre o cabeçalho? | CRC-8 deixa passar 1 em 256 quadros ruins; com o cabeçalho coberto um comprimento errado não gera pacote falso | 3a |
| Por que a sequência tem 24 bits? | a 1,2 Mbit/s a de 16 bits dava a volta dentro dos 60 s e o avaliador contaria os pacotes da 2ª volta como errados | bloco 10 |
| Como o FEC ganha alcance se dobra a taxa? | a taxa no ar dobra (−3 dB), mas o código ganha cerca de 5,9 dB; sobram 2,9 dB no receptor completo | bloco 09 |
| Por que DQPSK e não QPSK? | o mesmo motivo da DBPSK: detecção diferencial, imune à fase; custa cerca de 1,4 dB sobre a DBPSK na teoria, 1,7 dB medidos no receptor completo | bloco 10 |
| O que é o Eb/N0 medido na captura? | potência do sinal sobre N0 medido num trecho só de ruído antes do 1º quadro, dentro da banda do sinal | Etapa 5 |

## 11. Como reproduzir

```
python ferramentas/verificar.py                       portão: formatação, lint, tipos, regras NASA, testes
python ensaios/etapa6/ensaio_geral_ensaio.py          prova de 60 s simulada com os quatro perfis
python -m ferramentas.gerar_relatorio final           este relatório em PDF
```

Cada registro em `dados/logs/` traz a versão do código (`git describe`) que o gerou.
