# Etapa 2: recepção da OOK de referência no enlace real

Requisitos: **MOD-01** (OOK no enlace real), **RX-02** (captura gravada), **CAL-01** (correção aplicada no ensaio). Achado novo: **A17**.

![Continuidade da captura e um quadro recebido](figuras/etapa2_04nov.png)

## 1. Resultado

| Item | Valor |
|---|---|
| Mensagem recebida | `HELLO WORLD MANDRIAUM` (21 bytes), CRC-8 OK |
| Receptor da referência, sem alteração de lógica | **5 de 5** recepções com CRC OK (10:16 a 10:17) |
| Todos os quadros das 5 capturas da referência (0,5 s cada) | 95 com CRC OK, **12 com CRC falho**, 3 incompletos nas bordas |
| Todos os quadros da nossa captura contínua (4,1 s) | **178 de 178** completos com CRC OK, 0 falhos |
| Ganho do RTL | 10 dB (com os 30 dB da referência o ADC saturou em 26% a 29% das amostras) |
| Correção de frequência | +84 ppm ([calibração de 04/11](calibracao_rtl.md)) |

A OOK de referência funciona no enlace real. As falhas de CRC que sobraram não vêm do canal: vêm da forma como a referência lê o RTL, que perde amostras a cada 128 ms (achado A17, seção 5). Com a leitura assíncrona do nosso pacote nenhuma amostra se perde e todos os quadros passam no CRC.

## 2. Montagem

| Item | Valor |
|---|---|
| Transmissor | Pluto da equipe (Rev.C AD9364, fw v0.32, `ip:192.168.2.22`), `pluto_tx_ook_v2.py` |
| Sinal | OOK 10 kbit/s, portadora em LO + 200 kHz = 915,200 MHz, quadro repetido em buffer cíclico |
| Receptor | RTL-SDR RTL2832U + R820T2, 915 MHz, 2,048 MS/s, AGC desligado |
| Distância | rádios lado a lado na bancada |
| Aquecimento | RTL ligado desde antes da primeira medição FM (09:57), mais de 15 min antes do ensaio |

## 3. O que mudou nas cópias de ensaio

Os programas do professor ficam intactos em `referencia/`. O ensaio usa cópias geradas por [`ensaios/etapa2/gerar_copias.py`](../ensaios/etapa2/gerar_copias.py), e o diff completo está em [`ensaios/etapa2/diferencas.diff`](../ensaios/etapa2/diferencas.diff).

| Arquivo | Mudança | Motivo |
|---|---|---|
| TX | `while True` trocado por 60 s fixos, com `tx_destroy_buffer` no `finally` | o ensaio roda sem teclado e o Pluto não pode ficar transmitindo |
| RX | `GAIN = 30` para `GAIN = 10` | saturação (seção 4) |
| RX | `FREQ_CORRECTION_PPM = 34` para `84` | calibração do par com o Pluto da equipe |
| RX | grava a captura (`.npy`) e a figura (`.png`) em `dados/capturas/` | evidência da recepção |

A demodulação, o sincronismo, o limiar e o CRC da referência não foram tocados.

## 4. Saturação com o ganho da referência

Com os rádios lado a lado, o Pluto em −20 dB (padrão do `pluto_tx_ook_v2.py`) e o RTL em 30 dB, de 26% a 29% das amostras ficaram no fundo de escala do ADC de 8 bits. A envoltória fica achatada e uma das recepções falhou no CRC. Testei os ganhos com o mesmo sinal:

| Ganho do RTL | Amostras saturadas | Pico da amplitude |
|---|---|---|
| 30 dB | 26% a 29% | fundo de escala |
| 20 dB | 0% | 0,79 do fundo de escala |
| 10 dB | 0% | 0,32 do fundo de escala |

Adotei 10 dB por margem. O ganho certo depende da distância. Por isso `sdrlink.hw.rtl_rx.fracao_saturada` passa a ser conferida em todo ensaio, e acima de 0,1% o ganho tem de baixar.

## 5. Achado A17: a leitura em blocos perde amostras

### 5.1 Como apareceu

A referência decodifica só o primeiro quadro de cada captura (A1). Para ver o resto, decodifiquei **todos** os quadros de cada captura com as funções `crc8` e `read_bits` da própria referência ([`decodificar_quadros_ensaio.py`](../ensaios/etapa2/decodificar_quadros_ensaio.py)). De 2 a 3 quadros por captura falhavam no CRC, sempre os mesmos pontos no tempo.

O transmissor repete o quadro a cada 229 bits × 204,8 amostras = **46 899,2 amostras**, sem variação. Medindo o intervalo entre os sincronismos achados, ele bate com esse valor em quase todo lugar, menos exatamente nas emendas dos blocos de 256 k amostras (128 ms) do `capture_chunks`:

