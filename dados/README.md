# Dados de ensaio

As capturas IQ (`.npy`) ficam nesta pasta **fora do git**, por causa do tamanho. Os registros JSON e os logs de console dos ensaios (`logs/`) e os registros de calibração (`calibracao/`) são pequenos e **entram no git**, como evidência. Este índice é versionado e registra cada ensaio, para que qualquer resultado possa ser localizado e reproduzido.

| Data | Arquivo(s) | Ensaio | Configuração | Commit | Observações |
|---|---|---|---|---|---|
| 22/10/2026 10:48 | `calibracao/calibracao_20261022_104830.*` | Calibração com o `tx_test.py` do professor | ganho 40,2 dB, 2,048 MS/s, janela ±10 kHz | 856a5b6 | **inválido** (travou em espúrio do RTL); reprocessado em `..._111529` (+75,5 ppm) |
| 22/10/2026 11:16 | `calibracao/fm_20261022_111611.json` | Erro absoluto do RTL pelas rádios FM | ganho 20 dB, 3 emissoras | revisão do bloco 1 | mediana −68,3 ppm |
| 22/10/2026 11:18 | `calibracao/calibracao_20261022_111837.*` | Calibração ao vivo (sinal OOK) partindo de +1 ppm | ganho 40 dB | revisão do bloco 1 | reprocessado em `..._112118`: +77,9 ppm |
| 22/10/2026 11:19 | `calibracao/calibracao_20261022_111918.*` (antes e depois) | Calibração ao vivo (OOK), +1 e +77 ppm | ganho 40 dB | revisão do bloco 1 | reprocessado em `..._112123`: +77,5 ppm; resíduo com 77 de cerca de −0,6 kHz |
| 04/11/2026 09:57 | `calibracao/fm_20261104_095704.json` | Erro absoluto do RTL (FM), RTL frio, com +77 ppm | ganho 20 dB | bloco 1c | mediana −76,9 ppm |
| 04/11/2026 10:00 | `calibracao/calibracao_20261104_100033.*` | Tom do Pluto da equipe (915,25 MHz), RTL frio | TX −30 dB, RX 20 dB | bloco 1c | teste: par −83,6 ppm |
| 04/11/2026 10:06 | `calibracao/calibracao_20261104_100631.*` | Tom do Pluto da equipe, RTL aquecido | TX −30 dB, RX 20 dB, 8 blocos | bloco 1c | **par −84,04 ppm, correção +84**, resíduo −356 Hz |
| 04/11/2026 10:09 | `calibracao/calibracao_20261104_100917.*` | Tom do Pluto da equipe, RTL aquecido | TX −30 dB, RX 20 dB, 8 blocos | bloco 1c | **par −84,21 ppm, correção +84**, resíduo −524 Hz |
| 04/11/2026 10:10 | `calibracao/fm_20261104_101037.json` | Erro absoluto do RTL (FM), aquecido | ganho 20 dB | bloco 1c | mediana −74,6 ppm |
| 04/11/2026 10:16 a 10:17 | `capturas/ook_ref_20261104_1016*`, `..._1017*` (`.npy` e `.png`) | OOK de referência, cópia de ensaio do RX | Pluto da equipe TX −20 dB; RTL 915 MHz, 10 dB, 84 ppm, 0,5 s | e26167a | 5 de 5 com CRC OK; todos os quadros: 95 OK, 12 falhos nas emendas (A17) |
| 04/11/2026 10:23 | `capturas/ook_ref_continua_20261104.npy` | OOK de referência, `capturar` assíncrona | RTL 915 MHz, 10 dB, 84 ppm, 4,1 s | 70689d0 | 0 saltos, 178 de 178 quadros com CRC OK |
| 04/11/2026 10:38 | `logs/etapa2_tx_20261104_103806.log`, `logs/etapa2_rx_20261104_1038*.log`, `capturas/ook_ref_20261104_1038*` | OOK de referência com log de console | RTL 10 dB (8,7 aplicado), 84 ppm, 0,5 s | 5e5d103 | 3 de 3 com CRC OK |
| 04/11/2026 10:38 | `capturas/ook_ref_continua16s_20261104_103841.npy` | OOK de referência, `capturar` assíncrona, 16 s | RTL 8,7 dB, 84 ppm | 5e5d103 | 698 de 698 com CRC OK, PER 0%, BER 0/117 264, offset −1 343 Hz |
| 04/11/2026 10:42 | `logs/deriva_offset_20261104_104204.json`, `logs/etapa2_tx_20261104_104105_deriva.log` | Deriva do offset durante 60 s de TX | RTL 8,7 dB, 84 ppm, 0,5 s por ponto | 5e5d103 + script novo | offset de −1 184 a −1 623 Hz; Pluto a 34 a 35 °C (A18) |
| 04/11/2026 11:05 | `logs/varredura_faixa_20261104_110544.json`, `docs/figuras/varredura_faixa_04nov.png` | Varredura de 915 a 928 MHz sem transmissão | RTL 40,2 dB, 84 ppm, 8 passos de 1,6 MHz, 0,5 s cada | 513fb93 + script novo | linha mais forte perto de 921,6 MHz (harmônica 32 × 28,8 MHz do RTL); entrada para a decisão D5 |

