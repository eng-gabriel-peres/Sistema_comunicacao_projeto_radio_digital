# Projeto Final SDR: planejamento e auditoria inicial

SCM22108 Sistemas de Comunicação, IFSC. Documento vivo: atualizar a cada etapa.

| Item | Valor |
|---|---|
| Versão | 0.1 em 22/10 (planejamento inicial); a matriz (seção 6) e as decisões (seção 11) foram atualizadas em 22/11, no bloco 15 |
| Data | 22/10/2026 |
| Fonte dos requisitos | `Projeto_Final_SDR.docx.pdf` (versão revisada) |
| Código de partida | `referencia/` (fornecido pelo professor, mantido intocado) |

---

## 1. O que o professor quer, em uma frase

Montar um **enlace de rádio digital de um sentido só** (ADALM-Pluto transmite, RTL-SDR recebe, em computadores separados), que leve **pacotes de 128 bytes com número de sequência e CRC**, implementar **OOK, 2-FSK e BPSK** (QPSK opcional) com a cadeia de modulação **escrita por nós em Python**, **medir de verdade** (goodput, PER, BER e banda a 99%), comparar **teoria × simulação × medição**, e no fim competir em **velocidade** (prova A) e **alcance** (prova B), defendendo tudo individualmente.

A nota não vem da colocação na competição: vem principalmente de **funcionar, medir com método, explicar as discrepâncias e manter logs auditáveis**.

## 2. Prazos

| Etapas | Conteúdo | Prazo | Dias a partir de hoje |
|---|---|---|---|
| 1 e 2 | Integração SDR + calibração; estudo e auditoria da referência OOK | **29/10** | 7 |
| 3 | 2-FSK e BPSK (simulação + enlace real), formatação de pulso | 18/11 | 27 |
| 4 | Simulação do canal (AWGN, fase, offset, temporização) | 26/11 | 35 |
| 5 | Caracterização experimental + relatório parcial | 03/12 | 42 |
| 6 e 7 | Otimização, competição e defesa | 10/12 | 49 |

Toda entrega intermediária precisa de um **registro curto de uso de IA**: ferramenta, prompt, o que foi aproveitado e **como foi verificado** (cálculo, simulação ou medição).

## 3. Requisitos numerados (rastreabilidade)

Cada requisito do PDF recebeu um identificador. Todo código, teste e evidência vai apontar para esses IDs (matriz de rastreabilidade, seção 6).

### 3.1 Plataforma e regras

| ID | Requisito | Seção do PDF |
|---|---|---|
| PLT-01 | Pluto só como transmissor; RTL-SDR só como receptor; o receptor do Pluto nunca é usado | 1, 10 |
| PLT-02 | TX e RX em computadores distintos, sem rede entre eles nem com o avaliador durante o ensaio | 3, 8 |
| PLT-03 | Cadeia de modulação e demodulação implementada pela equipe, em Python (NumPy, SciPy, pyadi-iio, pyrtlsdr; outras bibliotecas só justificadas) | 3, 4 |
| PLT-04 | Sem amplificadores externos, alterações de hardware ou canais paralelos | 10 |
| PLT-05 | Frequência, potência e operação autorizadas e compatíveis com a Anatel: **faixa de 915 a 928 MHz**, definida pelo professor em 04/11/2026 | 10, 12 |
| PLT-06 | Aquecer o RTL-SDR cerca de 10 min antes de calibrar ou ensaiar | 10 |
| PLT-07 | Receptor sem acesso prévio aos payloads da prova | 8, 10 |

### 3.2 Funcionais

| ID | Requisito | Seção |
|---|---|---|
| MOD-01 | OOK de referência funcionando | 4 |
| MOD-02 | 2-FSK obrigatória | 4 |
| MOD-03 | BPSK obrigatória (DBPSK aceita, desde que comparada com BPSK coerente em simulação e justificada) | 4 |
| MOD-04 | QPSK opcional | 4 |
| PUL-01 | Pelo menos uma formatação de pulso além da retangular, justificada pela banda ocupada medida | 4, Etapa 3 |
| PKT-01 | Pacote com número de sequência (16 bits recomendado), payload e CRC-8 ou superior | 4 |
| PKT-02 | Discutir a escolha do CRC (CRC-8 é fraco para 128 bytes) | 4 |
| PKT-03 | Toda alteração no formato do quadro documentada | 4, 12 |
| PKT-04 | Payload de competição: 128 bytes por pacote, lidos de arquivo entregue pelo avaliador | 8, 12 |
| RX-01 | Receptor gera arquivo de saída com número de sequência e payload de cada pacote aceito | 8 |
| RX-02 | Pode gravar IQ e processar depois, terminando em até 10 min no computador do RX | 8 |
| RX-03 | Arquivo IQ e arquivo de saída entregues para auditoria | 8 |
| TX-01 | Log do transmissor com todos os pacotes transmitidos (base do cálculo de PER) | 7, 8 |
| CAL-01 | Correção de ppm do RTL-SDR calibrada e registrada | 4 |
| CAL-02 | Offset residual medido (ordem de centenas de Hz) e explicado como é tratado | 4 |
| CAL-03 | Recomendado: ajustar também a correção do oscilador do Pluto | 4 |

