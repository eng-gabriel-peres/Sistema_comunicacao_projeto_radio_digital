# Etapa 6k: 8-PSK coerente na prova A

Requisito: CMP-A (maior goodput).

Feito em 22/11/2026, sem hardware: viabilidade no bloco 23, implementação e ensaios no bloco 24. Perfil experimental `prova-a-8psk`.

## 1. Resultado

| Item | DQPSK (`prova-a`) | 8-PSK coerente (`prova-a-8psk`) |
|---|---|---|
| Bits por símbolo no corpo | 2 | 3 |
| Banda a 99% | 747 kHz | 747 kHz (mesmo pulso, mesma taxa de símbolos) |
| Prova de 60 s simulada (scripts da prova) | 1 217,8 kbit/s, PER 0,003% | **1 778,5 kbit/s (+46%), PER 0,015%**, RX em 159 s |
| Eb/N0 para PER 1%, receptor completo | 12,05 dB | 13,11 dB (13,13 com a fase real) |
| C/N0 necessário | 73,4 dB-Hz | **76,2 dB-Hz (+2,8 dB)** |
| Margem pelo C/N0 da bancada de 04/11 (78,3 dB-Hz) | 4,9 dB | **2,1 dB** |
| Diferença de relógio (ensaio de −100 a +200 ppm) | sem perda de −100 a +100 ppm; 291 de 300 a +200 | sem perda de −100 a +200 ppm |
| Ruído de fase tolerado (Wiener) | 1 kHz | **10 a 30 Hz**; o par medido equivale a 0,5 a 3,4 Hz |
| Janela do ADC sem perda | −30 a −6 dBFS | −30 a −6 dBFS (em −40 dBFS perde 50%, a DQPSK 11%) |
| Pacotes errados aceitos | nenhum | nenhum |

**Decisão:** a 8-PSK entra como perfil experimental, a primeira opção da regra de troca da prova A, mas só se a bancada mostrar as duas coisas que ela exige mais que a DQPSK:

1. C/N0 de pelo menos 78 dB-Hz na distância da prova (2 dB acima dos 76,2). Isso equivale a um Eb/N0 medido de 16,7 dB no teste com o `prova-a`.
2. Ruído de fase do par "ok" no `medir_ruido_de_fase.py`.

Ela é 100 vezes menos tolerante ao ruído de fase que a DQPSK. O par medido em 04/11 passa com folga de 3 a 60 vezes, mas outro par pode não passar. Sem isso, fica a DQPSK.

## 2. Por que coerente

A prova A é limitada pela banda (1 MHz) e pela potência, que é padronizada. Mais bits por símbolo é o único jeito de subir a taxa sem alargar o sinal. A 8-DPSK dispensaria estimar a fase, mas custa cerca de 3 dB a mais. Somados aos 1,8 dB da taxa 1,5 vez maior, não caberia na margem.

## 3. O receptor

O prefixo continua a 1 bit por símbolo, como na DBPSK e na DQPSK. A detecção dos quadros não muda, e o modelo do prefixo é o mesmo da DQPSK. No corpo, por quadro (`sdrlink/modem.py`):

1. **Fase de referência:** as decisões diferenciais do prefixo reconstroem os símbolos conhecidos e dão a fase de referência.
2. **Frequência:** sai da potência 8 dos símbolos do corpo, que tira a modulação. É o pico do espectro por FFT (máxima verossimilhança), refinado por parábola. A busca é limitada a ±0,02 rad por símbolo (2,2 kHz na prova A), o resíduo que o estimador do preâmbulo pode deixar.
3. **Fase inicial:** a do prefixo, levada até o início do corpo por essa frequência.
4. **Rastreio:** uma malha de fase guiada pelas decisões, símbolo a símbolo, com ganho de 0,1 por símbolo.
5. **Decisão:** mapa de Gray, com saída suave max-log por bit, que também serve ao Viterbi.

## 4. O ganho da malha de fase

`ensaios/etapa6/rastreio_8psk_ensaio.py`, com sincronismo ideal, offset residual de até ±300 Hz, 400 quadros por ponto, 1 dB acima do ponto de PER 1% (13,9 dB):