## Bancada de 25/11/2026 (bloco 26)

Detalhes e conclusões em [docs/bancada_20261125.md](../docs/bancada_20261125.md). Pluto da equipe (`ip:192.168.2.22`); RTL1 até 10:50 (oscilador modulado em 1,7 kHz, não usar), depois RTL2.

| Horário | Arquivo(s) | Ensaio | Configuração | Observações |
|---|---|---|---|---|
| 09:53 a 09:57 | `capturas/sessao_20261125/controle_*`, `calibracao/calibracao_20261125_095447.*`, `calibracao/fm_20261125_095526.json` | Controle sem TX e calibração, RTL1 | RX 20 dB | +56 ppm (RTL1) |
| 09:56 a 10:01 | `capturas/sessao_20261125/tom_*_ruido_de_fase.json` | Ruído de fase, RTL1 | tom do Pluto | raias de −8 dBc a ±1,7 kHz; 8-PSK em ATENÇÃO |
| 10:06 a 10:35 | `capturas/sessao_20261125/prova_a_60s_*`, `prova_a_pre_*`, `prova_a_final_*` | Prova A, 60 s | `prova-a`, TX −30 dB | sem `--pre-gerar` 36,6% de PER; com ele e a espera da fila, 0,017% e 1 217,7 kbit/s |
| 10:40 | `capturas/sessao_20261125/prova_a_8psk_*` | 8-PSK, RTL1 | `prova-a-8psk` | 28,3% de PER (ruído de fase do RTL1) |
| 10:46 a 11:11 | `capturas/sessao_20261125/prova_b_*` | Prova B a 919,75 MHz, vários níveis, RTL1 e RTL2 | `prova-b`, TX −30 a −68 dB | 694/694 a −30 dB; perdas em rajadas com sinal fraco |
| 11:06 | `calibracao/calibracao_20261125_110659.*` | Calibração e ruído de fase, RTL2 | | +87 ppm; 8-PSK ok (0,030 rad) |
| 15:11 a 15:23 | `capturas/sessao_20261125_casa/*`, `calibracao/calibracao_20261125_151216.*`, `logs/casa_*` | Casa: controle, calibração (+88 ppm, aquecido), prova B a 919,75 e 919,875 MHz, partida do TX | TX −49 a −60 dB | grade de 500 kHz de aparelhos ISM; a 375 kHz, 232/232 a −52 dB |
| 15:37 a 16:03 | `prova/ensaio_20261125/*`, `logs/ensaio_prova_tx_*` | Ensaio da competição com `prova_tx.py` e `prova_rx.py`, arquivo cifrado de teste | prova A −30 e −20 dB; prova B −40 a −57 dB | prova A 1 217,5 kbit/s (PER 0,034%); prova B 694/694 até −53 dB; `alcance.md` |
| 16:10 em diante | `capturas/sessao_20261125_casa/etapa5/*`, `logs/etapa5_casa_*` | Varredura da Etapa 5, RTL2 | dbpsk-256k, gfsk-128k, ook-128k, TX −28 a −48 dB | ver docs/bancada_20261125.md, seção 5 |

## Ensaios em simulação (21 e 22/11/2026)

Todos em `logs/`, gerados pelos scripts de `ensaios/`; cada JSON traz a versão do código que o gerou. Os logs de console têm o mesmo prefixo, com `_execucao.log`.

