# Etapa 3a: quadro v2 (número de sequência e CRC-16)

Requisitos: **PKT-01** (sequência, payload e verificação de integridade), **PKT-02** (escolha do CRC discutida), **PKT-03** (alteração do quadro documentada), **PKT-04** (payload de 128 bytes). Achados tratados: **A3** e **A9**.

Código: [`sdrlink/quadro.py`](../sdrlink/quadro.py). Testes: [`tests/test_quadro.py`](../tests/test_quadro.py). Análise do CRC: [`ensaios/etapa3/analise_crc_ensaio.py`](../ensaios/etapa3/analise_crc_ensaio.py).

## 1. Formato

Bits na ordem de transmissão. Cada campo de mais de um bit vai com o bit mais significativo primeiro, como na referência.

| Campo | Bits | Conteúdo | Mudou em relação à referência? |
|---|---|---|---|
| Preâmbulo | 16 | `1010...10` | não: limiar OOK e relógio |
| Sincronismo | 13 | Barker-13 `1111100110101` | não |
| Comprimento | 8 | tamanho do payload em bytes (0 a 255) | não |
| **Sequência** | **16** | número do pacote, 0 a 65 535 | **novo** |
| Payload | 8 × N | dados úteis (128 bytes na prova) | até 255 bytes no RX (referência: 64, A9) |
| **CRC** | **16** | CRC-16/CCITT-FALSE de comprimento + sequência + payload | **era CRC-8 só do payload** |
| Guarda | 16 | zeros | não |

Com 128 bytes de payload, o quadro tem **1 109 bits** (eficiência de 92,3%), o mesmo valor previsto no planejamento (seção 5.1).

**CRC adotado:** CRC-16/CCITT-FALSE, com polinômio x¹⁶ + x¹² + x⁵ + 1 (0x1021), valor inicial 0xFFFF, sem reflexão e sem XOR final. O valor de conferência é `crc16(b"123456789") = 0x29B1`, testado.

**Sequência:** o TX numera os pacotes a partir de 0 e volta a 0 depois de 65 535. Numa prova de 60 s, isso só acontece acima de cerca de 1 100 pacotes por segundo, o que não é atingível com 1 MHz de banda.

## 2. Por que o CRC cobre o cabeçalho

Na referência, o CRC-8 cobre só o payload. Um erro de bit no comprimento faz o RX ler o número errado de bits e, na maioria dos casos, falhar no CRC. Já um erro no número de sequência (campo novo) **passaria sem ser detectado**: o RX aceitaria o pacote com o número errado. O avaliador contaria isso como falha, e o pacote verdadeiro apareceria como perdido.

Por isso o CRC do quadro v2 cobre **comprimento, sequência e payload**. Um teste de mutante confirma que os testes pegam a volta ao comportamento da referência: com o CRC só do payload, 2 testes falham.

## 3. Por que CRC-16 (e não CRC-8 ou CRC-32)

O enunciado lembra que o CRC-8 "detecta mal erros em payloads de 128 bytes". Em vez de citar só a teoria, contei os erros que passam despercebidos no próprio quadro de 128 bytes.

O método é exato. O CRC é linear, então um padrão de erro passa sem ser detectado quando o XOR das "síndromes" dos bits errados é zero. Isso permite contar **todos** os erros de 1, 2 e 3 bits, sem amostragem. Para mais bits e para rajadas usei Monte Carlo (50 000 padrões por item, semente 20261104). O método foi conferido contra o CRC-16 real do `sdrlink.quadro` em 2 000 erros aleatórios.

| Erros não detectados | A: CRC-8 da referência, só no payload | **B: CRC-16, cabeçalho + payload (projeto)** | C: CRC-32, cabeçalho + payload |
|---|---|---|---|
| Bits por quadro depois do sync | 1 056 | 1 064 | 1 080 |
| Erros de 1 bit (exato) | **24** (todo o cabeçalho) | 0 | 0 |
| Erros de 2 bits (exato) | 3 960 | 0 | 0 |
| Erros de 3 bits (exato) | 90 440 | 0 | 0 |
| 4 bits aleatórios (Monte Carlo) | 0,67% | 0,006% | 0 em 50 000 |
| 8 bits aleatórios | 0,69% | 0,008% | 0 em 50 000 |
| Rajadas de 9 a 40 bits | 0,84% | 0 em 50 000 | 0 em 50 000 |

