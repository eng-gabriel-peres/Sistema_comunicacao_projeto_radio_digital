# Roteiro da prova

Passo a passo para a bancada e para as provas A e B (seção 8 do enunciado), com os comandos do projeto. Feito em 22/11/2026 (bloco 13). Os tempos e os resultados esperados vêm do ensaio geral sem hardware ([seção 7](#7-ensaio-geral-sem-hardware)).

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
| 3. Calibração do RTL (se o Pluto ou o RTL forem outros) | TX: `python scripts/transmitir_tom.py --freq-tom-hz <tom> --duracao-s 120`; RX, ao mesmo tempo: `python scripts/calibrar_rtl.py --freq-tom-hz <tom> --minutos-ligado 10` | anotar o ppm em `configs/rtl.toml` (hoje: +84 ppm para o par Pluto da equipe + RTL) |
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
| **Só se** o `medir_ruido_de_fase.py` deu "ok" para a `prova-a-8psk` (item 1.3b do plano) **e** o teste com `prova-a` mediu Eb/N0 de **16,7 dB ou mais** (C/N0 de 78 dB-Hz, 2 dB acima do que a 8-PSK pede): testar primeiro com `prova-a-8psk`; Eb/N0 de 15 dB ou mais e PER de até 0,5% ([etapa6_8psk.md](etapa6_8psk.md)) | `prova-a-8psk` (8-PSK coerente, 2 048 kbit/s no ar) | cerca de 1 775 kbit/s |
| **Só se** a sessão 1 do plano de bancada validou o RTL a 2,4 MS/s (gravação de 63 s sem perda e faixa plana até +904 kHz): testar primeiro com `prova-a-24`; Eb/N0 de 15 dB ou mais e PER de até 0,5% | `prova-a-24` (DQPSK a 2,4 MS/s, 1 600 kbit/s no ar) | cerca de 1 425 kbit/s |
| Eb/N0 medido de **15 dB ou mais** e PER de até 0,5% | `prova-a` (DQPSK, 1 365 kbit/s no ar) | cerca de 1 215 kbit/s |
| Senão, repetir o teste com `prova-a-fec`; PER de até 0,5% | `prova-a-fec` (DQPSK com FEC) | cerca de 625 kbit/s |
| Senão | `prova-a-dbpsk` (DBPSK, 682,7 kbit/s) | cerca de 625 kbit/s |

O `receber.py` mostra o Eb/N0 medido e a banda a 99%. **A banda tem de ficar abaixo de 1 MHz** (esperado: cerca de 750 kHz em todos os perfis da prova A).

**O arquivo do avaliador precisa ter pacotes para os 60 s.** Cabem cerca de 36 600 pacotes na DBPSK, 71 400 na DQPSK e 104 200 na 8-PSK. Se o arquivo tiver menos, o TX para antes do fim e o goodput cai; o `transmitir.py` avisa no início.

### 3.2 O ensaio

1. O avaliador entrega o arquivo de payloads ao TX. Ao rodar o `transmitir.py`, conferir que **não** aparece "AVISO: o arquivo tem N payloads, mas cabem M": a DQPSK manda cerca de 71 000 pacotes em 60 s. Se aparecer, avisar o avaliador antes de começar (o goodput cairia sem culpa do enlace).
2. RX, **antes** do comando de início: `python scripts/gravar_iq.py --perfil <perfil> --segundos 63 --nome prova_a`
3. TX, no comando de início: `python scripts/transmitir.py <payloads do avaliador> --perfil <perfil> --duracao-s 60`
4. RX, depois da gravação: `python scripts/receber.py dados/capturas/prova_a_<carimbo>.npy --perfil <perfil>`. Tempo esperado: de 1,5 a 2 min (limite: 10 min).
5. Entregar ao avaliador: `<captura>.npy` (a captura IQ) e `<captura>_saida.txt` (sequência e payload de cada pacote aceito, sem repetições). O `<captura>_rx.json` traz o que a seção 7 pede registrar.

## 4. Prova B: maior alcance

Em cada posição: goodput de pelo menos 10 kbit/s, PER de até 1% e **pelo menos 500 pacotes**. Até 5 minutos de reconfiguração por posição, registrando cada configuração.

| Item | Valor (perfil `prova-b`: DBPSK com FEC a 25,6 kbit/s no ar) |
|---|---|
| Goodput sem perdas | 11,84 kbit/s (folga de 17,2% sobre 10 kbit/s com PER de 1%) |
| Tempo para 500 pacotes | **43 s**: o ensaio tem de durar pelo menos isso; com 60 s, cerca de 690 pacotes |
| C/N0 necessário | 48,2 dB-Hz com o limiar de detecção de 0,4 do perfil (bloco 19; cerca de 25 dB a menos que o `prova-a` e 20 dB a menos que o `prova-a-dbpsk`: cerca de 18 vezes a distância do `prova-a` no espaço livre) |

Em cada posição:
1. RX: `python scripts/gravar_iq.py --perfil prova-b --segundos <duração + 3> --nome prova_b_pos<N>`
2. TX: `python scripts/transmitir.py <payloads> --perfil prova-b --duracao-s <duração>`
3. RX: `python scripts/receber.py dados/capturas/prova_b_pos<N>_<carimbo>.npy --perfil prova-b`
4. Anotar em `dados/README.md`: posição, perfil, ganhos de TX e RX, Eb/N0 medido, pacotes aceitos. O JSON de cada script já guarda o perfil completo.
5. **Banda:** se o `receber.py` avisar "banda não confiável", usar a banda medida na posição mais próxima. Com sinal fraco a medida por subtração do ruído não vale (seção 7).

Se uma posição falhar com o `prova-b`, não há perfil mais sensível pronto: o `prova-b-sem-fec` precisa de 2,9 dB **a mais**. A última posição validada é o resultado.

## 5. Depois da prova

1. Copiar as capturas e os registros para o repositório (`dados/capturas/` fica fora do git por tamanho; os JSON e logs entram).
2. Rodar `python scripts/avaliar.py` com o log do TX e a saída do RX de cada ensaio, para conferir a conta do avaliador.
3. Commit dos registros com o nome da prova.

## 6. O que ainda não foi testado com hardware

| Item | Risco | Onde está o plano |
|---|---|---|
| Banda a 99% dos perfis medida no RTL | a medida do avaliador ser diferente da nossa | [etapa6_prova_a.md](etapa6_prova_a.md), seção 2.6 |
| Python alimentando o Pluto a 2,048 MS/s por 60 s, sem buraco | quadros cortados | risco R1; se acontecer, `transmitir.py --pre-gerar` ([etapa6_robustez.md](etapa6_robustez.md)) |
| DQPSK no ar: ruído de fase e desequilíbrio IQ reais | a DQPSK precisar de mais que 12 dB | regra de troca, seção 3.1 |
| 8-PSK coerente no ar | ruído de fase do par da prova maior que o de 04/11 (ela tolera 10 a 30 Hz, a DQPSK 1 kHz); C/N0 abaixo de 78 dB-Hz | `medir_ruido_de_fase.py` (item 1.3b do plano) e o Eb/N0 do teste; senão, `prova-a` |
| Deriva do offset na prova B (quadros de 86 ms) | pior que os 35 Hz/s medidos | [etapa6_prova_b.md](etapa6_prova_b.md) |
| Gravação de 60 s no RTL (cerca de 1 GB em complex64) sem perder amostras | captura incompleta; só gravamos até 16 s no ar | `gravar_iq.py --segundos 63`; conferir o número de amostras no JSON |
| Recepção com o quadro v3 nas nossas modulações | nada além da OOK de referência foi recebido no ar | protocolo da Etapa 5 |

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
