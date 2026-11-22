# Etapa 3d: transmissor de prova, log do TX e métricas

Requisitos:
- **PKT-04:** payloads de 128 bytes lidos do arquivo do avaliador;
- **TX-01:** log do TX, referência da PER;
- **PLT-05:** banda dentro de 915 a 928 MHz;
- **MET-01** (goodput) e **MET-02** (PER): mesma conta do avaliador.

Achado tratado: **A4**. A referência repetia o mesmo quadro num buffer cíclico, sem log.

Código:
- [`sdrlink/transmissor.py`](../sdrlink/transmissor.py): transmissor;
- [`sdrlink/metricas.py`](../sdrlink/metricas.py): métricas;
- `transmitir_fluxo` em [`sdrlink/hw/pluto_tx.py`](../sdrlink/hw/pluto_tx.py): envio contínuo ao Pluto;
- comando [`scripts/transmitir.py`](../scripts/transmitir.py).

Testes: [`tests/test_transmissor.py`](../tests/test_transmissor.py).

## 1. Resultado: uma rodada de prova simulada, com os comandos reais

[`ensaios/etapa3/enlace_simulado_ensaio.py`](../ensaios/etapa3/enlace_simulado_ensaio.py) faz uma rodada inteira sem hardware:
1. gera um arquivo de 5 000 payloads aleatórios de 128 bytes, como o do avaliador;
2. roda `scripts/transmitir.py --simular` com janela de 10 s;
3. passa o sinal por um canal com 0,3 s de silêncio, offset de −1,4 kHz (dentro do A18), atraso fracionário e ruído;
4. roda `scripts/receber.py` na "captura";
5. compara o log do TX com a saída do RX por `sdrlink.metricas`.

| Caso | Transmitidos | Certos | PER | Goodput | Conteúdo errado aceito | Offset estimado | RX para 60 s |
|---|---|---|---|---|---|---|---|
| DBPSK RRC 256 kbit/s, 12 dB | 2 282 | 2 282 | **0%** | **233,7 kbit/s** | 0 | −1 386 Hz | cerca de 3,6 min |
| DBPSK RRC 256 kbit/s, 10 dB | 2 282 | 2 227 | 2,4% | 228,0 kbit/s | 0 | −1 384 Hz | cerca de 3,9 min |
| GFSK 128 kbit/s, 15 dB | 1 142 | 1 135 | 0,6% | 116,2 kbit/s | 0 | −1 428 Hz | cerca de 2,6 min |
| OOK RRC 128 kbit/s, 15 dB | 1 142 | 1 142 | **0%** | 116,9 kbit/s | 0 | −1 497 Hz | cerca de 2,8 min |

Registro: `dados/logs/enlace_simulado_20261121_231317.json` e `dados/logs/enlace_simulado_execucao.log`.

O que isso mostra:

- **A cadeia está completa.** Arquivo do avaliador, quadros numerados, sinal, receptor, arquivo de saída e PER com goodput pela regra do enunciado, sem nenhum passo manual.
- **Nenhum pacote foi aceito com conteúdo errado e não houve espúrios**, em 6 848 pacotes.
- **Prova B** (10 kbit/s de goodput, no mínimo 500 pacotes e PER de até 1%): a DBPSK a 256 kbit/s entrega cerca de 234 kbit/s e cerca de 13 700 pacotes em 60 s. Ela cumpre a PER a partir de cerca de 11 dB de Eb/N0 no receptor. A 10 dB a PER foi de 2,4%, o que bate com a curva do 3c.
- **Processamento:** o RX levou cerca de 3,5 s por segundo de captura a 256 kbit/s, ou seja, cerca de 3,6 min para os 60 s da prova, dentro dos 10 min. É mais lento que os 1,16 s/s medidos a 10 kbit/s porque há muito mais quadros por segundo e cada leitura demodula a janela do maior quadro possível. Fica como otimização para a Etapa 6.
- **TX:** gerou o sinal a 0,44 vez o tempo real. O Pluto consome em tempo real, então há folga de cerca de 2,3 vezes (ver o risco R1 na seção 5).

## 2. Como funciona

