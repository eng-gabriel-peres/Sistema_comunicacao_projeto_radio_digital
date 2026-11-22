# Etapa 6i: limiar de detecção na prova B

Requisito: CMP-B (maior alcance).

Feito em 22/11/2026, sem hardware (bloco 19).

## 1. Resultado

| Item | Resultado |
|---|---|
| Mudança | o limiar da métrica de detecção virou um campo do perfil; **0,4 no `prova-b`**, 0,5 (o de sempre) nos outros |
| Ganho na prova B | a curva de PER anda **de 0,4 a 1 dB** para a esquerda: no mesmo sinal, 4 dB por bit no ar passa de 9,0% para 1,3% de PER |
| Eb/N0 para PER 1% (nesta rodada) | 5,07 dB com 0,5; **4,12 dB com 0,4** |
| C/N0 necessário do `prova-b` | **48,2 dB-Hz** (49,2 com 0,5 nesta rodada; 48,4 com 0,5 no bloco 09) |
| Custo | só processamento: detecções a mais perto de quadros verdadeiros, rejeitadas pelo CRC; **nenhuma** detecção em 30 s só de ruído e nenhum pacote errado aceito |
| Prova de 60 s simulada, 5,5 dB no ar | 694 de 694 pacotes, goodput de 11,8 kbit/s, RX em 26 s |

## 2. Por que baixar o limiar

O limiar de 0,5 foi escolhido na Etapa 3c para quadros sem código: lá os quadros reais ficavam acima de 0,59 a partir de 8 dB, e o ruído ficava abaixo de 0,43 em 99,99% das janelas.

Com FEC o cenário muda. Cada bit no ar leva metade da energia, e o prefixo de 29 bits, que não é codificado, fica 3 dB mais fraco. A 4 dB por bit no ar a métrica dos quadros reais cai perto de 0,5, e no bloco 09 a detecção já era o gargalo (39 das 47 perdas a 4 dB). Uma detecção falsa só custa processamento, porque o quadro passa pelo Viterbi e o CRC o rejeita.

## 3. Ensaio

`ensaios/etapa6/limiar_ensaio.py`: o canal da prova B (offset de −1,4 kHz com deriva de 35 Hz/s, DC, imagem IQ), 400 quadros por ponto, **o mesmo sinal para os dois limiares**:

| Eb/N0 no ar | 2,5 | 3,0 | 3,5 | 4,0 | 4,5 | 5,0 | 5,5 | 6,0 dB |
|---|---|---|---|---|---|---|---|---|
| PER, limiar 0,5 | 84,8% | 56,8% | 21,7% | 9,0% | 3,0% | 1,3% | 0,3% | 0 |
| PER, limiar 0,4 | 72,0% | 38,0% | 10,5% | **1,3%** | **0,5%** | 0,3% | 0 | 0 |

Antes, uma varredura rápida (200 quadros) mostrou que **abaixo de 0,4 não há ganho**: a PER para de cair, porque a partir daí quem limita é o decodificador, e as detecções falsas perto dos quadros crescem muito (560 detecções para 200 quadros com 0,3).

**Sobre o número absoluto.** Com 400 quadros por ponto e uma curva tão íngreme, o cruzamento de PER 1% varia de 0,3 a 0,4 dB entre rodadas: o limiar 0,5 cruzou em 4,35 dB no bloco 09 e em 5,07 dB aqui. A comparação que vale é a pareada, no mesmo sinal, e nela o 0,4 ganha em todos os pontos.

**A reserva da prova A com FEC não ganha** (0,8% para 0,7% de PER a 4 dB): na DQPSK cada símbolo do prefixo leva a energia de 2 bits, então o prefixo é 3 dB mais forte e a detecção não é o gargalo. Ficou com 0,5.

## 4. Implementação e testes

- `Perfil.limiar` (padrão 0,5, validado entre 0 e 1); `receber.py` usa o do perfil, e `--limiar` continua valendo por cima.
- `test_limiar_de_deteccao_vem_do_perfil`: o padrão é o mesmo do receptor, o `prova-b` tem 0,4, e valores fora de (0, 1) são recusados.

## 5. Evidências

| Evidência | Onde |
|---|---|
| Ensaio do limiar | `ensaios/etapa6/limiar_ensaio.py`, `dados/logs/limiar_20261122_151453.json`, `dados/logs/limiar_execucao.log` |
| Prova de 60 s (5,5 dB no ar) | `dados/logs/prova_b_60s_6dB_20261122_151613.json` (o nome arredonda o Eb/N0), `dados/logs/prova_b_limiar_60s_execucao.log` |
