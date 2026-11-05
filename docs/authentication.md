# Autenticação local

A autenticação da R3 separa contas `gm` e `player`. A Engine de Som, suas APIs e
o WebSocket são exclusivos do mestre. Jogadores entram em `/player` e não têm
acesso aos dados operacionais de áudio.

## Primeira execução

Depois de atualizar as dependências e antes de iniciar o servidor:

```bash
uv sync --dev
uv run loremaster-bootstrap-gm
```

O comando solicita usuário e senha sem gravar a senha no histórico do terminal.
Ele cria somente a primeira conta ativa do mestre e recusa uma segunda execução.
Não existe senha padrão.

Inicie normalmente:

```bash
uv run loremaster
```

Abra o endereço mostrado no terminal. A aplicação redireciona para `/login`.
Depois de entrar, o mestre pode abrir **jogadores** e criar, desativar ou redefinir
a senha das contas da party.

## Segurança e rede

- Use senhas exclusivas do Loremaster enquanto o serviço estiver em HTTP local.
- Não exponha a porta diretamente à internet.
- Acesso remoto exige HTTPS e `LOREMASTER_COOKIE_SECURE=true`, além de limitação
  de tentativas de login e recuperação segura de conta.
- Desativar uma conta ou redefinir sua senha encerra as sessões existentes.
- O banco é copiado automaticamente antes da migração que cria as tabelas de
  autenticação.
