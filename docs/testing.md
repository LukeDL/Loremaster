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

## Gate de entrega

Antes de publicar um incremento:

1. executar os testes diretamente relacionados à mudança;
2. executar a suíte completa com `uv run pytest -q`;
3. validar sintaxe, build e `git diff --check`;
4. exercitar o fluxo visível no navegador quando houver mudança de interface;
5. registrar explicitamente qualquer aspecto que permaneça apenas manual.
