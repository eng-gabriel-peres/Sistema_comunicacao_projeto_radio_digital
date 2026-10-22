# Projeto Final SDR: planejamento e auditoria inicial

SCM22108 Sistemas de Comunicação, IFSC. Documento vivo: atualizar a cada etapa.

| Item | Valor |
|---|---|
| Versão | 0.1 (planejamento inicial, antes de escrever código) |
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
| PLT-05 | Frequência, potência e operação autorizadas e compatíveis com a Anatel (candidata: ISM 915 a 928 MHz, a confirmar pelo professor) | 10, 12 |
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

## 6. Matriz de rastreabilidade (estado em 22/10)

Legenda: ✅ atendido, 🟡 parcial, ❌ não atendido, ⏳ depende de hardware ou de definição do professor.

| ID | Estado hoje | Evidência / observação | Etapa que fecha |
|---|---|---|---|
| PLT-01 | 🟡 | Referência usa Pluto só como TX; falta confirmar IP e firmware | 1 |
| PLT-02 | ⏳ | Depende de dois computadores na bancada | 1 |
| PLT-03 | 🟡 | Referência em Python; 2-FSK e BPSK ainda não existem | 3 |
| PLT-05 | ⏳ | Frequência oficial ainda não definida pelo professor | 2 |
| MOD-01 | ✅ (simulação) / ⏳ (enlace) | Simulação decodificou com CRC OK; falta a recepção real | 1, 2 |
| MOD-02, MOD-03 | ❌ | | 3 |
| MOD-04 | ❌ (opcional) | Avaliar na Etapa 6 | 6 |
| PUL-01 | 🟡 | Só a rampa de cosseno levantado da OOK | 3 |
| PKT-01 a PKT-04 | ❌ | Achados A3, A4, A9 | 3 |
| RX-01 a RX-03 | ❌ | Achados A1, A2, A8 | 3, 5 |
| TX-01 | ❌ | Achado A4 | 3 |
| CAL-01, CAL-02 | ✅ | Calibrado em 22/10: correção 0 ppm, resíduo cerca de −44 Hz ([calibracao_rtl.md](calibracao_rtl.md)); achados A5 a A7 corrigidos | 1 |
| CAL-03 | ⏳ | Correção do oscilador do Pluto: o Pluto usado é o do professor | 1 |
| MET-01 a MET-05 | ❌ | | 5 |
| CMP-01 a CMP-04 | ❌ | | 4, 5 |
| CMP-A, CMP-B, CMP-C | ❌ | | 6, 7 |
| PRC-01 | 🟡 | Repositório git e portão de qualidade criados (Bloco 0); falta a configuração centralizada (A14) | 1 |
| PRC-02 | ⏳ | Abrir o registro de IA já na Etapa 1 | todas |

## 7. Ambiente de desenvolvimento

### 7.1 Situação deste PC (atualizada em 22/10, Bloco 0)

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

### Etapa 5 (até 03/12)

Ensaios reais: goodput, PER, BER com sequência pseudoaleatória, banda a 99% pela DEP do RTL, sensibilidade a ganho, taxa e distância. Relatório parcial comparando simulação e medição.

### Etapas 6 e 7 (até 10/12)

Otimizar velocidade (prova A) e alcance (prova B), comparando com a versão anterior nas mesmas condições; ensaiar o procedimento da prova (arquivo de payloads, 60 s, processamento em até 10 min); tag no repositório; preparar a defesa individual.

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

## 11. Decisões em aberto

| # | Decisão | Recomendação inicial | Quando decidir |
|:-:|---|---|---|
| D1 | CRC-16 ou CRC-32 | CRC-16/CCITT (`init = 0xFFFF`): 8 bits a mais que o CRC-8 e muito mais forte | Etapa 3 |
| D2 | BPSK coerente ou DBPSK | Implementar as duas na simulação e escolher pelos resultados | Etapa 3/4 |
| D3 | Taxa de amostragem do RX | Igual à do TX (ex.: 2,0 MS/s), para amostras por símbolo inteiras nos dois lados | Etapa 3 |
| D4 | RX em tempo real ou gravar e processar | Gravar e processar depois (mais simples e auditável) | Etapa 3 |
| D5 | Frequência e deslocamento do sinal | Aguardar a definição do professor (ISM 915 a 928 MHz) | Etapa 2 |
