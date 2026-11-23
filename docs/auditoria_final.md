# Auditoria final de conformidade com o enunciado

Confronto de cada exigência do enunciado ([Projeto_Final_SDR.docx.pdf](especificacao/Projeto_Final_SDR.docx.pdf), versão revisada) com o que existe no projeto e com a evidência. Feita em 22/11/2026, depois do bloco 14, sem hardware; os itens com bloco posterior foram atualizados até o bloco 25.

Legenda: ✅ atendido com evidência; 🟡 atendido em simulação ou em parte, falta a bancada; ❌ não atendido; ⏳ depende de terceiros ou de decisão da equipe.

## 1. Plataforma e regras (seções 1, 3 e 10)

| # | Exigência | Situação | Evidência ou o que falta |
|---|---|---|---|
| 1.1 | Pluto só como TX, RTL só como RX, receptor do Pluto nunca usado | ✅ | nenhum código abre o RX do Pluto (`sdrlink/hw/pluto_tx.py` só cria o TX) |
| 1.2 | TX e RX em computadores distintos, sem rede entre eles nem com o avaliador | 🟡 | o sistema não depende de rede (arquivos e scripts independentes); todos os ensaios reais até agora foram num PC só (P2) |
| 1.3 | Python; NumPy, SciPy, pyadi-iio, pyrtlsdr; outras bibliotecas justificadas | ✅ | `requirements.txt`; a cadeia de modulação e demodulação é do projeto; SciPy só para filtros, FFT e reamostragem |
| 1.4 | RTL até 2,4 MS/s; sinal longe do DC e das bordas do anti-aliasing | ✅ | 2,048 MS/s com o sinal de +50 a +800 kHz, dentro da faixa plana medida (±1 dB até ±850 kHz); 2,4 MS/s nunca testado no RTL |
| 1.5 | Entender que a referência não tem recuperação de relógio nem de fase | ✅ | auditoria (A10, A18); o nosso RX estima instante e offset por quadro |
| 1.6 | Frequência, potência e operação autorizadas (915 a 928 MHz) | ✅ | o TX recusa sinal, LO ou imagem fora da faixa (`conferir_faixa_autorizada`); LO de 919,5 MHz |
| 1.7 | Sem amplificadores, alterações de hardware ou canais paralelos | ✅ | nada disso no projeto |
| 1.8 | Aquecer o RTL 10 min antes de calibrar ou ensaiar | ✅ | registros de 04/11; roteiro, seção 2 |
| 1.9 | Registrar logs, parâmetros e capturas IQ para auditoria e reprodução | ✅ | JSON de cada script com versão do código e perfil; capturas `.npy` com JSON de metadados |

## 2. Requisitos mínimos (seção 4)

| # | Exigência | Situação | Evidência ou o que falta |
|---|---|---|---|
| 2.1 | OOK de referência funcionando | ✅ | 698/698 quadros no ar (04/11) e o nosso RX na mesma captura |
| 2.2 | 2-FSK implementada | 🟡 | CPFSK e GFSK em simulação e no receptor completo; **falta no ar** |
| 2.3 | BPSK implementada (DBPSK aceita com comparação em simulação e justificativa) | 🟡 | DBPSK, comparada com a BPSK coerente na Etapa 4 (a coerente aguenta 7,7 Hz de offset a 100 kbit/s; o medido chega a 1,6 kHz); **falta no ar** |
| 2.4 | QPSK (opcional) | 🟡 | DQPSK, bate com a teoria a 0,5%; perfil da prova A; 8-PSK coerente experimental (`prova-a-8psk`, bloco 24); **falta no ar** |
| 2.5 | Formatação de pulso justificada pela banda **medida** | 🟡 | RRC e gaussiano escolhidos pela banda simulada e pela teoria; a medição da banda no RTL está pronta (`receber.py`); **falta medir no ar** |
| 2.6 | Pacotes com sequência, payload e CRC-8 ou superior | ✅ | quadro v3: sequência de 24 bits, CRC-16 |
| 2.7 | Discutir a escolha do CRC | ✅ | etapa3_quadro.md, seção 3 |
| 2.8 | Toda alteração do quadro documentada | ✅ | v2 (etapa3_quadro.md), v3 (atualização na mesma página e em etapa6_dqpsk.md), FEC (etapa6_fec.md) |
| 2.9 | Avaliação **experimental** das três modulações obrigatórias | ❌ | depende da bancada (protocolo pronto: etapa5_software.md, seção 6) |
| 2.10 | Métricas PER, goodput, BER com sequência conhecida e banda a 99% | 🟡 | ferramentas validadas contra o valor verdadeiro em simulação; **falta medir** |
| 2.11 | Enlace real: pacotes recebidos corretamente pelo RTL | 🟡 | só a OOK de referência; **falta o quadro v3 nas nossas modulações** |
| 2.12 | Calibração do RTL em ppm registrada; offset residual medido e tratado | ✅ | +84 ppm (calibracao_rtl.md); resíduo de −0,36 a −1,62 kHz e deriva de até 35 Hz/s; o RX estima o offset por quadro |
| 2.13 | Ajustar também o oscilador do Pluto (recomendado) | ⏳ | erro estimado em −9,5 ppm; decisão pendente (P3) |
| 2.14 | Código executável, versionado, documentado e com parâmetros configuráveis | ✅ | git com tag por bloco, portão de qualidade, perfis de configuração |

