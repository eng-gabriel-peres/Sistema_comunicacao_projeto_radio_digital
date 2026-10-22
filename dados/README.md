# Dados de ensaio

Capturas IQ, logs de TX/RX e registros de calibração ficam nesta pasta, **fora do git** por causa do tamanho. A exceção são os registros de calibração (JSON e figura em `calibracao/`), que são pequenos e servem de evidência de entrega. Este índice é versionado e registra cada ensaio, para que qualquer resultado possa ser localizado e reproduzido.

| Data | Arquivo(s) | Ensaio | Configuração | Commit | Observações |
|---|---|---|---|---|---|
| 22/10/2026 10:48 | `calibracao/calibracao_20261022_104830.*` | Calibração com o `tx_test.py` do professor | ganho 40,2 dB, 2,048 MS/s, janela ±10 kHz | 856a5b6 | **inválido** (travou em espúrio do RTL); reprocessado em `..._111529` (+75,5 ppm) |
| 22/10/2026 11:16 | `calibracao/fm_20261022_111611.json` | Erro absoluto do RTL pelas rádios FM | ganho 20 dB, 3 emissoras | revisão do bloco 1 | mediana −68,3 ppm |
| 22/10/2026 11:18 | `calibracao/calibracao_20261022_111837.*` | Calibração ao vivo (sinal OOK) partindo de +1 ppm | ganho 40 dB | revisão do bloco 1 | reprocessado em `..._112118`: +77,9 ppm |
| 22/10/2026 11:19 | `calibracao/calibracao_20261022_111918.*` (antes e depois) | Calibração ao vivo (OOK), +1 e +77 ppm | ganho 40 dB | revisão do bloco 1 | reprocessado em `..._112123`: +77,5 ppm; resíduo com 77 de cerca de −0,6 kHz |
