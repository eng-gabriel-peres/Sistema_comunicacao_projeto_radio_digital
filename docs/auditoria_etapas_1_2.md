# Auditoria de conformidade das Etapas 1 e 2 (04/11/2026)

Confronto item por item do enunciado ([Projeto_Final_SDR.docx.pdf](especificacao/Projeto_Final_SDR.docx.pdf)) com o que foi feito e com a evidência que comprova. Regra: item sem evidência gravada (log, registro JSON, captura ou figura) não conta como atendido.

Legenda: ✅ atendido com evidência, 🟡 parcial, ❌ não atendido, ⏳ depende de terceiros.

## 1. Entregas das Etapas 1 e 2 (seção 6 do enunciado)

| # | Exigência | Situação | Evidência |
|:-:|---|:-:|---|
| 1.1 | Etapa 1: calibrar o RTL-SDR em ppm | ✅ | +84 ppm com o Pluto da equipe: [calibracao_rtl.md](calibracao_rtl.md) seção 10; `dados/calibracao/calibracao_20261104_100631.{json,png}` e `..._100917`; `configs/rtl.toml` |
| 1.2 | Etapa 1: medir o offset residual | ✅ | −356 e −524 Hz logo após a calibração; de −0,68 a −1,62 kHz durante os ensaios; deriva medida ([etapa2_recepcao_ook.md](etapa2_recepcao_ook.md) seção 6, `dados/logs/deriva_offset_20261104_104204.json`, figura `deriva_offset_04nov.png`) |
| 1.3 | Etapa 1: operar as modulações pelo enlace Pluto → RTL | ✅ | Só a OOK existe nesta fase; 8 de 8 recepções e 698 de 698 quadros ([etapa2_recepcao_ook.md](etapa2_recepcao_ook.md)) |
| 1.4 | Etapa 2: estudar e entender a OOK | ✅ | [00_planejamento_e_auditoria.md](00_planejamento_e_auditoria.md) seções 4 e 5; achados A1 a A19 |
| 1.5 | Etapa 2: mapear funções | ✅ | [00_planejamento_e_auditoria.md](00_planejamento_e_auditoria.md) seção 4.1 |
| 1.6 | Etapa 2: executar os códigos nos SDRs | ✅ | `dados/logs/etapa2_tx_*.log` e `etapa2_rx_*.log`; cópias de ensaio com diff em `ensaios/etapa2/diferencas.diff` |
| 1.7 | Etapa 2: registrar recepção válida | ✅ | Log com `CRC-8 received=0x44 computed=0x44 -> OK`, captura IQ e figura do receptor ([etapa2_recepcao_ook.md](etapa2_recepcao_ook.md) seção 3) |
| 1.8 | Toda entrega: registro de uso de IA (ferramentas, prompts, o que foi aproveitado, como foi verificado) | ❌ | [registro_ia.md](registro_ia.md) com a tabela das Etapas 1 e 2 **vazia**. Pendência P1 |
| 1.9 | Prazo das Etapas 1 e 2: 29/10 | ❌ | Ensaios concluídos em 04/11. Pendência P5 |

## 2. Requisitos gerais que já se aplicam (seções 3, 4, 7 e 10)

| # | Exigência | Situação | Evidência / observação |
|:-:|---|:-:|---|
| 2.1 | Pluto só como TX, RTL só como RX; receptor do Pluto nunca usado | ✅ | Nenhum código do projeto abre o RX do Pluto; o ensaio de deriva só lê o sensor de temperatura do Pluto |
| 2.2 | TX e RX em computadores distintos | 🟡 | Ensaios de 04/11 com **um só PC**. Obrigatório nas provas. Pendência P2 |
| 2.3 | Aquecer o RTL cerca de 10 min antes de calibrar ou ensaiar | ✅ | RTL ligado antes das 09:57; calibração adotada às 10:06 e 10:09 com o RTL aquecido; ensaios a partir das 10:16 |
| 2.4 | Correção de ppm calibrada e registrada | ✅ | item 1.1 |
| 2.5 | Ajustar a correção do oscilador do Pluto (recomendado) | 🟡 | Erro do Pluto da equipe estimado em cerca de −9,5 ppm; `xo_correction` ainda de fábrica. Pendência P3 |
| 2.6 | Frequência e potência autorizadas (Anatel) | 🟡 | 915,2 MHz, dentro da faixa ISM 902 a 928 MHz; TX −20 dB, rádios lado a lado. A frequência oficial ainda não foi definida pelo professor (PLT-05) |
| 2.7 | Registrar: pacotes transmitidos, recebidos, válidos e perdidos | ✅ | `decodificar_quadros_ensaio.py`: esperados, detectados, CRC OK, CRC falho, não detectados (seção 4 do registro da Etapa 2) |
| 2.8 | Registrar: duração, modulação e parâmetros | ✅ | Logs e tabela de montagem |
| 2.9 | Registrar: ganho do receptor com AGC desligado | ✅ | Corrigido nesta auditoria: o registro dizia 10 dB, mas o R820T aplica **8,7 dB** (degrau mais próximo). Os documentos passaram a citar o valor aplicado |
| 2.10 | Registrar: offset residual | ✅ | item 1.2 |
| 2.11 | Registrar logs, parâmetros e capturas IQ para auditoria | ✅ | Corrigido nesta auditoria: os logs de console não eram gravados. Agora ficam em `dados/logs/`, versionados; capturas IQ em `dados/capturas/` (fora do git pelo tamanho, indexadas em `dados/README.md`) |
| 2.12 | Código executável, versionado, documentado e com parâmetros configuráveis | ✅ | Repositório com tags `bloco-00` a `bloco-02`; portão de qualidade (ruff, mypy --strict, regras NASA, 74 testes); `configs/rtl.toml` |
| 2.13 | Toda alteração no código de referência documentada | ✅ | Originais intactos em `referencia/`; cópias geradas por script com diff versionado |