### 3.3 Métricas e ensaios

| ID | Requisito | Seção |
|---|---|---|
| MET-01 | Goodput = bits úteis de payload corretos / duração total (exclui cabeçalho, CRC, guarda, FEC, duplicatas; inclui tempo ocioso) | 7 |
| MET-02 | PER = pacotes não recebidos corretamente / transmitidos (pelo log do TX) | 7 |
| MET-03 | BER com sequência pseudoaleatória conhecida; política de quadros perdidos apresentada à parte | 7 |
| MET-04 | Banda ocupada = faixa com 99% da potência, pela DEP medida no RTL-SDR | 7 |
| MET-05 | Registrar: pacotes transmitidos, recebidos, válidos e perdidos; duração; modulação; parâmetros; ganho do RX com AGC desligado; offset residual | 7 |
| CMP-01 | Comparação experimental das três modulações obrigatórias | 4 |
| CMP-02 | Curvas BER × Eb/N0 simuladas comparadas às teóricas | Etapa 4 |
| CMP-03 | Simulação de AWGN, erro de fase, offset de frequência e erro de temporização nas três modulações | Etapa 4 |
| CMP-04 | Comparação simulação × teoria × medição com discrepâncias explicadas | 9 |

### 3.4 Competição

| ID | Requisito | Seção |
|---|---|---|
| CMP-A | Prova A: 60 s, maior goodput com PER ≤ 1% e banda a 99% ≤ 1 MHz | 8 |
| CMP-B | Prova B: em cada distância, goodput ≥ 10 kbit/s, PER ≤ 1%, pelo menos 500 pacotes; até 5 min de reconfiguração, registrando cada configuração | 8 |
| CMP-C | Versão do código marcada (tag) no repositório antes da prova | 8 |

### 3.5 Processo e entregas

| ID | Requisito | Seção |
|---|---|---|
| PRC-01 | Código executável, versionado, documentado e com parâmetros configuráveis | 4 |
| PRC-02 | Registro de uso de IA em cada entrega, consolidado em anexo no final | 6, 11 |
| PRC-03 | Logs de PER/goodput/BER, registro de calibração e capturas IQ das provas, com descrição do cálculo | 10, 11 |
| PRC-04 | Relatório técnico com texto próprio e análise de falhas | 9 |
| PRC-05 | Defesa oral individual: cada integrante explica qualquer bloco do sistema | 9 |

## 4. Auditoria do código de referência (base da Etapa 2)

Rodei a simulação do professor (`tx_ook_sim.py` → `canal_sim.py` → `rx_ook_sim.py`) com semente fixa: a mensagem `HELLO WORLD MANDRIAUM` foi decodificada com **CRC OK e 0 de 184 bits errados**, com SNR de 10 dB e offset de +1,5 kHz. A referência funciona na condição para a qual foi feita. Os pontos abaixo são o que **não atende** ao projeto final ou precisa de cuidado.

### 4.1 Mapa das funções

| Arquivo | Papel | Funções principais |
|---|---|---|
| `tx_test.py` | Pluto transmite um tom em +200 kHz | (script linear) |
| `rx_test_915.py` | RTL mede o tom e estima o erro em ppm | `capture_chunks`, `find_peak` |
| `Tx_Rx_OOK/pluto_tx_ook_v2.py` | TX OOK no Pluto, quadro repetido em buffer cíclico | `crc8`, `build_frame_bits`, `build_ook_envelope` |
| `Tx_Rx_OOK/rtl_rx_ook_v2.py` | RX OOK: translação, filtro, envoltória, Barker, limiar, CRC | `capture_chunks`, `simple_lowpass`, `crc8`, `bits_to_levels`, `read_bits` |
| `OOK_simulacao/*` | Mesma cadeia, com `.npy` no lugar do hardware e gráficos passo a passo | idem + `field_boundaries`, `bit_means`, `psd_db` |
| `teste_FM.py` | Varredura de espectro FM 88 a 108 MHz (teste do RTL) | `capture_spectrum` |
| `instalar.sh` | Instala ambiente Python do RTL no Fedora | (shell) |

Quadro de referência: `[preâmbulo 16][Barker-13][comprimento 8][payload 8·N][CRC-8][guarda 16]`, OOK 10 kbit/s, rampas de cosseno levantado (10% do bit), tom em +200 kHz, TX 2,0 MS/s, RX 2,048 MS/s.

### 4.2 Achados

