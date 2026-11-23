# Etapa 5b: análise automática da sessão de bancada

Requisitos: MET-01 a MET-05 (métricas medidas e registradas), CMP-01 (comparação experimental das modulações), CMP-04 (simulação × teoria × medição, com as diferenças explicadas).

Feito em 22/11/2026, sem hardware (bloco 20).

## 1. Resultado

| Item | Resultado |
|---|---|
| Ferramenta | `scripts/analisar_bancada.py <pasta da sessão>`: junta os registros de todos os pontos numa tabela e num gráfico, sem trabalho manual |
| Perda do enlace | para cada ponto sem FEC, **quantos dB a mais que a teoria** o enlace precisou para a BER medida (a distância horizontal entre o ponto e a curva teórica) |
| Ensaio geral da sessão, simulado | os **scripts da bancada de ponta a ponta** (gerar payloads, transmitir, receber com `--ber`, avaliar, analisar), 12 pontos em 4 perfis: a cadeia fecha sozinha |
| Eb/N0 medido × verdadeiro | erro mediano de −0,01 dB, **máximo de 0,26 dB** |
| Perda do enlace na simulação | mediana de **+0,07 dB** (de −0,30 a +0,37 dB); é o que se espera num canal AWGN, só a perda de implementação do receptor |
| Pacotes errados aceitos | nenhum, em todos os pontos |

Na bancada, o resultado esperado é o da simulação somado ao que o hardware acrescenta (ruído de fase, não linearidade do Pluto, resposta do RTL). A perda do enlace mede exatamente essa soma, ponto a ponto.

## 2. Como usar na bancada

Todas as capturas de uma sessão vão para a mesma pasta (`gravar_iq.py --pasta dados/capturas/sessao_<data>`). Cada ponto deixa, ao lado da captura, o `<captura>_rx.json` do `receber.py --ber` e o `<captura>_saida_avaliacao.json` do `avaliar.py`. No fim da sessão:

```
python scripts/analisar_bancada.py dados/capturas/sessao_<data>
```

Saídas na pasta da sessão:

- `analise_bancada.md`: uma linha por ponto com ganho do RX (dos metadados da gravação), Eb/N0 medido, BER, PER, goodput, banda a 99% (marcada quando não é confiável), offset e perda do enlace;
- `analise_bancada.png`: BER × Eb/N0 medido com a curva teórica de cada modulação na mesma cor, e PER × Eb/N0 medido com a linha de 1%.

O protocolo da [Etapa 5](etapa5_software.md) (seção 6) e o [plano de bancada](plano_de_bancada.md) (item 2.5) já incluem esse passo.

## 3. Decisões

- **A perda só é calculada sem FEC.** A curva teórica é a da modulação sem código; com FEC a BER depois do Viterbi não se compara com ela.
- **A perda só é calculada com pelo menos 10 erros contados.** Com menos, a BER varia demais: na primeira rodada, os pontos de 11 dB da DBPSK (3 erros) e de 14 dB da OOK (2 erros) davam perdas de 0,4 a 0,5 dB que eram só estatística. Com 10 erros a incerteza da BER é de cerca de 30%, o que dá 0,1 a 0,2 dB.
- **A GFSK aparece com perda negativa** (−0,30 e −0,10 dB). A curva de referência é a da 2-FSK ortogonal não coerente, de um símbolo; o receptor demodula depois do filtro de banda e observa além do símbolo, e fica um pouco melhor que essa curva. É o mesmo efeito medido na Etapa 3c (0,6 a 0,7 dB de ganho) e na Etapa 5 (achado A23).
- **A OOK perde de 0,3 a 0,4 dB**, porque o receptor tira o limiar dos 29 bits do preâmbulo, e a curva é a do limiar ótimo (Etapa 4).
- **A banda da prova B aparece como "não confiável"** nos três pontos: a 4 a 6 dB por bit no ar a SNR na captura fica abaixo de −5 dB (bloco 15). Na bancada, a banda se mede com sinal forte (item 2.3 do plano).

## 4. Ensaio

