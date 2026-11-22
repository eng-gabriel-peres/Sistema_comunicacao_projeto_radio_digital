# Etapa 6e: Viterbi em lote e a DQPSK com FEC como reserva da prova A

Requisitos: CMP-A (processamento em até 10 min no computador do RX), CMP-B.

Feito em 22/11/2026, sem hardware (bloco 11).

## 1. Resultado

| Item | Resultado |
|---|---|
| O que mudou | o receptor decodifica **todos os quadros com FEC de um bloco de captura de uma vez**, em vez de um por vez |
| Resultado | **idêntico, bit a bit**, ao receptor do bloco 10, em 5 casos (equivalência na seção 3) |
| Tempo do RX, DQPSK com FEC a 1,4 Mbit/s no ar | de cerca de 12,8 para **1,5 a 1,6 s por segundo de captura** (8 vezes) |
| Prova de 60 s simulada com o perfil `prova-a-fec` | **passa**: 36 313 de 36 313 pacotes (PER 0%) a 6 dB por bit no ar, goodput de 619,7 kbit/s, RX em 89 s (seção 4) |
| Nova reserva da prova A | `prova-a-fec`: DQPSK com FEC, o **mesmo goodput da DBPSK com 3,3 dB a mais de margem** (65,4 contra 68,7 dB-Hz de C/N0 necessário, bloco 10) |

## 2. Por que o Viterbi em lote

O decodificador de Viterbi percorre a treliça passo a passo: são 1 078 passos para um quadro de 128 bytes, e em cada passo atualiza 64 estados. Decodificando um quadro por vez, o laço em Python fazia 1 078 iterações por quadro com operações pequenas (64 elementos), e o custo fixo de cada operação do NumPy dominava. Na DQPSK com FEC a 1,4 Mbit/s no ar chegam cerca de 1 170 quadros por segundo, e o RX levava **6,9 s por segundo de captura** (bloco 10): cerca de 7 minutos para a prova de 60 s, perto do limite de 10 minutos.

Em lote, cada passo atualiza os 64 estados de **todos** os quadros do bloco na mesma operação: o número de iterações em Python fica o mesmo de um quadro só, e o custo fixo se divide entre centenas de quadros.

## 3. Como foi feito e como verifiquei

| Onde | O quê |
|---|---|
| `sdrlink/codigo.py` | `decodificar_lote(matriz, n_bits)`: uma palavra por linha, em lotes de até 256 (a memória das decisões é passos × lote × 64 bytes); `decodificar` virou o lote de uma palavra |
| `sdrlink/receptor.py` | a leitura de um quadro com FEC foi dividida em **primeira leitura** (saída suave na janela de 128 bytes) e **conclusão** (decide se relê com o comprimento decodificado); no `receber_bloco`, com FEC, primeiro todas as primeiras leituras, depois o lote, depois as releituras, na ordem original |

**Verificação:**
- **Decodificador:** em 300 palavras com muito ruído (14 327 bits errados), o lote dá exatamente os mesmos bits que a versão anterior, **11,7 vezes mais rápido**. O teste `test_lote_igual_a_um_por_vez_inclusive_acima_do_tamanho_do_lote` compara 300 palavras (dois lotes) e confere que colunas a mais são ignoradas.
- **Receptor:** `ensaios/etapa6/viterbi_lote_ensaio.py` roda o receptor novo e o da tag `bloco-10` (lido do git) nas mesmas capturas:

| Caso | Detecções | Aceitos | Idênticos | RX em lote | RX antes | Aceleração |
|---|---|---|---|---|---|---|
| DQPSK 1 365 kbit/s no ar com FEC, 4 dB (600 quadros) | 600 | 597 | sim | 1,61 s/s | 12,73 s/s | 7,9 vezes |
| DQPSK 1 365 kbit/s no ar com FEC, 6 dB (600 quadros) | 600 | 600 | sim | 1,53 s/s | 12,96 s/s | 8,5 vezes |
| DBPSK 25,6 kbit/s no ar com FEC (`prova-b`), 4 dB | 78 | 77 | sim | 0,39 s/s | 0,58 s/s | 1,5 vez |
| DBPSK, payloads de 40, 128 e 200 bytes e um curto no fim | 8 | 8 | sim | 2,31 s/s | 3,80 s/s | 1,6 vez |
| DQPSK, payloads de 40, 128 e 200 bytes e um curto no fim | 8 | 8 | sim | 5,10 s/s | 10,52 s/s | 2,1 vezes |

