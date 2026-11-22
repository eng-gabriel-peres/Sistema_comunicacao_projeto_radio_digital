# Etapa 6j: imperfeições do hardware (ruído de fase e ADC de 8 bits)

Requisitos: robustez dos perfis finais (CMP-A, CMP-B), preparação da bancada (RX-01, MET-05).

Feito em 22/11/2026, sem hardware novo, com as gravações reais do tom do Pluto da equipe de 04/11/2026 (bloco 21).

## 1. Resultado

| Item | Resultado |
|---|---|
| Ruído de fase **medido** no par Pluto + RTL | −62 dBc/Hz a 1 kHz, −71 a 3 kHz, −77 a 10 kHz; acima de 30 kHz some no piso branco da gravação (−79 dBc/Hz) |
| Variação de fase em **um símbolo** | **não detectável** em nenhum perfil: a medida é toda explicada pelo ruído branco da gravação (a previsão bate em 3%); o limite superior é cerca de 0,01 rad na prova B e menos na prova A |
| Onde o ruído de fase aparece | só em escalas bem mais longas que um símbolo: 0,037 rad em 0,39 ms e 0,18 rad em 1,6 ms |
| Fase real aplicada aos perfis | **nenhum efeito detectável** na PER: em 4 sementes, os intervalos de 95% com e sem a fase real se sobrepõem nos cinco perfis |
| Margem (ruído de Wiener até a PER passar de 1%) | prova A aguenta **1 kHz** de largura de linha (0,096 rad por símbolo); DBPSK e DQPSK com FEC, **3 kHz**; prova B, **300 Hz** (0,27 rad por símbolo). Contra o medido (menos de 0,0054 rad por símbolo na prova A, cerca de 0,01 rad na prova B): folga de **16 a 31 vezes** |
| ADC de 8 bits do RTL | **sem perda de −30 a −6 dBFS** de nível eficaz na entrada; em −40 dBFS a prova A já perde 11% dos pacotes; em −3 dBFS um terço das amostras satura, e ainda assim a detecção diferencial resiste |
| Na bancada | o `gravar_iq.py` registra e mostra o nível eficaz; o `receber.py` avisa fora da janela; ganho do RX para ficar entre **−20 e −12 dBFS**; `scripts/medir_ruido_de_fase.py` repete a medida do tom com o par da prova (item 1.3b do plano) |

## 2. Por que olhar isso

A simulação até aqui tinha AWGN, offset e deriva de frequência, DC, imagem IQ e diferença de relógio. Faltavam duas imperfeições do hardware que podem derrubar um enlace que funciona na simulação:

- **Ruído de fase dos osciladores** do Pluto e do RTL. Os receptores diferenciais decidem pela variação de fase de um símbolo para o seguinte. Se o oscilador andar demais nesse intervalo, a decisão erra. A DQPSK, com margem de 45°, é a mais sensível por símbolo. A prova B, com símbolos 27 vezes mais longos, é a que dá mais tempo para a fase andar.
- **O ADC de 8 bits do RTL.** Com o ganho baixo, o sinal ocupa poucos níveis e o erro de quantização vira ruído. Com o ganho alto, o sinal satura.

## 3. Ruído de fase medido

**Método** (`sdrlink/fase.py`): o tom é misturado para zero e filtrado em ±50 kHz, e a fase é desdobrada. Depois:

- **Variação em τ amostras:** calculo o valor eficaz da variação de fase em τ, com o offset de cada trecho de 16 ms retirado, porque o RX estima o offset em cada quadro.
- **Desconto do ruído branco:** a parte que vem do ruído branco da própria gravação é calculada pelo piso do espectro e pela autocorrelação do filtro, e descontada.
- **Emendas de leitura:** as gravações de 04/11 são anteriores à leitura assíncrona (achado A17) e têm **30 a 37 saltos de fase**, um em cada emenda de leitura de 262 144 amostras. Os trechos em volta dos saltos ficam fora da conta.

| τ | O que é | Medida | Só ruído branco | Ruído de fase |
|---|---|---|---|---|
| 3 amostras | um símbolo da prova A | 0,0054 rad | 0,0056 rad | não detectável |
| 80 amostras | um símbolo da prova B | 0,0338 rad | 0,0343 rad | não detectável |
| 800 amostras | 0,39 ms | 0,050 rad | 0,033 rad | 0,037 rad |
| 3 200 amostras | 1,6 ms | 0,186 rad | 0,033 rad | 0,183 rad |

As duas gravações, feitas com 3 minutos de diferença, dão os mesmos números a menos de 0,002 rad.

