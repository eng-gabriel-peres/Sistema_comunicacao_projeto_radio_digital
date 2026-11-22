# Plano de bancada: o que falta fazer com o hardware

Tudo o que dá para fazer sem hardware está pronto e validado em simulação ([relatorio_final.md](relatorio_final.md), [auditoria_final.md](auditoria_final.md)). Este plano lista o que **só** a bancada resolve, em que ordem, com o comando, o critério de aprovação e o tempo estimado de cada teste, para dimensionar quanto tempo pedir o Pluto e o RTL ao professor.

## 1. Resumo

| Sessão | Objetivo | Tempo estimado | Fecha |
|---|---|---|---|
| 1 | Preparar os dois computadores, calibrar e provar a cadeia no ar | 3 h | PLT-02, CAL-03, RX-02, risco R1, enlace com o quadro v3 (3e) |
| 2 | Medições da Etapa 5 nas três modulações | 3 a 4 h | MOD-02, MOD-03, PUL-01, MET-01 a MET-05, CMP-01, CMP-04 |
| 3 | Ensaio da prova A na bancada | 2 a 3 h | CMP-A (regra de troca, banda medida, tempo do RX no PC da prova) |
| 4 | Ensaio da prova B nas distâncias da sala | 2 a 3 h | CMP-B |
| **Total** | | **10 a 13 h de bancada**, em **4 sessões** (ou 2 dias inteiros) | |

Recomendo pedir o hardware por **uma semana**, com 4 sessões de 3 h e folga para repetir o que falhar. Se só der um dia, a ordem de prioridade é a das sessões: a 1 e a 2 são as que mais pesam na nota (enlace real e caracterização, 40% dos critérios).

Antes de cada sessão: RTL ligado no USB **10 minutos** antes de medir, e os dois computadores sem rede entre si.

**Ganho do RX em todas as sessões** (bloco 21): o `gravar_iq.py` mostra o nível eficaz da gravação. Ajustar o ganho para ficar entre **−20 e −12 dBFS**; a janela sem perda vai de −30 a −6 dBFS (abaixo, o ADC de 8 bits perde resolução; acima, satura). Com o enlace longe o nível é o do ruído do próprio RTL, e a regra continua valendo.

## 2. Sessão 1: preparar, calibrar e provar a cadeia (3 h)

| # | Teste | Comando ou ação | Aprovado se | Tempo |
|---|---|---|---|---|
| 1.1 | Ambiente nos **dois** PCs | `pip install -r requirements-dev.txt`, `pip install -e .`, libiio no TX, WinUSB no RX; `python scripts/verificar_ambiente.py` e `python ferramentas/verificar.py` | o portão passa nos dois | 40 min |
| 1.2 | Captura de controle, Pluto desligado | `python scripts/gravar_iq.py --perfil prova-a --segundos 2 --nome controle` | nada forte entre 919,5 e 920,4 MHz | 5 min |
| 1.3 | Calibração do RTL | TX: `scripts/transmitir_tom.py --freq-tom-hz <tom> --duracao-s 120`; RX: `scripts/calibrar_rtl.py --freq-tom-hz <tom> --minutos-ligado 10` | correção perto de +84 ppm (mesmo par); anotar em `configs/rtl.toml` | 20 min |
| 1.3b | **Ruído de fase do par** ([etapa6_imperfeicoes.md](etapa6_imperfeicoes.md)) | TX: `transmitir_tom.py --freq-tom-hz 919.75e6 --duracao-s 30`; RX: `gravar_iq.py --centro-hz 919.5e6 --segundos 4 --nome tom` e `scripts/medir_ruido_de_fase.py <captura>` | "ok" nos cinco perfis finais; "inconclusivo" pede mais ganho | 10 min |
| 1.4 | Decisão do `xo_correction` do Pluto (P3) | medir o erro do Pluto contra as rádios FM e decidir | decisão registrada; se mudar, recalibrar (1.3) | 20 min |
| 1.5 | **Gravação de 63 s no RTL** sem perder amostras | `gravar_iq.py --perfil prova-a --segundos 63` | número de amostras do JSON = 63 × 2,048 M; saturação 0; nível eficaz entre −30 e −6 dBFS (o `gravar_iq.py` mostra e avisa) | 10 min |
| 1.5b | **RTL a 2,4 MS/s** (perfil experimental, [etapa6_taxa_24.md](etapa6_taxa_24.md)) | `gravar_iq.py --perfil prova-a-24 --segundos 63`; com o Pluto desligado, 2 s e `scripts/resposta_rtl.py <captura> --taxa-sps 2.4e6` | 63 × 2,4 M amostras; faixa plana até pelo menos +904 kHz | 15 min |
| 1.6 | **TX de 60 s no Pluto sem buraco** (risco R1) | `transmitir.py <payloads> --perfil prova-a --duracao-s 60`, gravando ao mesmo tempo; se faltar quadro, repetir com `--pre-gerar` ([etapa6_robustez.md](etapa6_robustez.md)) | pacotes recebidos = log do TX; nenhum quadro cortado | 15 min |
| 1.7 | **Quadro v3 no ar** (sub-bloco 3e), as três modulações | `--perfil dbpsk-256k`, `gfsk-128k`, `ook-128k`, 10 s cada, `receber.py` + `avaliar.py` | PER de até 1% com sinal forte nas três | 40 min |
| 1.8 | TX e RX em computadores diferentes (P2) | 1.7 com os dois PCs | o mesmo resultado | (junto com 1.7) |

