# Contribuindo com o TubeSlice

Obrigado por querer melhorar o projeto.

## Fluxo recomendado

1. Abra uma issue descrevendo o problema ou a proposta.
2. Crie uma branch a partir da versão mais recente.
3. Faça uma mudança pequena e focada.
4. Atualize a documentação quando o comportamento mudar.
5. Valide antes de abrir o pull request:

```bash
python -m py_compile app_4.py
```

No pull request, informe o sistema operacional, a versão do Python, a versão
do FFmpeg e os passos para reproduzir o resultado.

## Regras importantes

- Não inclua arquivos baixados, históricos pessoais, credenciais ou binários
  gerados no commit.
- Não altere a licença de dependências de terceiros.
- Não adicione funções para baixar conteúdo protegido ou contornar controles de
  acesso.
- Preserve a compatibilidade com Windows, Linux e macOS sempre que possível.