| # | Gravidade | Onde | Achado | Consequência para o projeto | Requisito |
|:-:|---|---|---|---|---|
| A1 | **Crítico** | `rtl_rx_ook_v2.py` | O RX decodifica **um único quadro** por captura (`argmax` da correlação) | Impossível medir PER e goodput, que exigem decodificar todos os pacotes de um ensaio | MET-01, MET-02 |
| A2 | **Crítico** | RX | Não há **limiar de detecção**: o maior pico da correlação sempre vira "quadro", mesmo só com ruído | Falsos quadros; precisa de detecção com limiar e validação | RX-01 |
| A3 | **Crítico** | quadro | Sem **número de sequência**; CRC-8 com `init = 0x00` | Não identifica pacotes nem duplicatas; CRC-8 detecta mal erros em 128 bytes | PKT-01, PKT-02 |
| A4 | **Crítico** | `pluto_tx_ook_v2.py` | TX repete **o mesmo quadro** em buffer cíclico, sem log | Na prova, cada pacote tem payload diferente vindo de arquivo, e o TX precisa registrar o que transmitiu | PKT-04, TX-01 |
| A5 | Alto | `rx_test_915.py` | Começa com `freq_correction = 34` e depois aplica **só o erro medido**, descartando os 34 ppm já aplicados | A correção final fica errada, a menos que a calibração parta de 0 ppm. Validar no hardware | CAL-01 |
| A6 | Alto | `rx_test_915.py` | Resolução da FFT: 2,048 MHz / 4096 = **500 Hz por bin** | Não mede um residual de "centenas de Hz", que é exatamente o que o professor pede. Precisa de FFT maior ou interpolação | CAL-02 |
| A7 | Alto | `rx_test_915.py` | O erro medido mistura o erro do Pluto e o do RTL (mede um contra o outro) | Precisa ser declarado no registro de calibração; ajustar também o Pluto (`xo_correction`) | CAL-01, CAL-03 |
| A8 | Alto | RX | `read_samples` devolve `complex128` | 60 s a 2,4 MS/s = **2,3 GB** de RAM. Para a prova, gravar os bytes brutos (`uint8`, 288 MB) | RX-02 |
| A9 | Médio | RX | `MAX_EXPECTED_PAYLOAD_BYTES = 64` | Menor que os 128 bytes da prova | PKT-04 |
| A10 | Médio | RX | Amostras por bit pela taxa nominal (204,8), sem recuperação de relógio | Funciona em quadros curtos; em taxas altas o desvio de relógio acumula. O próprio PDF pede que isso seja entendido | Etapa 1 |
| A11 | Médio | `instalar.sh` | Só funciona no Fedora; o passo [1/5] não instala nada; **não instala pyadi-iio nem libiio**; `scipy` aparece duas vezes; não trata o driver DVB do kernel | O PC do TX não fica pronto com esse script | PRC-01 |
| A12 | Baixo | `teste_FM.py` | Força o backend `Qt5Agg`, que exige PyQt5 (não instalado pelo script) | Pode falhar ao abrir o gráfico | (teste) |
| A13 | Baixo | TX | `PLUTO_URI = "ip:192.168.2.22"`; o padrão de fábrica é `192.168.2.1` | Confirmar o IP do Pluto da bancada | PLT-01 |
| A14 | Baixo | todos | Parâmetros espalhados como constantes em cada script, sem arquivo de configuração | O requisito pede parâmetros configuráveis e o TX e o RX precisam concordar | PRC-01 |
| A15 | Alto | `tx_test.py` | O tom de 200 kHz completa 102,4 ciclos no buffer cíclico de 1024 amostras: o espectro vira um pente de 1953 Hz e a raia principal fica em LO + 199,219 kHz | Calibrar contra 915,2 MHz exatos erra 0,85 ppm (descoberto no ensaio de 22/10) | CAL-01 |
| A16 | Alto | RTL-SDR do projeto | O dongle erra cerca de −68 ppm (medido pelas rádios FM), apesar de vendido como TCXO, e gera espúrios em múltiplos de 100 kHz e de taxa/8 | Uma calibração que trave num espúrio dá um resultado falso (aconteceu em 22/10) | CAL-01, CAL-02 |
| A17 | Alto | `rtl_rx_ook_v2.py` (`capture_chunks`) e todo leitor síncrono do RTL | A leitura síncrona em blocos de 256 k amostras perde de 2 a 5 mil amostras em **cada emenda** (a cada 128 ms), cerca de 1,3% do sinal | Quadros que cruzam a emenda falham no CRC ou somem (12 de 107 no ensaio de 04/11); PER e goodput sairiam errados. Corrigido com leitura assíncrona ([etapa2_recepcao_ook.md](etapa2_recepcao_ook.md)) | RX-02, MET-01 |
| A18 | Alto | enlace Pluto da equipe → RTL | Mesmo com +84 ppm, o offset residual não é fixo: foi de −0,36 a −1,62 kHz em 35 min e andou 440 Hz dentro de uma transmissão de 60 s (até cerca de −35 Hz/s); a temperatura do chip do Pluto ficou parada | Na BPSK, 2 kHz giram a fase 20 voltas por pacote de 10 ms: o receptor tem de estimar o offset em cada pacote, com busca de pelo menos ±3 kHz | CAL-02, MOD-03 |
| A19 | Baixo | `sdrlink.hw.rtl_rx` (leitura assíncrona) | Em cerca de 5% das capturas a librtlsdr acusa erro de I2C ao pôr o sintonizador em repouso no fechamento; nunca com leitura síncrona | Não afeta os dados (captura sempre completa e a seguinte funciona); fica sob observação | RX-02 |
| A20 | Médio | ensaios de 04/11 e referência (`CENTER_FREQ = 915e6`) | O LO do Pluto ficou em 915,000 MHz, exatamente na borda da faixa autorizada; o vazamento do LO fica na borda e a imagem IQ (LO − 200 kHz = 914,8 MHz) cai fora dela. O sinal útil (915,2 MHz) estava dentro | Nos próximos ensaios o LO vai para perto do meio da faixa; o código do projeto recusa transmitir se sinal, LO ou imagem saírem de 915 a 928 MHz | PLT-05 |
| A21 | Médio | medição da banda no RTL | A 2,048 MS/s o RTL enxerga só ±1,02 MHz, com as bordas atenuadas pelo filtro anti-aliasing: a banda a 99% de um sinal de caudas largas (pulso retangular) sai sempre subestimada | Medir a banda só com pulsos RRC ou gaussiano e com o sinal longe do DC e das bordas ([etapa3_modulacoes.md](etapa3_modulacoes.md), seção 4) | MET-04 |
| A22 | Alto | `sdrlink.modem` (2-FSK) | Desde a troca da integral de fase (sub-bloco 3c), a janela do correlator da 2-FSK ficou 1,5 amostra adiantada: a BER da GFSK subiu 2,6 vezes em 11 dB. A CPFSK quase não sentiu, e os testes não pegaram | Janela corrigida (+1 amostra) e testes de regressão (janela no ótimo; GFSK contra o valor da Etapa 4). Os números de GFSK do 3c e do 3d foram medidos de novo ([etapa5_software.md](etapa5_software.md)) | MOD-02 |
| A23 | Alto | `sdrlink.receptor` (2-FSK) | O correlator da 2-FSK trabalhava na banda decimada inteira: um sinal forte fora da banda do pulso (o pico de DC do RTL, outro sinal ISM) entrava nele, e um pico do tamanho do sinal multiplicou a BER por 25 | A 2-FSK passou a demodular depois do filtro de banda do pulso: imune ao pico e, de quebra, 4 a 10 vezes menos BER na GFSK entre 11 e 13 dB ([etapa5_software.md](etapa5_software.md)) | MOD-02, RX-01 |