## 3. Sessão 2: medições da Etapa 5 (3 a 4 h)

Protocolo completo em [etapa5_software.md](etapa5_software.md), seção 6. Cada ponto: gravar 12 s, transmitir 10 s, processar com `--ber`, avaliar; cerca de 2 min por ponto.

| # | Varredura | Pontos | Aprovado se | Tempo |
|---|---|---|---|---|
| 2.1 | Ganho de TX, de −30 dB descendo de 3 em 3 até a PER passar de 50%, nas **três modulações** | cerca de 10 por modulação | curvas de PER, BER e goodput × Eb/N0 **medido**, sobrepostas às simuladas; diferença explicada | 1 h 30 |
| 2.2 | Taxa: DBPSK a 64, 128 e 256 kbit/s com a mesma potência | 3 | goodput cresce com a taxa até a PER subir | 15 min |
| 2.3 | **Banda a 99% medida no RTL** com sinal forte, em cada perfil | 6 perfis | prova A abaixo de 1 MHz (esperado: 750 kHz); justifica o pulso (PUL-01) | 20 min |
| 2.4 | Offset residual e deriva ao longo da sessão | junto com 2.1 | dentro de ±3 kHz (a grade do RX) | (junto) |
| 2.5 | `scripts/analisar_bancada.py` na pasta da sessão, depois o relatório parcial da Etapa 5 | | tabela e gráficos gerados dos registros; perda do enlace pequena e explicada; simulação × teoria × medição (CMP-04) | 5 min + fora da bancada |

## 4. Sessão 3: prova A na bancada (2 a 3 h)

| # | Teste | Aprovado se | Tempo |
|---|---|---|---|
| 3.1 | Regra de troca ([roteiro](roteiro_da_prova.md), seção 3.1): 10 s com `prova-a-24` (se 1.5b passou), depois `prova-a`, `prova-a-fec` e `prova-a-dbpsk` | escolher o perfil pelo Eb/N0 medido e pela PER | 30 min |
| 3.2 | **DQPSK no ar**: ruído de fase e desequilíbrio IQ reais | PER de até 0,5% com Eb/N0 de 15 dB ou mais | (junto com 3.1) |
| 3.3 | Ensaio completo de 60 s com o perfil escolhido, como no dia | PER ≤ 1%, banda < 1 MHz, goodput registrado | 20 min |
| 3.4 | Tempo de processamento **no computador que vai para a prova** | menos de 10 min (esperado: 1 a 2 min) | (junto) |
| 3.5 | Comparação com a OOK de referência **nas mesmas condições** (critério de otimização) | goodput das duas medido na mesma posição e potência | 30 min |

## 5. Sessão 4: prova B na sala (2 a 3 h)

| # | Teste | Aprovado se | Tempo |
|---|---|---|---|
| 4.1 | Banda do `prova-b` medida na posição **mais próxima** (com sinal fraco a medida não vale; ver o roteiro, seção 7) | cerca de 30 kHz | 10 min |
| 4.2 | Cada posição da sala, do mais perto ao mais longe, 60 s com `prova-b` | goodput ≥ 10 kbit/s, PER ≤ 1%, ≥ 500 pacotes | 15 min por posição |
| 4.3 | Na última posição que passar: `prova-b-limite` (11,6 kbit/s, +0,4 dB) | idem | 15 min |
| 4.4 | Registrar cada configuração (o JSON já guarda o perfil) e anotar em `dados/README.md` | | (junto) |

## 6. O que pode dar errado, e o que fazer

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Nenhum quadro detectado | LO, deslocamento ou taxa diferentes no TX e no RX | o `receber.py` avisa se a gravação usou outro centro ou taxa que o perfil; usar o mesmo `--perfil` nos dois lados |
| Detecta, mas o CRC falha sempre | offset fora de ±3 kHz, ou ganho saturando | recalibrar (1.3); o JSON mostra o offset e a saturação |
| PER alta só na DQPSK | ruído de fase ou desequilíbrio IQ | conferir o 1.3b (`medir_ruido_de_fase.py`); regra de troca: `prova-a-fec` ou `prova-a-dbpsk` |
| PER alta com sinal forte e nenhum aviso de offset | nível da gravação fora da janela do ADC | o `receber.py` avisa o nível; ajustar o ganho do RX para −20 a −12 dBFS |
| Quadros perdidos de tempos em tempos no meio dos 60 s | o Python não alimentou o Pluto a tempo (R1) | comparar o log do TX com a saída; se for isso, `transmitir.py --pre-gerar` |
| Banda medida absurda (centenas de kHz ou mais de 1 MHz) | SNR baixa na captura | medir a banda numa posição mais próxima (o `receber.py` marca "não confiável") |