## 3. Limites das provas (seções 8 e 12), situação hoje

| # | Limite | Situação | Observação |
|:-:|---|:-:|---|
| 3.1 | PER ≤ 1% | ✅ na OOK de referência | 0 / 698 com a nossa captura. Com o leitor da referência seria 14 / 109 (12,8%) por causa do A17. A PER oficial, pelo log do TX, depende do quadro com número de sequência (Etapa 3) |
| 3.2 | Banda ocupada a 99% ≤ 1 MHz | ⏳ | Ainda não medida; obrigatória na Etapa 3 |
| 3.3 | Goodput ≥ 10 kbit/s (prova B), 500 pacotes | ❌ esperado | O próprio enunciado avisa que a OOK de referência não chega lá; é meta da Etapa 3 em diante |
| 3.4 | Payload de 128 bytes, número de sequência, CRC adequado | ❌ | Etapa 3 (achados A3, A4, A9) |
| 3.5 | Receptor processa em até 10 min e gera arquivo de saída | ❌ | Etapa 3 e 5 (A1) |

**Sobre BER**: o enunciado não fixa limite de BER, só manda medir (Etapa 5, com sequência pseudoaleatória). Medido agora, com a mensagem conhecida: 0 erros em 117 264 bits de payload.

## 4. Problemas encontrados nesta auditoria e o que foi feito

| # | Problema | Ação |
|:-:|---|---|
| F1 | O registro dizia ganho de 10 dB, mas o rádio aplicou 8,7 dB | Documentos corrigidos; a Etapa 3 registra sempre `Captura.ganho_db` (valor lido do rádio) |
| F2 | Logs de console das recepções não eram gravados | Ensaio repetido às 10:38 com os logs gravados e versionados (`dados/logs/`) |
| F3 | Offset residual medido só na calibração | Medido em todas as capturas e num ensaio de deriva dedicado: achado A18 |
| F4 | A PER tinha sido estimada com só 179 quadros | Captura de 16 s: 698 quadros, PER 0%, BER 0 |
| F5 | O topo de `calibracao_rtl.md` ainda mostrava +77 ppm e a figura de 22/10 | Topo atualizado para +84 ppm com a figura de 04/11; revisão 2 marcada como histórico |
| F6 | Erro de I2C ao fechar o RTL depois da leitura assíncrona | Investigado e registrado como A19 (não afeta os dados) |

## 5. Pendências

| # | Pendência | Responsável | Quando |
|:-:|---|---|---|
| P1 | Preencher o registro de uso de IA das Etapas 1 e 2 (texto próprio da equipe) | Gabriel | antes de entregar |
| P2 | Repetir uma recepção com TX e RX em computadores distintos e gravar o log dos dois lados | equipe | próxima bancada |
| P3 | Decidir sobre o `xo_correction` do Pluto e, se ajustar, recalibrar o RTL | equipe | próxima bancada |
| P4 | Separar a deriva do Pluto da do RTL (rádios FM medidas junto com a OOK) | equipe | Etapa 3 |
| P5 | Confirmar com o professor como entregar as Etapas 1 e 2 fora do prazo | Gabriel | já |
| P6 | Pedir ao professor a frequência oficial (PLT-05) | Gabriel | já |