Conclusão da auditoria: a referência é uma **boa base didática** (quadro, Barker, limiar pelo preâmbulo, CRC), mas atende só MOD-01 e parte de PKT-01. O restante tem de ser construído. Os achados A1 a A4 são o núcleo do trabalho de engenharia.

## 5. Cálculos que orientam o projeto

Todos os números abaixo foram calculados (script de verificação em Python) e serão revalidados na simulação.

### 5.1 Overhead do quadro (payload de 128 bytes = 1024 bits)

Bits por quadro = preâmbulo 16 + sync 13 + comprimento 8 + sequência + 1024 + CRC + guarda 16.

| Formato | Bits/quadro | Eficiência | Goodput a 10 kbit/s | Taxa mínima para 10 kbit/s com PER 1% |
|---|---|---|---|---|
| Referência (sem sequência, CRC-8) | 1085 | 94,4% | 9,44 kbit/s | 10,70 kbit/s |
| + sequência 16, CRC-8 | 1101 | 93,0% | 9,30 kbit/s | 10,86 kbit/s |
| + sequência 16, **CRC-16** | 1109 | 92,3% | 9,23 kbit/s | **10,94 kbit/s** |
| + sequência 16, CRC-32 | 1125 | 91,0% | 9,10 kbit/s | 11,10 kbit/s |

Isso confirma a observação do PDF: a OOK de referência a 10 kbit/s **não passa** na prova B. Para a prova B com folga: taxa de pelo menos **16 a 20 kbit/s**.

### 5.2 Banda ocupada a 99% (limite da prova: 1 MHz)

| Pulso | Banda a 99% | Taxa de símbolos máxima em 1 MHz |
|---|---|---|
| Retangular (BPSK/OOK) | ≈ 20 × Rs | ≈ 50 kbaud |
| RRC, α = 0,25 | 1,10 × Rs | ≈ 900 kbaud |
| RRC, α = 0,35 | 1,17 × Rs | ≈ 850 kbaud |
| RRC, α = 0,50 | 1,26 × Rs | ≈ 790 kbaud |
| 2-FSK (Carson, aproximado) | ≈ 2(Δf + Rb) | depende do desvio Δf |

Conclusão: **pulso retangular inviabiliza a prova A**; a formatação RRC (ou cosseno levantado) é o que libera taxa. O limite prático passa a ser o RTL-SDR: a 2,4 MS/s a janela é ±1,2 MHz e o sinal deve ficar longe do DC (pico do RTL) e das bordas do filtro anti-aliasing.

### 5.3 Offset residual e BPSK

Depois da calibração sobra um offset Δf de centenas de Hz (1 ppm em 915 MHz = 915 Hz). A fase gira 360°·Δf/Rs a cada símbolo:

| Δf | Rs = 10 kbaud | Rs = 100 kbaud | Rs = 250 kbaud |
|---|---|---|---|
| 100 Hz | 3,6°/símbolo, 3992° no pacote | 0,36°, 399° | 0,14°, 160° |
| 300 Hz | 10,8°/símbolo, 11977° no pacote | 1,08°, 1198° | 0,43°, 479° |
| 500 Hz | 18°/símbolo, 19962° no pacote | 1,8°, 1996° | 0,72°, 798° |