## 3. Arquitetura (seção 5)

| # | Exigência | Situação | Evidência |
|---|---|---|---|
| 3.1 | Cadeia de TX: dados, pacote, símbolos, pulso, IQ, Pluto | ✅ | `quadro`, `codigo`, `modem`, `pulsos`, `transmissor`, `hw/pluto_tx` |
| 3.2 | Cadeia de RX: RTL, gravação, filtragem, detecção, decisão, bits, quadro, integridade, métricas | ✅ | `hw/rtl_rx`, `receptor`, `metricas`, `medicao` |
| 3.3 | Técnica nova explicada e com benefício demonstrado | ✅ | cada bloco da Etapa 6 compara a versão nova com a anterior nas mesmas condições |

## 4. Entregas por etapa (seção 6)

| # | Etapa | Situação | Evidência ou o que falta |
|---|---|---|---|
| 4.1 | Registro de uso de IA em cada entrega | ❌ | `registro_ia.md` vazio em todas as etapas (P1: texto da equipe) |
| 4.2 | Etapa 1: calibrar, medir o resíduo, operar as modulações pelo enlace | 🟡 | calibração e resíduo ✅; só a OOK operada no enlace |
| 4.3 | Etapa 2: estudo, mapa de funções, execução, recepção válida | ✅ | auditoria A1 a A23, recepção da OOK |
| 4.4 | Etapa 3: 2-FSK e BPSK em simulação com pulso além do retangular | ✅ | etapa3_modulacoes.md |
| 4.5 | Etapa 3: transmitir pacotes com sequência nas novas modulações e validar a integridade | ❌ | **bancada** (sub-bloco 3e) |
| 4.6 | Etapa 3, entrega: formas de onda, espectros com banda de 99% e constelação BPSK | ✅ | etapa3_modulacoes.md, figuras |
| 4.7 | Etapa 4: AWGN, fase, offset e temporização nas três modulações; BER × Eb/N0 contra a teoria; offset típico | ✅ | etapa4_canal.md |
| 4.8 | Etapa 5: goodput, PER, BER, banda e sensibilidade medidos; comparação simulação × medição | 🟡 | ferramentas, referência simulada e protocolo prontos; **medições na bancada** |
| 4.9 | Etapa 6: melhorar velocidade, robustez ou alcance; comparar com a versão anterior nas mesmas condições | 🟡 | em simulação, em todos os blocos 06 a 24; **falta confirmar no ar** |
| 4.10 | Etapa 7: provas, apresentação e defesa | ❌ | dia da prova; roteiro e perguntas prováveis prontos |
| 4.11 | Prazos | ❌ | Etapas 1, 2 e 3 entregues depois do prazo |

## 5. Definições de desempenho (seção 7)

| # | Exigência | Situação | Evidência |
|---|---|---|---|
| 5.1 | Goodput: só bits de payload corretos, sem duplicatas, sobre a duração total | ✅ | `metricas.avaliar`; testes |
| 5.2 | PER pelo log do TX; perdido, CRC inválido ou conteúdo diferente contam como falha | ✅ | `metricas.avaliar` |
| 5.3 | BER com referência conhecida; política dos quadros perdidos à parte | ✅ | `metricas.medir_ber` (compara quadros com CRC falho, conta os não detectados à parte) |
| 5.4 | Banda a 99% pela DEP medida no RTL | 🟡 | `medicao.banda_99_medida`; confiável só com SNR na captura acima de −5 dB (bloco 13) |
| 5.5 | Registrar transmitidos, recebidos, válidos, perdidos, duração, modulação, parâmetros, **ganho do RX (AGC desligado)** e offset residual | ✅ | `<captura>_rx.json` com perfil, contagens, offset e, desde o bloco 15, os metadados da gravação (ganho, ppm, centro, taxa, saturação); transmitidos e perdidos no `avaliar.py`, contra o log do TX |

## 6. Regulamento (seções 8 e 12)

