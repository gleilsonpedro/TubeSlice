# TubeSlice

Aplicativo desktop em Python para baixar vídeos ou áudio do YouTube e organizar
shows completos em faixas individuais. O projeto é gratuito, aberto a
colaborações e usa a licença MIT.

> **Uso responsável:** baixe somente conteúdo que você tem autorização para
> baixar. Respeite os direitos autorais, os termos do YouTube e a legislação
> aplicável. O projeto não contorna DRM nem controles de acesso.

## Recursos

- Download de vídeo em MP4 ou áudio em MP3 (320 kbps).
- Vídeo único, playlist completa ou seleção de itens de uma playlist.
- Corte automático de shows usando capítulos, timestamps da descrição ou
  transcrição.
- Metadados ID3 e capa quando disponíveis.
- Fila de downloads, progresso, cancelamento de itens pendentes e histórico.
- Windows, Linux e macOS quando Python, FFmpeg e as dependências estão
  disponíveis.

## Instalação para desenvolvimento

Requer Python 3.10 ou superior e [FFmpeg](https://ffmpeg.org/download.html).

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app_4.py
```

No Linux/macOS, ative o ambiente com `source .venv/bin/activate` e execute
`python app_4.py`. O FFmpeg precisa estar no `PATH`; o aplicativo também
detecta um `ffmpeg` colocado ao lado do executável empacotado.

## Como usar

1. Abra a aba **Playlists & Vídeos Únicos**.
2. Cole um link e escolha MP3 ou MP4.
3. Para um show, use **Fatiador Automático (Shows)**.
4. Escolha a pasta de destino e acompanhe a fila.

Downloads novos são salvos por padrão em `Downloads`. O histórico fica na pasta
de dados do usuário, evitando problemas de permissão em executáveis instalados.

## Executáveis para download

O workflow [`build.yml`](.github/workflows/build.yml) gera artefatos para
Windows, Ubuntu e macOS quando uma tag no formato `v*` é publicada. O executável
não inclui FFmpeg: distribua-o junto do pacote ou instale-o separadamente e
confira as licenças aplicáveis do FFmpeg e das dependências.

Para gerar localmente:

```bash
python -m pip install pyinstaller -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name TubeSlice app_4.py
```

## Contribuindo

Abra uma issue para relatar problemas ou propor melhorias. Pull requests são
bem-vindos: descreva o comportamento alterado, mantenha mudanças focadas e
teste com `python -m py_compile app_4.py`.

## Licença

Distribuído sob a [licença MIT](LICENSE).
