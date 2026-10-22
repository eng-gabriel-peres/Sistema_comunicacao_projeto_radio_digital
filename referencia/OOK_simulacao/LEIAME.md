# Simulação Tx/Rx OOK (sem SDR)

Versão para computador dos scripts `pluto_tx_ook_v2.py` e `rtl_rx_ook_v2.py`.
O processamento de sinais é o mesmo; só o hardware foi trocado por arquivos `.npy`.

```
tx_ook_sim.py  ──tx_iq.npy──►  canal_sim.py  ──rx_iq.npy──►  rx_ook_sim.py
 (Pluto)                       (RF + RTL-SDR)                (decodificador)
```

## Como rodar

```bash
pip install numpy matplotlib scipy
python tx_ook_sim.py
python canal_sim.py
python rx_ook_sim.py
```

Cada script abre um gráfico por passo (feche a janela para avançar).
Para abrir todos de uma vez, use `PAUSAR_ENTRE_PASSOS = False`.
Todas as figuras também ficam salvas na pasta `figuras/`.

## O que cada passo mostra

| Script | Passo | Conteúdo |
|---|---|---|
| TX | 1 | Bits do quadro com cada campo colorido e os caracteres do payload |
| TX | 2 | Envoltória OOK e zoom nas rampas de cosseno levantado |
| TX | 3 | I e Q da portadora de 200 kHz modulada; plano IQ |
| TX | 4 | Espectro transmitido (lóbulo principal ≈ ±10 kHz) |
| Canal | 1 | Sinal limpo × sinal com ruído no tempo |
| Canal | 2 | Espectro: tom, pico DC do RTL, piso de ruído, desvio de frequência |
| Canal | 3 | Plano IQ antes e depois do canal |
| RX | 1 | Espectro capturado (como no script original) |
| RX | 2 | Translação de −200 kHz e filtro passa-faixa complexo |
| RX | 3 | Sem filtro → detector de envoltória → envoltória suavizada |
| RX | 4 | Correlação com o Barker-13 e por que Barker (autocorrelação) |
| RX | 5 | Níveis alto/baixo do preâmbulo, limiar e diagrama de olho |
| RX | 6 | Média de cada bit, decisão, caracteres e CRC |

## Experimentos sugeridos (em `canal_sim.py`)

- `SNR_DB = -12` → aparecem bits errados (em vermelho no RX passo 6) e o CRC acusa.
- `ERRO_FREQ_HZ = 12e3` → o sinal sai do filtro de ±10 kHz, o byte de comprimento é lido
  errado e a decodificação desanda. Isso mostra a importância do `FREQ_CORRECTION_PPM`.
- `OFFSET_DC = 0`, `QUANTIZAR_8_BITS = False` → canal "ideal".
- No TX: mude `MESSAGE`, `BIT_RATE` ou `RAMP_FRACTION` e veja o espectro mudar.
  (Se mudar `BIT_RATE`, mude também no RX.)

## Analisar uma captura real

Em `rtl_rx_ook_v2.py`, logo após `samples = capture_chunks(...)`, acrescente:

```python
np.save("captura_real.npy", samples)
```

Depois, em `rx_ook_sim.py`, use `ARQUIVO_ENTRADA = "captura_real.npy"` para ver os mesmos
gráficos passo a passo com o sinal real.

## Modelo do canal (resumo)

Buffer cíclico do Pluto → início aleatório da captura → reamostragem de 2,000 para 2,048 MS/s
→ erro de frequência + fase aleatória → atenuação + ruído branco gaussiano → offset DC →
ADC de 8 bits.

Observação: no RX, a filtragem usa `scipy.signal.fftconvolve` quando o scipy está instalado.
O resultado é o mesmo do `np.convolve` original, só que muito mais rápido.
