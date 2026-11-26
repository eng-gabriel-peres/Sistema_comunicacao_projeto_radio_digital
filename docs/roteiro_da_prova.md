# Roteiro da prova

Passo a passo para a bancada e para as provas A e B (seção 8 do enunciado), com os comandos do projeto. Feito em 22/11/2026 (bloco 13) e refeito depois da bancada de 25/11 (bloco 26). Os tempos e os resultados esperados vêm do ensaio geral sem hardware ([seção 7](#7-ensaio-geral-sem-hardware)).

## 0. No dia da competição (10/12): os comandos

Depois da bancada de 25/11 juntei tudo em quatro scripts. O professor entrega um arquivo cifrado (qualquer tipo e tamanho); o TX fatia em payloads de 128 bytes (o último é completado com zeros) e o RX remonta o arquivo na ordem da sequência. Os dois lados usam o mesmo perfil e o mesmo deslocamento.

| Momento | PC do TX (Pluto) | PC do RX (RTL, ligado há 10 min) |
|---|---|---|
| Prova B, antes de cada posição (Pluto parado) | | `python scripts/escolher_canal.py --perfil prova-b` (se o deslocamento do perfil não for o mais limpo, usar o escolhido com `--deslocamento-hz` nos dois lados) |
| 1. Gerar o sinal | `python scripts/prova_tx.py <arquivo> --prova a --perfil prova-a-8psk --ganho-db -20` (ou o perfil que a regra da seção 3.1 escolher; o mesmo `--perfil` no RX) (prova B: `--prova b --ganho-db <G>`); se o arquivo não enche os 60 s, `--repetir` | esperar |
| 2. Começar | o TX mostra **Sinal pronto; no ar em 10 s** (gerar leva cerca de 1 min) | no aviso: `python scripts/prova_rx.py --prova a` (prova B: `--prova b --posicao P<n>`) |
| 3. Resultado | o log `tx_<carimbo>.txt` fica em `dados/prova/<data>/` | o RX grava 70 s, decodifica e mostra **RESULTADO: pacotes, goodput, PER**; na prova A diz também se **PASSA** (PER de até 1% e banda abaixo de 1 MHz) |
| Prova B, no fim | | `python scripts/relatorio_alcance.py dados/prova/<data> --distancias P1=<m> P2=<m> ...`: tabela e gráfico de goodput e PER por distância e a maior distância validada |

O que o `prova_rx.py` deixa na pasta da prova, para cada ensaio:

| Arquivo | O que é |
|---|---|
| `<captura>.npy` | a captura IQ (entregar ao avaliador) |
| `<captura>_saida.txt` | sequência e payload de cada pacote aceito (entregar ao avaliador) |
| `<captura>_arquivo.bin` | o arquivo do professor remontado (com zeros no lugar dos pacotes perdidos e o enchimento do último) |
| `<captura>_relatorio.md` e `.png` | goodput, PER, Eb/N0, banda a 99% com o limite de 1 MHz, offset e pacotes por segundo |
| `<captura>_resumo.json` | o mesmo em JSON; o `relatorio_alcance.py` junta estes por distância |

Sem o log do TX o RX estima a PER e o goodput pelos buracos de sequência (o RX não precisa do arquivo). Com o log copiado do TX (`--log-tx <arquivo ou pasta>`), os números são os exatos do `avaliar.py`. Para reprocessar uma gravação: `--captura <arquivo .npy>`.

Ensaio com estes comandos em casa, em 25/11, com um arquivo cifrado de teste (`dados/prova/ensaio_20261125/`):

| Ensaio | TX | Pacotes certos / transmitidos | PER | Goodput | Banda a 99% |
|---|---|---|---|---|---|
| Prova A, arquivo de 9,5 MB | −20 dB | 71 335 / 71 359 | 0,034% | **1 217,5 kbit/s** | 747,4 kHz |
| Prova A, mesmo arquivo | −30 dB | 32 335 / 71 359 | 54,7% | 551,9 kbit/s | 737,9 kHz |
| Prova B, P1 | −40 dB | 694 / 694 | 0 | 11,8 kbit/s | |
| Prova B, P2 | −50 dB | 694 / 694 | 0 | 11,8 kbit/s | |
| Prova B, P3 | −53 dB | 694 / 694 | 0 | 11,8 kbit/s | |
| Prova B, P4 | −57 dB | 519 / 694 | 25,2% | 8,9 kbit/s | |

As distâncias do ensaio (10 a 70 m) foram só rótulos para testar o relatório: em casa variei a atenuação do Pluto, não a distância. **Com dois computadores e as antenas a cerca de 1 m** (26/11): DQPSK com TX a −10 dB, 70 873 pacotes, PER de 0,68%, 1 209,6 kbit/s; com as antenas afastadas e o TX a −20 dB, o sinal chegou 11 dB mais fraco e nada passou. **Na sala, começar com o TX a −10 dB** e conferir o nível no RX (−12 a −8 dBFS) antes do ensaio que vale.

A −30 dB a PER da prova A foi alta porque o enlace em casa é cerca de 6,5 dB mais fraco que o do laboratório (Eb/N0 de 12 dB, no limite da DQPSK); por isso **na prova A começar com −20 dB** e conferir o Eb/N0 no relatório (15 dB ou mais).

Cuidados que vieram da bancada:
1. **Um TX por vez.** Dois processos abrindo o Pluto dão "Open unlocked: -16" e estragam o sinal.
2. **Gravar só no aviso "Sinal pronto".** Antes dele o TX ainda está gerando o sinal; o `prova_tx.py` sempre gera tudo antes (sem isso o TX não acompanha o tempo real: 60 s de sinal levaram 99 s).
3. **Nível no RTL entre −20 e −12 dBFS** (o relatório da captura mostra). Fora de −30 a −6 dBFS, mudar o `--ganho-db` do RX.
4. **Prova B no deslocamento de 375 kHz** (919,875 MHz): na bancada havia aparelhos ISM em surtos numa grade de 500 kHz (919,25 e 919,75 MHz) que derrubavam pacotes com sinal fraco.

## 1. Antes do dia (nos dois computadores)

1. Clonar o repositório na versão marcada para a prova (CMP-C): `git checkout <tag da prova>`. A tag tem de existir **antes** da prova.
2. Instalar o ambiente como no [README](../README.md) e em [ambiente.md](ambiente.md): `py -3.13 -m venv .venv`, depois `.venv\Scripts\python -m pip install -r requirements-dev.txt` e `.venv\Scripts\python -m pip install -e .` (sem o `-e .` os scripts não acham o pacote `sdrlink`). No PC do TX, a **libiio 0.25**; no PC do RX, o **driver WinUSB do RTL** (Zadig). Conferir com `python scripts/verificar_ambiente.py`.
3. Rodar `python ferramentas/verificar.py`: o portão de qualidade tem de passar no computador da prova.
4. Os dois computadores **sem rede entre si** e sem rede com o avaliador durante o ensaio (PLT-02). O RX **não** recebe o arquivo de payloads (PLT-07).

## 2. Na bancada, antes de cada sessão

| Passo | Comando ou ação | Conferir |
|---|---|---|
| 1. Aquecer o RTL | ligado no USB por **10 minutos** antes de calibrar ou medir (PLT-06) | |
| 2. Captura de controle, Pluto desligado | `python scripts/gravar_iq.py --perfil prova-a --segundos 2 --nome controle` | nada forte entre 919,5 e 920,4 MHz (o sinal da prova A fica de +50 a +800 kHz do LO de 919,5 MHz) |
| 3. Calibração do RTL (se o Pluto ou o RTL forem outros) | TX: `python scripts/transmitir_tom.py --freq-tom-hz <tom> --duracao-s 120`; RX, ao mesmo tempo: `python scripts/calibrar_rtl.py --freq-tom-hz <tom> --minutos-ligado 10` | anotar o ppm em `configs/rtl.toml` (hoje: +88 ppm para o RTL da equipe aquecido, bancada de 25/11) |
| 4. Ganho do RX | `gravar_iq.py --ganho-db <G>`, AGC desligado | o JSON da captura registra o ganho (MET-05) e a fração de amostras saturadas: tem de ser 0 |

## 3. Prova A: maior goodput em 60 s

### 3.1 Escolha do perfil (regra de troca)

Com a potência e a distância da prova, transmitir 10 s e processar:

```
python scripts/gerar_payloads.py --aleatorios 20000 dados/capturas/teste_a.bin
python scripts/gravar_iq.py --perfil prova-a --segundos 12 --nome teste_a      (RX, primeiro)
python scripts/transmitir.py dados/capturas/teste_a.bin --perfil prova-a --duracao-s 10   (TX)
python scripts/receber.py dados/capturas/teste_a_<carimbo>.npy --perfil prova-a          (RX)
python scripts/avaliar.py dados/logs/tx_<carimbo>.txt dados/capturas/teste_a_<carimbo>_saida.txt --duracao-s 10
```

Para o teste o `avaliar.py` pode rodar no RX com o log do TX copiado por pen drive. Na prova quem compara é o avaliador.

| Se | Perfil | Goodput esperado |
|---|---|---|
| **Primeiro, testar a 8-PSK** (no ar em 25/11 com o RTL2: 1 777,6 kbit/s e PER de 0,064% com Eb/N0 estimado de 22 dB; com 17 dB a PER foi de 5%). Usar se o teste der **PER de até 0,5%** e o `prova_rx.py` disser "Prova A: PASSA"; o Eb/N0 estimado tem de ficar em **20 dB ou mais**. O `medir_ruido_de_fase.py` tem de dar "ok" para a `prova-a-8psk` se o RTL não for o RTL2 | `prova-a-8psk` (8-PSK coerente, 2 048 kbit/s no ar) | cerca de 1 778 kbit/s |
| **Só se** a sessão 1 do plano de bancada validou o RTL a 2,4 MS/s (gravação de 63 s sem perda e faixa plana até +904 kHz): testar primeiro com `prova-a-24`; Eb/N0 de 15 dB ou mais e PER de até 0,5% | `prova-a-24` (DQPSK a 2,4 MS/s, 1 600 kbit/s no ar) | cerca de 1 425 kbit/s |
| Eb/N0 medido de **15 dB ou mais** e PER de até 0,5% | `prova-a` (DQPSK, 1 365 kbit/s no ar) | cerca de 1 215 kbit/s |
| Senão, repetir o teste com `prova-a-fec`; PER de até 0,5% | `prova-a-fec` (DQPSK com FEC) | cerca de 625 kbit/s |
| Senão | `prova-a-dbpsk` (DBPSK, 682,7 kbit/s) | cerca de 625 kbit/s |

O `receber.py` mostra o Eb/N0 medido e a banda a 99%. **A banda tem de ficar abaixo de 1 MHz** (esperado: cerca de 750 kHz em todos os perfis da prova A).

**O arquivo do avaliador precisa ter pacotes para os 60 s.** Cabem cerca de 36 600 pacotes na DBPSK, 71 400 na DQPSK e 104 200 na 8-PSK. Se o arquivo tiver menos, o TX para antes do fim e o goodput cai; o `transmitir.py` avisa no início.

### 3.2 O ensaio

Pelos comandos da [seção 0](#0-no-dia-da-competição-1012-os-comandos): `prova_tx.py <arquivo> --prova a` no TX e `prova_rx.py --prova a` no RX, no aviso "Sinal pronto". Para outro perfil da regra de troca, `--perfil <nome>` nos dois lados.

1. Conferir no TX que **não** aparece "AVISO: o arquivo tem N payloads, mas cabem M". Se aparecer e a regra permitir repetir, usar `--repetir`; senão, avisar o avaliador (o goodput cairia sem culpa do enlace).
2. O RX processa em 1,5 a 3 min (limite: 10 min).
3. Entregar ao avaliador `<captura>.npy` e `<captura>_saida.txt`. O `<captura>_rx.json` traz o que a seção 7 do enunciado pede registrar.

## 4. Prova B: maior alcance

Em cada posição: goodput de pelo menos 10 kbit/s, PER de até 1% e **pelo menos 500 pacotes**. Até 5 minutos de reconfiguração por posição, registrando cada configuração.

| Item | Valor (perfil `prova-b`: DBPSK com FEC a 25,6 kbit/s no ar) |
|---|---|
| Goodput sem perdas | 11,84 kbit/s (folga de 17,2% sobre 10 kbit/s com PER de 1%) |
| Tempo para 500 pacotes | **43 s**: o ensaio tem de durar pelo menos isso; com 60 s, cerca de 690 pacotes |
| C/N0 necessário | 48,2 dB-Hz com o limiar de detecção de 0,4 do perfil (bloco 19; cerca de 25 dB a menos que o `prova-a` e 20 dB a menos que o `prova-a-dbpsk`: cerca de 18 vezes a distância do `prova-a` no espaço livre) |

A prova é por posições paradas, não andando: em cada uma a antena fica fixa pelo menos 43 s (500 pacotes). Um lado fica fixo e o outro se afasta, posição por posição, até uma falhar. **TX no máximo** (`--ganho-db 0`), salvo se o professor limitar a potência; RX com ganho alto (40 dB), porque longe o nível é o do ruído do próprio RTL.

Em cada posição, pelos comandos da [seção 0](#0-no-dia-da-competição-1012-os-comandos):
1. Pluto parado: `escolher_canal.py --perfil prova-b` no RX. Se aparecer surto no deslocamento do perfil, usar o mais limpo com `--deslocamento-hz` nos dois lados.
2. TX: `prova_tx.py <arquivo> --prova b --ganho-db <G>`; RX, no aviso: `prova_rx.py --prova b --posicao P<n>`. A distância não precisa ser conhecida na hora: anote o nome da posição e deixe quem mede (o professor, com trena ou pelo mapa do pátio) dizer a distância depois.
3. A linha "Prova B: PASSA" ou "NÃO PASSA" diz se a posição valeu (500 pacotes, 10 kbit/s, PER de até 1%). Passou: afastar para a próxima. Não passou: a anterior é o resultado (vale repetir a mesma posição uma vez, se houve interferência). A configuração fica no `<captura>_resumo.json` e no JSON do TX.
4. **Banda:** se o `receber.py` avisar "banda não confiável", usar a banda medida na posição mais próxima. Com sinal fraco a medida por subtração do ruído não vale (seção 7).
5. No fim: `relatorio_alcance.py dados/prova/<data> --distancias P1=<m> P2=<m> ...` (as distâncias medidas de cada posição; sem elas o relatório lista as posições pelo nome, com o resultado de cada uma).

Se uma posição falhar com o `prova-b`, não há perfil mais sensível pronto: o `prova-b-sem-fec` precisa de 2,9 dB **a mais**. A última posição validada é o resultado.

## 5. Depois da prova

1. Copiar as capturas e os registros para o repositório (`dados/capturas/` fica fora do git por tamanho; os JSON e logs entram).
2. Rodar `python scripts/avaliar.py` com o log do TX e a saída do RX de cada ensaio, para conferir a conta do avaliador.
3. Commit dos registros com o nome da prova.

## 6. O que a bancada de 25/11 testou

| Item | Resultado | Registro |
|---|---|---|
| Banda a 99% da prova A medida no RTL | 747 a 748 kHz, abaixo de 1 MHz | `dados/prova/ensaio_20261125/` |
| Python alimentando o Pluto por 60 s (risco R1) | sem `--pre-gerar` 60 s levaram 99 s; com ele, 61,5 s no ar. O `prova_tx.py` sempre gera antes | `dados/logs/` |
| DQPSK no ar | prova A com 71 335 de 71 359 pacotes (PER de 0,034%) e 1 217,5 kbit/s | seção 0 |
| Gravação de 70 s no RTL sem perder amostras | ok em todos os ensaios | JSON de cada captura |
| Prova B no ar com o quadro v3 | 694 de 694 pacotes até −53 dB de TX | seção 0 |
| 8-PSK coerente no ar | com o RTL2: 104 157 de 104 224 pacotes, PER de 0,064%, **1 777,6 kbit/s** a −20 dB; a −25 dB, PER de 5% (não passa) | `dados/prova/ensaio_20261125/prova_a_8psk_*` |
| RTL a 2,4 MS/s | não testado: usar só os perfis a 2,048 MS/s | |

Defeitos que a bancada achou e que já estão corrigidos estão em [bancada_20261125.md](bancada_20261125.md).

## 7. Ensaio geral sem hardware

`ensaios/etapa6/ensaio_geral_ensaio.py`: a prova de 60 s simulada com cada perfil final, pelos comandos da prova (`gerar_payloads.py`, `transmitir.py --simular`, canal com os defeitos medidos do RTL, `receber.py`, `avaliar.py`), de 1,5 a 2 dB acima do Eb/N0 necessário de cada perfil. Código `bloco-12-2-ga4d089b` (sem pendências).

| Perfil | Eb/N0 no ar (necessário) | Certos / transmitidos | PER | Goodput | Banda medida | RX (captura de 61,5 s) |
|---|---|---|---|---|---|---|
| `prova-a` (DQPSK, emenda) | 14 dB (12,1) | 71 357 / 71 359 | 0,003% | **1 217,8 kbit/s** | 748,6 kHz | 74,5 s |
| `prova-a-fec` (DQPSK com FEC, emenda) | 6 dB (4,0) | 36 703 / 36 703 | 0 | 626,4 kbit/s | 750,0 kHz | 89,1 s |
| `prova-a-dbpsk` (DBPSK, emenda) | 12 dB (10,4) | 36 631 / 36 637 | 0,016% | 625,2 kbit/s | 749,2 kHz | 65,6 s |
| `prova-b` (DBPSK com FEC) | 6 dB (4,35) | 694 / 694 | 0 | 11,8 kbit/s | **266,3 kHz (errada)** | 25,2 s |

Nenhum pacote com conteúdo diferente, nenhum espúrio, e todos os tempos de RX bem abaixo dos 10 minutos.

**A banda da prova B saiu errada, e isso virou correção.** O sinal da prova B ocupa 30 kHz (29,9 kHz medidos no TX). A 6 dB por bit, numa banda de 25,6 kHz dentro dos 2 MHz capturados, a SNR na captura é de cerca de −13 dB, e a medida por subtração do ruído fica dominada pelo resíduo da estimativa do ruído, somado em 2 MHz. Medi a mesma configuração em vários níveis:

| Eb/N0 por bit no ar | SNR na captura | Banda medida (4 sementes, captura curta) | Banda medida (4 sementes, captura longa) |
|---|---|---|---|
| 6 dB | −12,9 dB | 1 884; 1 152; 26,7; 519 kHz | 635; 673; 29,8; 182 kHz |
| 10 dB | −9,0 dB | 764; 30,4; 28,3; 333 kHz | 430; 260; 29,8; 29,9 kHz |
| 15 dB | −4,0 dB | 29,3 a 30,9 kHz | 29,8 a 30,5 kHz |
| 20 dB | +1,0 dB | 29,7 a 30,2 kHz | 29,9 a 30,1 kHz |

Registro: `ensaios/etapa6/banda_snr_ensaio.py`, `dados/logs/banda_snr_20261122_141637.json` (bloco 15). Abaixo do limite a medida é praticamente sorteio: o mesmo sinal, com outro ruído, dá de 27 a 1 884 kHz. Por isso o ensaio geral, a 6 dB, deu 266 kHz. Acima de −5 dB ela fica a menos de 1 kHz do valor verdadeiro, e a marcação de confiança acertou nos 40 casos.

A 6 dB a medida chegou a passar de 1 MHz: pareceria uma violação do limite sem que nada estivesse errado no sinal. Correção (commit `46749ac`): o `medir_captura` registra a SNR na captura e marca `banda_99_confiavel = false` abaixo de −5 dB, e o `receber.py` avisa na tela. **Na prova B, medir a banda na posição mais próxima** (a banda não muda com a distância).

Registros: `dados/logs/ensaio_geral_20261122_115928.json`, `dados/logs/ensaio_geral_execucao.log` e um registro por perfil (`prova_a_60s_14dB_...`, `prova_a_fec_60s_6dB_...`, `prova_a_dbpsk_60s_12dB_...`, `prova_b_60s_6dB_...`).
