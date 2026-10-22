# Padrão de código e de desenvolvimento

A NASA não tem uma norma específica para Python. Este projeto adapta as regras **"Power of 10"** do JPL (Gerard Holzmann, 2006), escritas para software crítico em C, e as práticas de processo da **NPR 7150.2** (requisitos, rastreabilidade, verificação e gerência de configuração).

## 1. Regras de código

| # | Regra (Power of 10, adaptada) | Como aplicamos | Verificação |
|:-:|---|---|---|
| 1 | Fluxo de controle simples | Sem recursão, sem `exec`/`eval`, sem exceção usada como `if` | Automática: `verificar.py` (recursão) e ruff `S102`/`S307` |
| 2 | Todo laço com limite fixo | Laços sobre comprimentos conhecidos; laços de transmissão com duração ou contagem máxima | Automática: `verificar.py` proíbe `while True` |
| 3 | Sem alocação dinâmica no caminho crítico | Vetores NumPy pré-alocados; processamento vetorizado, nada de `append` por amostra | Revisão |
| 4 | Funções curtas | No máximo 60 linhas por função | Automática: `verificar.py`; ruff `PLR0915` (40 comandos) e `C901` (complexidade 10) |
| 5 | Pelo menos 2 verificações por função | Validar entradas e saídas com `if ...: raise ValueError(...)`. **Nunca** `assert` no pacote, porque o Python o remove com `-O` | Ruff `S101` no pacote; revisão |
| 6 | Menor escopo possível | Nenhum estado global mutável; configuração em `dataclass(frozen=True)` | Revisão |
| 7 | Verificar todo retorno | Toda chamada ao hardware é conferida e registrada no log | Revisão |
| 8 | Metaprogramação limitada | Sem monkeypatch no pacote, sem import dinâmico | Revisão (desvios na seção 3) |
| 9 | Indireção limitada | Sem argumento padrão mutável; cópia explícita antes de alterar um vetor recebido | Ruff `B006`; revisão |
| 10 | Zero avisos desde o primeiro dia | ruff + mypy `--strict` + pytest com avisos tratados como erro | Automática: portão de qualidade |

Regras complementares:

- **Unidade no nome** de toda grandeza física: `freq_hz`, `taxa_amostragem_sps`, `duracao_s`, `ganho_db`, `ppm`. (Lição do Mars Climate Orbiter, perdido em 1999 por mistura de unidades.)
- **Docstring** em todo módulo, classe e função pública, no estilo Google, dizendo o que faz, parâmetros com unidade, exceções e os IDs dos requisitos atendidos.
- **Tipagem completa** (mypy estrito).
- **Hardware isolado** em `sdrlink/hw/`: o resto do pacote não sabe se as amostras vieram do rádio, de um arquivo ou da simulação.
- **Reprodutibilidade:** toda simulação tem semente fixa; todo ensaio grava configuração, hash do commit, ganho, ppm e offset residual.

## 2. Portão de qualidade

`python ferramentas/verificar.py` roda, em ordem: formatação, lint, tipagem, regras NASA e testes. O hook `.githooks/pre-commit` roda o mesmo script a cada commit e **bloqueia o commit** se algo falhar.

## 3. Desvios justificados

Quando uma regra precisa ser quebrada, o desvio é registrado aqui e no próprio código.

| Arquivo | Regra | Justificativa |
|---|---|---|
| `sdrlink/ambiente.py` | 8 (import dinâmico) | O módulo existe para testar se cada biblioteca carrega; usar `importlib` evita que uma biblioteca ausente derrube o diagnóstico inteiro |

## 4. Fluxo no git

- `main` **sempre funciona**: só recebe código que passou no portão de qualidade.
- Cada bloco em uma branch própria: `bloco/NN-nome-curto` (ex.: `bloco/01-calibracao`).
- Commits pequenos e frequentes, cada um com uma ideia só.
- Bloco pronto → merge na `main` com `git merge --no-ff`, para o histórico mostrar onde cada bloco começou e terminou.
- Tag em cada marco: `bloco-NN` ao fechar um bloco, `etapaN` em cada entrega ao professor e uma tag **obrigatória antes de cada prova** (requisito CMP-C).
- Para voltar a uma versão que funcionava: `git switch -c teste <tag>`, sem apagar nada do histórico; para desfazer um commit já publicado, `git revert`.
- Arquivos grandes (capturas IQ) nunca entram no git: ficam em `dados/`, e o índice `dados/README.md` registra o que foi gravado.

### Mensagens de commit

Formato `tipo(área): descrição no imperativo`, em português:

| Tipo | Quando |
|---|---|
| `feat` | funcionalidade nova |
| `fix` | correção de erro |
| `test` | testes |
| `docs` | documentação |
| `refactor` | reorganização sem mudar o comportamento |
| `chore` | ambiente, dependências, ferramentas |

Exemplo: `feat(quadro): adiciona número de sequência de 16 bits (PKT-01)`.

## 5. Critério de "pronto" de um bloco

1. Portão de qualidade passando, sem nenhum aviso.
2. Testes cobrindo o comportamento novo, incluindo casos de erro.
3. Requisitos atendidos citados no código e atualizados na matriz de rastreabilidade.
4. Evidência guardada (gráfico, log, captura) quando o bloco envolve medição.
5. Uso de IA anotado em `docs/registro_ia.md`.
6. Merge na `main` e tag do bloco.