| Ganho | Wiener 10 Hz | 30 Hz | 100 Hz | 300 Hz | PER só com ruído branco a 12,9 dB |
|---|---|---|---|---|---|
| 0 (uma reta por quadro) | 16,5% | 55,8% | 96,5% | 100% | 1,40% |
| 0,05 | 0,25% | 1,0% | 44,5% | 99,3% | 1,45% |
| **0,1 (o escolhido)** | 0 | 0,25% | 10,0% | 89,3% | 1,65% |
| 0,2 | 0 | 0,25% | 3,0% | 40,3% | 2,40% |

O ganho 0,1 custa cerca de 0,2 dB no ruído branco (13,11 contra 12,92 dB no receptor completo) e leva a tolerância de menos de 10 Hz para algo entre 10 e 30 Hz no receptor completo. O 0,2 aguentaria mais, mas custaria cerca de 0,4 dB, e o par medido não precisa disso.

## 5. Ensaios

**Receptor completo** (`prova_a_8psk_ensaio.py`): o canal da prova A, com offset de −1,4 kHz, atraso fracionário, DC e imagem IQ medidos na captura real, 1 000 quadros por ponto. A DQPSK no mesmo canal dá os mesmos 12,05 dB do bloco 12.

| Eb/N0 (dB) | 11 | 12 | 12,5 | 13 | 13,5 | 14 | 14,5 a 16 |
|---|---|---|---|---|---|---|---|
| PER da 8-PSK | 32,6% | 7,9% | 4,4% | 1,3% | 0,4% | 0,2% | 0 a 0,1% |
| PER com a fase real | 34,0% | 10,5% | 4,3% | 2,2% | 0,1% | 0,2% | 0 |

**Imperfeições** (`imperfeicoes_ensaio.py`, a 8-PSK junto dos outros perfis):

- **Fase real:** sem efeito detectável (5,8% contra 5,1% e 5,7%, intervalos de 95% sobrepostos).
- **Wiener**, 1 dB acima do ponto de 1%: 0,25% com 10 Hz, 1,5% com 30 Hz, 15,8% com 100 Hz.
- **ADC:** sem perda de −30 a −6 dBFS; 50% em −40 dBFS; 2% em −3 dBFS, com 36% das amostras saturadas.

**Relógio** (`relogio_ensaio.py`): 300 de 300 quadros de −100 a +200 ppm (o ensaio não vai a −200).

**Prova de 60 s** (`prova_a_60s_ensaio.py 15 prova-a-8psk`), com os scripts da prova:

- **Pacotes:** 104 208 de 104 224 certos.
- **Goodput:** 1 778,5 kbit/s.
- **Banda medida:** 748 kHz.
- **RX:** 159 s.

## 6. Defeitos achados no caminho

1. **Estimador de frequência da primeira versão (bloco 23).** Usava a diferença de fase entre vizinhos da potência 8, que multiplica o ruído por 8. Dava BER de 6,7% a 14 dB. Trocado pela busca do pico por FFT.
2. **O mapa não era Gray (blocos 23 e 24).** O vetor de Gray foi usado no sentido contrário (fase → bits em vez de bits → fase): as fases vizinhas 2 e 3 levavam 010 e 111. O teste do mapa achou, e a viabilidade foi refeita (12,8 dB só com ruído, contra 12,99 da teoria).
3. **A BER teórica "exata" foi integrada com o mesmo mapa errado.** Por isso batia com a simulação errada e parecia 25% acima da aproximação dos vizinhos. Com o Gray certo, as duas coincidem. A integração também estourava (`exp`) acima de 24 dB, e foi reescrita sem estouro.
4. **Uma reta de fase por quadro não acompanhava o ruído de fase.** Com Wiener de 10 Hz a PER ia a 16,5%. Na primeira tentativa de rastreio, uma média móvel das decisões do quadro inteiro, a janela não fazia diferença: com a fase longe da reta, as primeiras decisões no meio do quadro já saíam erradas e a média só as confirmava. A malha símbolo a símbolo resolveu.
5. **A ambiguidade de 45° pela fase média do corpo.** Com ruído de fase, a fase média do corpo se afasta da do prefixo. A fase inicial passou a vir do próprio prefixo: com ganho 0,2 e 100 Hz, a PER caiu de 8% para 2,75%. Nenhum caso sem ruído separa as duas versões, então essa escolha tem evidência estatística, não teste de mutante.
6. **A malha em Python custava 2,4 ms por quadro**, cerca de 121 s numa prova de 60 s. O laço passou a andar só sobre os ângulos, em aritmética escalar: 0,09 ms por quadro, com o mesmo resultado.
7. **A referência de pico e banda do TX era curta demais para 3 bits por símbolo** (4 000 bits, 1 334 símbolos, menos que o segmento de Welch). Agora tem pelo menos 2 000 símbolos. A DQPSK e as de 1 bit por símbolo ficaram exatamente como estavam.
8. **A passada guiada por uma reta nas decisões** foi medida e não deu ganho (4,3% contra 4,45% de PER a 12 dB): ficou de fora.
9. **O ensaio de 60 s ficava sem payloads aos 57 s** (100 000 no arquivo, cabem 104 224). Agora gera 130 000. **Na prova, o arquivo do avaliador precisa ter pacotes para os 60 s**: o `transmitir.py` avisa quando não tem.
10. **O `medir_ruido_de_fase.py` olhava só um símbolo**, o que basta para os diferenciais, mas não para a 8-PSK, e diria "ok" num par que a derrubaria. Para a 8-PSK ele mede em 0,39 ms, onde o ruído de fase real aparece, contra o Wiener de 10 Hz que ela tolera. O par de 04/11 dá 0,034 a 0,037 rad contra a tolerância de 0,157.