`ensaios/etapa5/bancada_simulada_ensaio.py`: roda os scripts de verdade, na ordem do plano de bancada. O único passo trocado é o `gravar_iq.py`: a captura é montada a partir do sinal do `transmitir.py --simular`, com 0,5 s de ruído antes, offset de −1,4 kHz, atraso fracionário, DC e ruído no Eb/N0 pedido, e com um JSON de metadados igual ao do `gravar_iq.py`. Cada ponto tem 2 s de transmissão.

| Perfil | Eb/N0 verdadeiro (dB) | Eb/N0 medido (dB) | BER | PER | Goodput (kbit/s) | Perda (dB) |
|---|---|---|---|---|---|---|
| `dbpsk-256k` | 7 / 9 / 11 | 6,98 / 9,01 / 11,00 | 3,6 × 10⁻³ / 2,0 × 10⁻⁴ / 6,5 × 10⁻⁶ | 95% / 17% / 0,7% | 11 / 193 / 231 | +0,05 / +0,08 / (3 erros) |
| `gfsk-128k` | 10 / 12 / 14 | 10,00 / 12,01 / 14,00 | 2,4 × 10⁻³ / 1,5 × 10⁻⁴ / 0 | 92% / 14% / 0 | 9 / 100 / 116 | −0,30 / −0,10 / (sem erros) |
| `ook-128k` | 10 / 12 / 14 | 9,85 / 11,86 / 13,82 | 3,1 × 10⁻³ / 2,3 × 10⁻⁴ / 4,3 × 10⁻⁶ | 93% / 20% / 0,4% | 8 / 93 / 116 | +0,27 / +0,37 / (2 erros) |
| `prova-b` (com FEC) | 4 / 5 / 6 | 3,90 / 5,26 / 5,96 | 2,0 × 10⁻⁴ / 0 / 0 | 4,2% / 0 / 0 | 11,8 / 12,3 / 12,3 | (com FEC) |

A OOK mede o Eb/N0 0,15 a 0,18 dB abaixo do verdadeiro: o estimador usa a potência média da captura, e na OOK o quadro tem trechos sem portadora. Fica dentro do erro já medido na Etapa 5.

## 5. Testes

`tests/test_bancada.py` (15 testes):

- leitura de um ponto com e sem a avaliação, sem medidas e com BER `NaN` (o `medir_ber` sem bits comparados), e a taxa de bits da DQPSK com 2 bits por símbolo;
- a inversão da curva teórica em todas as modulações (a 0,02 dB) e os casos fora da curva;
- a perda como distância horizontal até a teoria (+1,5 dB num ponto construído), nula com FEC e com menos de 10 erros, e o limite exato de 10 erros;
- a tabela com e sem dados (sem "sem dado%"), o aviso de banda não confiável e a ordem dos pontos;
- o script de ponta a ponta numa pasta e a recusa de uma pasta vazia.

Mutantes (10, todos mortos): `NaN` aceito, bits por símbolo fixo, FEC ignorado, sinal da perda trocado, mínimo de erros ignorado, mínimo de erros deslocado de 1, sem piso na curva, avaliação ignorada, aviso de banda sumido e ordem invertida.

## 6. Defeitos achados no caminho

- **A pasta da sessão não entrava no git.** O `.gitignore` só liberava arquivos direto em `dados/logs/`; agora libera os JSON, a tabela e o gráfico das subpastas de sessão.
- **A análise saía "suja"** quando havia documento ainda não commitado: a versão do código agora ignora `dados/` e `docs/`, como nos ensaios.
- **A curva teórica chegava a zero** em 40 dB e quebrava o logaritmo da interpolação: grade até 25 dB e piso de 10⁻³⁰⁰. A grade passou de 0,01 para 0,05 dB e a curva é calculada uma vez por modulação, porque a OOK otimiza o limiar ponto a ponto (o teste caiu de 18 s para 1 s).

## 7. Evidências

| Evidência | Onde |
|---|---|
| Ensaio da sessão simulada | `ensaios/etapa5/bancada_simulada_ensaio.py`, `dados/logs/bancada_simulada_20261122_153017.json`, `dados/logs/bancada_simulada_execucao.log` |
| A sessão como ela fica na bancada | `dados/logs/bancada_simulada_20261122_153017/`: o `_rx.json`, a avaliação e os metadados de cada ponto, `analise_bancada.md` e `analise_bancada.png` |
