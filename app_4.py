import os
import re
import gc
import json
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from youtube_transcript_api import YouTubeTranscriptApi
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, error

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def obter_pasta_dados():
    """Retorna uma pasta gravável para preferências e histórico do aplicativo."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    pasta = os.path.join(base, "TubeSlice")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def localizar_ffmpeg():
    """Encontra FFmpeg instalado ou distribuído junto do executável."""
    nomes = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
    locais = [shutil.which(nome) for nome in nomes]
    pasta_aplicativo = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    locais.extend(os.path.join(pasta_aplicativo, nome) for nome in nomes)
    for caminho in locais:
        if caminho and os.path.isfile(caminho):
            return caminho
    return None


# Ajuste fino da detecção por [Música]
DURACAO_MIN_FAIXA = 60          
MAX_PALAVRAS_ENTRE_TRECHOS = 12 
MAX_SEGUNDOS_ENTRE_TRECHOS = 45
MARGEM_INICIO = 1.0             
MARGEM_FIM = 2.0                

RE_TAG_MUSICA = re.compile(r'\[\s*(?:m[úu]sica|music|musique)\s*\]|♪', re.I)
RE_TAG_APLAUSO = re.compile(r'\[\s*(?:aplausos?|palmas|applause|cheering)\s*\]', re.I)
RE_TAG_QUALQUER = re.compile(r'\[[^\]]*\]|\([^)]*\)|♪')
RE_TS_LINHA = re.compile(r'^\W*(?:\d+[.)]\s*)?(\d{1,2}(?::\d{2}){1,2})\W*\s*(.*)$')


class HistoricoWindow(ctk.CTkToplevel):
    def __init__(self, master, caminho_txt, caminho_json):
        super().__init__(master)
        self.title("Histórico de Downloads - TubeSlice")
        self.geometry("620x500")
        self.caminho_txt = caminho_txt
        self.caminho_json = caminho_json

        self.lbl_titulo = ctk.CTkLabel(self, text="Histórico de Downloads Realizados", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_titulo.pack(pady=10)

        self.txt_view = ctk.CTkTextbox(self, width=580, height=380, font=ctk.CTkFont(family="Courier", size=11))
        self.txt_view.pack(padx=15, pady=5, fill="both", expand=True)

        if os.path.exists(self.caminho_txt):
            with open(self.caminho_txt, "r", encoding="utf-8") as f:
                conteudo = f.read()
            self.txt_view.insert("0.0", conteudo)
        else:
            self.txt_view.insert("0.0", "Nenhum download registrado até o momento.")
        self.txt_view.configure(state="disabled")

        self.btn_abrir = ctk.CTkButton(self, text="Abrir Arquivo TXT", command=self.abrir_txt)
        self.btn_abrir.pack(pady=10)
        self.grab_set()

    def abrir_txt(self):
        if os.path.exists(self.caminho_txt):
            if os.name == "nt":
                os.startfile(self.caminho_txt)
            else:
                webbrowser.open(f"file://{os.path.abspath(self.caminho_txt)}")


class SelecaoPlaylistWindow(ctk.CTkToplevel):
    def __init__(self, master, playlist_info, callback_adicionar):
        super().__init__(master)
        self.title("Selecionar Faixas da Playlist")
        self.geometry("520x600")
        self.callback_adicionar = callback_adicionar
        self.entries = playlist_info.get('entries', [])
        
        self.lbl_titulo = ctk.CTkLabel(self, text=playlist_info.get('title', 'Playlist'), font=ctk.CTkFont(weight="bold", size=15))
        self.lbl_titulo.pack(pady=10)

        self.scroll = ctk.CTkScrollableFrame(self, width=470, height=450)
        self.scroll.pack(pady=10, padx=10, fill="both", expand=True)

        self.checkboxes = []
        for video in self.entries:
            if video:
                var = tk.BooleanVar(value=True)
                titulo = video.get('title', 'Vídeo')
                cb = ctk.CTkCheckBox(self.scroll, text=titulo, variable=var)
                cb.pack(anchor="w", pady=2, padx=5)
                self.checkboxes.append((var, video))

        self.btn_confirmar = ctk.CTkButton(self, text="Confirmar e Iniciar", fg_color="#2b8a3e", hover_color="#237032", command=self.confirmar)
        self.btn_confirmar.pack(pady=10)
        self.grab_set()

    def confirmar(self):
        selecionados = [video for var, video in self.checkboxes if var.get()]
        self.callback_adicionar(selecionados)
        self.destroy()


class TubeSliceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TubeSlice")
        self.geometry("780x820")
        self.resizable(False, False)

        pasta_projeto = os.path.dirname(os.path.abspath(__file__))
        self.pasta_destino = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(self.pasta_destino):
            self.pasta_destino = pasta_projeto
        pasta_dados = obter_pasta_dados()
        self.caminho_historico_json = os.path.join(pasta_dados, "historico_downloads.json")
        self.caminho_historico_txt = os.path.join(pasta_dados, "historico_downloads.txt")
        for nome in ("historico_downloads.json", "historico_downloads.txt"):
            antigo = os.path.join(pasta_projeto, nome)
            novo = os.path.join(pasta_dados, nome)
            if os.path.exists(antigo) and not os.path.exists(novo):
                try:
                    shutil.copy2(antigo, novo)
                except OSError:
                    pass

        self.fila_downloads = []
        self.processando = False
        self.ffmpeg = localizar_ffmpeg()

        self.criar_interface()

    def criar_interface(self):
        self.lbl_titulo = ctk.CTkLabel(self, text="TubeSlice", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_titulo.pack(pady=(12, 2))

        self.lbl_sub = ctk.CTkLabel(self, text="Divisor inteligente de áudio e gerenciador de mídia", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_sub.pack(pady=(0, 6))

        # ABAS
        self.tabview = ctk.CTkTabview(self, width=730, height=170)
        self.tabview.pack(pady=5, padx=25)

        self.tab_fatiador = self.tabview.add("Fatiador Automático (Shows)")
        self.tab_playlist = self.tabview.add("Playlists & Vídeos Únicos")

        # ABA 1: Fatiador
        self.lbl_l1 = ctk.CTkLabel(self.tab_fatiador, text="Link do Show (detecta quebras e corta sozinho):", font=ctk.CTkFont(weight="bold"))
        self.lbl_l1.pack(anchor="w", padx=10, pady=(4, 0))
        self.entry_fatiador = ctk.CTkEntry(self.tab_fatiador, width=690, placeholder_text="Cole o link do show aqui...")
        self.entry_fatiador.pack(pady=5)
        
        self.btn_add_fatiador = ctk.CTkButton(self.tab_fatiador, text="Baixar e Fatiar Show", fg_color="#2b8a3e", hover_color="#237032", command=self.acao_adicionar_fatiador)
        self.btn_add_fatiador.pack(pady=6)

        # ABA 2: Playlist / Vídeo Normal
        self.lbl_l2 = ctk.CTkLabel(self.tab_playlist, text="Link da Playlist ou Vídeo Único:", font=ctk.CTkFont(weight="bold"))
        self.lbl_l2.pack(anchor="w", padx=10, pady=(4, 0))
        self.entry_playlist = ctk.CTkEntry(self.tab_playlist, width=690, placeholder_text="Cole o link da playlist ou vídeo...")
        self.entry_playlist.pack(pady=5)

        self.frame_opt = ctk.CTkFrame(self.tab_playlist, fg_color="transparent")
        self.frame_opt.pack(pady=2)
        self.formato_normal = tk.StringVar(value="mp3")
        ctk.CTkRadioButton(self.frame_opt, text="MP3 (Áudio 320kbps)", variable=self.formato_normal, value="mp3").pack(side="left", padx=15)
        ctk.CTkRadioButton(self.frame_opt, text="MP4 (Vídeo)", variable=self.formato_normal, value="mp4").pack(side="left", padx=15)

        self.btn_add_play = ctk.CTkButton(self.tab_playlist, text="Processar Playlist / Vídeo", fg_color="#2b8a3e", hover_color="#237032", command=self.acao_adicionar_playlist)
        self.btn_add_play.pack(pady=5)

        # PASTA DE DESTINO E HISTÓRICO
        self.frame_pasta = ctk.CTkFrame(self, width=730, fg_color="transparent")
        self.frame_pasta.pack(pady=4, padx=25, fill="x")
        
        self.btn_pasta = ctk.CTkButton(self.frame_pasta, text="Alterar Pasta", command=self.selecionar_pasta, width=110)
        self.btn_pasta.pack(side="left", padx=(0, 8))
        
        self.btn_historico = ctk.CTkButton(self.frame_pasta, text="Ver Histórico", fg_color="#34495e", hover_color="#2c3e50", command=self.abrir_historico, width=110)
        self.btn_historico.pack(side="left", padx=(0, 10))

        self.lbl_caminho_pasta = ctk.CTkLabel(self.frame_pasta, text=f"Destino: {self.pasta_destino}", text_color="gray", justify="left")
        self.lbl_caminho_pasta.pack(side="left", fill="x", expand=True)

        # BARRA DE PROGRESSO
        self.frame_progresso = ctk.CTkFrame(self, width=730, fg_color="transparent")
        self.frame_progresso.pack(pady=(8, 2), padx=25, fill="x")
        
        self.lbl_progresso_pct = ctk.CTkLabel(self.frame_progresso, text="0%", font=ctk.CTkFont(weight="bold", size=12))
        self.lbl_progresso_pct.pack(side="right", padx=(10, 0))
        
        self.barra_progresso = ctk.CTkProgressBar(self.frame_progresso, height=12, progress_color="#2b8a3e")
        self.barra_progresso.set(0)
        self.barra_progresso.pack(side="left", fill="x", expand=True)

        # FILA VISUAL COM CANCELAMENTO
        self.lbl_fila = ctk.CTkLabel(self, text="Fila de Downloads (Clique em [X] para cancelar itens pendentes):", font=ctk.CTkFont(weight="bold"))
        self.lbl_fila.pack(anchor="w", padx=30, pady=(4, 0))
        
        self.scroll_fila = ctk.CTkScrollableFrame(self, width=710, height=105)
        self.scroll_fila.pack(padx=25, pady=3)

        # STATUS E LOGS
        self.lbl_status = ctk.CTkLabel(self, text="Aguardando link...", font=ctk.CTkFont(size=12, slant="italic"), text_color="#2b8a3e")
        self.lbl_status.pack(pady=(3, 0))

        self.txt_log = ctk.CTkTextbox(self, width=730, height=160, fg_color="#141414", text_color="#00ff41", font=ctk.CTkFont(family="Courier", size=11))
        self.txt_log.pack(pady=5, padx=25)

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(initialdir=self.pasta_destino, title="Selecione a pasta")
        if pasta:
            self.pasta_destino = pasta
            self.lbl_caminho_pasta.configure(text=f"Destino: {self.pasta_destino}")

    def log(self, msg):
        self.txt_log.insert("end", f"{msg}\n")
        self.txt_log.see("end")

    def atualizar_status(self, txt):
        self.lbl_status.configure(text=txt)

    def formatar_tempo(self, segundos):
        m, s = divmod(int(segundos), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def extrair_id(self, url):
        padrao = r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})'
        m = re.search(padrao, url)
        return m.group(1) if m else url

    # --- GERENCIAMENTO DE HISTÓRICO ---
    def carregar_historico_json(self):
        if os.path.exists(self.caminho_historico_json):
            try:
                with open(self.caminho_historico_json, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def salvar_no_historico(self, video_id, url, titulo, tipo):
        agora = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
        dados = self.carregar_historico_json()
        dados[video_id] = {
            "titulo": titulo,
            "url": url,
            "tipo": tipo,
            "data": agora
        }
        try:
            with open(self.caminho_historico_json, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"[Aviso] Falha ao atualizar histórico JSON: {e}")

        # Salva em TXT formatado para leitura direta
        try:
            linha = f"[{agora}] ({tipo.upper()}) {titulo} | Link: {url}\n"
            with open(self.caminho_historico_txt, "a", encoding="utf-8") as f:
                f.write(linha)
        except Exception as e:
            self.log(f"[Aviso] Falha ao atualizar histórico TXT: {e}")

    def checar_duplicado(self, url):
        v_id = self.extrair_id(url)
        # 1. Checa se já está na fila ativa
        for item in self.fila_downloads:
            if item.get('video_id') == v_id or item.get('url') == url:
                messagebox.showwarning("Item já na Fila", "Este link já está aguardando na fila de download.")
                return False

        # 2. Checa se já foi baixado anteriormente no histórico
        hist = self.carregar_historico_json()
        if v_id in hist:
            item_hist = hist[v_id]
            data_str = item_hist.get("data", "data anterior")
            resp = messagebox.askyesno(
                "Link Já Baixado",
                f"O vídeo:\n\"{item_hist.get('titulo')}\"\n\nJá foi baixado em {data_str}.\nDeseja baixar novamente?"
            )
            return resp
        return True

    def abrir_historico(self):
        HistoricoWindow(self, self.caminho_historico_txt, self.caminho_historico_json)

    # --- CONTROLE VISUAL DA FILA & CANCELAMENTO ---
    def atualizar_interface_fila(self):
        for widget in self.scroll_fila.winfo_children():
            widget.destroy()
        
        for i, item in enumerate(self.fila_downloads):
            frame = ctk.CTkFrame(self.scroll_fila, fg_color="transparent")
            frame.pack(fill="x", pady=2)
            
            tag = "[FATIAR]" if item['tipo'] == 'fatiar' else f"[{item.get('formato', 'MP3').upper()}]"
            is_ativo = (i == 0 and self.processando)
            status_txt = "Em andamento..." if is_ativo else "Aguardando"
            
            lbl = ctk.CTkLabel(frame, text=f"{i+1}. {tag} {item['titulo'][:50]} ({status_txt})", anchor="w")
            lbl.pack(side="left", padx=5)

            # Botão de cancelar/remover (apenas para itens que ainda não iniciaram)
            if not is_ativo:
                btn_cancelar = ctk.CTkButton(
                    frame, text="X", width=28, height=20, fg_color="#c0392b", hover_color="#922b21",
                    command=lambda idx=i: self.remover_item_fila(idx)
                )
                btn_cancelar.pack(side="right", padx=5)

    def remover_item_fila(self, indice):
        if 0 <= indice < len(self.fila_downloads):
            # Não remove o item 0 se ele já estiver em download
            if indice == 0 and self.processando:
                messagebox.showinfo("Aviso", "O download atual já está em execução e não pode ser interrompido por aqui.")
                return
            removido = self.fila_downloads.pop(indice)
            self.log(f"[FILA] Removido: {removido.get('titulo', 'Item')}")
            self.atualizar_interface_fila()

    # --- ADIÇÃO DE LINKS ---
    def acao_adicionar_fatiador(self):
        texto_bruto = self.entry_fatiador.get().strip()
        if not texto_bruto:
            return

        # Expressão regular para capturar todos os links de YouTube no texto colado
        padrao_url = r'https?://(?:www\.)?(?:youtube\.com/[^\s,;]+|youtu\.be/[^\s,;]+)'
        urls_encontradas = re.findall(padrao_url, texto_bruto)

        # Fallback: caso seja apenas um link sem formatação padrão
        if not urls_encontradas and texto_bruto.startswith("http"):
            urls_encontradas = [texto_bruto]

        if not urls_encontradas:
            messagebox.showwarning("Aviso", "Nenhum link válido do YouTube foi detectado.")
            return

        self.entry_fatiador.delete(0, "end")
        self.log(f"[FILA] Detectado(s) {len(urls_encontradas)} show(s) para processamento em lote.")

        for url in urls_encontradas:
            url_limpa = url.strip()
            if not self.checar_duplicado(url_limpa):
                continue

            item_placeholder = {
                'tipo': 'fatiar',
                'url': url_limpa,
                'titulo': 'Obtendo informações do show...',
                'video_id': self.extrair_id(url_limpa),
                'pronto': False
            }
            self.fila_downloads.append(item_placeholder)
            threading.Thread(target=self._carregar_fatiador_thread, args=(url_limpa, item_placeholder)).start()

        self.atualizar_interface_fila()

    def _carregar_fatiador_thread(self, url, item_ref):
        try:
            ydl_opts = {'quiet': True, 'nocheckcertificate': True, 'no_warnings': True}
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            item_ref['titulo'] = info.get('title', 'Show')
            item_ref['video_id'] = info.get('id', self.extrair_id(url))
            item_ref['info'] = info
            item_ref['pronto'] = True
            
            self.after(0, self.atualizar_interface_fila)
            self.after(0, self._checar_fila)
        except Exception as e:
            self.after(0, self.log, f"Falha ao ler dados do show: {e}")
            if item_ref in self.fila_downloads:
                self.fila_downloads.remove(item_ref)
                self.after(0, self.atualizar_interface_fila)

    def acao_adicionar_playlist(self):
        url = self.entry_playlist.get().strip()
        if not url:
            return

        self.entry_playlist.delete(0, "end")
        self.log(f"[FILA] Analisando link: {url}")
        threading.Thread(target=self._carregar_playlist_thread, args=(url,)).start()

    def _carregar_playlist_thread(self, url):
        try:
            ydl_opts = {'extract_flat': True, 'quiet': True, 'nocheckcertificate': True}
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if 'entries' in info and info['entries']:
                self.after(0, lambda: SelecaoPlaylistWindow(self, info, self._adicionar_itens_playlist))
            else:
                if self.checar_duplicado(url):
                    self._adicionar_itens_playlist([info])
        except Exception as e:
            self.after(0, self.log, f"Falha ao processar link: {e}")

    def _adicionar_itens_playlist(self, lista):
        fmt = self.formato_normal.get()
        adicionados = 0
        for v in lista:
            v_url = v.get('url') or f"https://www.youtube.com/watch?v={v.get('id')}"
            v_id = v.get('id') or self.extrair_id(v_url)
            
            # Checa se já está na fila
            if any(item.get('video_id') == v_id for item in self.fila_downloads):
                continue
                
            self.fila_downloads.append({
                'tipo': 'normal',
                'url': v_url,
                'video_id': v_id,
                'titulo': v.get('title', 'Vídeo'),
                'formato': fmt,
                'pronto': True
            })
            adicionados += 1

        self.atualizar_interface_fila()
        self.log(f"[FILA] {adicionados} item(ns) adicionado(s) à fila.")
        self._checar_fila()

    def _checar_fila(self):
        if not self.processando and self.fila_downloads:
            if self.fila_downloads[0].get('pronto', False):
                self.processando = True
                threading.Thread(target=self._processador_fila).start()

    def hook_progresso(self, d):
        if d['status'] == 'downloading':
            pct_raw = d.get('_percent_str', '0%')
            pct_clean = re.sub(r'\x1b[^m]*m', '', pct_raw).replace('%', '').strip()
            try:
                pct = float(pct_clean)
            except ValueError:
                pct = 0.0
            
            val_norm = max(0.0, min(1.0, pct / 100.0))
            self.after(0, self._atualizar_barra, val_norm, pct)

    def _atualizar_barra(self, val_norm, pct):
        self.barra_progresso.set(val_norm)
        self.lbl_progresso_pct.configure(text=f"{pct:.1f}%")

    def _processador_fila(self):
        while self.fila_downloads:
            item = self.fila_downloads[0]
            if not item.get('pronto', False):
                break
                
            self.after(0, self.atualizar_interface_fila)
            try:
                if item['tipo'] == 'fatiar':
                    self._fatiar_show(item)
                else:
                    self._baixar_normal(item)
                
                # Registra sucesso no histórico
                self.salvar_no_historico(item['video_id'], item['url'], item['titulo'], item['tipo'])
            except Exception as e:
                self.log(f"Erro ao processar {item['titulo']}: {e}")

            if self.fila_downloads and self.fila_downloads[0] == item:
                self.fila_downloads.pop(0)
            self.after(0, self.atualizar_interface_fila)

        self.processando = False
        self.after(0, self.barra_progresso.set, 0)
        self.after(0, self.lbl_progresso_pct.configure, {"text": "0%"})
        self.after(0, self.atualizar_status, "Pronto para novos downloads.")

    # --- LÓGICA DE TRANSCRIÇÃO & CORTE ---
    def _obter_transcricao(self, video_id, info):
        try:
            if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
                lista = YouTubeTranscriptApi.list_transcripts(video_id)
            else:
                lista = YouTubeTranscriptApi().list(video_id)
            idiomas = ['pt', 'pt-BR', 'pt-PT', 'en']
            try:
                t_obj = lista.find_transcript(idiomas)
            except Exception:
                t_obj = lista.find_generated_transcript(idiomas)
            dados = t_obj.fetch()
            if hasattr(dados, 'to_raw_data'):
                dados = dados.to_raw_data()
            if dados:
                self.log("   [Legenda] Obtida via youtube_transcript_api")
                return [{'start': d['start'], 'duration': d.get('duration', 0), 'text': d['text']} for d in dados]
        except Exception as e:
            self.log(f"   [Aviso] Falha transcript_api: {e}")

        try:
            for chave in ('subtitles', 'automatic_captions'):
                legendas = info.get(chave) or {}
                for lang in sorted(legendas.keys()):
                    if not (lang.startswith('pt') or lang.startswith('en')):
                        continue
                    for fmt in legendas[lang]:
                        if fmt.get('ext') == 'json3':
                            dados = requests.get(fmt['url'], timeout=15).json()
                            saida = []
                            for ev in dados.get('events', []):
                                segs = ev.get('segs')
                                if not segs:
                                    continue
                                txt = ''.join(s.get('utf8', '') for s in segs).strip()
                                if txt:
                                    saida.append({
                                        'start': ev.get('tStartMs', 0) / 1000.0,
                                        'duration': ev.get('dDurationMs', 0) / 1000.0,
                                        'text': txt
                                    })
                            if saida:
                                self.log(f"   [Legenda] Obtida via fallback yt-dlp ({chave}/{lang})")
                                return saida
        except Exception as e:
            self.log(f"   [Aviso] Falha fallback yt-dlp: {e}")
        return []

    def _classificar_entrada(self, texto):
        t = texto.replace('\n', ' ').strip()
        if '♪' in t:
            return 'M'
        resto = RE_TAG_QUALQUER.sub('', t).strip()
        if RE_TAG_MUSICA.search(t):
            return 'M' if len(resto.split()) <= 4 else 'S'
        if RE_TAG_APLAUSO.search(t) and not resto:
            return 'A'
        return 'S' if resto else 'N'

    def _segmentos_por_musica(self, entradas, duracao):
        ents = sorted(
            [[float(e['start']), float(e['start']) + float(e.get('duration', 0)), e['text']] for e in entradas],
            key=lambda x: x[0]
        )
        for i in range(len(ents) - 1):
            ents[i][1] = min(ents[i][1], ents[i + 1][0])
        ents = [(ini, fim, self._classificar_entrada(txt), txt) for ini, fim, txt in ents]

        runs, atual = [], None
        for ini, fim, tipo, _ in ents:
            if tipo == 'M':
                if atual is None:
                    atual = {'ini': ini, 'fim': fim}
                else:
                    atual['fim'] = fim
            elif tipo == 'S' and atual:
                atual['fim'] = ini
                atual['fechou'] = 'S'
                runs.append(atual)
                atual = None
            elif tipo == 'A' and atual:
                atual['fim'] = ini
                atual['fechou'] = 'A'
                runs.append(atual)
                atual = None
        if atual:
            atual['fim'] = duracao if duracao else atual['fim']
            atual['fechou'] = 'F'
            runs.append(atual)

        juntos = []
        for r in runs:
            if juntos and juntos[-1]['fechou'] == 'S':
                ant = juntos[-1]
                palavras = sum(
                    len(RE_TAG_QUALQUER.sub('', txt).split())
                    for ini, fim, tipo, txt in ents
                    if tipo == 'S' and ini >= ant['fim'] - 0.01 and ini < r['ini']
                )
                if palavras <= MAX_PALAVRAS_ENTRE_TRECHOS and (r['ini'] - ant['fim']) <= MAX_SEGUNDOS_ENTRE_TRECHOS:
                    ant['fim'] = r['fim']
                    ant['fechou'] = r['fechou']
                    continue
            juntos.append(dict(r))

        faixas = [r for r in juntos if (r['fim'] - r['ini']) >= DURACAO_MIN_FAIXA]
        segmentos = []
        for i, r in enumerate(faixas):
            ini = max(0.0, r['ini'] - MARGEM_INICIO)
            fim = r['fim'] + MARGEM_FIM
            if i + 1 < len(faixas):
                fim = min(fim, faixas[i + 1]['ini'])
            if duracao:
                fim = min(fim, duracao)
            segmentos.append({'inicio': ini, 'fim': fim, 'nome': f"Faixa {str(i + 1).zfill(2)}"})
        return segmentos

    def _ts_para_seg(self, txt):
        s = 0
        for p in txt.split(':'):
            s = s * 60 + int(p)
        return float(s)

    def _segmentos_por_descricao(self, info):
        achados = []
        for linha in (info.get('description') or '').splitlines():
            m = RE_TS_LINHA.match(linha)
            if m:
                nome = re.sub(r'[\\/*?:"<>|]', '', m.group(2)).strip(' -–—:|')
                achados.append((self._ts_para_seg(m.group(1)), nome or f"Faixa {len(achados) + 1:02d}"))
        if len(achados) < 3:
            return []
        if any(achados[i][0] >= achados[i + 1][0] for i in range(len(achados) - 1)):
            return []
        dur = info.get('duration')
        return [{'inicio': ini, 'fim': achados[i + 1][0] if i + 1 < len(achados) else dur, 'nome': nome}
                for i, (ini, nome) in enumerate(achados)]

    def _mapear_segmentos(self, info, video_id):
        capitulos = info.get('chapters')
        if capitulos:
            self.log(f"-> {len(capitulos)} capítulos oficiais encontrados.")
            return [{
                'inicio': c.get('start_time', 0.0),
                'fim': c.get('end_time'),
                'nome': re.sub(r'[\\/*?:"<>|]', '', c.get('title', f"Faixa {i + 1}")).strip()
            } for i, c in enumerate(capitulos)], 'capitulos'

        segs = self._segmentos_por_descricao(info)
        if segs:
            self.log(f"-> {len(segs)} faixas encontradas na descrição.")
            return segs, 'descricao'

        self.log("-> Buscando marcações na transcrição...")
        entradas = self._obter_transcricao(video_id, info)
        if not entradas:
            return [], 'nenhuma'
        segs = self._segmentos_por_musica(entradas, info.get('duration'))
        for s in segs:
            self.log(f"   -> {s['nome']}: {self.formatar_tempo(s['inicio'])} → {self.formatar_tempo(s['fim'])}")
        return segs, 'transcricao'

    def embutir_metadados(self, caminho_mp3, titulo, artista, url_capa):
        try:
            audio = MP3(caminho_mp3, ID3=ID3)
            try:
                audio.add_tags()
            except error:
                pass
            audio.tags.add(TIT2(encoding=3, text=titulo))
            audio.tags.add(TPE1(encoding=3, text=artista))
            if url_capa:
                try:
                    r = requests.get(url_capa, timeout=5)
                    if r.status_code == 200:
                        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=r.content))
                except Exception:
                    pass
            audio.save()
        except Exception:
            pass

    def _fatiar_show(self, item):
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg não encontrado. Instale-o e adicione-o ao PATH.")
        url = item['url']
        video_id = item['video_id']
        info = item['info']

        titulo_limpo = re.sub(r'[\\/*?:"<>|]', "", info.get('title', f"Show_{video_id}")).strip()
        canal = info.get('uploader', 'TubeSlice')
        capa = info.get('thumbnail')

        self.atualizar_status(f"Mapeando: {titulo_limpo[:32]}...")
        self.log(f"\n[SHOW] {titulo_limpo}")

        segmentos, origem = self._mapear_segmentos(info, video_id)

        self.atualizar_status("Baixando áudio completo do show...")
        caminho_tmp = os.path.join(self.pasta_destino, f"temp_{video_id}")
        ydl_opts = {
            'outtmpl': f'{caminho_tmp}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
            'progress_hooks': [self.hook_progresso]
        }
        ydl_opts['ffmpeg_location'] = os.path.dirname(self.ffmpeg)
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        arquivo_bruto = f"{caminho_tmp}.mp3"
        self.log("[PROCESSAMENTO] Download concluído. Fatiando áudio...")

        if segmentos:
            pasta_show = os.path.join(self.pasta_destino, titulo_limpo)
            os.makedirs(pasta_show, exist_ok=True)

            audio = AudioSegment.from_mp3(arquivo_bruto)
            duracao_total = len(audio)

            if origem in ('capitulos', 'descricao') and segmentos[0]['inicio'] > 15:
                segmentos.insert(0, {'inicio': 0.0, 'fim': segmentos[0]['inicio'], 'nome': 'Abertura'})

            for i, seg in enumerate(segmentos):
                ini_ms = int(seg['inicio'] * 1000)
                fim_ms = int(seg['fim'] * 1000) if seg['fim'] else duracao_total
                fim_ms = min(fim_ms, duracao_total)
                if fim_ms <= ini_ms:
                    continue

                nome_arq = f"{str(i + 1).zfill(2)} - {seg['nome']}.mp3"
                caminho_faixa = os.path.join(pasta_show, nome_arq)
                audio[ini_ms:fim_ms].export(caminho_faixa, format="mp3", bitrate="320k")
                self.embutir_metadados(caminho_faixa, seg['nome'], canal, capa)
                self.log(f"   Faixa salva: {nome_arq}")

            # Liberação explícita de memória RAM (evita MemoryError)
            del audio
            gc.collect()

            if os.path.exists(arquivo_bruto):
                os.remove(arquivo_bruto)
            self.log(f"[CONCLUÍDO] Show salvo em: {titulo_limpo}")
        else:
            caminho_final = os.path.join(self.pasta_destino, f"{titulo_limpo}.mp3")
            if os.path.exists(arquivo_bruto):
                if os.path.exists(caminho_final):
                    os.remove(caminho_final)
                os.rename(arquivo_bruto, caminho_final)
                self.embutir_metadados(caminho_final, titulo_limpo, canal, capa)
            self.log("[AVISO] Sem marcações detectadas; salvo como arquivo único.")

    def _baixar_normal(self, item):
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg não encontrado. Instale-o e adicione-o ao PATH.")
        url = item['url']
        titulo = item['titulo']
        fmt = item['formato']

        self.atualizar_status(f"Baixando: {titulo[:32]}...")
        self.log(f"\n[DOWNLOAD] {titulo}")

        nome_limpo = re.sub(r'[\\/*?:"<>|]', "", titulo).strip()
        caminho_saida = os.path.join(self.pasta_destino, nome_limpo)

        ydl_opts = {
            'outtmpl': f'{caminho_saida}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [self.hook_progresso]
        }
        ydl_opts['ffmpeg_location'] = os.path.dirname(self.ffmpeg)

        if fmt == "mp3":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]
            })
        else:
            ydl_opts.update({
                'format': 'bestvideo[height<=1080]+bestaudio/best',
                'merge_output_format': 'mp4'
            })

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if fmt == "mp3":
                arq_mp3 = f"{caminho_saida}.mp3"
                if os.path.exists(arq_mp3):
                    self.embutir_metadados(arq_mp3, titulo, info.get('uploader', 'TubeSlice'), info.get('thumbnail'))

        self.log(f"[CONCLUÍDO] Arquivo salvo: {nome_limpo}.{fmt}")


def main():
    app = TubeSliceApp()
    app.mainloop()


if __name__ == "__main__":
    main()