Nos casos com poucos quadros o ganho é menor, porque o lote tem poucas palavras: o laço continua com o mesmo número de passos. Nas capturas curtas o tempo por segundo é alto por causa do custo fixo de cada bloco; o que importa é o caso da prova, com muitos quadros.

- **Teste do receptor:** `test_fec_em_lote_igual_a_leitura_quadro_a_quadro` confere que cada quadro lido em lote é igual, bit a bit, ao lido sozinho por `demodular_quadro`.

## 4. Prova de 60 s com a DQPSK com FEC

`ensaios/etapa6/prova_a_60s_ensaio.py 6 prova-a-fec`: os comandos da prova com o perfil `prova-a-fec`, a 6 dB por bit no ar (2 dB acima dos 4,0 dB necessários).

| Item | Resultado | Limite da prova |
|---|---|---|
| Pacotes transmitidos (log do TX) | 36 313 | |
| Recebidos certos | **36 313** | |
| PER | **0%** | até 1% |
| Goodput | **619,7 kbit/s** | |
| Conteúdo diferente / espúrios | 0 / 0 | |
| Banda a 99% medida na captura | **749,9 kHz** | até 1 MHz |
| Tempo do RX para a captura de 61,5 s | **89,2 s** (antes do lote seriam cerca de 7 min) | até 10 min |

## 5. A regra de troca da prova A, agora com três degraus

| Perfil | Goodput | C/N0 necessário | Margem na bancada de 04/11 | RX |
|---|---|---|---|---|
| `prova-a` (DQPSK) | 1 193 kbit/s | 73,4 dB-Hz | 4,9 dB | cerca de 1,3 min para 60 s |
| `prova-a-fec` (DQPSK com FEC) | 620 kbit/s | 65,4 dB-Hz | 12,9 dB | cerca de 1,5 min |
| `prova-a-dbpsk` (DBPSK) | 619 kbit/s | 68,7 dB-Hz | 9,6 dB | cerca de 1,2 min |

Na bancada, antes da prova:
1. Transmitir 10 s com `prova-a` e processar: o `receber.py` mede o Eb/N0.
2. **Eb/N0 de pelo menos 15 dB e PER de até 0,5%:** fica `prova-a`.
3. Senão, repetir com `prova-a-fec`. **PER de até 0,5%:** fica `prova-a-fec`.
4. Senão: `prova-a-dbpsk`. A DQPSK com FEC é mais robusta ao ruído branco, mas os pontos da DQPSK estão a 90°, não a 180°: se o ruído de fase ou o desequilíbrio IQ reais pesarem mais que o previsto, a DBPSK pode se sair melhor mesmo com menos margem teórica. O passo 4 cobre esse caso.

## 6. Testes

Total do projeto: 227 testes. Novos: lote igual a um por vez (dois lotes e colunas a mais), entradas inválidas do lote, receptor em lote igual à leitura quadro a quadro.

| Mutante | Testes que falham |
|---|---|
| Traceback com as decisões da primeira palavra do lote | 6 |
| Lote que perde a última palavra de cada fatia | 1 |
| Conclusão sem a releitura | 2 |
| Lote devolvido fora de ordem | 4 |
| Normalização da métrica pelo máximo global, e não o de cada palavra | 0: **mutante equivalente**. Subtrair a mesma constante de todos os estados de uma palavra não muda nenhuma decisão; nenhum teste pode distinguir os dois |

## 7. Evidências

| Evidência | Onde |
|---|---|
| Equivalência e tempo | `ensaios/etapa6/viterbi_lote_ensaio.py`, `dados/logs/viterbi_lote_20261122_112923.json`, `dados/logs/viterbi_lote_execucao.log` |
| Prova de 60 s | `dados/logs/prova_a_fec_60s_6dB_20261122_113148.json`, `dados/logs/prova_a_fec_60s_execucao.log` |
| Código e testes | `sdrlink/codigo.py`, `sdrlink/receptor.py`, `configs/perfis.toml` (`prova-a-fec`), `tests/test_codigo.py`, `tests/test_receptor.py` |
