# Registro de calibração do RTL-SDR (Etapa 1)

Requisitos: **CAL-01** (correção de ppm calibrada e registrada) e **CAL-02** (offset residual medido).

## 1. Montagem do ensaio (22/10/2026)

| Item | Valor |
|---|---|
| Transmissor | ADALM-Pluto do professor, rodando `referencia/tx_test.py` sem alterações: LO em 915 MHz e tom complexo em +200 kHz, ou seja, **915,2 MHz**, ganho de TX −20 dB |
| Receptor | RTL-SDR RTL2832U + R820T2 com TCXO, no Windows 11, driver WinUSB |
| Aquecimento do RTL | cerca de 30 min ligado (estimativa; acima dos 10 min pedidos em PLT-06) |
| Sintonia do RTL | 914,95 MHz, para o tom cair em +250 kHz, longe do pico DC |
| Taxa de amostragem | 2,048 MS/s |
| Ganho | 40 dB pedido, **40,2 dB** aplicado pelo sintonizador, AGC desligado |
| Saturação do ADC | nenhuma amostra no fundo de escala |
| Ferramenta | `scripts/calibrar_rtl.py` (commit 856a5b6) |

## 2. Método

1. Captura **sem correção** (freq_correction = 0), em 8 blocos de 2²⁰ amostras (0,51 s cada, 4,1 s no total).
2. Espectro médio dos 8 blocos (janela de Hann, 1,95 Hz por bin). A média deixa o ruído liso e mostra as raias estáveis.
3. Escolha da raia mais forte numa janela de ±10 kHz em torno do esperado. O script para se a segunda raia estiver a menos de 3 dB da primeira.
4. Estimativa fina em cada bloco (±100 Hz em torno da raia), com interpolação parabólica do pico: média, desvio e deriva.
5. Erro em ppm = (f_medida − f_esperada) / f_esperada × 10⁶; correção inteira da librtlsdr = arredondamento de −erro.
6. Nova captura **com** a correção, para medir o resíduo de verdade.

## 3. Resultados

| Medição | Offset sem correção | Erro | Desvio entre blocos | Deriva | SNR mín. | Correção | Resíduo medido |
|---|---|---|---|---|---|---|---|
| 10:48:05 (só impressa; a figura falhou ao salvar, defeito corrigido) | −43,8 Hz | −0,048 ppm | 1,26 Hz | +0,20 Hz/s | 21,2 dB | 0 ppm | −43,3 Hz |
| **10:48:30 (registro oficial)** | **−42,4 Hz** | **−0,046 ppm** | 1,02 Hz | +0,17 Hz/s | 20,7 dB | **0 ppm** | **−45,7 Hz** |

Nas varreduras de diagnóstico feitas antes dessas duas medições, o tom apareceu sempre entre −41 e −47 Hz.

**Conclusão:**
- Para o par "Pluto do professor + nosso RTL-SDR", a correção de ppm é **0**.
- O **offset residual é de cerca de −44 Hz** (cerca de −0,05 ppm), estável: desvio de 1 a 2 Hz e deriva abaixo de 0,5 Hz/s.
- Esse resíduo não vem do arredondamento da correção inteira (o erro já é bem menor que 0,5 ppm). É a diferença real entre os dois osciladores.

O erro medido é **relativo** entre os dois rádios (achado A7). Com outro Pluto, a calibração precisa ser refeita.

Evidência: `dados/calibracao/calibracao_20261022_104830.json` e `.png`. A captura IQ de 64 MB (`.npy`) fica só no disco, fora do git.

## 4. Comparação com o `rx_test_915.py` do professor

O mesmo tom foi medido com o script de referência, uma vez sem alteração e outra com `freq_correction = 1` no lugar de 34, como o professor pediu. A segunda rodada usou uma cópia, para a referência ficar intocada.

| Rodada | Pico encontrado | Potência | ppm estimado | Pico depois da correção |
|---|---|---|---|---|
| Original (34 ppm) | 915,3310 MHz (+331,0 kHz) | −78,5 dB | −143,2 | 915,1690 MHz |
| Com 1 ppm | 915,1845 MHz (+184,5 kHz) | −76,5 dB | +16,9 | 915,6985 MHz |

As duas leituras estão erradas. Um RTL com TCXO não tem erro de 143 nem de 17 ppm, e o tom foi medido em 915,19996 MHz. Os motivos, confirmados no ensaio:

1. **Resolução de 500 Hz por bin** (FFT de 4096 pontos a 2,048 MS/s, achado A6). Cada bin junta o ruído de uma faixa de 500 Hz, e um tom fraco some no meio dele. Com 2²⁰ pontos o bin tem 1,95 Hz e o ruído por bin cai 256 vezes (24 dB).
2. **Busca do maior pico na banda inteira.** Há outros sinais na faixa ISM com potência parecida com a do tom aqui. A rodada com 1 ppm travou exatamente num deles.
3. **Correção inicial fixa** (34 ppm, achado A5). Num dongle com TCXO ela introduz um erro de cerca de 31 kHz, e o valor calculado depois descarta essa correção inicial.

## 5. Interferência observada na faixa

Com o espectro médio apareceram, além do tom do Pluto:

| Frequência | Desvio do tom | Altura sobre o ruído (ganho 40 dB) |
|---|---|---|
| ~915,1845 MHz (várias raias próximas) | −15,5 kHz | até 18,8 dB |
| ~915,140 MHz | −60 kHz | cerca de 20 dB |

São outros dispositivos da faixa ISM, intermitentes. Isso tem duas consequências para o projeto:
- o receptor não pode assumir que o sinal mais forte da banda é o nosso;
- a escolha da frequência e da banda do enlace precisa considerar esses sinais.

## 6. Impacto nas próximas etapas

O resíduo de cerca de 44 Hz não afeta a OOK (filtro de ±10 kHz, detecção de envoltória), mas afeta a BPSK coerente. A fase gira 360° × 44 / Rs por símbolo:

| Taxa de símbolos | Giro por símbolo | Giro num pacote de 1109 símbolos |
|---|---|---|
| 10 kbaud | 1,6° | cerca de 1760° (quase 5 voltas) |
| 100 kbaud | 0,16° | cerca de 176° |
| 250 kbaud | 0,06° | cerca de 70° |

Então, mesmo calibrado, a BPSK precisa de DBPSK ou de estimativa e correção do offset pelo preâmbulo, decisão D2 do planejamento.

## 7. Como reproduzir

Com o RTL ligado há pelo menos 10 min e o Pluto transmitindo o `tx_test.py`:

```powershell
.venv\Scripts\python scripts\calibrar_rtl.py --freq-tom-hz 915.2e6 --janela-busca-hz 10e3 --minutos-ligado 30 --salvar-iq
```

Sem `--janela-busca-hz`, a busca usa ±60 kHz. Se houver interferente parecido, o script para e avisa da ambiguidade em vez de escolher às cegas.
