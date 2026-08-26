# Operação do BDDente

## Deploy

    fly deploy

Segredos (uma vez):

    fly secrets set SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
    fly postgres attach <nome-do-banco>

Migrations e o primeiro usuário rodam à mão depois do deploy:

    fly ssh console -C "alembic upgrade head"
    fly ssh console --pty -C "python -m scripts.criar_usuario katia@exemplo.com 'Katia'"

## Requisitos que o provedor precisa cumprir

Dado de saúde é dado pessoal sensível pela LGPD — a categoria de maior proteção.
Confira, e anote a data da conferência:

- **HTTPS obrigatório** — garantido pelo `force_https` no `fly.toml`.
- **Criptografia em repouso no banco.** O Postgres gerenciado do Fly.io cifra os
  volumes; se um dia o banco mudar de provedor, isto tem de ser reconfirmado antes
  da migração, não depois.
- **Região do dado.** `primary_region = "gru"` (São Paulo) mantém o prontuário no
  Brasil.

## Backup

Diário, automático, com retenção do provedor mais uma cópia própria:

    python -m scripts.backup backups/

O script recusa dump menor que 100 KB — um banco com 5.561 pacientes e 44.812
lançamentos nunca é tão pequeno, então tamanho pequeno significa dump truncado.

O script **não apaga backup antigo**. Prontuário tem guarda mínima de 10 anos após o
último atendimento (e, se a paciente era menor, o prazo começa quando ela faz 18).
Descartar backup é decisão da clínica, não do script.

## Teste de restauração — TRIMESTRAL, obrigatório

Backup nunca restaurado não conta como backup. A cada três meses:

    createdb bddente_restaurado
    python -m scripts.restaurar backups/bddente-AAAA-MM-DD.dump \
        postgresql://usuario:senha@localhost:5432/bddente_restaurado

O script confere as contagens e falha alto se faltar registro. Anote a data do último
teste bem-sucedido aqui:

| Data do teste | Backup usado | Resultado |
|---|---|---|
| (preencher no primeiro teste) | | |

## Se der problema

- **Aplicação não sobe:** `fly logs`. O health check é `GET /saude`.
- **Migration travada:** `fly ssh console -C "alembic current"` mostra onde parou.
- **Dado de paciente parece errado:** consulte `revisar_motivo` na tabela `paciente`
  e `lancamento` — a migração marca o que é suspeito em vez de corrigir no chute.
- **Nunca rode `DELETE`.** Toda exclusão do sistema é lógica (`excluido_em`).
