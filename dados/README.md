# Dados de ensaio

Capturas IQ, logs de TX/RX e registros de calibração ficam nesta pasta, **fora do git** por causa do tamanho. A exceção são os registros de calibração (JSON e figura em `calibracao/`), que são pequenos e servem de evidência de entrega. Este índice é versionado e registra cada ensaio, para que qualquer resultado possa ser localizado e reproduzido.

| Data | Arquivo(s) | Ensaio | Configuração | Commit | Observações |
|---|---|---|---|---|---|
| 22/10/2026 10:48 | `calibracao/calibracao_20261022_104830.{json,png,npy}` | Calibração do RTL com o tom do Pluto do professor (915,2 MHz) | ganho 40,2 dB, 2,048 MS/s, janela ±10 kHz, 8 blocos | 856a5b6 | offset −42,4 Hz (−0,046 ppm), correção 0 ppm, resíduo −45,7 Hz; `.npy` só no disco. Ver docs/calibracao_rtl.md |
