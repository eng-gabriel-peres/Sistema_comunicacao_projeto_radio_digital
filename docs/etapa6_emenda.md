# Etapa 6f: emenda das caudas do RRC

Requisito: CMP-A (maior goodput).

Feito em 22/11/2026, sem hardware (bloco 12).

## 1. Resultado

| Item | Resultado |
|---|---|
| O que mudou | nas modulações lineares o quadro seguinte começa **logo depois do último símbolo do anterior**, e as caudas do pulso RRC se somam, em vez de cada quadro esperar a cauda do anterior terminar |
| Ganho de goodput | **+2,1% na DQPSK** (1 193 para 1 218 kbit/s sem perdas) e **+1,1% na DBPSK** (619 para 625 kbit/s) |
| Custo em sensibilidade no ponto de PER 1% | 0,03 dB na DQPSK, −0,01 dB na DBPSK: **dentro da flutuação** |
| Custo na parte íngreme da curva | **real, de 0,1 a 0,2 dB** na DQPSK (seção 3) |
| Decisão | **ligada nos perfis da prova A** (vale o goodput, com 4,9 dB de margem); **desligada na prova B** (vale a sensibilidade, e o ganho seria só 0,5%) |
| Configuração | campo `emendar_caudas` do perfil e `--emendar-caudas` / `--no-emendar-caudas` nos scripts; no código, o padrão é desligado |

## 2. A ideia

Cada quadro modulado tem, além dos seus símbolos, uma subida de 6 símbolos antes do primeiro e uma descida de 6 símbolos depois do último: é o pulso RRC truncado em 12 símbolos. Até o bloco 11 o TX encostava um quadro no outro, então cada quadro ocupava 13 símbolos a mais que os seus bits (12 de cauda e 1 de referência da modulação diferencial). Na DQPSK isso era 13 em 586 símbolos, 2,2%.

Numa modulação linear o sinal é uma soma de pulsos. Se o quadro seguinte começa no símbolo logo depois do último do anterior, e as caudas se somam, o resultado é **exatamente** o de uma modulação contínua com a sequência de símbolos dos dois quadros. Nos instantes de amostragem o RRC casado não tem interferência entre símbolos, então os dados não sofrem.

Na 2-FSK isso não vale: a fase é contínua dentro do quadro, e somar as caudas de dois quadros não é uma modulação contínua. Lá a opção não muda nada (há teste disso).

## 3. Ensaio

`ensaios/etapa6/emenda_caudas_ensaio.py`: as duas configurações da prova A, com e sem a emenda, no canal com os defeitos medidos do RTL, 1 000 quadros por ponto e as mesmas sementes nos dois modos.

| Configuração | Símbolos por quadro no fluxo | Goodput sem perdas | PER por Eb/N0 | Eb/N0 para PER 1% |
|---|---|---|---|---|
| DQPSK, sem emenda | 586 | 1 192,9 kbit/s | 10 dB: 27,6% · 11: 6,5% · 12: 1,2% · 13: 0 | 12,04 dB |
| **DQPSK, com emenda** | **574** | **1 217,9 kbit/s** | 10 dB: 33,3% · 11: 9,2% · 12: 1,1% · 13: 0,3% | 12,07 dB |
| DBPSK, sem emenda | 1 130 | 618,6 kbit/s | 8 dB: 58,0% · 9: 16,8% · 10: 2,0% · 11: 0,3% | 10,37 dB |
| **DBPSK, com emenda** | **1 118** | **625,3 kbit/s** | 8 dB: 61,0% · 9: 16,9% · 10: 2,5% · 11: 0,2% | 10,36 dB |

Nenhum pacote errado foi aceito. Quadros que nem chegaram a ser detectados: 3 de 1 000, só na DBPSK com emenda a 8 dB (PER de 61%, longe da operação).