Conclusão: BPSK coerente **sem** tratar o offset não funciona (a fase dá várias voltas dentro de um pacote). Opções: (a) **DBPSK**, que só depende da diferença de fase entre símbolos vizinhos (de 0,1° a 18° por símbolo, tolerável); (b) estimar o offset pelo preâmbulo e corrigir, mais uma malha de fase. O PDF exige, se usarmos DBPSK, a comparação com BPSK coerente em simulação.

### 5.4 Calibração

- Resolução de frequência da FFT = fs / N. Com 2,048 MS/s e N = 4096, são 500 Hz. Para medir o residual com resolução de cerca de 10 Hz, usar N ≥ 2²⁰ (cerca de 2 Hz) ou interpolar o pico.
- ppm = (f_medida − f_esperada) / f_portadora × 10⁶, aplicada **sobre** a correção já ativa (achado A5).

## 6. Matriz de rastreabilidade (estado em 22/11/2026, depois do bloco 15)

Legenda: ✅ atendido com evidência; 🟡 atendido em simulação ou em parte, falta a bancada; ❌ não atendido; ⏳ depende de terceiros ou de decisão. A auditoria item a item do enunciado está em [auditoria_final.md](auditoria_final.md).

| ID | Estado | Evidência / o que falta | Etapa |
|---|---|---|---|
| PLT-01 | ✅ | Pluto só como TX (`ip:192.168.2.22`, fw v0.32), RTL só como RX; nenhum código abre o RX do Pluto | 1 |
| PLT-02 | 🟡 | O sistema não depende de rede (arquivos e scripts independentes nos dois lados); todos os ensaios reais até agora foram num PC só (pendência P2) | bancada |
| PLT-03 | ✅ | Toda a cadeia de modulação e demodulação é do projeto, em Python; SciPy só para filtros, FFT e reamostragem | 3 |
| PLT-04 | ✅ | Sem amplificadores, alteração de hardware ou canal paralelo: o projeto usa só o Pluto e o RTL como vêm | todas |
| PLT-05 | ✅ | Faixa de 915 a 928 MHz conferida pelo TX antes de transmitir (sinal, vazamento do LO e imagem IQ); LO de 919,5 MHz, longe da harmônica de 921,6 MHz do RTL (D5) | 3 |
| PLT-06 | ✅ | RTL aquecido 10 min nos ensaios de 04/11; passo 1 do roteiro da prova | 1 |
| PLT-07 | ✅ | O RX não lê payloads: só a captura e o perfil | 3 |
| MOD-01 | ✅ | OOK de referência no ar em 04/11: 698 de 698 quadros, PER 0%, BER 0 em 117 264 bits ([etapa2_recepcao_ook.md](etapa2_recepcao_ook.md)) | 2 |
| MOD-02, MOD-03 | 🟡 | 2-FSK (CPFSK e GFSK) e DBPSK em simulação, no receptor completo e contra a teoria (a menos de 0,08 dB); a BPSK coerente comparada em simulação e descartada pelo offset medido ([etapa4_canal.md](etapa4_canal.md)); **falta no ar** | 3, bancada |
| MOD-04 | 🟡 | DQPSK (bloco 10): bate com a fórmula exata a 0,5%; 1 365 kbit/s na mesma banda de 747 kHz, 1,7 dB acima da DBPSK no receptor completo (1,4 dB na teoria); **falta no ar** ([etapa6_dqpsk.md](etapa6_dqpsk.md)) | 6, bancada |
| PUL-01 | 🟡 | RRC (β = 0,35 na Etapa 3 e 0,25 nos perfis da prova A) e gaussiano BT = 0,5, escolhidos pela banda a 99% simulada contra a teoria; **falta a banda medida no RTL**, que o enunciado pede | 3, bancada |
| PKT-01 a PKT-03 | ✅ | Quadro v3: sequência de 24 bits (16 no v2, que dava a volta em 60 s na DQPSK) e CRC-16 sobre comprimento, sequência e payload; CRC justificado; cada mudança documentada ([etapa3_quadro.md](etapa3_quadro.md), [etapa6_dqpsk.md](etapa6_dqpsk.md)) | 3, 6 |
| PKT-04 | ✅ | TX lê o arquivo do avaliador (.bin ou .txt) de 128 bytes e avisa se ele não enche a janela | 3, 6 |
| RX-01, RX-03 | ✅ | Receptor multiquadro com saída no formato da prova; 698/698 na captura real da OOK; **falta o quadro v3 no ar** | 3, bancada |
| RX-02 | 🟡 | Gravação sem perda de amostras (`scripts/gravar_iq.py`, leitura assíncrona, A17); processamento de 60 s em 25 a 89 s no ensaio geral; **falta uma gravação de 60 s (1 GB) no RTL** | 3, bancada |
| TX-01 | ✅ | Log do TX por pacote e registro JSON com o perfil; só começam pacotes dentro da janela | 3 |
| CAL-01, CAL-02 | ✅ | +84 ppm com o Pluto da equipe; resíduo de −0,36 a −1,62 kHz e deriva de até 35 Hz/s; o RX estima o offset por quadro ([calibracao_rtl.md](calibracao_rtl.md)) | 1 |
| CAL-03 | ⏳ | Erro do Pluto estimado em −9,5 ppm; decidir se ajusta o `xo_correction` (P3) | bancada |
| MET-01, MET-02 | 🟡 | PER e goodput pela regra da seção 7 (`metricas.avaliar`, `scripts/avaliar.py`), validados em simulação; **falta medir** | 5, bancada |
| MET-03 a MET-05 | 🟡 | BER com sequência conhecida, banda a 99% (com marcação de confiança) e Eb/N0 da captura; registro com perfil, contagens, offset e o ganho do RX da gravação; **falta medir** | 5, bancada |
| CMP-01 | ❌ | Comparação **experimental** das três modulações: protocolo pronto (perfis `dbpsk-256k`, `gfsk-128k`, `ook-128k`) | bancada |
| CMP-02, CMP-03 | ✅ | BER × Eb/N0 simuladas contra a teoria; AWGN, fase, offset e temporização nas três modulações ([etapa4_canal.md](etapa4_canal.md)); diferença de relógio de amostragem: ±50 ppm sem perda ([etapa6_robustez.md](etapa6_robustez.md)) | 4 |
| CMP-04 | 🟡 | Simulação × teoria pronto; **falta a medição** e a explicação das diferenças | 5, bancada |
| CMP-A | 🟡 | DQPSK a 1 365 kbit/s (`prova-a`): **1 217,8 kbit/s** de goodput e PER de 0,003% na prova de 60 s simulada; reservas `prova-a-fec` e `prova-a-dbpsk` com regra de troca ([roteiro_da_prova.md](roteiro_da_prova.md)) | 6, 7 |
| CMP-B | 🟡 | DBPSK com FEC a 25,6 kbit/s no ar (`prova-b`): 11,8 kbit/s, 500 pacotes em 43 s, C/N0 necessário de 48,4 dB-Hz, **25,0 dB** abaixo do `prova-a` (20,2 dB abaixo do `prova-a-dbpsk`) | 6, 7 |
| CMP-C | ⏳ | Tags por bloco (`bloco-00` a `bloco-15`); falta a tag da prova | 7 |
| PRC-01 | ✅ | git, portão de qualidade em todo commit, perfis de configuração (A14) | todas |
| PRC-02 | ❌ | **Registro de uso de IA vazio em todas as etapas**; tem de ser texto da equipe (P1) | todas |
| PRC-03 | 🟡 | Logs de simulação e de calibração versionados com a versão do código; capturas das provas no dia | todas |
| PRC-04 | 🟡 | Relatórios por etapa e relatório final com análise de falhas; falta a parte medida | 7 |
| PRC-05 | ⏳ | Defesa oral individual; perguntas prováveis em [relatorio_final.md](relatorio_final.md), seção 10 | 7 |

