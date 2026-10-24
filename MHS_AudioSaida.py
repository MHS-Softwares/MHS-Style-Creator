import os
import threading
import array

# O sounddevice (PortAudio) só mostra o ASIO se esta variável existir ANTES do primeiro "import sounddevice".
os.environ.setdefault("SD_ENABLE_ASIO", "1")
try:
    import _sounddevice_data  # os .dll do PortAudio (com e sem ASIO): o compilador só os leva se ele aparecer aqui
    import sounddevice as sd
except Exception:  # sem a biblioteca ou sem o PortAudio: o programa segue só com o winmm
    sd = None

import MHS_AudioStyle as AS
from MHS_AudioStyle import TocadorDeAudio, TAXA, BYTES_POR_FRAME

# --- SAÍDA DE ÁUDIO DO AUDIO STYLE ---
# O tocador original (MHS_AudioStyle.TocadorDeAudio) usa o winmm/waveOut, que passa pela
# camada MME do Windows: o áudio sai sempre uns 15 a 40 ms depois do MIDI. Aqui o
# usuário escolhe o sistema de som (ASIO, WASAPI, DirectSound, MME ou WDM-KS) e a
# placa, como no Afinador, e o tocador ajusta o início do áudio pela latência que o
# próprio driver informa. O que sobrar (a latência do MIDI, do sintetizador) é o
# "Ajuste fino" em milissegundos, nas configurações.
#
# A escolha mora no config.json:
#   audio_host         nome do sistema de som ("" = o winmm de sempre)
#   audio_saida        nome da placa dentro desse sistema
#   audio_canais       primeiro canal do par de saída (0 = 1 e 2, 2 = 3 e 4...), só no ASIO
#   audio_latencia_ms  0 = a mais baixa que o driver aceita; senão, o tamanho do buffer
#   audio_compensar    adiantar o áudio pela latência informada pelo driver
#   audio_adiantar_ms  ajuste fino, vale também no winmm (negativo atrasa)

LATENCIAS = [("A mais baixa que o driver aceitar", 0), ("Curta, 10 milissegundos", 10),
             ("Média, 30 milissegundos", 30), ("Longa, 100 milissegundos", 100)]
NOME_WINMM = "Padrão do Windows (winmm, sem escolher a placa)"
OCIOSO_SEGUNDOS = 20.0


def disponivel():
    return sd is not None


def _no_principal(funcao, espera=4.0):
    # Os drivers ASIO só carregam (e só descarregam) na thread principal do programa, a que tem o COM
    # da janela: aberto de dentro da thread do Play, o PortAudio devolve "Failed to load ASIO driver".
    # Quem chama de outra thread pede à janela principal e espera o resultado.
    try:
        import wx
        app = wx.GetApp()
        if app is None or wx.IsMainThread():
            return funcao()
    except Exception:
        return funcao()
    pronto = threading.Event()
    caixa = {}

    def executar():
        try:
            caixa['valor'] = funcao()
        except BaseException as e:
            caixa['erro'] = e
        finally:
            pronto.set()

    wx.CallAfter(executar)
    if not pronto.wait(espera):
        raise RuntimeError("a janela principal não respondeu a tempo para abrir a saída de áudio")
    if 'erro' in caixa:
        raise caixa['erro']
    return caixa.get('valor')


def listar_sistemas():
    if sd is None:
        return []
    return [h['name'] for h in sd.query_hostapis()]


def listar_saidas(sistema):
    # [(índice no PortAudio, nome)] das placas com saída dentro do sistema de som.
    if sd is None:
        return []
    saida = []
    for i, d in enumerate(sd.query_devices()):
        if d['max_output_channels'] > 0 and sd.query_hostapis(d['hostapi'])['name'] == sistema:
            saida.append((i, d['name']))
    return saida


def achar_saida(sistema, nome):
    # O Windows às vezes renumera ou encurta o nome da placa: tenta o nome igual e depois o começo dele.
    saidas = listar_saidas(sistema)
    for i, n in saidas:
        if n == nome:
            return i
    base = (nome or "").strip().lower()
    for i, n in saidas:
        if base and (n.lower().startswith(base) or base.startswith(n.lower())):
            return i
    return None


def pares_de_canais(indice):
    # [(canal inicial, "1 e 2")...] - o ASIO deixa escolher em qual par de saídas o áudio sai.
    n = int(sd.query_devices(indice)['max_output_channels'])
    pares = [(c, f"{c + 1} e {c + 2}") for c in range(0, n - 1, 2)]
    return pares or [(0, "1")]


def _reamostrar_estereo(pcm, taxa_destino):
    amostras = array.array('h')
    amostras.frombytes(pcm)
    # interpolação linear de TAXA para taxa_destino, canal por canal
    def convertido(canal):
        n = len(canal)
        total = int(n * taxa_destino / TAXA)
        passo = TAXA / taxa_destino
        saida = array.array('h', bytes(total * 2))
        ultimo = n - 1
        for i in range(total):
            x = i * passo
            j = int(x)
            if j >= ultimo:
                saida[i] = canal[ultimo]
            else:
                a = canal[j]
                saida[i] = int(a + (canal[j + 1] - a) * (x - j))
        return saida
    e, d = convertido(amostras[0::2]), convertido(amostras[1::2])
    estereo = array.array('h', bytes(len(e) * 4))
    estereo[0::2] = e
    estereo[1::2] = d
    return estereo.tobytes()