**Leitura honesta dos números:**
- No ponto que importa, PER de 1%, a diferença é de 0,03 dB ou menos.
- Na parte íngreme da curva da DQPSK a emenda **perde de verdade**: 33,3% contra 27,6% a 10 dB e 9,2% contra 6,5% a 11 dB. Com 1 000 quadros são 3 a 4 desvios, não é flutuação. Em Eb/N0 isso é algo como 0,1 a 0,2 dB, que some no ponto de 1%.
- **Causa provável, não medida:** o instante e o offset de cada quadro são estimados pelo prefixo inteiro, e o começo do prefixo agora recebe a cauda da guarda do quadro anterior. O modelo que o receptor procura começa do silêncio. A detecção não perdeu quadros na DQPSK, então o efeito deve estar na estimativa do instante ou do offset; não separei as duas.
- **Melhoria possível:** gerar o modelo do prefixo com a cauda de uma guarda antes dele. Mas a fase da guarda anterior depende dos dados do quadro anterior, então o modelo teria de cobrir os dois sinais possíveis. Fica anotado.

## 4. Por que ligada só na prova A

| Prova | Vale | Ganho da emenda | Custo | Decisão |
|---|---|---|---|---|
| A | goodput, com 4,9 dB de margem na DQPSK | 2,1% | menos de 0,1 dB no ponto de operação | **ligada** |
| B | distância (sensibilidade) | 0,5% (o quadro com FEC é longo: 13 em 2 214 símbolos) | décimos de dB na parte íngreme | **desligada** |

## 5. Implementação

| Onde | O quê |
|---|---|
| `sdrlink/modem.py` | `ConfigModem.linear` (OOK, BPSK, DBPSK e DQPSK) |
| `sdrlink/transmissor.py` | `ConfigTransmissor.emendar_caudas`; o `fluxo` soma cada quadro no buffer na sua posição e só entrega amostras anteriores ao início do próximo quadro (que ainda vai somar a cauda); `amostras_por_quadro(..., emendar_caudas)` dá o período novo |
| `sdrlink/config.py`, `configs/perfis.toml`, scripts | o campo no perfil, a opção na linha de comando e o período certo no `receber.py` (BER e fim da captura) |

## 6. Testes

Total do projeto: 231 testes.

| Teste | O que garante |
|---|---|
| `test_fluxo_em_blocos_fixos_com_fase_continua` (blocos de 5 000, 8 950 e 997 amostras) | o fluxo é igual à soma dos quadros a um período de distância, inclusive com a borda do bloco caindo dentro da sobreposição |
| `test_emenda_nao_vale_para_a_2fsk` | na 2-FSK o sinal é o mesmo com e sem a opção |
| tamanhos e períodos (`test_fluxo_com_fec_e_periodo_do_quadro_codificado`, `test_dqpsk_dobra_a_taxa_e_encurta_o_quadro`) | 1 118 e 574 símbolos com a emenda, 1 130 e 586 sem |
| `test_emenda_das_caudas_so_nos_perfis_da_prova_a` | os três perfis da prova A com a emenda, os outros sem; o campo só aceita booleano |
| `test_tx_e_rx_com_o_mesmo_perfil_fecham_o_enlace` | `transmitir.py --perfil prova-a` aplica a emenda: cabem 48 quadros em 0,04 s |

| Mutante | Testes que falham |
|---|---|
| Fluxo sem sobrepor mesmo com a opção | 2 |
| Emenda também na 2-FSK | 1 |
| Período ignora a opção | 3 |
| Bloco entregue antes de o quadro seguinte somar a cauda | 2 (sobreviveu à primeira versão do teste, com blocos de 5 000 amostras, que nunca cortavam na sobreposição; o teste passou a usar também 8 950 e 997) |
| `transmitir.py` ignora a emenda do perfil | 1 |
| Perfil aceita valor numérico | 9 |

**Um teste que mostrou o custo:** `test_cadeia_completa_de_ber_bate_com_a_teoria` (DBPSK a 7 dB, 150 quadros) passou a perder 2 a 3 quadros na detecção quando a emenda era o padrão do TX. É o mesmo custo da parte íngreme da curva. Por isso o padrão do código ficou **desligado**, e a emenda entra só pelos perfis da prova A.

## 7. Evidências

| Evidência | Onde |
|---|---|
| Ensaio | `ensaios/etapa6/emenda_caudas_ensaio.py`, `dados/logs/emenda_caudas_20261122_113942.json`, `dados/logs/emenda_caudas_execucao.log` |
| Código e testes | `sdrlink/transmissor.py`, `sdrlink/config.py`, `configs/perfis.toml`, `tests/test_transmissor.py`, `tests/test_config.py` |