## 7. Ambiente de desenvolvimento

### 7.1 Situação deste PC (em 22/10, Bloco 0; a libiio e o driver WinUSB foram instalados antes dos ensaios de 04/11)

| Item | Estado |
|---|---|
| Windows 11 | ok |
| Python 3.13 com numpy, scipy, matplotlib | ok |
| git 2.55 | ok |
| VS Code | ok |
| pyadi-iio + libiio (Pluto) | pyadi-iio no `.venv`; **falta instalar a libiio 0.25** (instalador baixado) |
| pyrtlsdr + driver WinUSB (RTL-SDR) | pyrtlsdr no `.venv`; **falta o driver WinUSB** (Zadig baixado) |
| pytest, ruff, mypy (qualidade) | instalados no `.venv` |
| Pluto ou RTL-SDR conectados | RTL-SDR (RTL2832U + R820T2, TCXO) conectado; Pluto ainda não |

### 7.2 O que instalar (Windows)

| # | O quê | Para quê | Observação |
|:-:|---|---|---|
| 1 | Ambiente virtual do projeto (`.venv`) | Isolar versões, gerar `requirements.txt` | Python 3.13 já instalado |
| 2 | Drivers USB do PlutoSDR (Analog Devices) | Pluto aparece como rede USB (`192.168.2.1`) | Instalador oficial da ADI |
| 3 | libiio (biblioteca C, instalador Windows da ADI) | Comunicação com o Pluto | Depois `pip install pyadi-iio` |
| 4 | Zadig: driver **WinUSB** na interface `Bulk-In, Interface 0` do RTL-SDR | O Windows não acessa o RTL sem isso | Só uma vez por PC/porta |
| 5 | `pip install "pyrtlsdr[lib]"` | Controle do RTL em Python | O extra `[lib]` traz a librtlsdr pronta |
| 6 | `pip install pytest pytest-cov ruff mypy` | Testes, cobertura, lint, tipagem | Padrão de qualidade (seção 8) |
| 7 | Opcional: SDR++ ou SDR# | Ver o espectro "a olho" na calibração | Só para conferência, não entra na avaliação |