**Payloads.** O formato do arquivo do avaliador ainda não foi divulgado. Por isso aceito dois:
- `.bin`: bytes corridos, 128 por pacote;
- `.txt`: um payload em hexadecimal por linha.

Tamanho errado, arquivo vazio ou extensão desconhecida param a transmissão com mensagem clara.

**Numeração.** A sequência começa em 0 e volta a 0 depois de 65 535 (`numerar`).

**Fluxo de amostras** (`fluxo`):
- cada pacote vira um quadro v2 (`sdrlink.quadro`), modulado (`sdrlink.modem`) e deslocado para LO + deslocamento, com a **fase contínua** de um quadro para o outro;
- os quadros vão um atrás do outro, separados pela guarda de 16 bits do próprio quadro;
- o fluxo sai em **blocos de tamanho fixo** (2¹⁸ amostras, 128 ms), porque a libiio fixa o tamanho do buffer no primeiro envio;
- **só começam pacotes dentro da janela** pedida. A seção 8 diz que "contam os pacotes cuja transmissão começa dentro da janela". O pacote que começou termina, e o último bloco é completado com zeros.

**Amplitude.** Pico em 70% do fundo de escala do DAC de 16 bits. O pico é medido numa sequência longa de referência, com 10% de folga para a sobrelevação do RRC. O fator é o mesmo em todos os quadros, para que a OOK tenha nível estável. No ensaio, o pico real foi de 20 852 contra 32 767.

**Banda conferida antes de transmitir.** O `scripts/transmitir.py` mede a banda a 99% do próprio sinal (`sdrlink.espectro`, o mesmo cálculo da Etapa 3b) e confere duas coisas:
- que a banda tem **no máximo 1 MHz** (limite da prova);
- que a **banda inteira**, o vazamento do LO e a imagem IQ ficam **dentro de 915 a 928 MHz** (`conferir_faixa_autorizada`, A20).

Se não couber, não transmite.

**LO padrão: 919,5 MHz.** O sinal fica em 919,75 MHz, de 919,60 a 919,90 MHz para a DBPSK a 256 kbit/s. É o trecho limpo da varredura de 04/11, longe da harmônica de 921,6 MHz do RTL. A escolha final (decisão D5) depende de uma captura de controle na bancada (3e).

**Envio ao Pluto** (`transmitir_fluxo`):
- modo **não cíclico**: cada `sdr.tx()` bloqueia até o Pluto aceitar o bloco, então o ritmo é o do DAC;
- recusa bloco de tamanho diferente do primeiro ou acima do fundo de escala;
- **sempre** destrói o buffer e baixa o ganho ao mínimo no fim, com sucesso ou com erro, como já fazia o transmissor de tom.

**Log do TX:**
- `tx_<carimbo>.txt`: uma linha por pacote, `sequência<TAB>payload em hex`, **o mesmo formato da saída do RX**;
- `tx_<carimbo>.json`: versão do código, horário de início, modo (Pluto ou simulado), parâmetros, banda a 99%, payloads no arquivo, pacotes transmitidos e instante do último início.

**Métricas** (`sdrlink.metricas.avaliar`), pela seção 7 do enunciado:

| Recebido | Classificação | Efeito |
|---|---|---|
| sequência e payload iguais a um transmitido | certo | conta no goodput (só uma vez) |
| mesmo pacote de novo | duplicado | não conta |
| sequência transmitida, payload diferente | conteúdo diferente | **falha** na PER |
| sequência que o TX não mandou | espúrio | não conta |

- PER = (transmitidos − certos) / transmitidos;
- goodput = bits de payload dos certos / duração da janela.

## 3. Como usar na prova

Na bancada, no PC do TX:

```
python scripts/transmitir.py payloads_do_avaliador.bin --modulacao dbpsk --pulso rrc --taxa-bits 256e3 --duracao-s 60
```

No PC do RX, gravar durante a janela (`scripts/gravar_iq.py`, centro 919,5 MHz) e depois processar:

```
python scripts/receber.py dados/capturas/<captura>.npy --modulacao dbpsk --pulso rrc --taxa-bits 256e3
```

O avaliador compara a saída do RX com o log do TX. Na bancada, o mesmo cálculo é feito com `sdrlink.metricas`.

