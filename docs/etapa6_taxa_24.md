# Etapa 6h: perfil experimental a 2,4 MS/s

Requisitos: CMP-A (maior goodput), seção 3 do enunciado ("recomenda-se operar o RTL-SDR em até 2,4 MS/s").

Feito em 22/11/2026, sem hardware (bloco 17). **Experimental**: depende de dois testes de bancada.

## 1. Resultado

| Item | `prova-a` (2,048 MS/s) | **`prova-a-24` (2,4 MS/s)** |
|---|---|---|
| Configuração | DQPSK, RRC β = 0,25, 3 amostras por símbolo, caudas emendadas | DQPSK, **RRC β = 0,20**, 3 amostras por símbolo, caudas emendadas |
| Taxa no ar | 1 365 kbit/s | **1 600 kbit/s** |
| Banda a 99% | 747 kHz (de +52 a +799 kHz do LO) | 850 kHz (de +54 a +904 kHz do LO) |
| Eb/N0 para PER de 1% | 12,2 dB | 12,3 dB |
| Margem pela bancada de 04/11 | 4,7 dB | 4,0 dB |
| Prova de 60 s simulada (14 dB) | 1 217,8 kbit/s (ensaio geral) | **1 427,1 kbit/s**: 83 622 de 83 624 pacotes, banda medida de 853,6 kHz, RX em 87 s |
| Ganho | | **+17% de goodput**, por 0,7 dB de margem |

## 2. Por que β = 0,20

Com 2,4 MS/s e 3 amostras por símbolo, a taxa de símbolos sobe para 800 ksímbolos/s. Com β = 0,25 a banda a 99% iria a 875 kHz, com só 12,5% de folga sobre o limite de 1 MHz. Com β = 0,20 ela fica em 850 kHz (15% de folga), e a borda alta do sinal em +904 kHz: a mesma fração da faixa útil que o `prova-a` usa a 2,048 MS/s (cerca de 0,78 da frequência de Nyquist). Na Etapa 6a, β = 0,20 e 0,25 deram PER quase iguais (diferença de 0,1 a 0,2 dB).

## 3. O que só a bancada responde

1. **O RTL grava 60 s a 2,4 MS/s sem perder amostras?** A leitura assíncrona (achado A17) foi validada a 2,048 MS/s. A 2,4 MS/s o USB e o computador têm de dar conta de 17% a mais de dados. Teste: `gravar_iq.py --perfil prova-a-24 --segundos 63`; o número de amostras do JSON tem de ser 63 × 2,4 M.
2. **A resposta do RTL é plana até +904 kHz a 2,4 MS/s?** A 2,048 MS/s ela não cai mais que 1 dB até cerca de ±880 kHz (0,86 da frequência de Nyquist; medida na captura de 04/11). Se a forma do filtro anti-aliasing acompanhar a taxa, a 2,4 MS/s ela iria até cerca de ±1 030 kHz. Teste: gravar 2 s com o Pluto desligado e rodar `python scripts/resposta_rtl.py <captura> --taxa-sps 2.4e6`.

Se os dois passarem, o `prova-a-24` entra na regra de troca da prova A antes do `prova-a` ([roteiro_da_prova.md](roteiro_da_prova.md), seção 3.1).

## 4. Ferramenta nova: faixa plana do RTL

`medicao.faixa_plana` e `scripts/resposta_rtl.py`: a partir de uma captura só de ruído, acha até onde o piso não cai mais que 1 dB abaixo do centro, que é a queda do filtro anti-aliasing.

**Achado no caminho.** A primeira versão procurava onde o piso ficava a ±1 dB do centro e, na captura real de 04/11, parava em −590 kHz. Medindo de 50 em 50 kHz, a resposta do nosso RTL tem uma **elevação de +1,0 dB** perto de −650 a −700 kHz, e só depois cai (−0,37 dB em −850 kHz, −1,31 dB em −900 kHz). A elevação não atrapalha o sinal; o que importa é a queda. O critério passou a ser "não cai mais que 1 dB", e a mesma captura dá −887 kHz. A frase do bloco 07, "plana dentro de ±1 dB até ±850 kHz", continua certa (pior desvio de 1,01 dB).

## 5. Testes e evidências

| Item | Onde |
|---|---|
| Perfil cabe em 1 MHz, longe do DC e dentro da faixa útil | `test_perfil_experimental_a_2_4_ms_por_segundo_cabe_em_1_mhz` |
| Faixa plana: ruído filtrado com queda em 0,82 da metade da taxa, e ruído sem filtro | `test_faixa_plana_acha_onde_o_filtro_derruba_o_piso` |
| Ensaio contra o `prova-a` e prova de 60 s | `ensaios/etapa6/taxa_24_ensaio.py`, `dados/logs/taxa_24_20261122_143526.json`, `dados/logs/prova_a_24_60s_14dB_20261122_143526.json`, `dados/logs/taxa_24_execucao.log` |