**"Compilar as placas":** neste projeto não há firmware para compilar. O Pluto usa o firmware da ADI (só conferir a versão e, se o professor permitir, atualizar) e o RTL-SDR não tem firmware. Tudo o que desenvolvemos roda no computador, em Python.

Os computadores da bancada provavelmente usam **Fedora** (o `instalar.sh` do professor é para Fedora). O código precisa rodar igual no Windows e no Linux: caminhos com `pathlib`, nada específico de sistema operacional dentro do pacote.

## 8. Padrão de código (inspirado na NASA)

A NASA não tem norma específica para Python. Adaptamos as regras **"Power of 10"** do JPL (Holzmann) e as boas práticas de processo da **NPR 7150.2** (requisitos, rastreabilidade, verificação, gerência de configuração).

### 8.1 Regras de código

| # | Regra (Power of 10, adaptada) | Como aplicamos em Python |
|:-:|---|---|
| 1 | Fluxo de controle simples | Sem recursão, sem `exec`/`eval`, sem exceção usada como `if` |
| 2 | Todo laço com limite fixo | Laços sobre comprimentos conhecidos; o laço de transmissão tem duração ou contagem máxima |
| 3 | Sem alocação dinâmica no caminho crítico | Vetores NumPy pré-alocados; processamento vetorizado, sem `append` amostra por amostra |
| 4 | Funções curtas | Até **60 linhas** por função (uma página) |
| 5 | Pelo menos 2 verificações por função | Validar entradas e saídas com `if ...: raise ValueError(...)`. Não usar `assert` no código de produção, porque o Python o remove com `-O` |
| 6 | Menor escopo possível | Nenhum estado global mutável; configuração em `dataclass(frozen=True)` lida de arquivo TOML |
| 7 | Verificar todo retorno | Toda chamada ao hardware é verificada e registrada no log |
| 8 | Metaprogramação limitada | Sem monkeypatch, sem import dinâmico |
| 9 | Indireção limitada | Sem argumentos padrão mutáveis; cópia explícita quando um vetor NumPy for alterado |
| 10 | Zero avisos desde o primeiro dia | `ruff` + `mypy --strict` + `pytest` sem avisos antes de cada commit |

Regra extra, lição do Mars Climate Orbiter: **toda grandeza física leva a unidade no nome** (`freq_hz`, `dur_s`, `ganho_db`, `taxa_sps`).

### 8.2 Regras de processo

- Cada requisito com ID (seção 3); cada módulo e teste cita os IDs que atende.
- Repositório git com tag por etapa (`etapa1`, `etapa2`, ...) e **tag obrigatória antes da prova** (CMP-C).
- Todo ensaio grava: configuração usada, versão do código (hash do commit), ganho, ppm, offset residual, captura IQ e log. Resultado sem log não entra no relatório.
- Simulações com semente fixa, para serem reproduzíveis.
- Os códigos do professor ficam em `referencia/` **sem alteração**, como referência.

### 8.3 Estrutura proposta do repositório

```
Sistema_comunicacao_projeto_radio_digital/
├── referencia/           referência do professor (intocada)
├── ferramentas/          portão de qualidade (verificar.py)
├── docs/                 planejamento, requisitos, auditorias, relatórios, registro de IA
├── configs/              arquivos .toml (um por modulação/ensaio)
├── sdrlink/              pacote Python do projeto
│   ├── config.py         leitura e validação da configuração
│   ├── quadro.py         montagem/leitura do pacote, sequência, CRC
│   ├── pulsos.py         retangular, RRC, cosseno levantado
│   ├── modulacoes/       ook.py, fsk.py, bpsk.py (qpsk.py opcional)
│   ├── sincronismo.py    detecção, estimativa de offset, temporização
│   ├── canal.py          canal simulado (AWGN, fase, offset, temporização)
│   ├── metricas.py       PER, BER, goodput, banda a 99%
│   └── hw/               pluto_tx.py, rtl_rx.py (única parte que toca o hardware)
├── scripts/              calibrar, transmitir, gravar, processar, ensaios
├── tests/                testes automáticos (pytest)
└── dados/                capturas IQ e logs (fora do git por tamanho, com índice versionado)
```

## 9. Plano por etapa

### Etapas 1 e 2 (até 29/10)

1. Preparar o ambiente (seção 7) e criar o repositório com a estrutura acima.
2. Escrever o documento de estudo da referência (mapa de funções e achados da seção 4).
3. Corrigir a calibração (A5, A6, A7) num script nosso: medir ppm, registrar, medir o residual com resolução de cerca de 10 Hz.
4. Na bancada: aquecer o RTL 10 min, calibrar, transmitir a OOK de referência, **gravar a captura IQ** e registrar uma recepção válida com CRC OK.
5. Entrega: documento de auditoria, registro de calibração, captura e log da recepção, registro de IA.

### Etapa 3 (até 18/11)

1. Quadro v2: sequência de 16 bits e CRC-16 (justificar contra CRC-8 e CRC-32), com TX lendo payloads de arquivo e gerando log.
2. RX que decodifica **todos** os quadros da captura, com limiar de detecção, e gera o arquivo de saída (sequência + payload).
3. 2-FSK e BPSK em simulação, com pulso retangular e RRC; gráficos de forma de onda, espectro com banda a 99% e constelação BPSK.
4. Transmitir pelo enlace real nas novas modulações e validar a integridade.