## 4. Testes

Total do projeto: 141 testes. São 11 em `tests/test_transmissor.py`:

| Teste | O que garante |
|---|---|
| `test_ler_payloads_nos_dois_formatos` | `.bin` e `.txt`; tamanho errado e extensão desconhecida recusados |
| `test_sequencia_volta_a_zero` | 65534, 65535, 0 |
| `test_fluxo_em_blocos_fixos_com_fase_continua` | blocos de tamanho fixo; todos os pacotes, em ordem, uma vez; **o fluxo é igual ao sinal montado de uma vez**, mesmo com quadros cortados entre blocos (fase contínua); último bloco completado com zeros; pico dentro da amplitude |
| `test_registro_vai_com_o_bloco_em_que_o_quadro_comeca` | blocos maiores que um quadro (o caso real) |
| `test_so_comecam_pacotes_dentro_da_janela` | janela de 2,5 quadros: começam 3 pacotes |
| `test_banda_do_sinal_transmitido` | banda a 99% = 1,165 × Rb, centrada no deslocamento |
| `test_ida_e_volta_tx_rx_metricas` | TX → canal → RX → arquivos → métricas: 12 de 12, PER 0, goodput exato |
| `test_metricas_classificam_cada_recebido` | certo, duplicado, conteúdo diferente e espúrio; PER e goodput |
| `test_ler_pacotes_rejeita_linha_fora_do_formato` | arquivo malformado recusado com o número da linha |
| `test_transmitir_fluxo_envia_em_ordem_e_desliga` | Pluto falso: modo não cíclico, ordem, buffer destruído e ganho mínimo no fim |
| `test_transmitir_fluxo_desliga_mesmo_com_erro` | bloco de tamanho errado ou acima do fundo de escala: erro, e o Pluto desliga |

Testes de mutante feitos à mão:

| Mutante | Testes que falham |
|---|---|
| Fase recomeçando a cada quadro | 1 |
| Sem a janela da prova | 1 |
| Conteúdo diferente contado como certo | 1 |
| Duplicata contada como certo | 1 |
| Pluto em modo cíclico no fluxo | 1 |
| Sem desligar o Pluto quando um bloco dá erro | 1 |

Um sétimo mutante, que entregava todos os pacotes pendentes junto com o bloco em vez de filtrar pelo início, **sobreviveu**. A análise mostrou que ele era **equivalente**: um bloco só sai logo depois que um quadro entra, e esse quadro sempre começa antes do fim do primeiro bloco que sai. O filtro era sempre verdadeiro. O código foi simplificado para deixar essa invariante explícita, e o teste com blocos maiores que um quadro ficou para guardá-la.

## 5. Riscos para o ensaio no ar (3e)

| # | Risco | Como verificar na bancada |
|:-:|---|---|
| R1 | O Python não alimentar o Pluto a tempo (buraco no meio de um quadro) | Simulado com folga de 2,3 vezes. Na bancada, medir o tempo de cada `sdr.tx()` pelo `ao_enviar` e comparar o número de quadros recebidos com o log. Se faltar folga, gerar todos os blocos antes de começar (60 s ocupam cerca de 1 GB em complex64) |
| R2 | Frequência escolhida (919,5 MHz) com interferência | Captura de controle com o Pluto desligado no centro escolhido (decisão D5) |
| R3 | Diferença de relógio entre Pluto e RTL | Erro de amostragem de poucos ppm: menos de 0,05 amostra ao longo de um quadro. Confirmar pelo desvio do instante entre quadros na captura real |
| R4 | Ganho de TX e de RX | Começar com TX em −30 dB e RTL em 10 dB lado a lado e conferir `fracao_saturada`, como na Etapa 2 |

## 6. Evidências

| Evidência | Onde |
|---|---|
| Rodada simulada | `dados/logs/enlace_simulado_20261121_231317.json`, `dados/logs/enlace_simulado_execucao.log` |
| Código e testes | `sdrlink/transmissor.py`, `sdrlink/metricas.py`, `sdrlink/hw/pluto_tx.py`, `scripts/transmitir.py`, `tests/test_transmissor.py` |