| Captura (04/11) | Amostras perdidas em cada emenda |
|---|---|
| 10:16:54 | 3 948, 3 102, 4 512 (nesta o quadro inteiro sumiu) |
| 10:17:00 | 2 727, 3 008, 3 477 |
| 10:17:05 | 4 324, 5 075, 3 665 |
| 10:17:10 | 2 256, 2 350, 2 632 |
| 10:17:16 | 3 760 (quadro sumiu), 3 008, 2 820 |

São 15 perdas em 15 emendas, de 1,1 a 2,5 ms cada, ou seja, cerca de 1,3% das amostras. Um quadro que atravessa a emenda fica com um buraco no meio e falha no CRC; se o buraco cai no sincronismo, o quadro nem é detectado.

### 5.2 Causa

`read_samples` e `read_bytes` fazem uma transferência USB síncrona por chamada. Entre uma chamada e a próxima (conversão para complexo e cópia no Python), o RTL continua amostrando e o buffer interno transborda. Nossa primeira versão de `capturar` lia do mesmo jeito e perdeu 31 vezes em 4,1 s.

### 5.3 Correção

`sdrlink.hw.rtl_rx.capturar` passou a usar a **leitura assíncrona** da librtlsdr (`read_bytes_async`). A biblioteca mantém 15 buffers USB em fila e chama um callback a cada bloco. O callback (`Acumulador`) só copia o bloco para um vetor pré-alocado e cancela a leitura quando o vetor enche. Um temporizador garante o término mesmo se o rádio parar de responder (regra 2 do padrão de código).

Detalhe encontrado no hardware: ao cancelar, a librtlsdr devolve o código do último `libusb_cancel_transfer`, que é `LIBUSB_ERROR_NOT_FOUND` quando a transferência já tinha terminado. O pyrtlsdr transforma isso em exceção e fecha o rádio. Com o vetor cheio esse erro é o fim normal da leitura e é ignorado; com o vetor incompleto vira `RuntimeError`. Os dois casos têm teste automático.

### 5.4 Verificação

| Captura | Leitura | Saltos de intervalo | Desvio máximo do intervalo | CRC OK |
|---|---|---|---|---|
| 5 capturas da referência, 0,5 s | síncrona | 15 | 5 075 amostras | 95 de 107 |
| 2 capturas do `capturar`, 4,1 s | assíncrona | **0** | **1,8 amostra** | **178 de 178** (1ª) |

O desvio de ±2 amostras que sobra é só o arredondamento do pico da correlação.

## 6. Linha do tempo

| Horário | O quê | Resultado |
|---|---|---|
| antes de 10:16 | Primeiras recepções com ganho 30 dB (capturas apagadas) | 26% a 29% saturado, uma falha de CRC |
| 10:16 a 10:17 | 5 recepções com a cópia de ensaio (ganho 10 dB, 84 ppm) | 5 de 5 com CRC OK |
| depois | Decodificação de todos os quadros das 5 capturas | 12 falhas, todas nas emendas: achado A17 |
| 10:23 | Captura contínua com a leitura assíncrona, duas rodadas | 0 saltos, 178 de 178 com CRC OK |

## 7. Como reproduzir

```
python ensaios/etapa2/gerar_copias.py
python ensaios/etapa2/pluto_tx_ook_v2_ensaio.py        # PC do TX, 60 s
python ensaios/etapa2/rtl_rx_ook_v2_ensaio.py          # PC do RX, grava em dados/capturas/
python ensaios/etapa2/decodificar_quadros_ensaio.py dados/capturas/<captura>.npy
python ensaios/etapa2/figura_etapa2_ensaio.py <captura_ref.npy> <captura_continua.npy> docs/figuras/etapa2_04nov.png
```

## 8. Evidências

| Evidência | Onde |
|---|---|
| Capturas IQ e figuras da referência | `dados/capturas/ook_ref_20261104_1016*.{npy,png}` e `..._1017*` (fora do git, índice em [dados/README.md](../dados/README.md)) |
| Captura contínua (4,1 s, 64 MB) | `dados/capturas/ook_ref_continua_20261104.npy` (fora do git) |
| Diferenças das cópias de ensaio | [`ensaios/etapa2/diferencas.diff`](../ensaios/etapa2/diferencas.diff) |
| Figura resumo | [`figuras/etapa2_04nov.png`](figuras/etapa2_04nov.png) |
| Código da correção do A17 | `sdrlink/hw/rtl_rx.py` e `tests/test_rtl_rx.py` |

## 9. O que isso muda para a Etapa 3

1. **Leitura**: o receptor do projeto usa só `capturar` (assíncrona). Para os 60 s da prova serão 123 M amostras; o vetor de bytes brutos (246 MB) cabe na memória, e a conversão para complexo será feita em pedaços.
2. **Ganho**: começar em 10 dB lado a lado e conferir `fracao_saturada` antes de cada ensaio.
3. **Todos os quadros**: o decodificador desta etapa já mostra a estrutura que falta na referência (A1): procurar todos os sincronismos acima de um limiar e decodificar cada um. É o ponto de partida do RX multiquadro com número de sequência e CRC-16.