### Etapa 4 (até 26/11)

Canal simulado com AWGN, erro de fase, offset de frequência e erro de temporização nas três modulações; curvas BER × Eb/N0 contra a teoria; efeito de um offset residual típico; se a escolha for DBPSK, a comparação com BPSK coerente.

**Feito em 21/11/2026** ([etapa4_canal.md](etapa4_canal.md)): simulação a menos de 0,1 dB da teoria; a BPSK coerente só aguenta offset de Δf/Rb < 7,7 × 10⁻⁵ (7,7 Hz a 100 kbit/s), então a BPSK do projeto é a **DBPSK** (perde 1,1 dB a 10⁻³ e tolera o offset medido a partir de 50 kbit/s).

### Etapa 5 (até 03/12)

Ensaios reais: goodput, PER, BER com sequência pseudoaleatória, banda a 99% pela DEP do RTL, sensibilidade a ganho, taxa e distância. Relatório parcial comparando simulação e medição.

**Parte em software feita em 21 e 22/11/2026** ([etapa5_software.md](etapa5_software.md)): BER com sequência conhecida (inclusive quadros com CRC falho), banda a 99% e Eb/N0 medidos na captura, validados contra a verdade; curvas de referência simuladas; protocolo de bancada. Achados A22 e A23 corrigidos. Falta medir no ar.

### Etapas 6 e 7 (até 10/12)

Otimizar velocidade (prova A) e alcance (prova B), comparando com a versão anterior nas mesmas condições; ensaiar o procedimento da prova (arquivo de payloads, 60 s, processamento em até 10 min); tag no repositório; preparar a defesa individual.

**Prova A em software feita em 22/11/2026** ([etapa6_prova_a.md](etapa6_prova_a.md)): DBPSK RRC a 682,7 kbit/s, a maior taxa de símbolos que cabe em 1 MHz a 2,048 MS/s; perfis de enlace (A14). **Atualização:** depois vieram a prova B (blocos 08 e 09), a DQPSK, que passou a ser o `prova-a` (bloco 10), o Viterbi em lote (11), a emenda das caudas (12) e o roteiro da prova (13). Resumo em [relatorio_final.md](relatorio_final.md).

## 10. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Pouco tempo de bancada (4 Plutos por reserva) | Atraso nas etapas reais | Tudo validado antes em simulação e com capturas IQ gravadas, reprocessadas sem hardware |
| Perda de amostras do RTL em Python a 2,4 MS/s | PER falsa | Gravar bytes brutos em arquivo e verificar a contagem de amostras |
| TX contínuo de 60 s com pacotes diferentes | Buffer cíclico não serve; buffer único seria grande demais | Transmissão em fluxo (buffer não cíclico) com pacotes inteiros por bloco; testar cedo |
| Offset residual na BPSK | Fase gira dentro do pacote | DBPSK ou estimativa de offset pelo preâmbulo (seção 5.3) |
| Banda de 1 MHz | Desclassificação na prova A | Pulso RRC e medição da banda a 99% no próprio RX antes da prova |
| Diferença Windows × Fedora | Código que só roda em um PC | Testar nos dois; nada específico de sistema no pacote |
| Prazo de 29/10 | Nota de processo | Começar pelo ambiente e pela auditoria, que não dependem de hardware |

## 11. Decisões (todas fechadas em 22/11/2026)

| # | Decisão | Recomendação inicial | Quando decidir | Decidido |
|:-:|---|---|---|---|
| D1 | CRC-16 ou CRC-32 | CRC-16/CCITT (`init = 0xFFFF`): 8 bits a mais que o CRC-8 e muito mais forte | Etapa 3 | CRC-16/CCITT (Etapa 3a) |
| D2 | BPSK coerente ou DBPSK | Implementar as duas na simulação e escolher pelos resultados | Etapa 3/4 | DBPSK (Etapa 4), e DQPSK opcional (bloco 10) |
| D3 | Taxa de amostragem do RX | Igual à do TX (ex.: 2,0 MS/s), para amostras por símbolo inteiras nos dois lados | Etapa 3 | 2,048 MS/s nos dois lados |
| D4 | RX em tempo real ou gravar e processar | Gravar e processar depois (mais simples e auditável) | Etapa 3 | gravar e processar depois |
| D5 | Frequência e deslocamento do sinal | Faixa definida pelo professor: 915 a 928 MHz. Varredura sem transmissão em 04/11 (`dados/logs/varredura_faixa_20261104_110544.json`, figura `varredura_faixa_04nov.png`): a linha mais forte (+35 dB) fica perto de 921,6 MHz = 32 × 28,8 MHz, harmônica do cristal do RTL, então **evitar 921,6 MHz**; trechos mais limpos por volta de 919 a 920,4 MHz e 923 a 924 MHz. Escolha final no sub-bloco 3d, com captura de controle | Etapa 3 | LO de 919,5 MHz (bloco 07) |
