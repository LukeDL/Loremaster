# Testes headless

Execute a suíte completa com:

```sh
uv sync --dev
uv run pytest -q
```

Os testes de API e interface usam a aplicação real com engine, loader, banco e
lifespan substituídos explicitamente por fakes. A coleta não requer PortAudio,
dispositivo de áudio, multicast, display ou navegador.

A suíte estática valida `/`, `/map`, import maps e assets locais. Ela não
substitui o gate posterior de áudio em hardware real.