class TocadorSD(TocadorDeAudio):
    # Mesmo contrato do TocadorDeAudio (tocar, parar, iniciar_passagem), mas pela placa e pelo
    # sistema de som escolhidos. O fluxo de áudio fica aberto entre um Play e outro por
    # OCIOSO_SEGUNDOS (abrir um driver ASIO leva uma fração de segundo); depois disso é fechado,
    # para o ASIO não prender a interface de áudio de outros programas.
    def __init__(self, indice, canal_inicial=0, latencia_ms=0, compensar=True):
        super().__init__()
        self.indice = indice
        self.canal_inicial = canal_inicial
        self.latencia_ms = latencia_ms
        self.compensar = compensar
        self.erro = None
        self.latencia_s = 0.0
        self._fluxo = None
        self._taxa = TAXA
        self._cb_trava = threading.Lock()
        self._dados = None
        self._posb = 0
        self._ativo = False
        self._consumidos = 0
        self._ultimo = (0.0, 0, 0)
        self._timer = None
        self._reamostrado = None

    # --- fluxo ---
    def _abrir(self):
        if self._fluxo is not None:
            return
        _no_principal(self._abrir_aqui)

    def preparar(self):
        # Chamado pela thread principal quando o Play começa: abre a placa já, antes de o motor MIDI precisar dela.
        with self._trava:
            self._cancelar_timer()
            try:
                self.erro = None
                self._abrir()
            except Exception as e:
                self.erro = str(e) or e.__class__.__name__

    def _abrir_aqui(self):
        if self._fluxo is not None:
            return
        info = sd.query_devices(self.indice)
        sistema = sd.query_hostapis(info['hostapi'])['name']
        extra = None
        if sistema == 'ASIO':
            extra = sd.AsioSettings(channel_selectors=[self.canal_inicial, self.canal_inicial + 1])
        elif sistema == 'Windows WASAPI':
            extra = sd.WasapiSettings(auto_convert=True)
        latencia = 'low' if not self.latencia_ms else self.latencia_ms / 1000.0
        taxas = [TAXA]
        padrao = int(info['default_samplerate'])
        if padrao != TAXA:
            taxas.append(padrao)
        ultimo_erro = None
        for taxa in taxas:
            try:
                fluxo = sd.RawOutputStream(samplerate=taxa, channels=2, dtype='int16', device=self.indice,
                                           latency=latencia, callback=self._cb, extra_settings=extra)
                fluxo.start()
            except Exception as e:
                ultimo_erro = e
                continue
            self._fluxo = fluxo
            self._taxa = taxa
            self.DESVIO_MAXIMO = taxa * 20 // 1000
            try:
                self.latencia_s = float(fluxo.latency)
            except Exception:
                self.latencia_s = 0.0
            return
        raise ultimo_erro

    def _fechar(self):
        fluxo, self._fluxo = self._fluxo, None
        if fluxo is not None:
            try:
                fluxo.stop()
                fluxo.close()
            except Exception:
                pass

    def fechar(self):
        with self._trava:
            self._parar()
            self._cancelar_timer()
            self._fechar()

    def _cancelar_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fechar_ocioso(self):
        # Roda numa thread do Timer: quem fecha o driver (ASIO) é a janela principal.
        try:
            import wx
            wx.CallAfter(self._fechar_ocioso_principal)
        except Exception:
            self._fechar_ocioso_principal()

    def _fechar_ocioso_principal(self):
        with self._trava:
            if self._saida is None:
                self._fechar()

    # --- a placa pede áudio ---
    def _cb(self, saida, frames, tempo, status):
        n = frames * BYTES_POR_FRAME
        with self._cb_trava:
            dados = self._dados
            if not self._ativo or not dados:
                saida[:n] = bytes(n)
                return
            pos, total = self._posb, len(dados)
            partes, faltam = [], n
            while faltam:
                pedaco = dados[pos:pos + faltam]
                partes.append(pedaco)
                pos += len(pedaco)
                faltam -= len(pedaco)
                if pos >= total:
                    pos = 0
            self._posb = pos
            self._ultimo = (tempo.currentTime, self._consumidos, frames)
            self._consumidos += frames
        saida[:n] = b''.join(partes)

    # --- contrato do TocadorDeAudio ---
    def _pcm_na_taxa(self, pcm):
        if self._taxa == TAXA:
            return pcm
        if self._reamostrado and self._reamostrado[0] is pcm and self._reamostrado[1] == self._taxa:
            return self._reamostrado[2]
        convertido = _reamostrar_estereo(pcm, self._taxa)
        self._reamostrado = (pcm, self._taxa, convertido)
        return convertido

    def _tocar(self, pcm, frame_inicial):
        self.erro = None
        self._cancelar_timer()
        try:
            self._abrir()
        except Exception as e:
            self.erro = str(e) or e.__class__.__name__
            raise
        dados = self._pcm_na_taxa(pcm)
        total = len(dados) // BYTES_POR_FRAME
        if total <= 0:
            return
        inicio = frame_inicial * self._taxa // TAXA
        if self.compensar:
            # O áudio só chega à placa depois da latência do driver; começa esse tanto à frente.
            inicio += int(round(self.latencia_s * self._taxa))
        inicio %= total
        with self._cb_trava:
            self._dados = dados
            self._posb = inicio * BYTES_POR_FRAME
            self._consumidos = 0
            self._ultimo = (0.0, 0, 0)
            self._ativo = True
        self._pcm = pcm
        self._saida = self._fluxo
        self._desvio_de_base = None
        self._frames_do_loop = total
        self._frames_antes_do_loop = total - inicio if inicio else 0

    def _parar(self):
        with self._cb_trava:
            self._ativo = False
            self._dados = None
        self._saida = None
        self._pcm = None
        if self._fluxo is not None and self._timer is None:
            self._timer = threading.Timer(OCIOSO_SEGUNDOS, self._fechar_ocioso)
            self._timer.daemon = True
            self._timer.start()

    def _desvio(self):
        fluxo = self._fluxo
        if fluxo is None:
            return None
        with self._cb_trava:
            t_cb, antes, bloco = self._ultimo
            if not bloco:
                return None
        try:
            decorrido = fluxo.time - t_cb
        except Exception:
            decorrido = 0.0
        extra = max(0.0, min(decorrido, 2.0 * bloco / self._taxa)) * self._taxa
        tocados = antes + int(extra)
        desvio = (tocados - self._frames_antes_do_loop) % self._frames_do_loop
        if desvio > self._frames_do_loop // 2:
            desvio -= self._frames_do_loop
        return desvio


