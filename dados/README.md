# Dados de ensaio

Capturas IQ, logs de TX/RX e registros de calibração ficam nesta pasta, **fora do git** por causa do tamanho. A exceção são os registros de calibração (JSON e figura em `calibracao/`), que são pequenos e servem de evidência de entrega. Este índice é versionado e registra cada ensaio, para que qualquer resultado possa ser localizado e reproduzido.

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
