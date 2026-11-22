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
| 22/11/2026 | `relogio_20261122_142809.json` | Tolerância ao erro de relógio (±50 ppm) em todos os perfis | bloco 16 |
| 22/11/2026 | `taxa_24_20261122_143526.json, prova_a_24_60s_14dB_20261122_143526.json` | Perfil experimental a 2,4 MS/s e a prova de 60 s | bloco 17 |
| 22/11/2026 | `limiar_20261122_151453.json, prova_b_60s_6dB_20261122_151613.json` (ensaio a 5,5 dB; o nome arredonda) | Limiar de detecção 0,5 × 0,4 na prova B e a prova de 60 s | bloco 19 |
| 22/11/2026 | `bancada_simulada_20261122_153017.json` e a pasta `bancada_simulada_20261122_153017/` | Sessão de bancada simulada com os scripts da bancada e a análise automática | bloco 20 |
| 04/11/2026 | `analise_crc_20261104_110847.json` | Contagens e Monte Carlo do CRC (quadro v2) | Etapa 3a |
