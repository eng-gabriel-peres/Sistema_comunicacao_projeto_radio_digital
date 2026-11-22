# Etapa 6k: viabilidade da 8-PSK coerente na prova A

Requisito: CMP-A (maior goodput).

Feito em 22/11/2026, sem hardware (bloco 23). É um estudo de viabilidade, com o instante de amostragem ideal, como o do FEC no bloco 09. Ainda não há perfil nem receptor de 8-PSK.

## 1. Resultado

| Item | DQPSK (`prova-a`) | 8-PSK coerente |
|---|---|---|
| Bits por símbolo no corpo | 2 | 3 |
| Banda a 99% | 749 kHz | a mesma (mesmo pulso, mesma taxa de símbolos) |
| Goodput sem perdas | 1 218 kbit/s | **1 797 kbit/s (+48%)** |
| Eb/N0 para PER 1%, canal realista | 11,8 dB | 12,9 dB (teoria: 13,0) |
| C/N0 necessário | 73,2 dB-Hz | **76,0 dB-Hz (+2,8 dB)** |
| Margem pelo C/N0 da bancada de 04/11 (78,3 dB-Hz) | 5,1 dB | **2,3 dB** |

A prova A tem potência padronizada, então a 8-PSK só se paga se o C/N0 na distância da prova sobrar. Com os 78,3 dB-Hz medidos em 04/11 sobrariam 2,3 dB. É menos que os 5,1 dB da DQPSK, mas ainda é margem.

**Decisão:** vale implementar a 8-PSK no receptor de verdade como perfil experimental (`prova-a-8psk`). Ela entra com uma regra de troca: só é usada se o C/N0 medido na bancada, na distância da prova, ficar pelo menos 2 dB acima dos 76,0 dB-Hz. Senão, fica a DQPSK. A implementação é o próximo bloco.

## 2. Por que coerente

A prova A é limitada pela banda (1 MHz). Mais bits por símbolo é o único jeito de subir a taxa sem alargar o sinal. A 8-DPSK, que dispensaria estimar a fase, custa cerca de 3 dB a mais que a 8-PSK coerente. Somados aos 1,8 dB da taxa maior, não caberia na margem.

A detecção coerente depende de a fase não andar dentro do quadro. A fase real do par Pluto + RTL, medida nos tons de 04/11, anda 0,005 rad (mediana) e 0,008 a 0,009 rad (p95) num quadro de 0,84 ms, depois de tirar o offset ([etapa6_imperfeicoes.md](etapa6_imperfeicoes.md)). A 8-PSK tem margem de 0,39 rad (22,5°).

## 3. O detector do ensaio

Por quadro, depois do filtro casado no instante ideal:

1. **Frequência e fase pela potência 8 dos símbolos do corpo**, que tira a modulação. A frequência sai do pico do espectro por FFT de 8 192 pontos, refinado por parábola (máxima verossimilhança). A fase sai da média depois de tirar a rampa.
2. **Ambiguidade de 45° resolvida pela fase do prefixo**, que é conhecido: o prefixo continua a 1 bit por símbolo, como na DQPSK.
3. **Uma passada guiada pelas decisões:** a fase residual de z·conj(símbolo decidido) é ajustada por uma reta, já com a SNR cheia.

**Primeira versão errada.** Ela estimava a frequência pela diferença de fase entre símbolos vizinhos da potência 8. Na potência 8, o ruído de fase de cada símbolo é multiplicado por 8, e a média de 362 diferenças deixava um erro que se acumulava até cerca de 1 rad nas pontas do quadro: BER de 6,7% a 14 dB, contra cerca de 10⁻⁶ da teoria. A busca do pico por FFT resolveu: a BER passou a bater com a teoria (9,5 × 10⁻⁶ medido contra 9,4 × 10⁻⁶ a 13 dB).

## 4. Ensaio

`ensaios/etapa6/psk8_viabilidade_ensaio.py`, 1 000 quadros de 128 bytes por ponto:

- **Pulso:** RRC β = 0,25, 3 amostras por símbolo a 2,048 MS/s (os do `prova-a`).
- **Canal realista:** offset residual de até ±500 Hz (o que o estimador do preâmbulo deixa) e a trajetória de fase real dos tons, mais ruído branco.
- **Referência:** a DQPSK passa pelo mesmo arranjo com o demodulador de produção. Ela dá 12,07 dB só com ruído, o mesmo número do receptor completo no bloco 12, então o arranjo está calibrado.

| Eb/N0 (dB) | 11 | 12 | 12,5 | 13 | 13,5 | 14 | 14,5 a 17 |
|---|---|---|---|---|---|---|---|
| PER da 8-PSK, só ruído | 24,0% | 6,1% | 2,7% | 0,6% | 0,3% | 0,1% | 0 |
| PER da 8-PSK, realista | 23,4% | 6,6% | 2,4% | 0,8% | 0,4% | 0 | 0 a 0,1% |

**Um piso de erro que não era da 8-PSK.** A primeira rodada mostrava, no canal realista, 0,1 a 0,2% de quadros perdidos até 16,5 dB, cada um com centenas de bits errados. Os quadros que falhavam tinham, na trajetória de fase, desvios de 0,13 a 0,16 rad, contra 0,006 rad no quadro mediano. A investigação achou um defeito na trajetória de fase do bloco 21: restos das emendas de leitura da gravação e quinas de frequência nas junções ([etapa6_imperfeicoes.md](etapa6_imperfeicoes.md), seção 6). Corrigido o defeito, o piso sumiu: sobra 1 quadro em 1 000 a 14,5 dB, com 1 bit errado.

## 5. O que falta para virar perfil

1. **Receptor:** o detector desta seção entra no `receptor.py` para a modulação `8psk`, com o instante estimado (não ideal) e o offset do preâmbulo.
2. **Transmissor e perfil:** 8-PSK no `modem.py` e o perfil `prova-a-8psk`.
3. **Ensaios:** a prova de 60 s simulada com os scripts, a tolerância a relógio (±50 ppm) e ao ADC de 8 bits, como nos outros perfis.
4. **Regra de troca no roteiro da prova.**
5. **Na bancada:** medir o C/N0 na distância da prova antes de escolher.

## 6. Evidências

| Evidência | Onde |
|---|---|
| Ensaio | `ensaios/etapa6/psk8_viabilidade_ensaio.py`, `dados/logs/psk8_viabilidade_20261122_201441.json`, `dados/logs/psk8_viabilidade_execucao.log` |