**Limite do método.** O filtro de 50 kHz não vê o ruído de fase acima de 50 kHz de afastamento. Ali o espectro do tom já está no piso branco (−79 dBc/Hz), então esse ruído de fase, se existir, se comporta como ruído branco somado ao do canal e entra no Eb/N0 medido.

**A fase dentro de um quadro** (bloco 22, `ensaios/etapa6/fase_no_quadro_ensaio.py`). Uma detecção coerente estimaria a fase e o offset uma vez por quadro; o que sobra é o desvio da fase real em torno dessa reta:

| Perfil | Quadro | Desvio eficaz: mediana | p95 | máximo | Perda coerente no p95 / no máximo |
|---|---|---|---|---|---|
| `prova-a` | 0,84 ms | 0,006 rad | 0,009 rad | 0,15 a 0,17 rad | 0 / 0,1 dB |
| `prova-a-fec`, `prova-a-dbpsk` | 1,6 ms | 0,006 rad | 0,009 rad | 0,12 a 0,19 rad | 0 / 0,06 a 0,16 dB |
| `prova-b` | 86 ms | 0,08 a 0,09 rad | 0,23 a 0,25 rad | 0,38 a 0,40 rad | 0,23 a 0,28 / 0,66 a 0,72 dB |

Na prova B a perda da detecção coerente nos piores quadros é do tamanho do ganho que ela daria com FEC (0,3 dB, bloco 09): a detecção diferencial continua a escolha certa. Nos quadros curtos da prova A a fase quase não anda, e uma detecção coerente seria viável ali.

**O nível das gravações reais.** As gravações de 04/11 ficaram entre −17 e −19 dBFS, sem saturação: os ganhos usados naquele dia já estavam dentro da janela recomendada.

## 4. Ensaio nos perfis finais

`ensaios/etapa6/imperfeicoes_ensaio.py`, com offset de −1,4 kHz e o receptor completo. O Eb/N0 de referência é o de PER 1% de cada perfil (relatório final, seção 4).

**Fase real**: a trajetória de fase dos tons, filtrada em 2 kHz (a parte acima do piso), sem os saltos, aplicada aos sinais simulados 0,5 dB abaixo do ponto de 1%. Girar a fase do sinal muda quais amostras de ruído causam erro, então a comparação é estatística: 4 sementes de ruído e o intervalo de Wilson de 95%.

| Perfil | Sem | Com o tom 1 | Com o tom 2 |
|---|---|---|---|
| `prova-a` | 3,6% [2,8; 4,7] | 2,8% [2,1; 3,7] | 2,6% [2,0; 3,5] |
| `prova-a-24` | 2,3% [1,7; 3,2] | 2,3% [1,6; 3,1] | 2,3% [1,6; 3,1] |
| `prova-a-fec` | 6,1% [4,9; 7,6] | 6,8% [5,5; 8,4] | 6,7% [5,4; 8,2] |
| `prova-a-dbpsk` | 3,6% [2,7; 4,8] | 2,9% [2,1; 4,0] | 3,2% [2,3; 4,3] |
| `prova-b` | 10,6% [8,2; 13,7] | 7,9% [5,8; 10,7] | 10,0% [7,6; 13,0] |

As diferenças vão para os dois lados e cabem nos intervalos.

**Margem**: ruído de Wiener cada vez maior, 1 dB acima do ponto de 1% (PER):

| Largura de linha | 0 | 100 Hz | 300 Hz | 1 kHz | 3 kHz | 10 kHz |
|---|---|---|---|---|---|---|
| `prova-a` | 0,3% | 0,5% | 0 | **1,0%** | 11,8% | 99,5% |
| `prova-a-24` | 0,3% | 0,3% | 0 | **0,8%** | 6,5% | 93,8% |
| `prova-a-fec` | 0 | 0 | 0 | 0 | **0,3%** | 14,3% |
| `prova-a-dbpsk` | 0,3% | 0 | 0 | 0 | **0,3%** | 13,0% |
| `prova-b` | 0 | 0 | **0,8%** | 29,2% | 98,3% | |

**ADC de 8 bits**: o sinal com ruído, 1 dB acima do ponto de 1%, pelo ADC do RTL com nível eficaz de −60 a −3 dBFS (PER):

| Nível | −60 | −50 | −40 | −30 | −20 | −12 | −6 | −3 dBFS |
|---|---|---|---|---|---|---|---|---|
| `prova-a` | 100% | 100% | 11,0% | 0,3% | 0,3% | 0,3% | 0,3% | 0,3% |
| `prova-a-24` | 100% | 100% | 8,3% | 0,5% | 0,3% | 0,3% | 0,3% | 0,8% |
| `prova-a-fec` | 88,3% | 83,0% | 0 | 0 | 0 | 0 | 0 | 0 |
| `prova-a-dbpsk` | 99,0% | 98,7% | 1,3% | 0 | 0,3% | 0,3% | 0,3% | 0,7% |
| `prova-b` | 26,7% | 13,3% | 0,8% | 0 | 0 | 0 | 0 | 0 |
| Amostras saturadas | 0 | 0 | 0 | 0 | 0 | 0 a 0,02% | 4 a 9% | 30 a 35% |