def criar_tocador(config):
    # O tocador que a configuração pede; o winmm de sempre quando nada foi escolhido ou a escolha não existe mais.
    sistema = config.get("audio_host") or ""
    if not sistema or sd is None:
        return TocadorDeAudio()
    indice = achar_saida(sistema, config.get("audio_saida", ""))
    if indice is None:
        return TocadorDeAudio()
    return TocadorSD(indice, int(config.get("audio_canais", 0) or 0), int(config.get("audio_latencia_ms", 0) or 0),
                     bool(config.get("audio_compensar", True)))


class TocadorEscolhido:
    # O que o resto do programa enxerga como MHS_AudioStyle.tocador: entrega tudo ao tocador da
    # configuração e, se a placa escolhida falhar (ocupada por outro programa, por exemplo), volta
    # sozinho para o winmm e avisa uma vez.
    def __init__(self, falar=None):
        self._b = TocadorDeAudio()
        self._falar = falar
        self._avisou = False

    def configurar(self, config):
        antigo = self._b
        self._b = criar_tocador(config)
        self._avisou = False
        try:
            antigo.parar()
            if hasattr(antigo, 'fechar'):
                antigo.fechar()
        except Exception:
            pass

    def fechar(self):
        try:
            if hasattr(self._b, 'fechar'):
                self._b.fechar()
            else:
                self._b.parar()
        except Exception:
            pass

    def iniciar_passagem(self, *a, **k):
        self._b.iniciar_passagem(*a, **k)
        if self._falhou():
            self._b.iniciar_passagem(*a, **k)

    def tocar(self, *a, **k):
        try:
            self._b.tocar(*a, **k)
        except Exception:
            if not self._falhou():
                raise
            self._b.tocar(*a, **k)

    def preparar(self, frame):
        # Só quando o estilo tem áudio que vai tocar; abre a placa na thread principal, antes do Play.
        if not getattr(frame, 'audio_style', None) or getattr(frame, 'audio_mute', False):
            return
        if hasattr(self._b, 'preparar'):
            self._b.preparar()
            self._falhou()

    def _falhou(self):
        erro = getattr(self._b, 'erro', None)
        if not erro:
            return False
        self._b = TocadorDeAudio()
        if self._falar and not self._avisou:
            self._avisou = True
            self._falar("A saída de áudio escolhida não abriu. O áudio vai tocar pelo padrão do Windows.", imediato=True)
        return True

    def __getattr__(self, nome):
        return getattr(self._b, nome)


def instalar(config, falar=None):
    # Chamada na abertura do programa e sempre que as configurações mudam.
    atual = AS.tocador
    if not isinstance(atual, TocadorEscolhido):
        atual = TocadorEscolhido(falar)
        AS.tocador = atual
    atual.configurar(config)
    return atual


def pcm_de_teste():
    # Três toques curtos (1 kHz) em um segundo, para ouvir a saída escolhida.
    import math
    n = TAXA
    amostras = array.array('h', bytes(n * 4))
    for inicio in (0, TAXA // 3, 2 * TAXA // 3):
        for i in range(TAXA // 25):
            v = int(9000 * math.sin(2 * math.pi * 1000 * i / TAXA) * (1 - i / (TAXA // 25)))
            amostras[2 * (inicio + i)] = v
            amostras[2 * (inicio + i) + 1] = v
    return amostras.tobytes()