| Data | Arquivo(s) | Ensaio | Etapa ou bloco |
|---|---|---|---|
| 21/11/2026 | `modulacoes_20261121_203042.json` | OOK, 2-FSK e BPSK em simulação, banda a 99% | Etapa 3b |
| 21/11/2026 | `etapa4_canal_20261121_210352.json` | Canal: BER × Eb/N0, fase, offset, temporização | Etapa 4 |
| 21/11/2026 | `receptor_captura_real_20261121_213841.json, ..._234321.json` | Receptor na captura real da OOK (698/698) | Etapa 3c |
| 21 e 22/11/2026 | `receptor_desempenho_20261121_215254.json, ..._20261122_000354.json` | Perda de implementação do receptor | Etapa 3c |
| 21/11/2026 | `enlace_simulado_20261121_231317.json, ..._235020.json` | Prova simulada de ponta a ponta (10 s) | Etapa 3d |
| 21/11/2026 | `etapa5_referencia_20261121_234655.json` | Referência simulada da cadeia de medição | Etapa 5 |
| 22/11/2026 | `receptor_captura_real_20261122_002415.json, receptor_otimizacao_20261122_002709.json` | Receptor acelerado: captura real e equivalência | bloco 06 |
| 22/11/2026 | `prova_a_20261122_011645.json, prova_a_60s_11dB_20261122_011906.json` | Prova A: varredura de taxas e 60 s simulados (DBPSK) | bloco 07 |
| 22/11/2026 | `prova_b_20261122_103822.json` | Prova B sem código | bloco 08 |
| 22/11/2026 | `prova_b_fec_20261122_104747.json, fec_sincronismo_ideal_20261122_105017.json` | FEC no receptor completo e com sincronismo ideal | bloco 09 |
| 22/11/2026 | `prova_a_dqpsk_20261122_111533.json, prova_a_60s_13dB_20261122_111755.json, prova_a_60s_13dB_20261122_110647_quadro_v2_sequencia_volta.json` | DQPSK; prova de 60 s (e a rodada que falhou com a sequência de 16 bits) | bloco 10 |
| 22/11/2026 | `viterbi_lote_20261122_112923.json, prova_a_fec_60s_6dB_20261122_113148.json` | Viterbi em lote: equivalência e 60 s com prova-a-fec | bloco 11 |
| 22/11/2026 | `emenda_caudas_20261122_113942.json` | Emenda das caudas do RRC | bloco 12 |
| 22/11/2026 | `ensaio_geral_20261122_115928.json e um por perfil (prova_a_60s_14dB, prova_a_fec_60s_6dB_..._115606, prova_a_dbpsk_60s_12dB, prova_b_60s_6dB)` | Ensaio geral com os quatro perfis finais | bloco 13 |
| 22/11/2026 | `banda_snr_20261122_141637.json` | Banda medida × SNR na captura (prova B) | bloco 15 |
| 22/11/2026 | `relogio_20261122_210538.json` (refeito no bloco 24 com a 8-PSK; os outros perfis iguais) | Tolerância ao erro de relógio (±50 ppm) em todos os perfis | bloco 16 |
| 22/11/2026 | `taxa_24_20261122_143526.json, prova_a_24_60s_14dB_20261122_143526.json` | Perfil experimental a 2,4 MS/s e a prova de 60 s | bloco 17 |
| 22/11/2026 | `limiar_20261122_151453.json, prova_b_60s_6dB_20261122_151613.json` (ensaio a 5,5 dB; o nome arredonda) | Limiar de detecção 0,5 × 0,4 na prova B e a prova de 60 s | bloco 19 |
| 22/11/2026 | `bancada_simulada_20261122_153017.json` e a pasta `bancada_simulada_20261122_153017/` | Sessão de bancada simulada com os scripts da bancada e a análise automática | bloco 20 |
| 22/11/2026 | `imperfeicoes_20261122_211000.json` (refeito nos blocos 23 e 24) | Ruído de fase medido nos tons de 04/11, margem de ruído de fase e janela do ADC de 8 bits nos perfis finais | bloco 21 |
| 22/11/2026 | `fase_no_quadro_20261122_201412.json` (refeito no bloco 23) | Desvio da fase real dentro de um quadro de cada perfil | bloco 22 |
| 22/11/2026 | `psk8_viabilidade_20261122_203837.json` (refeito no bloco 24 com o Gray certo) | Viabilidade da 8-PSK coerente na prova A | bloco 23 |
| 22/11/2026 | `prova_a_8psk_20261122_210316.json`, `rastreio_8psk_20261122_210124.json`, `prova_a_8psk_60s_15dB_20261122_212032.json` | 8-PSK coerente: receptor completo, ganho da malha de fase e prova de 60 s | bloco 24 |
| 04/11/2026 | `analise_crc_20261104_110847.json` | Contagens e Monte Carlo do CRC (quadro v2) | Etapa 3a |
