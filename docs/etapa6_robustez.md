# Etapa 6g: robustez sem hardware (relógio de amostragem e alimentação do Pluto)

Requisitos: seção 3 do enunciado (a referência "utiliza amostras por bit calculadas pela taxa nominal, sem uma malha contínua de recuperação de relógio"), Etapa 4 (erro de temporização), risco R1 (o Python alimentar o Pluto a tempo).

Feito em 22/11/2026, sem hardware (bloco 16).

## 1. Resultado

| Item | Resultado |
|---|---|
| Diferença de relógio entre o DAC do Pluto e o ADC do RTL | **todos os perfis finais aguentam ±50 ppm sem perder nenhum quadro**; depois da calibração sobram cerca de 2 ppm: folga de 25 vezes |
| Ferramenta nova | `canal.reamostrar(sinal, ppm)`: o mesmo sinal amostrado por um relógio ppm partes por milhão mais rápido (interpolação sinc com janela de Kaiser, 33 coeficientes) |
| Risco R1 | opção `transmitir.py --pre-gerar`: o sinal inteiro é gerado antes de abrir o Pluto (cerca de 1 GB para 60 s), e o Pluto só recebe blocos prontos |

## 2. Diferença de relógio

O nosso RX estima o instante de cada quadro pelo prefixo, mas não acompanha a deriva dentro do quadro: não há malha de recuperação de relógio, como na referência. Se o relógio do RTL for diferente do do Pluto, o último símbolo do quadro chega deslocado de ppm × 10⁻⁶ × a duração do quadro. Isso pesa mais no quadro longo da prova B: 177 120 amostras, ou seja, 8,9 amostras de deslocamento a 50 ppm (11% de um símbolo de 80 amostras).

**Quanto de diferença esperar.** A correção de ppm do RTL ajusta o oscilador do sintonizador e a taxa de amostragem juntos, porque os dois vêm do mesmo cristal. Depois da calibração, a diferença de relógio que sobra é a mesma do offset residual: 1,6 kHz em 919,5 MHz, cerca de **2 ppm**. Sem calibração seriam uns 75 ppm (o erro do nosso RTL).

`ensaios/etapa6/relogio_ensaio.py`: cada perfil final, 2 dB acima do Eb/N0 necessário, com o sinal reamostrado:

| Perfil | Amostras por quadro | Deriva no quadro a 50 ppm | Certos com 0, 2, 20 e 50 ppm | 100 ppm | −100 ppm | 200 ppm |
|---|---|---|---|---|---|---|
| `prova-a` (DQPSK) | 1 722 | 0,09 amostra | 300 de 300 | 300 | 300 | 291 |
| `prova-a-fec` | 3 348 | 0,17 amostra | 300 de 300 | 300 | 300 | 295 |
| `prova-a-dbpsk` | 3 354 | 0,17 amostra | 299 a 300 de 300 | 296 | 300 | 151 |
| `prova-b` | 177 120 | 8,9 amostras | 60 de 60 | 58 | 59 | 0 |

**Conclusão: não precisamos de recuperação de relógio.** Mesmo a prova B, com o quadro mais longo, só começa a perder quadros a 100 ppm, 50 vezes o esperado depois da calibração. Seria um problema só se o RTL rodasse sem a correção de ppm, e o roteiro garante que ela é aplicada (`configs/rtl.toml`, lida por padrão pelo `gravar_iq.py`).

## 3. Alimentação do Pluto (risco R1)

O Pluto em modo não cíclico precisa receber cada bloco antes de terminar o anterior. Em simulação o TX gera o sinal a 0,45 vez o tempo real (folga de cerca de 2 vezes), mas isso nunca foi medido com o Pluto, e o computador da prova pode ser mais lento.

Com `--pre-gerar` o `transmitir.py` gera **o sinal inteiro antes** de abrir o Pluto, e o envio vira só a cópia dos blocos prontos. Custa memória: 60 s a 2,048 MS/s em complex64 ocupam cerca de 1 GB. O registro do TX guarda a opção usada.

Teste: `test_pre_gerar_entrega_ao_pluto_os_mesmos_blocos_ja_prontos` confere que os blocos são idênticos nos dois modos e que, com a opção, o log do TX está completo antes de o primeiro bloco ir para o Pluto. Na bancada (plano, sessão 1, teste 1.6): se aparecerem quadros perdidos no meio dos 60 s, repetir com `--pre-gerar`.

## 4. Testes

| Teste | O que garante |
|---|---|
| `test_reamostrar_simula_a_diferenca_de_relogio` | um tom reamostrado a 1 000 ppm sai na frequência esperada; 0 ppm devolve o sinal; limites de entrada |
| `test_aguenta_50_ppm_de_diferenca_de_relogio_no_quadro_longo_da_prova_b` | quadros com FEC a 25,6 kbit/s no ar, reamostrados a 50 ppm, chegam todos |
| `test_pre_gerar_entrega_ao_pluto_os_mesmos_blocos_ja_prontos` (com e sem a opção) | os mesmos blocos; com a opção, tudo pronto antes do primeiro envio |

## 5. Evidências

| Evidência | Onde |
|---|---|
| Ensaio de relógio | `ensaios/etapa6/relogio_ensaio.py`, `dados/logs/relogio_20261122_142809.json`, `dados/logs/relogio_execucao.log` |
| Código | `sdrlink/canal.py` (`reamostrar`), `scripts/transmitir.py` (`--pre-gerar`, `fonte_de_blocos`) |