O ADC simulado é ideal. O do RTL tem cerca de 7 bits efetivos, por isso a janela recomendada fica com folga dos dois lados: −20 a −12 dBFS.

**Desequilíbrio IQ.** Não foi varrido aqui. Em todos os perfis o deslocamento passa da metade da banda, então a imagem cai do outro lado do DC e não se sobrepõe ao sinal. O ensaio da prova B já inclui uma imagem a −45 dBc.

## 5. Implementação e testes

- `sdrlink/fase.py`: `fase_do_tom`, `variacao_de_fase_rad`, `variacao_do_ruido_branco_rad`, `descontar`, `ruido_de_fase_dbc_hz`, `trajetoria`, `largura_equivalente_hz`.
- `sdrlink/canal.py`: `ruido_de_fase` (Wiener) e `quantizar_8_bits` (a escala do pyrtlsdr).
- `sdrlink/hw/rtl_rx.py`: `nivel_eficaz_dbfs` e `aviso_de_nivel`, usados pelo `gravar_iq.py` e pelo `receber.py`.
- `scripts/medir_ruido_de_fase.py`: a medida do tom na bancada, perfil a perfil, contra a tolerância. Situações: "ok", "ATENÇÃO" ou "inconclusivo", quando o tom está fraco demais.

Testes (`tests/test_fase.py`, `tests/test_rtl_rx.py`, `tests/test_config.py`), todos com sinais de ruído de fase conhecido:

- **Wiener:** a variância do modelo em vários atrasos.
- **ADC:** os 256 níveis do pyrtlsdr, a SQNR de 32,9 dB a −20 dBFS e a saturação perto do fundo de escala.
- **Fase do tom:** frequência e variação de fase de Wiener medidas no tom.
- **Deriva:** uma deriva forte de frequência fora da conta.
- **Saltos de emenda:** 10 saltos de 1,5 rad detectados e excluídos.
- **Ruído branco:** a parte prevista dele em todo atraso, e o desconto devolvendo o ruído de fase.
- **Espectro:** L(f) contra Δν/(2πf²) e o piso branco.
- **Trajetória:** contínua, sem degrau e do tamanho pedido.
- **Janela de nível:** o aviso do `receber.py` aparece.
- **Script de bancada:** "ok", "ATENÇÃO" e "inconclusivo".

Os testes estatísticos passam em 5 sementes diferentes.

Mutantes (11, todos mortos):

- saltos não excluídos;
- offset do trecho mantido (o primeiro teste deixou esse passar e foi refeito com ruído de fase perto do real);
- ruído branco não descontado;
- correlação do filtro ignorada;
- degrau na repetição da trajetória;
- ADC sem saturação;
- Wiener com metade da variância;
- limite da janela de nível;
- script sem "inconclusivo" e sem "ATENÇÃO".

## 6. Defeitos achados no caminho

- **A detecção de saltos do primeiro rascunho via só os saltos perto de π.** O filtro espalha um salto por cerca de 40 amostras, e o limiar era por amostra. Com isso a variação medida na prova B saía inflada (0,0407 rad em vez de 0,0338). A detecção passou a olhar a variação em 64 amostras, com limiar adaptativo (8 desvios robustos, no mínimo 0,3 rad).
- **A comparação de PER com uma semente só enganava.** Na primeira rodada a fase real "piorou" a DQPSK com FEC de 6% para 9% e "melhorou" a prova A. Era variação estatística. Refiz com 4 sementes e o intervalo de confiança.
- **Na docstring do ruído de Wiener eu tinha escrito L(f) ≈ Δν/(πf²).** O certo é Δν/(2πf²), e o teste agora confere.

## 7. Evidências

| Evidência | Onde |
|---|---|
| Ensaio | `ensaios/etapa6/imperfeicoes_ensaio.py`, `dados/logs/imperfeicoes_20261122_161617.json`, `dados/logs/imperfeicoes_execucao.log` |
| Fase dentro de um quadro (bloco 22) | `ensaios/etapa6/fase_no_quadro_ensaio.py`, `dados/logs/fase_no_quadro_20261122_195512.json`, `dados/logs/fase_no_quadro_execucao.log` |
| Gravações reais usadas | `dados/calibracao/calibracao_20261104_100631_depois.npy` e `..._100917_depois.npy` (fora do git pelo tamanho; os JSON de calibração estão no git) |
