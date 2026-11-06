# Estratégia de testes

## Regra de regressão

Todo defeito funcional ou de segurança que puder ser reproduzido deve gerar um
teste automatizado permanente. O teste precisa representar o comportamento que
falhou, falhar sem a correção e passar com ela.

A correção não é considerada concluída apenas com um smoke test manual. O teste
de regressão deve ficar na camada estável mais próxima da causa:

- regras e persistência: teste unitário ou de repositório;
- autenticação, autorização e contratos: teste de API;
- estrutura e assets da interface: teste HTTP/HTML;
- interação no navegador: teste de interface quando a infraestrutura existir.

Para julgamentos exclusivamente estéticos, automatizamos o contrato estrutural e
as interações objetivas. A avaliação estética restante deve ser exercitada nas
resoluções afetadas e registrada como verificação manual.

## Regressões no navegador

Os contratos visuais objetivos usam Playwright com Chromium. Depois de
sincronizar o ambiente de desenvolvimento pela primeira vez, instale o navegador
gerenciado pelo Playwright:

```bash
uv sync --dev
uv run playwright install chromium
```

Em um Linux recém-instalado, se o navegador informar bibliotecas de sistema
ausentes, instale também essas dependências com permissão administrativa:

```bash
uv run playwright install --with-deps chromium
```

A suíte executada por `uv run pytest -q` inclui essas regressões. Ela falha com
uma instrução explícita quando o Chromium ainda não está instalado; não pula
silenciosamente a proteção visual.

## Gate de entrega

Antes de publicar um incremento:

1. executar os testes diretamente relacionados à mudança;
2. executar a suíte completa com `uv run pytest -q`;
3. validar sintaxe, build e `git diff --check`;
4. exercitar o fluxo visível no navegador quando houver mudança de interface;
5. registrar explicitamente qualquer aspecto que permaneça apenas manual.