Fração de pacotes **aceitos com conteúdo errado** em função da BER do canal, combinando as contagens exatas com o Monte Carlo:

| BER | A: CRC-8 da referência | **B: CRC-16** | C: CRC-32 |
|---|---|---|---|
| 10⁻⁴ | 0,22% | 3 × 10⁻¹⁰ | desprezível |
| 10⁻³ | **0,99%** | 1,4 × 10⁻⁶ | desprezível |
| 10⁻² | 0,67% | 6 × 10⁻⁵ | desprezível |

Conclusões:

1. **O CRC-8 da referência não serve para a prova.** Com BER de 10⁻³, cerca de 1% dos pacotes seria aceito com conteúdo errado. Pela definição do enunciado isso conta como falha, então esse efeito sozinho já consome todo o limite de PER de 1%. Pior: o receptor não saberia que errou.
2. **O CRC-16 resolve.** Detecta todo erro de até 3 bits (distância de Hamming 4 até 32 751 bits) e toda rajada de até 16 bits. Os erros não detectados ficam na casa de 10⁻⁶ dos pacotes, quatro ordens de grandeza abaixo do limite.
3. **O CRC-32 não compensa.** Custa mais 16 bits por quadro (eficiência de 92,3% para 91,0%) e protege contra um risco que já é desprezível com o CRC-16.

## 4. Testes

| Teste | O que garante |
|---|---|
| `test_crc16_valor_de_conferencia_e_residuo_zero` | CRC-16/CCITT-FALSE padrão (0x29B1) e resto zero do quadro íntegro |
| `test_quadro_da_prova_tem_1109_bits_e_mantem_preambulo_e_sync_da_referencia` | tamanho previsto e compatibilidade de preâmbulo e sync com a referência |
| `test_ida_e_volta` | montar e interpretar devolve o mesmo pacote (payload vazio, 128 e 255 bytes, sequência 0 e 65 535) |
| `test_bits_a_mais_depois_do_quadro_sao_ignorados` | o RX pode passar mais bits do que o quadro tem |
| `test_todo_erro_de_um_bit_e_detectado` | todos os 1 064 erros possíveis de 1 bit são detectados |
| `test_amostra_de_erros_de_dois_e_tres_bits_e_detectada` | 1 000 erros aleatórios de 2 e 3 bits, todos detectados |
| `test_erro_na_sequencia_e_no_comprimento_e_detectado` | o cabeçalho está protegido (diferença em relação à referência) |
| `test_bits_insuficientes` | quadro cortado vira "curto", não erro de CRC |
| `test_validacoes` | sequência e payload fora dos limites são recusados |

Testes de mutante feitos à mão em 04/11:
- com o CRC só do payload, 2 testes falham;
- com valor inicial 0, 1 teste falha.

Nos dois casos o código original foi restaurado e os 9 testes voltaram a passar.

## 5. Evidências

| Evidência | Onde |
|---|---|
| Contagens e Monte Carlo do CRC | `dados/logs/analise_crc_20261104_110847.json` |
| Código e testes | `sdrlink/quadro.py`, `tests/test_quadro.py` |

## 6. O que fica para os próximos sub-blocos

- **3b:** os moduladores recebem os bits de `montar_quadro` e os demoduladores entregam bits a `interpretar`.
- **3c:** o RX procura todos os sincronismos acima de um limiar e chama `interpretar` em cada um. Com o comprimento protegido pelo CRC, um comprimento errado vira quadro rejeitado, não pacote errado.
- **3d:** o TX lê o arquivo de payloads de 128 bytes, numera os pacotes e grava no log a sequência e o payload de cada um. É a base para a PER oficial.