## 7. Alternativa considerada e descartada

**8-PSK com o RTL a 2,4 MS/s:** cerca de 2 085 kbit/s, mas pediria 76,9 dB-Hz. Com os 2 dB de folga da regra, seriam 78,9 dB-Hz, acima dos 78,3 dB-Hz da bancada de 04/11. Ela ainda dependeria de três validações ao mesmo tempo (2,4 MS/s, ruído de fase e C/N0). Com a evidência que temos não passa, e o perfil não foi criado.

## 8. Testes

- **`tests/test_modem.py`:**
  - ida e volta com qualquer fase e offset de ±500 Hz, para corpos de 1 a 1 088 bits;
  - o mapa de Gray (vizinhos diferem em 1 bit) e o prefixo igual ao da DBPSK;
  - a perda de implementação a 10 dB (BER entre 0,85 e 1,5 vez a teoria, em 3 sementes);
  - a BER teórica exata, contra a aproximação e sem estouro;
  - a saída suave com o sinal da decisão, e o erro sem prefixo;
  - o limite da busca de frequência;
  - o rastreio com Wiener de 30 Hz (PER abaixo de 2%, em 2 sementes).
- **`tests/test_receptor.py`:**
  - a 8-PSK no teste de todos os quadros com offset, atraso e emendas;
  - o perfil da prova A com e sem FEC.
- **`tests/test_config.py`:** o perfil, a taxa e a banda abaixo de 1 MHz.
- **`tests/test_fase.py`:** o script de bancada para a 8-PSK.

Mutantes mortos:

- ambiguidade não resolvida;
- referência sem as decisões do prefixo;
- ordem dos bits;
- sem estimar a frequência;
- FFT truncada;
- busca sem limite;
- mapa não Gray;
- referência do TX curta;
- sem rastreio.

O único que sobrevive é a fase inicial pela média da potência 8 (item 5 da seção 6, com a medida estatística).

## 9. Evidências

| Evidência | Onde |
|---|---|
| Viabilidade (bloco 23, refeita com o Gray certo) | `ensaios/etapa6/psk8_viabilidade_ensaio.py`, `dados/logs/psk8_viabilidade_20261122_203837.json` |
| Receptor completo | `ensaios/etapa6/prova_a_8psk_ensaio.py`, `dados/logs/prova_a_8psk_20261122_210316.json`, `dados/logs/prova_a_8psk_execucao.log` |
| Ganho da malha de fase | `ensaios/etapa6/rastreio_8psk_ensaio.py`, `dados/logs/rastreio_8psk_20261122_210124.json` |
| Imperfeições e relógio (todos os perfis) | `dados/logs/imperfeicoes_20261122_211000.json`, `dados/logs/relogio_20261122_210538.json` |
| Prova de 60 s | `dados/logs/prova_a_8psk_60s_15dB_20261122_212032.json`, `dados/logs/prova_a_8psk_60s_execucao.log` |
