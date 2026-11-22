# Configurações

| Arquivo | Conteúdo |
|---|---|
| `rtl.toml` | correção de frequência do RTL-SDR adotada pela equipe (+84 ppm com o Pluto da equipe), com o histórico das medições ([docs/calibracao_rtl.md](../docs/calibracao_rtl.md)) |
| `perfis.toml` | perfis de enlace com nome: modulação, pulso, amostras por símbolo, taxa, deslocamento, LO, FEC e emenda das caudas ([docs/etapa6_prova_a.md](../docs/etapa6_prova_a.md), seção 3) |

O transmissor, a gravação e o receptor leem o **mesmo** perfil (`--perfil <nome>`), para nunca ficarem com parâmetros diferentes (achado A14 da auditoria). Um parâmetro dado na linha de comando substitui só aquele campo, e o JSON de cada script registra o perfil completo usado.

Perfis: `prova-a` (DQPSK), `prova-a-fec` e `prova-a-dbpsk` (reservas da prova A), `prova-b` (DBPSK com FEC), `prova-b-sem-fec` e `prova-b-limite`, e os da bancada da Etapa 5 (`dbpsk-256k`, `gfsk-128k`, `ook-128k`).