| # | Exigência | Situação | Evidência |
|---|---|---|---|
| 6.1 | Banda a 99% até 1 MHz | 🟡 | 749 kHz simulada nos perfis da prova A; falta medir no RTL |
| 6.2 | Payload do avaliador lido no TX; RX sem acesso a ele | ✅ | `transmitir.py` lê `.bin` ou `.txt`; o RX não lê payloads |
| 6.3 | Contam os pacotes que começam dentro da janela | ✅ | `transmissor.fluxo` (teste) |
| 6.4 | Gravar IQ e processar em até 10 min no PC do RX | ✅ | 25 a 89 s para 60 s no ensaio geral; falta medir no computador da prova |
| 6.5 | Arquivo de saída com sequência e payload de cada pacote aceito | ✅ | `<captura>_saida.txt` |
| 6.6 | Captura IQ e saída entregues | ✅ | roteiro, seção 3.2 |
| 6.7 | Versão marcada no repositório antes da prova | ⏳ | criar a tag da prova |
| 6.8 | Prova A: 60 s, PER até 1%, banda até 1 MHz | 🟡 | ensaio geral: 1 217,8 kbit/s, PER 0,003% |
| 6.9 | Prova B: goodput de 10 kbit/s, PER até 1%, 500 pacotes; registrar cada configuração | 🟡 | 11,8 kbit/s, 694 pacotes em 60 s; perfis registrados no JSON |
| 6.10 | 128 bytes por pacote | ✅ | `TAMANHO_PAYLOAD = 128`; o TX recusa outro tamanho |

## 7. Entregas finais (seção 11)

| # | Exigência | Situação |
|---|---|---|
| 7.1 | Logs de PER, goodput e BER, registro de calibração e capturas IQ das provas, com a descrição das métricas | 🟡 simulação e calibração prontas; capturas das provas no dia |
| 7.2 | Registros de uso de IA de todas as etapas, consolidados em anexo | ❌ vazio (P1) |
| 7.3 | Demonstração prática e defesa individual | ⏳ |

## 8. Auditoria do código e dos documentos (bloco 15)

Feita com duas leituras independentes, uma do código e uma dos documentos, sem as conclusões anteriores; cada achado foi conferido antes de ser corrigido.

**Código.** Nenhum resultado errado no caminho da prova. Corrigido:
- os testes e um ensaio da DQPSK passavam ao `canal.awgn` as amostras **por símbolo**: o ruído ficava 3 dB acima do declarado (os testes estavam mais difíceis do que diziam); o `awgn` passou a aceitar amostras por bit fracionárias e os chamadores passam sps / bits por símbolo;
- a mensagem de erro do perfil mostrava a razão errada para a DQPSK, e a regra dos bits por símbolo estava copiada em dois módulos;
- um perfil com `emendar_caudas` numa 2-FSK era aceito e ignorado em silêncio; agora é recusado;
- o `receber.py` não registrava o ganho do RX (seção 7 do enunciado); agora junta os metadados da gravação e avisa se o centro, a taxa ou a saturação divergem do perfil;
- código morto (`receptor.ler_quadro`), constantes duplicadas (prefixo, payload de 128 bytes), a DQPSK fora da tabela de BER teórica;
- cerca de 30 comentários e docstrings desatualizados (quadro v2 de 16 bits, "amostras por bit" onde é por símbolo, emenda descrita como sempre ligada, 20 ms de ruído em vez de 200 ms, números dos perfis do quadro v2);
- três testes novos: `receber.py --ber` de ponta a ponta com `prova-a` e `prova-b` (BER, Eb/N0 por bit e por bit útil), Eb/N0 da captura na DQPSK, e os metadados da gravação.

**Documentos.** Corrigido:
- "20,2 dB a menos que o `prova-a`" no relatório, no roteiro e na matriz era de quando o `prova-a` era a DBPSK: com a DQPSK são **25,0 dB**;
- a tabela de banda × SNR do roteiro não tinha registro: virou o ensaio `banda_snr`, que também explica por que a mesma condição deu 266 kHz num ensaio e 1 884 kHz no outro;
- **o roteiro mandava instalar só o `requirements.txt`**: sem o `pip install -e .` os scripts não rodam (isso falharia no dia da prova); a calibração no roteiro não dizia que o TX roda o `transmitir_tom.py`;
- a comparação "167 vezes a OOK" misturava um número simulado com um medido; o texto agora diz isso;
- matriz de rastreabilidade reescrita (estava em 04/11, com linhas contraditórias e sem seis requisitos); decisões D1 a D5 fechadas; README, `configs/README.md` e o índice `dados/README.md` atualizados; notas de atualização onde um documento antigo apresentava fatos superados; dois travessões removidos;
- os desvios do padrão de código (tags `etapaN`, formato de commit, registro de IA) registrados em [padrao_de_codigo.md](padrao_de_codigo.md), seção 6.

## 9. Conclusão

| Grupo | ✅ | 🟡 | ❌ | ⏳ |
|---|---|---|---|---|
| Tudo o que dá para fazer sem hardware | código, simulação, ferramentas, roteiro, relatórios | | registro de IA (da equipe) | |
| O que depende da bancada | | enlace no ar das três modulações, medições da Etapa 5, banda medida, provas | comparação experimental (CMP-01) | `xo_correction` do Pluto, tag da prova |

O que falta é a bancada (ver [plano_de_bancada.md](plano_de_bancada.md)) e o registro de uso de IA.
