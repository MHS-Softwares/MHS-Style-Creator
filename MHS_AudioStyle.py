import os
import sys
import math
import array
import wave
import ctypes
import threading
import wx
from MHS_Utils import falar
import MHS_AudioAndamento as Andamento

# --- AUDIO STYLE (.aus) ---
# Um Audio Style é um estilo comum (MIDI + CASM) com dois blocos a mais no
# fim do arquivo, no mesmo formato "etiqueta de 4 letras + tamanho de 4
# bytes" do CASM:
#
#   AASM  uma entrada (ASEG) por seção que tem áudio:
#           Adec  nome da seção ("Main A", "Fill In AA"...)
#           Atab  97 bytes, parecido com o Ctab do CASM - o que muda de uma
#                 seção pra outra é só o nome do áudio (50 bytes) que liga
#                 a seção ao ADSg de mesmo nome dentro do AFil
#           AMix  resolução (2 bytes) + eventos MIDI: compasso, volume, pan,
#                 expression, reverb e chorus da parte de áudio
#   AFil  um áudio (ADSg) por seção:
#           ANdc  nome do áudio (50 bytes)
#           AWav  "WAVE" + Afmt (igual ao "fmt " de um WAV, só que big
#                 endian) + Sfmt + Adat (PCM 16 bits estéreo 44100 Hz,
#                 little endian, sem compressão) + AInf
#           Sfmt  35 bytes de cabeçalho (andamento, compasso, número de
#                 compassos, total de frames) + SPnt + Sdec (nome da seção)
#           AInf  BPnt + OPnt + APnt + ATmp
#
# As tabelas de pontos dizem ao teclado ONDE cada coisa está dentro do áudio
# (posição em frames):
#   BPnt  o início de cada tempo, mais o fim do áudio
#   APnt  as fatias do áudio: onde cada uma começa (posição) e em que
#         momento do compasso ela toca (tempo, tick de 0 a 1919) - ao que
#         tudo indica, é por elas que o teclado estica o áudio
#   OPnt  ataques mais fortes (mesmo formato do APnt)
#   SPnt  um ponto por tempo (posição, índice, compasso, tempo, tick)
#
# Tudo isso foi levantado comparando dois Audio Styles de fábrica com um
# gerado pelo Yamaha Audio Phraser. O Audio Phraser grava três coisas
# diferentes da fábrica, e é por causa delas que a parte de áudio das
# viradas só toca se a virada entrar exatamente na virada do compasso:
#   - no Sfmt, o total de frames sai sempre 22050 (meio segundo), em vez do
#     tamanho de verdade do áudio;
#   - no SPnt, compasso e tempo saem sempre 4 e 4, em vez de contar;
#   - o OPnt sai vazio.
# Aqui as três saem como nos arquivos de fábrica, e um áudio que veio do
# Audio Phraser tem as tabelas refeitas ao salvar (ver _tabelas_validas).

TAXA = 44100
BYTES_POR_FRAME = 4
TICKS_POR_TEMPO = 1920
# Os pontos do APnt/OPnt dos arquivos de fábrica caem sempre de 16 em 16
# frames - é o passo da análise deles, e o nosso.
PASSO = 16
# Quantas fatias (pontos do APnt) cada tempo tem. Os arquivos de fábrica
# usam 4 (semicolcheia) nos estilos mais movimentados e 2 nos mais lentos.
# Testado no teclado com 4 e com 8 nas viradas, e também com fatias
# faltando (só onde havia ataque): não se ouviu diferença nenhuma entre os
# três - fica o padrão de fábrica.
FATIAS_POR_TEMPO = 4
FATIAS_POR_TEMPO_VIRADA = 4

# Quando duas seções têm exatamente o mesmo áudio (o mesmo WAV colocado
# nas duas), o áudio é gravado uma vez só e as duas seções apontam pra ele
# - o Atab liga a seção ao áudio pelo nome. Nenhum arquivo de fábrica
# examinado faz isso, mas foi testado no teclado: um arquivo com 3 Mains e
# 5 viradas dividindo 2 áudios carregou e tocou igual ao que tinha uma
# cópia por seção, com bem menos tamanho.
COMPARTILHAR_AUDIO_IGUAL = True

# Diferença de tamanho (em frames) que ainda conta como "o áudio já tem o
# tamanho da seção" - os de fábrica variam poucos frames entre si.
TOLERANCIA_FRAMES = 64

# Ordem em que as seções aparecem nos Audio Styles de fábrica.
ORDEM_FABRICA = [
    "Main A", "Fill In AA", "Intro A", "Ending A",
    "Main B", "Fill In BB", "Fill In BA", "Intro B", "Ending B",
    "Main C", "Fill In CC", "Intro C", "Ending C",
    "Main D", "Fill In DD",
]

AFMT = bytes.fromhex("00010002" "0000ac44" "0002b110" "0004" "0010")
ATAB_INICIO = b'\x00' + b' ' * 8 + b'\x29'
ATAB_FIM = bytes.fromhex(
    "010fff07ffffffff" "0000007f00" "0000007f00" "000000007f00" "000000007f00" "00000000000000")
# Andamento mínimo e máximo (em microssegundos por semínima) que vêm fixos
# em todo Sfmt: 500 BPM e 5 BPM.
SFMT_FAIXA_ANDAMENTO = bytes.fromhex("01d4c0" "b71b00")

VOLUME_PADRAO = 100
PAN_PADRAO = 64

# --- VOLUME E PAN DO ÁUDIO ---
# O volume (CC 7) e o pan (CC 10) da parte de áudio moram no AMix de cada seção, e o teclado os aplica
# sozinho ao tocar. O programa guarda um valor GERAL (frame.audio_volume / frame.audio_pan) e, se a seção
# tiver o seu, 'volume' / 'pan' dentro do próprio áudio (None ou ausente = vale o geral).
# No Play do programa o mesmo ajuste é aplicado ao PCM (o ganho é relativo ao padrão: volume 100 e pan 64
# tocam o WAV como ele é). "Aplicar nos arquivos" grava esse ganho dentro do WAV e volta o volume e o pan
# ao padrão - o WAV é PCM, então nada se perde além do arredondamento de 16 bits.


def ganho_do_volume(volume):
    return (max(0, min(127, int(volume))) / float(VOLUME_PADRAO)) ** 2


def ganhos_estereo(volume, pan):
    # (esquerdo, direito): o volume vale pros dois lados; o pan atenua só o lado oposto (balanço).
    g = ganho_do_volume(volume)
    p = max(-1.0, min(1.0, (int(pan) - PAN_PADRAO) / 63.0))
    return g * min(1.0, 1.0 - p), g * min(1.0, 1.0 + p)


def valores_da_secao(audio, volume_geral, pan_geral):
    v, p = audio.get('volume'), audio.get('pan')
    return (volume_geral if v is None else v), (pan_geral if p is None else p)


def neutro(volume, pan):
    return int(volume) == VOLUME_PADRAO and int(pan) == PAN_PADRAO


def pico_depois(pcm, volume, pan):
    # Maior amostra (valor absoluto) que sairia depois do ganho - passou de 32767, estoura.
    amostras = array.array('h')
    amostras.frombytes(pcm)
    if sys.byteorder == 'big':
        amostras.byteswap()
    pico = max(max(amostras), -min(amostras)) if len(amostras) else 0
    return pico * max(ganhos_estereo(volume, pan))


def aplicar_volume_e_pan(pcm, volume, pan):
    gl, gr = ganhos_estereo(volume, pan)
    if abs(gl - 1.0) < 1e-9 and abs(gr - 1.0) < 1e-9:
        return pcm
    try:
        import audioop  # só até o Python 3.12; depois cai no caminho lento abaixo
    except ImportError:
        audioop = None
    if audioop is not None and sys.byteorder == 'little':
        esquerdo = audioop.tostereo(audioop.tomono(pcm, 2, 1, 0), 2, gl, 0)
        direito = audioop.tostereo(audioop.tomono(pcm, 2, 0, 1), 2, 0, gr)
        return audioop.add(esquerdo, direito, 2)
    amostras = array.array('h')
    amostras.frombytes(pcm)
    if sys.byteorder == 'big':
        amostras.byteswap()
    for i in range(0, len(amostras) - 1, 2):
        amostras[i] = max(-32768, min(32767, int(amostras[i] * gl)))
        amostras[i + 1] = max(-32768, min(32767, int(amostras[i + 1] * gr)))
    if sys.byteorder == 'big':
        amostras.byteswap()
    return amostras.tobytes()


def aplicar_nos_arquivos(audio_style, volume_geral, pan_geral):
    # Grava o volume e o pan de cada seção dentro do PCM. Devolve (seções alteradas, seções que estouram).
    feitos, estouros = 0, 0
    vistos = set()
    for nome, audio in audio_style.items():
        if id(audio) in vistos:
            continue
        vistos.add(id(audio))
        volume, pan = valores_da_secao(audio, volume_geral, pan_geral)
        audio.pop('volume', None)
        audio.pop('pan', None)
        if neutro(volume, pan):
            continue
        if pico_depois(audio['pcm'], volume, pan) > 32767:
            estouros += 1
        audio['pcm'] = aplicar_volume_e_pan(audio['pcm'], volume, pan)
        for chave in ('_ajustado', '_pronto', '_tocavel', 'original'):
            audio.pop(chave, None)
        audio['original'] = None
        feitos += 1
    return feitos, estouros

# Como achar a seção certa pelo nome do arquivo WAV ("maina.wav",
# "Fill In AA.wav", "break.wav"...) - ver secao_pelo_nome_do_arquivo.
_APELIDOS = {
    "Intro A": ["introa", "intro1"], "Intro B": ["introb", "intro2"], "Intro C": ["introc", "intro3"],
    "Main A": ["maina", "main1"], "Main B": ["mainb", "main2"],
    "Main C": ["mainc", "main3"], "Main D": ["maind", "main4"],
    "Fill In AA": ["fillinaa", "fillaa", "fillina", "filla", "fill1"],
    "Fill In BB": ["fillinbb", "fillbb", "fillinb", "fillb", "fill2"],
    "Fill In CC": ["fillincc", "fillcc", "fillinc", "fillc", "fill3"],
    "Fill In DD": ["fillindd", "filldd", "fillind", "filld", "fill4"],
    "Fill In BA": ["fillinba", "fillba", "break", "breakfill"],
    "Ending A": ["endinga", "ending1"], "Ending B": ["endingb", "ending2"], "Ending C": ["endingc", "ending3"],
}


def _bloco(etiqueta, conteudo):
    return etiqueta + len(conteudo).to_bytes(4, 'big') + conteudo


def _percorrer(dados, inicio=0):
    # Anda pelos blocos "etiqueta + tamanho + conteúdo" a partir de `inicio`.
    # Para sem erro no primeiro bloco que não couber no que sobrou.
    i = inicio
    while i + 8 <= len(dados):
        tamanho = int.from_bytes(dados[i + 4:i + 8], 'big')
        if i + 8 + tamanho > len(dados):
            return
        yield dados[i:i + 4], dados[i + 8:i + 8 + tamanho]
        i += 8 + tamanho


def separar_audio(dados):
    # Tira os blocos AASM e AFil de dentro de um arquivo de estilo. Devolve
    # (arquivo sem o áudio, conteúdo do AASM, conteúdo do AFil) - os dois
    # últimos vazios se o arquivo não for um Audio Style.
    # O resto do programa procura o CASM com find()/finditer() no arquivo
    # inteiro; sem tirar o áudio antes, essa busca varreria dezenas de MB
    # de PCM (onde as letras "CSEG" podem aparecer por acaso).
    if b'AFil' not in dados and b'AASM' not in dados:
        return dados, b'', b''
    resto = bytearray()
    aasm = afil = b''
    i = 0
    while i + 8 <= len(dados):
        etiqueta = dados[i:i + 4]
        tamanho = int.from_bytes(dados[i + 4:i + 8], 'big')
        fim = i + 8 + tamanho
        if fim > len(dados) or not all(32 <= c < 127 for c in etiqueta):
            break
        if etiqueta == b'AASM':
            aasm = dados[i + 8:fim]
        elif etiqueta == b'AFil':
            afil = dados[i + 8:fim]
        else:
            resto += dados[i:fim]
        i = fim
    resto += dados[i:]
    return bytes(resto), aasm, afil


def ler_blocos_de_audio(aasm, afil):
    secoes, volume, _pan = ler_blocos_de_audio_completo(aasm, afil)
    return secoes, volume


def ler_blocos_de_audio_completo(aasm, afil):
    # Devolve ({nome da seção: áudio}, volume geral, pan geral). Cada áudio é um dict:
    #   'pcm'      PCM 16 bits estéreo 44100 Hz
    #   'origem'   texto que a tela mostra (de onde o áudio veio)
    #   'original' cabeçalho do Sfmt + SPnt + AInf como estavam no arquivo,
    #              pra regravar igual se continuarem servindo
    audios = {}
    for etiqueta, adsg in _percorrer(afil):
        if etiqueta != b'ADSg':
            continue
        partes = dict(_percorrer(adsg))
        awav = partes.get(b'AWav', b'')
        if awav[:4] != b'WAVE':
            continue
        wav = dict(_percorrer(awav, 4))
        sfmt = wav.get(b'Sfmt', b'')
        if wav.get(b'Afmt') != AFMT or b'Adat' not in wav or len(sfmt) < 35:
            continue
        dentro_sfmt = dict(_percorrer(sfmt, 35))
        nome = partes.get(b'ANdc', b'').split(b'\x00')[0]
        audios[nome] = {
            'pcm': wav[b'Adat'],
            'origem': "já estava no arquivo",
            'original': {'cabecalho': sfmt[:35], 'spnt': dentro_sfmt.get(b'SPnt', b''),
                         'ainf': wav.get(b'AInf', b'')},
        }
    secoes = {}
    volume = pan = None
    proprios = {}
    for etiqueta, aseg in _percorrer(aasm):
        if etiqueta != b'ASEG':
            continue
        partes = dict(_percorrer(aseg))
        nome_secao = partes.get(b'Adec', b'').decode('latin-1').strip()
        audio = audios.get(partes.get(b'Atab', b'')[10:60].split(b'\x00')[0])
        if not nome_secao or audio is None:
            continue
        secoes[nome_secao] = audio
        amix = partes.get(b'AMix', b'')
        v = p = None
        pos = amix.find(b'\xb0\x07')
        if pos != -1 and pos + 2 < len(amix):
            v = amix[pos + 2]
        pos = amix.find(b'\xb0\x0a')
        if pos != -1 and pos + 2 < len(amix):
            p = amix[pos + 2]
        proprios[nome_secao] = (v, p)
    # O geral é o valor que a maioria das seções tem (empate: o mais perto do padrão, que é onde quem mexe numa
    # seção costuma NÃO estar); as outras guardam o seu.
    def mais_comum(valores, padrao):
        valores = [x for x in valores if x is not None]
        if not valores:
            return padrao
        return max(valores, key=lambda x: (valores.count(x), -abs(x - padrao), -valores.index(x)))
    volume = mais_comum([v for v, _ in proprios.values()], VOLUME_PADRAO)
    pan = mais_comum([p for _, p in proprios.values()], PAN_PADRAO)
    # Seção cujo volume ou pan é diferente do geral guarda o seu. Se o áudio é dividido com outra seção, ganha
    # uma cópia do dicionário (o PCM continua sendo o mesmo objeto) pra cada uma ter o seu valor.
    for nome_secao, (v, p) in proprios.items():
        diferente_v = v is not None and v != volume
        diferente_p = p is not None and p != pan
        if not (diferente_v or diferente_p):
            continue
        audio = dict(secoes[nome_secao])
        if diferente_v:
            audio['volume'] = v
        if diferente_p:
            audio['pan'] = p
        secoes[nome_secao] = audio
    return secoes, volume, pan


def ler_audio_de_arquivo_aus(caminho):
    with open(caminho, 'rb') as f:
        dados = f.read()
    _, aasm, afil = separar_audio(dados)
    return ler_blocos_de_audio(aasm, afil)


def ler_audio_de_arquivo_aus_completo(caminho):
    with open(caminho, 'rb') as f:
        dados = f.read()
    _, aasm, afil = separar_audio(dados)
    return ler_blocos_de_audio_completo(aasm, afil)


def ler_wav(caminho):
    # Lê um WAV e devolve (PCM 16 bits estéreo 44100 Hz, lista de avisos
    # sobre o que precisou ser convertido). Levanta ValueError com uma
    # mensagem pronta pra falar se o arquivo não servir.
    try:
        with wave.open(caminho, 'rb') as w:
            canais, largura, taxa, n_frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            bruto = w.readframes(n_frames)
    except (wave.Error, EOFError) as e:
        raise ValueError("Este arquivo não é um WAV PCM que o programa consiga ler "
                         f"(use WAV de 16 ou 24 bits, sem compressão). Detalhe: {e}")
    if canais < 1 or largura not in (1, 2, 3, 4):
        raise ValueError("Formato de WAV não suportado.")
    avisos = []
    n_amostras = len(bruto) // largura
    if largura == 2:
        dados16 = bruto[:n_amostras * 2]
    else:
        # Fica só com os 2 bytes mais significativos de cada amostra (WAV é
        # little endian: são os dois últimos).
        saida = bytearray(n_amostras * 2)
        if largura == 1:
            saida[1::2] = bytes(b ^ 0x80 for b in bruto)  # 8 bits é sem sinal
        else:
            saida[0::2] = bruto[largura - 2::largura][:n_amostras]
            saida[1::2] = bruto[largura - 1::largura][:n_amostras]
        dados16 = bytes(saida)
        avisos.append(f"convertido de {largura * 8} para 16 bits")
    amostras = array.array('h')
    amostras.frombytes(dados16)
    if sys.byteorder == 'big':
        amostras.byteswap()
    n = len(amostras) // canais
    if canais == 1:
        esquerdo = direito = amostras
        avisos.append("mono duplicado nos dois lados")
    else:
        esquerdo, direito = amostras[0::canais][:n], amostras[1::canais][:n]
        if canais > 2:
            avisos.append(f"usados só os 2 primeiros de {canais} canais")
    if taxa != TAXA:
        esquerdo, direito = _reamostrar(esquerdo, taxa), _reamostrar(direito, taxa)
        avisos.append(f"convertido de {taxa} para {TAXA} Hz")
    estereo = array.array('h', bytes(len(esquerdo) * 4))
    estereo[0::2] = esquerdo
    estereo[1::2] = direito
    if sys.byteorder == 'big':
        estereo.byteswap()
    if not len(estereo):
        raise ValueError("Este WAV está vazio.")
    return estereo.tobytes(), avisos


def _reamostrar(amostras, taxa_origem):
    # Interpolação linear - simples, mas suficiente pra um WAV que não veio
    # em 44100 Hz (o ideal continua sendo renderizar já em 44100).
    n = len(amostras)
    if n < 2:
        return amostras
    total = int(n * TAXA / taxa_origem)
    passo = taxa_origem / TAXA
    saida = array.array('h', bytes(total * 2))
    ultimo = n - 1
    for i in range(total):
        x = i * passo
        j = int(x)
        if j >= ultimo:
            saida[i] = amostras[ultimo]
        else:
            a = amostras[j]
            saida[i] = int(a + (amostras[j + 1] - a) * (x - j))
    return saida


def secao_pelo_nome_do_arquivo(caminho, secoes_disponiveis):
    # "maina.wav", "Main A.wav", "Fill In AA.wav", "break.wav" -> nome da
    # seção, ou None. Compara só letras e números, sem maiúsculas.
    base = ''.join(c for c in os.path.splitext(os.path.basename(caminho))[0].lower() if c.isalnum())
    melhor, tamanho = None, 0
    for nome in secoes_disponiveis:
        chaves = [''.join(c for c in nome.lower() if c.isalnum())] + _APELIDOS.get(nome, [])
        for chave in chaves:
            # O nome pode ter mais coisa em volta ("baiao_maina_114bpm") -
            # entre duas seções que casam, ganha a de apelido mais comprido
            # ("fillinba" antes de "fillinb").
            if chave in base and len(chave) > tamanho:
                melhor, tamanho = nome, len(chave)
    return melhor


def unidade_de_tempo(numerador, denominador):
    # Devolve (quantas semínimas vale um "tempo" das tabelas, quantos tempos
    # cabem num compasso). O tempo é a semínima sempre que o compasso tiver
    # um número inteiro delas (4/4, 2/4, 3/4, 6/8 = 3 semínimas); senão
    # (7/8, 5/8) é a figura do próprio denominador.
    if (numerador * 4) % denominador == 0:
        return 1.0, (numerador * 4) // denominador
    return 4.0 / denominador, numerador


def frames_da_secao(seminimas, micros_por_seminima):
    return int(round(seminimas * micros_por_seminima * TAXA / 1000000.0))


def ajustar_tamanho(pcm, n_frames):
    # Corta ou completa com silêncio pra dar exatamente `n_frames`. Ao
    # cortar, os últimos 3 milissegundos descem até o silêncio pra não dar
    # estalo.
    atual = len(pcm) // BYTES_POR_FRAME
    if atual == n_frames:
        return pcm
    if atual < n_frames:
        return pcm + bytes((n_frames - atual) * BYTES_POR_FRAME)
    rampa = min(128, n_frames)
    corpo = pcm[:(n_frames - rampa) * BYTES_POR_FRAME]
    fim = array.array('h')
    fim.frombytes(pcm[(n_frames - rampa) * BYTES_POR_FRAME:n_frames * BYTES_POR_FRAME])
    if sys.byteorder == 'big':
        fim.byteswap()
    for i in range(rampa):
        ganho = (rampa - i) / rampa
        fim[i * 2] = int(fim[i * 2] * ganho)
        fim[i * 2 + 1] = int(fim[i * 2 + 1] * ganho)
    if sys.byteorder == 'big':
        fim.byteswap()
    return corpo + fim.tobytes()


def _envelope(pcm):
    # Pico (em valor absoluto) de cada janela de PASSO frames.
    amostras = array.array('h')
    amostras.frombytes(pcm)
    if sys.byteorder == 'big':
        amostras.byteswap()
    por_janela = PASSO * 2
    env = []
    for i in range(0, len(amostras) - por_janela + 1, por_janela):
        trecho = amostras[i:i + por_janela]
        alto, baixo = max(trecho), -min(trecho)
        env.append(alto if alto > baixo else baixo)
    return env


def _ataques(env, piso, distancia_minima):
    # Devolve [(força, janela)] dos ataques: trechos em que o volume sobe
    # bem acima da média dos ~23 ms anteriores. O ataque fica marcado na
    # janela em que a subida COMEÇA (é onde os arquivos de fábrica marcam:
    # um tiquinho antes do tempo, não no pico que vem depois), com a força
    # do ponto mais alto da subida. Entre dois ataques a menos de
    # `distancia_minima` janelas um do outro, fica o mais forte.
    janela_media = 64
    soma = 0
    candidatos = []
    inicio, forca = None, 0.0
    for k, valor in enumerate(env):
        subindo = False
        if k >= janela_media:
            media = soma / janela_media
            if valor > piso * 2 and valor > (media + piso) * 1.8:
                subindo = True
                if inicio is None:
                    inicio, forca = k, 0.0
                forca = max(forca, valor / (media + piso))
            soma -= env[k - janela_media]
        elif k == 0 and valor > piso * 2:
            candidatos.append((valor / piso, 0))
        if inicio is not None and (not subindo or k - inicio >= janela_media):
            candidatos.append((forca, inicio))
            inicio = None
        soma += valor
    if inicio is not None:
        candidatos.append((forca, inicio))
    candidatos.sort(reverse=True)
    ocupado = bytearray(len(env) + 1)
    aceitos = []
    d = max(1, int(distancia_minima))
    for forca, k in candidatos:
        if any(ocupado[max(0, k - d):k + d + 1]):
            continue
        ocupado[k] = 1
        aceitos.append((forca, k))
    return aceitos


def analisar(pcm, n_tempos, tempos_por_compasso, fatias_por_tempo=FATIAS_POR_TEMPO):
    # Gera as tabelas de pontos de um áudio que dura exatamente `n_tempos`
    # tempos. Devolve (conteúdo do SPnt, conteúdo do AInf).
    n_frames = len(pcm) // BYTES_POR_FRAME
    inicio_tempo = [int(round(i * n_frames / n_tempos)) for i in range(n_tempos + 1)]
    tempo_em_janelas = n_frames / n_tempos / PASSO

    def ponto(posicao):
        # (posição, tempo, tick dentro do tempo)
        posicao = max(0, min(n_frames - 1, int(posicao)))
        t = min(n_tempos - 1, int(posicao * n_tempos // n_frames))
        while t > 0 and posicao < inicio_tempo[t]:
            t -= 1
        while t < n_tempos - 1 and posicao >= inicio_tempo[t + 1]:
            t += 1
        duracao = max(1, inicio_tempo[t + 1] - inicio_tempo[t])
        tick = int(round((posicao - inicio_tempo[t]) * TICKS_POR_TEMPO / duracao))
        return posicao, t, max(0, min(TICKS_POR_TEMPO - 1, tick))

    def tabela(pontos):
        return b''.join(p.to_bytes(4, 'big') + t.to_bytes(2, 'big') + k.to_bytes(2, 'big') for p, t, k in pontos)

    env = _envelope(pcm)
    pico = max(env) if env else 0
    piso = max(1.0, pico * 0.02)
    ataques = _ataques(env, piso, tempo_em_janelas / 8) if pico > 64 else []
    acumulado = [0]
    for valor in env:
        acumulado.append(acumulado[-1] + valor)

    bpnt = b''.join(p.to_bytes(4, 'big') + i.to_bytes(2, 'big') + b'\x00\x00' for i, p in enumerate(inicio_tempo))

    # APnt: uma fatia por subdivisão do tempo, sempre, como nos arquivos de
    # fábrica mais movimentados - começando no ataque mais forte que houver
    # perto da subdivisão, ou nela mesma se não houver ataque.
    por_janela = {k: forca for forca, k in ataques}
    janelas_com_ataque = sorted(por_janela)
    celula = tempo_em_janelas / fatias_por_tempo
    apnt = []
    indice = 0
    for j in range(n_tempos * fatias_por_tempo):
        de, ate = max(0, int(round((j - 0.5) * celula))), min(len(env), int(round((j + 0.5) * celula)))
        while indice < len(janelas_com_ataque) and janelas_com_ataque[indice] < de:
            indice += 1
        melhor, i = None, indice
        while i < len(janelas_com_ataque) and janelas_com_ataque[i] < ate:
            k = janelas_com_ataque[i]
            if melhor is None or por_janela[k] > por_janela[melhor]:
                melhor = k
            i += 1
        if melhor is not None:
            apnt.append(ponto(melhor * PASSO))
        else:
            apnt.append(ponto(round(j * celula * PASSO)))

    # OPnt: o começo do áudio e os ataques mais marcados, sem dois a menos
    # de um terço de tempo um do outro.
    fortes = sorted((forca, k) for forca, k in ataques if forca >= 2.5)
    fortes.reverse()
    escolhidos = [0]
    for forca, k in fortes:
        if all(abs(k - outro) >= tempo_em_janelas / 3 for outro in escolhidos):
            escolhidos.append(k)
    opnt = [ponto(k * PASSO) for k in sorted(escolhidos)]

    # SPnt: em cada tempo, o trecho de ~12 ms mais quieto; se o tempo for
    # todo silêncio (ou curto demais pra procurar), o meio dele.
    largura = 32
    spnt = b''
    for t in range(n_tempos):
        de, ate = inicio_tempo[t] // PASSO, min(len(env), inicio_tempo[t + 1] // PASSO)
        meio = (inicio_tempo[t] + inicio_tempo[t + 1]) // 2
        posicao = meio
        if ate - de > largura * 2 and max(env[de:ate]) > piso:
            menor, onde = None, de
            for k in range(de, ate - largura):
                soma = acumulado[k + largura] - acumulado[k]
                if menor is None or soma < menor:
                    menor, onde = soma, k
            posicao = (onde + largura // 2) * PASSO
        p, _, tick = ponto(posicao)
        if posicao == meio:
            tick = TICKS_POR_TEMPO // 2
        spnt += (p.to_bytes(4, 'big') + t.to_bytes(2, 'big')
                 + bytes([min(255, t // tempos_por_compasso), t % tempos_por_compasso]) + tick.to_bytes(2, 'big'))

    ainf = _bloco(b'BPnt', bpnt) + _bloco(b'OPnt', tabela(opnt)) + _bloco(b'APnt', tabela(apnt)) + _bloco(b'ATmp', b'')
    return spnt, ainf


def _tabelas_validas(original, n_frames, n_tempos, tempos_por_compasso):
    # As tabelas que vieram do arquivo ainda servem pra este áudio, nesta
    # seção? Não servem se a seção mudou de tamanho ou de compasso, nem se
    # têm os defeitos do Audio Phraser (ver o topo do arquivo).
    if not original:
        return False
    cabecalho, spnt, ainf = original['cabecalho'], original['spnt'], original['ainf']
    if int.from_bytes(cabecalho[27:31], 'big') != n_frames or int.from_bytes(cabecalho[31:35], 'big') != n_frames:
        return False
    if len(spnt) != n_tempos * 10:
        return False
    for t in range(n_tempos):
        if spnt[t * 10 + 6] != min(255, t // tempos_por_compasso) or spnt[t * 10 + 7] != t % tempos_por_compasso:
            return False
    partes = dict(_percorrer(ainf))
    if len(partes.get(b'BPnt', b'')) != (n_tempos + 1) * 8 or not partes.get(b'OPnt'):
        return False
    return True


def pcm_no_tamanho(audio, seminimas, micros_por_seminima):
    # O PCM de um áudio já no tamanho exato da seção (cortado ou completado
    # com silêncio, se precisar). Guardado dentro do próprio `audio`, pra
    # servir tanto ao Salvar quanto ao Play sem refazer o ajuste.
    alvo = frames_da_secao(seminimas, micros_por_seminima)
    pronto = audio.get('_ajustado')
    if pronto and pronto[0] == alvo:
        return pronto[1]
    pcm = audio['pcm']
    n_frames = len(pcm) // BYTES_POR_FRAME
    if abs(n_frames - alvo) > TOLERANCIA_FRAMES:
        pcm = ajustar_tamanho(pcm, alvo)
    elif len(pcm) != n_frames * BYTES_POR_FRAME:
        pcm = pcm[:n_frames * BYTES_POR_FRAME]
    audio['_ajustado'] = (alvo, pcm)
    return pcm


def preparar_secao(audio, seminimas, numerador, denominador, micros_por_seminima, fatias_por_tempo=FATIAS_POR_TEMPO):
    # Deixa o áudio de uma seção pronto pra gravar: no tamanho da seção e
    # com as tabelas de pontos. Devolve (pcm, n_tempos, tempos_por_compasso,
    # spnt, ainf). O resultado fica guardado dentro do próprio `audio` -
    # analisar um áudio leva tempo, e sem isso todo Ctrl+S refaria a conta
    # de todas as seções.
    seminimas_por_tempo, tempos_por_compasso = unidade_de_tempo(numerador, denominador)
    n_tempos = max(1, int(round(seminimas / seminimas_por_tempo)))
    alvo = frames_da_secao(seminimas, micros_por_seminima)
    chave = (n_tempos, tempos_por_compasso, alvo, fatias_por_tempo)
    pronto = audio.get('_pronto')
    if pronto and pronto[0] == chave:
        return pronto[1]
    pcm = pcm_no_tamanho(audio, seminimas, micros_por_seminima)
    n_frames = len(pcm) // BYTES_POR_FRAME
    original = audio.get('original')
    if pcm is audio['pcm'] and _tabelas_validas(original, n_frames, n_tempos, tempos_por_compasso):
        spnt, ainf = original['spnt'], original['ainf']
    else:
        spnt, ainf = analisar(pcm, n_tempos, tempos_por_compasso, fatias_por_tempo)
    resultado = (pcm, n_tempos, tempos_por_compasso, spnt, ainf)
    audio['_pronto'] = (chave, resultado)
    return resultado


def _nome_do_audio(nome_estilo, nome_secao):
    limpo = ''.join(c if (c.isascii() and (c.isalnum() or c in ' _-')) else '_' for c in nome_estilo)[:24].strip()
    return f"Au_{limpo or 'Style'}_{nome_secao}".encode('ascii', errors='replace')[:49]


def montar_blocos(audios, secoes, ppq, micros_por_seminima, volume, nome_estilo, pan=PAN_PADRAO):
    # audios: {nome da seção: áudio}; secoes: {nome da seção: (duração em
    # ticks, numerador, denominador)} - só o que existe de verdade no
    # estilo. Áudio de seção que não existe mais não é gravado. Devolve os
    # blocos AASM + AFil prontos pra irem pro fim do arquivo (vazio se não
    # sobrar nenhum áudio).
    por_chave = {nome.strip().lower(): nome for nome in audios}
    ordem = [por_chave[n.lower()] for n in ORDEM_FABRICA if n.lower() in por_chave]
    ordem += [nome for nome in audios if nome not in ordem]
    info_por_chave = {nome.strip().lower(): info for nome, info in secoes.items()}
    aasm = bytearray()
    afil = bytearray()
    ja_gravados = {}
    volume = max(0, min(127, int(volume)))
    pan = max(0, min(127, int(pan)))
    for nome in ordem:
        info = info_por_chave.get(nome.strip().lower())
        if not info:
            continue
        ticks, numerador, denominador = info
        if not ticks or ticks <= 0:
            continue
        seminimas = ticks / ppq
        eh_virada = nome.strip().lower().startswith("fill")
        pcm, n_tempos, tempos_por_compasso, spnt, ainf = preparar_secao(
            audios[nome], seminimas, numerador, denominador, micros_por_seminima,
            FATIAS_POR_TEMPO_VIRADA if eh_virada else FATIAS_POR_TEMPO)
        n_frames = len(pcm) // BYTES_POR_FRAME
        nome_bytes = nome.encode('latin-1', errors='replace')
        compasso = bytes([numerador, max(0, denominador.bit_length() - 1), 0x18, 0x08])
        identidade = (pcm, n_tempos, tempos_por_compasso, compasso, eh_virada)
        nome_audio = ja_gravados.get(identidade) if COMPARTILHAR_AUDIO_IGUAL else None
        repetido = nome_audio is not None
        if not repetido:
            nome_audio = _nome_do_audio(nome_estilo, nome).ljust(50, b'\x00')
            ja_gravados[identidade] = nome_audio
        n_compassos = max(1, int(round(n_tempos / tempos_por_compasso)))
        # Como nos arquivos de fábrica, o andamento gravado é o que o
        # próprio áudio tem (tamanho dividido pelo número de semínimas).
        andamento = max(1, min(0xFFFFFF, int(round(n_frames / seminimas / TAXA * 1000000.0))))

        vol_secao, pan_secao = valores_da_secao(audios[nome], volume, pan)
        vol_secao, pan_secao = max(0, min(127, int(vol_secao))), max(0, min(127, int(pan_secao)))
        amix = (min(0xFFFF, ppq).to_bytes(2, 'big') + b'\x00\xff\x58\x04' + compasso
                + b'\x00\xb0\x07' + bytes([vol_secao]) + b'\x00\xb0\x0a' + bytes([pan_secao]) + b'\x00\xb0\x0b\x7f'
                + b'\x00\xb0\x5b\x00' + b'\x00\xb0\x5d\x00')
        aasm += _bloco(b'ASEG', _bloco(b'Adec', nome_bytes)
                       + _bloco(b'Atab', ATAB_INICIO + nome_audio + ATAB_FIM) + _bloco(b'AMix', amix))

        if repetido:
            continue
        cabecalho = (b'\x00\x01' + andamento.to_bytes(3, 'big') + SFMT_FAIXA_ANDAMENTO + compasso
                     + b'\x00\x01' + min(0xFFFF, n_compassos).to_bytes(2, 'big') + bytes(8)
                     + n_frames.to_bytes(4, 'big') * 2)
        sfmt = cabecalho + _bloco(b'SPnt', spnt) + _bloco(b'Sdec', nome_bytes)
        awav = b'WAVE' + _bloco(b'Afmt', AFMT) + _bloco(b'Sfmt', sfmt) + _bloco(b'Adat', pcm) + _bloco(b'AInf', ainf)
        afil += _bloco(b'ADSg', _bloco(b'ANdc', nome_audio) + _bloco(b'AWav', awav))
    if not afil:
        return b''
    return _bloco(b'AASM', bytes(aasm)) + _bloco(b'AFil', bytes(afil))


class _WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", ctypes.c_uint16), ("nChannels", ctypes.c_uint16),
                ("nSamplesPerSec", ctypes.c_uint32), ("nAvgBytesPerSec", ctypes.c_uint32),
                ("nBlockAlign", ctypes.c_uint16), ("wBitsPerSample", ctypes.c_uint16), ("cbSize", ctypes.c_uint16)]


class _WAVEHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", ctypes.c_uint32),
                ("dwBytesRecorded", ctypes.c_uint32), ("dwUser", ctypes.c_size_t),
                ("dwFlags", ctypes.c_uint32), ("dwLoops", ctypes.c_uint32),
                ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]


class _MMTIME(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wType", ctypes.c_uint32), ("valor", ctypes.c_uint32), ("resto", ctypes.c_uint32)]


class TocadorDeAudio:
    # Toca o áudio da seção junto com o Play do programa, pela saída de som
    # padrão do Windows (winmm/waveOut via ctypes - sem biblioteca nova).
    #
    # O áudio entra em loop sozinho, emendado pela própria placa de som (sem
    # buraco na virada), e o motor MIDI chama iniciar_passagem() no começo
    # de cada passagem pela seção. Os dois andam em relógios diferentes (o
    # MIDI no do computador, o áudio no da placa), então a cada volta do
    # loop o tocador confere onde o áudio está. A placa sempre responde com
    # algum atraso fixo (uns 15 a 40 ms), então o que conta não é a
    # distância até o começo do loop, e sim o quanto essa distância mudou
    # desde a primeira volta: passou de 20 milissegundos, recomeça dali.
    DESVIO_MAXIMO = TAXA * 20 // 1000

    def __init__(self):
        self._trava = threading.Lock()
        self._winmm = None
        self._saida = None
        self._cabecalhos = []
        self._pcm = None
        self._frames_antes_do_loop = 0
        self._frames_do_loop = 0
        self._desvio_de_base = None

    def _api(self):
        if self._winmm is None:
            w = ctypes.WinDLL("winmm")
            ponteiro, inteiro = ctypes.c_void_p, ctypes.c_uint32
            w.waveOutOpen.argtypes = [ctypes.POINTER(ponteiro), inteiro, ctypes.POINTER(_WAVEFORMATEX),
                                      ctypes.c_size_t, ctypes.c_size_t, inteiro]
            for nome in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
                getattr(w, nome).argtypes = [ponteiro, ctypes.POINTER(_WAVEHDR), inteiro]
            w.waveOutReset.argtypes = [ponteiro]
            w.waveOutClose.argtypes = [ponteiro]
            w.waveOutGetPosition.argtypes = [ponteiro, ctypes.POINTER(_MMTIME), inteiro]
            self._winmm = w
        return self._winmm

    def _soltar_cabecalhos(self):
        for cabecalho, _dados in self._cabecalhos:
            self._winmm.waveOutUnprepareHeader(self._saida, ctypes.byref(cabecalho), ctypes.sizeof(_WAVEHDR))
        self._cabecalhos = []

    def _enfileirar(self, pcm, em_loop):
        dados = ctypes.create_string_buffer(pcm, len(pcm))
        cabecalho = _WAVEHDR()
        cabecalho.lpData = ctypes.cast(dados, ctypes.c_void_p)
        cabecalho.dwBufferLength = len(pcm)
        if em_loop:
            cabecalho.dwFlags = 0x4 | 0x8  # WHDR_BEGINLOOP | WHDR_ENDLOOP
            cabecalho.dwLoops = 0x7FFFFFFF
        self._winmm.waveOutPrepareHeader(self._saida, ctypes.byref(cabecalho), ctypes.sizeof(_WAVEHDR))
        # O Windows lê direto dessa memória enquanto toca - `dados` e
        # `cabecalho` precisam continuar vivos até o _soltar_cabecalhos.
        self._cabecalhos.append((cabecalho, dados))
        self._winmm.waveOutWrite(self._saida, ctypes.byref(cabecalho), ctypes.sizeof(_WAVEHDR))

    def tocar(self, pcm, frame_inicial=0):
        # Começa a tocar `pcm` em loop, a partir de `frame_inicial`.
        with self._trava:
            self._tocar(pcm, frame_inicial)

    def _tocar(self, pcm, frame_inicial):
        w = self._api()
        if self._saida is None:
            formato = _WAVEFORMATEX(1, 2, TAXA, TAXA * BYTES_POR_FRAME, BYTES_POR_FRAME, 16, 0)
            saida = ctypes.c_void_p()
            if w.waveOutOpen(ctypes.byref(saida), 0xFFFFFFFF, ctypes.byref(formato), 0, 0, 0) != 0:
                return
            self._saida = saida
        else:
            w.waveOutReset(self._saida)
            self._soltar_cabecalhos()
        total = len(pcm) // BYTES_POR_FRAME
        frame_inicial = max(0, min(total - 1, frame_inicial))
        self._pcm = pcm
        self._desvio_de_base = None
        self._frames_do_loop = total
        self._frames_antes_do_loop = total - frame_inicial if frame_inicial else 0
        if frame_inicial:
            # Primeiro o resto da passagem atual, uma vez só; o loop
            # inteiro vem emendado logo atrás.
            self._enfileirar(pcm[frame_inicial * BYTES_POR_FRAME:], False)
        self._enfileirar(pcm, True)

    def parar(self):
        with self._trava:
            self._parar()

    def _parar(self):
        if self._saida is None:
            return
        self._winmm.waveOutReset(self._saida)
        self._soltar_cabecalhos()
        self._winmm.waveOutClose(self._saida)
        self._saida = None
        self._pcm = None

    def _desvio(self):
        # A quantos frames o áudio está do começo do loop (negativo = ainda
        # não chegou). None se não der pra saber.
        tempo = _MMTIME(2, 0, 0)  # TIME_SAMPLES
        if self._winmm.waveOutGetPosition(self._saida, ctypes.byref(tempo), ctypes.sizeof(_MMTIME)) != 0:
            return None
        if tempo.wType == 4:  # TIME_BYTES
            tocados = tempo.valor // BYTES_POR_FRAME
        elif tempo.wType == 2:
            tocados = tempo.valor
        else:
            return None
        desvio = (tocados - self._frames_antes_do_loop) % self._frames_do_loop
        if desvio > self._frames_do_loop // 2:
            desvio -= self._frames_do_loop
        return desvio

    def iniciar_passagem(self, frame, idx_secao, tick, repeticao):
        # Chamado pelo motor MIDI (na thread dele) logo antes de cada
        # passagem pela seção começar a contar. `tick` é de onde a passagem
        # parte dentro da seção; `repeticao` diz que é a mesma seção
        # voltando ao início do loop sozinha. Nunca deixa um erro daqui
        # derrubar o Play.
        try:
            with self._trava:
                pcm = self._pcm_da_secao(frame, idx_secao)
                if pcm is None:
                    self._parar()
                    return
                if repeticao and tick == 0 and self._saida is not None and self._pcm is pcm:
                    desvio = self._desvio()
                    if desvio is not None:
                        if self._desvio_de_base is None:
                            self._desvio_de_base = desvio
                        if abs(desvio - self._desvio_de_base) <= self.DESVIO_MAXIMO:
                            return
                ppq = frame.current_midi_data.ticks_per_beat
                total = len(pcm) // BYTES_POR_FRAME
                inicial = int(round(tick / ppq * frame.current_tempo * TAXA / 1000000.0))
                # "Adiantar o áudio": compensa o atraso da placa de som
                # começando o áudio um pouco à frente.
                inicial += int(frame.config.get("audio_adiantar_ms", 0)) * TAXA // 1000
                self._tocar(pcm, inicial % total)
        except Exception:
            pass

    def _pcm_da_secao(self, frame, idx_secao):
        # Mute/Solo do canal "Áudio" da lista de canais (ver
        # _tem_linha_audio em MHS_MainFrame): mutado, ou com algum canal
        # MIDI em Solo sem o áudio em Solo também, não toca.
        if getattr(frame, 'audio_mute', False):
            return None
        if any(c['Solo'] for c in frame.canais) and not getattr(frame, 'audio_solo', False):
            return None
        audios = getattr(frame, 'audio_style', None)
        secoes = getattr(frame, 'sections_info', None)
        if not audios or not secoes or not frame.current_midi_data or not (0 <= idx_secao < len(secoes)):
            return None
        nome = secoes[idx_secao].get('name', '')
        chave = nome.strip().lower()
        audio = next((a for n, a in audios.items() if n.strip().lower() == chave), None)
        info = frame.secoes_para_audio_style(nome).get(nome)
        if audio is None or not info:
            return None
        base = pcm_no_tamanho(audio, info[0] / frame.current_midi_data.ticks_per_beat, frame.current_tempo)
        volume, pan = valores_da_secao(audio, getattr(frame, 'audio_volume', VOLUME_PADRAO), getattr(frame, 'audio_pan', PAN_PADRAO))
        if neutro(volume, pan):
            return base
        # Guardado no próprio áudio: o mesmo objeto a cada volta do loop (o tocador confere isso pra não
        # recomeçar o áudio à toa) e a conta só é refeita quando o volume ou o pan mudam.
        chave = (volume, pan, id(base))
        pronto = audio.get('_tocavel')
        if pronto and pronto[0] == chave:
            return pronto[1]
        tocavel = aplicar_volume_e_pan(base, volume, pan)
        audio['_tocavel'] = (chave, tocavel)
        return tocavel


tocador = TocadorDeAudio()


def descrever_pan(pan):
    pan = int(pan)
    if pan == PAN_PADRAO:
        return "centro"
    return f"{PAN_PADRAO - pan} para a esquerda" if pan < PAN_PADRAO else f"{pan - PAN_PADRAO} para a direita"


class AudioSecaoDialog(wx.Dialog):
    # Volume e pan do áudio de UMA seção (o AMix dela). Marcando "usar o geral", a seção volta a seguir o
    # volume e o pan do estilo todo.
    def __init__(self, parent, nome, volume, pan, usa_geral):
        super().__init__(parent, title=f"Volume e pan do áudio - {nome}")
        v = wx.BoxSizer(wx.VERTICAL)
        self.chk_geral = wx.CheckBox(self, label="&Usar o volume e o pan gerais do estilo")
        self.chk_geral.SetValue(usa_geral)
        v.Add(self.chk_geral, 0, wx.ALL, 10)
        v.Add(wx.StaticText(self, label="&Volume (0 a 127, 100 é o padrão):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.sp_volume = wx.SpinCtrl(self, min=0, max=127, initial=int(volume), name="Volume desta seção")
        v.Add(self.sp_volume, 0, wx.ALL, 10)
        v.Add(wx.StaticText(self, label="&Pan (0 a 127, 64 é o centro):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.sp_pan = wx.SpinCtrl(self, min=0, max=127, initial=int(pan), name="Pan desta seção")
        v.Add(self.sp_pan, 0, wx.ALL, 10)
        v.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizerAndFit(v)
        self.chk_geral.Bind(wx.EVT_CHECKBOX, self._atualizar)
        self._atualizar(None)
        wx.CallLater(100, self.chk_geral.SetFocus)

    def _atualizar(self, event):
        livre = not self.chk_geral.GetValue()
        self.sp_volume.Enable(livre)
        self.sp_pan.Enable(livre)

    def valores(self):
        if self.chk_geral.GetValue():
            return None, None
        return self.sp_volume.GetValue(), self.sp_pan.GetValue()


def editar_volume_da_secao(frame, nome, parent=None):
    # Abre o diálogo da seção `nome` e grava o resultado no áudio dela (entra no Ctrl+Z). True se mudou.
    chave = next((n for n in frame.audio_style if n.strip().lower() == nome.strip().lower()), None)
    if chave is None:
        falar(f"A seção {nome} não tem áudio.", imediato=True)
        return False
    audio = frame.audio_style[chave]
    geral_v, geral_p = getattr(frame, 'audio_volume', VOLUME_PADRAO), getattr(frame, 'audio_pan', PAN_PADRAO)
    v, p = valores_da_secao(audio, geral_v, geral_p)
    usa_geral = audio.get('volume') is None and audio.get('pan') is None
    dlg = AudioSecaoDialog(parent or frame, chave, v, p, usa_geral)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return False
        novo_v, novo_p = dlg.valores()
    finally:
        dlg.Destroy()
    if (novo_v, novo_p) == (audio.get('volume'), audio.get('pan')):
        return False
    frame.save_state(f"Volume e Pan do Áudio da Seção {chave}")
    copia = dict(audio)          # o dicionário pode estar dividido com outra seção que usa o mesmo áudio
    for campo, valor in (('volume', novo_v), ('pan', novo_p)):
        if valor is None:
            copia.pop(campo, None)
        else:
            copia[campo] = valor
    frame.audio_style[chave] = copia
    frame.dirty = True
    frame.atualizar_titulo()
    frame._reavaliar_audio_no_play()
    if novo_v is None:
        falar(f"Seção {chave}: o áudio segue o volume e o pan gerais.", imediato=True)
    else:
        falar(f"Seção {chave}: volume {novo_v}, pan {novo_p}, {descrever_pan(novo_p)}.", imediato=True)
    return True


def gravar_ganho_nos_audios(frame, parent=None):
    # "Aplicar nos arquivos": grava o volume e o pan (gerais e das seções) dentro do PCM de cada seção e volta
    # tudo ao padrão (100 e 64). Pergunta antes; entra no Ctrl+Z. True se gravou.
    geral_v, geral_p = getattr(frame, 'audio_volume', VOLUME_PADRAO), getattr(frame, 'audio_pan', PAN_PADRAO)
    if not getattr(frame, 'audio_style', None):
        falar("O estilo não tem áudio.", imediato=True)
        return False
    alteraveis, estouram = [], []
    vistos = set()
    for nome, audio in frame.audio_style.items():
        if id(audio) in vistos:
            continue
        vistos.add(id(audio))
        v, p = valores_da_secao(audio, geral_v, geral_p)
        if neutro(v, p):
            continue
        alteraveis.append(nome)
        if pico_depois(audio['pcm'], v, p) > 32767:
            estouram.append(nome)
    if not alteraveis:
        falar("O volume e o pan estão no padrão, 100 e 64: não há nada para gravar nos áudios.", imediato=True)
        return False
    pergunta = (f"Gravar o volume e o pan dentro dos áudios de {len(alteraveis)} "
                f"{'seção' if len(alteraveis) == 1 else 'seções'}? Depois o volume volta para 100 e o pan para 64, e o "
                "som continua igual. Ctrl+Z desfaz.")
    if estouram:
        pergunta += f" Atenção: em {', '.join(estouram)} o volume maior vai estourar e achatar o som (distorção)."
    falar(pergunta, imediato=True)
    if wx.MessageBox(pergunta, "Áudio do Estilo - gravar volume e pan", wx.YES_NO | wx.ICON_QUESTION, parent or frame) != wx.YES:
        return False
    frame.save_state("Gravar Volume e Pan nos Áudios")
    feitos, estouros = aplicar_nos_arquivos(frame.audio_style, geral_v, geral_p)
    frame.audio_volume, frame.audio_pan = VOLUME_PADRAO, PAN_PADRAO
    frame.dirty = True
    frame.atualizar_titulo()
    try:
        frame.update_mixer_list()
    except Exception:
        pass
    frame._reavaliar_audio_no_play()
    falar(f"Volume e pan gravados dentro dos áudios de {feitos} {'seção' if feitos == 1 else 'seções'}. "
          "O volume voltou para 100 e o pan para 64." + (f" {estouros} com distorção." if estouros else ""), imediato=True)
    return True


def _segundos(valor):
    return f"{valor:.1f}".replace(".", ",")


class AudioStyleDialog(wx.Dialog):
    # Tela "Áudio do Estilo": uma linha por seção (as 15 do padrão Yamaha,
    # existam ou não no estilo), com o WAV que toca junto com ela. Colocar
    # um WAV numa seção que ainda não existe cria a seção, com os compassos
    # que o WAV tiver - é assim que se começa um Audio Style pelo áudio,
    # antes de ter qualquer parte MIDI. Tudo vale na hora (mexe direto em
    # frame.audio_style), vai pro arquivo no próximo Salvar e entra no
    # Ctrl+Z da tela principal (cada ação desta tela é um passo; o volume
    # e o "Adiantar" não entram).
    def __init__(self, frame):
        super().__init__(frame, title="Áudio do Estilo (Audio Style)", size=(680, 520))
        self.frame = frame
        self.secoes = frame.secoes_para_audio_style()
        self.nomes = [sec['name'] for sec in frame.sections_info] or list(self.secoes)
        self._tocando = None
        self._arquivo_previa = None

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label="&Seções (Enter adiciona ou troca o WAV, e cria a seção se ela não existir; Delete remove; Alt+P ouve; Espaço marca a caixa de várias seções, pra receberem o mesmo WAV):"),
                 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        # Caixas de marcar (o leitor de telas já fala "marcado"/"não
        # marcado" sozinho, igual nas outras telas do programa): com
        # alguma caixa marcada, Adicionar e Remover valem pra todas as
        # marcadas; sem nenhuma, valem pra linha em foco.
        self.lista = wx.CheckListBox(self, choices=[], name="Seções do estilo")
        vbox.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)

        linha1 = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_adicionar = wx.Button(self, label="&Adicionar ou trocar WAV...")
        self.btn_varios = wx.Button(self, label="Adicionar &vários WAVs pelo nome do arquivo...")
        self.btn_remover = wx.Button(self, label="&Remover áudio")
        for b in (self.btn_adicionar, self.btn_varios, self.btn_remover):
            linha1.Add(b, 0, wx.ALL, 5)
        vbox.Add(linha1, 0, wx.ALIGN_CENTER)

        linha2 = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ouvir = wx.Button(self, label="Ouvir ou &parar")
        self.btn_importar = wx.Button(self, label="&Importar áudio de um arquivo .aus...")
        self.btn_exportar = wx.Button(self, label="E&xportar áudio para WAV...")
        linha2.Add(self.btn_ouvir, 0, wx.ALL, 5)
        linha2.Add(self.btn_importar, 0, wx.ALL, 5)
        linha2.Add(self.btn_exportar, 0, wx.ALL, 5)
        linha2.Add(wx.StaticText(self, label="Vo&lume do áudio (0 a 127):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        self.sp_volume = wx.SpinCtrl(self, min=0, max=127, initial=int(getattr(frame, 'audio_volume', VOLUME_PADRAO)),
                                     name="Volume do áudio")
        linha2.Add(self.sp_volume, 0, wx.ALL, 5)
        linha2.Add(wx.StaticText(self, label="Pa&n do áudio (0 a 127, 64 é o centro):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        self.sp_pan = wx.SpinCtrl(self, min=0, max=127, initial=int(getattr(frame, 'audio_pan', PAN_PADRAO)), name="Pan do áudio")
        linha2.Add(self.sp_pan, 0, wx.ALL, 5)
        vbox.Add(linha2, 0, wx.ALIGN_CENTER)

        linha2b = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_secao_volume = wx.Button(self, label="Volume e pan da s&eção em foco...")
        self.btn_gravar_ganho = wx.Button(self, label="&Gravar o volume e o pan dentro dos áudios...")
        linha2b.Add(self.btn_secao_volume, 0, wx.ALL, 5)
        linha2b.Add(self.btn_gravar_ganho, 0, wx.ALL, 5)
        vbox.Add(linha2b, 0, wx.ALIGN_CENTER)

        linha3 = wx.BoxSizer(wx.HORIZONTAL)
        linha3.Add(wx.StaticText(self, label="A&diantar o áudio no Play (milissegundos):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        self.sp_adiantar = wx.SpinCtrl(self, min=-300, max=300, initial=int(frame.config.get("audio_adiantar_ms", 0)),
                                       name="Adiantar o áudio no Play, em milissegundos")
        linha3.Add(self.sp_adiantar, 0, wx.ALL, 5)
        self.btn_andamento = wx.Button(self, label="Descobrir o a&ndamento pelos áudios...")
        linha3.Add(self.btn_andamento, 0, wx.ALL, 5)
        vbox.Add(linha3, 0, wx.ALIGN_CENTER)

        self.btn_fechar = wx.Button(self, wx.ID_CANCEL, label="&Fechar")
        vbox.Add(self.btn_fechar, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(vbox)

        self.btn_adicionar.SetDefault()
        self.btn_adicionar.Bind(wx.EVT_BUTTON, self.OnAdicionar)
        self.btn_varios.Bind(wx.EVT_BUTTON, self.OnAdicionarVarios)
        self.btn_remover.Bind(wx.EVT_BUTTON, self.OnRemover)
        self.btn_ouvir.Bind(wx.EVT_BUTTON, self.OnOuvir)
        self.btn_importar.Bind(wx.EVT_BUTTON, self.OnImportar)
        self.btn_exportar.Bind(wx.EVT_BUTTON, self.OnExportar)
        self.btn_andamento.Bind(wx.EVT_BUTTON, self.OnDescobrirAndamento)
        self.btn_secao_volume.Bind(wx.EVT_BUTTON, self.OnVolumeDaSecao)
        self.btn_gravar_ganho.Bind(wx.EVT_BUTTON, self.OnGravarGanho)
        self.sp_volume.Bind(wx.EVT_SPINCTRL, self.OnVolume)
        self.sp_volume.Bind(wx.EVT_TEXT, self.OnVolume)
        self.sp_pan.Bind(wx.EVT_SPINCTRL, self.OnPan)
        self.sp_pan.Bind(wx.EVT_TEXT, self.OnPan)
        self.sp_adiantar.Bind(wx.EVT_SPINCTRL, self.OnAdiantar)
        self.sp_adiantar.Bind(wx.EVT_TEXT, self.OnAdiantar)
        self.lista.Bind(wx.EVT_KEY_DOWN, self.OnTeclaLista)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self.OnAdicionar)
        self.Bind(wx.EVT_CLOSE, self.OnFechar)
        self.btn_fechar.Bind(wx.EVT_BUTTON, self.OnFechar)

        self.lista.Set([self._linha(nome) for nome in self.nomes])
        if self.nomes:
            self.lista.SetSelection(0)
        com_audio = sum(1 for nome in self.nomes if self._audio(nome))
        orfaos = self._audios_sem_secao()
        bpm = f"{60000000.0 / frame.current_tempo:.1f}".replace(".", ",").replace(",0", "")
        fala = (f"Áudio do Estilo. {com_audio} de {len(self.nomes)} seções com áudio. "
                f"Andamento do estilo: {bpm} BPM, compasso {frame.beats_per_measure} por 4.")
        if orfaos:
            fala += (f" Atenção: o arquivo tem áudio para {len(orfaos)} seção(ões) que não existem neste estilo "
                     f"({', '.join(orfaos)}); esse áudio não será salvo.")
        falar(fala, imediato=True)
        wx.CallLater(150, self.lista.SetFocus)

    # --- dados ---
    def _chave(self, nome):
        # O nome guardado em frame.audio_style pode ter outra caixa/espaços
        # que o da seção (veio de dentro de um arquivo).
        alvo = nome.strip().lower()
        for existente in self.frame.audio_style:
            if existente.strip().lower() == alvo:
                return existente
        return None

    def _audio(self, nome):
        chave = self._chave(nome)
        return self.frame.audio_style.get(chave) if chave else None

    def _audios_sem_secao(self):
        existentes = {n.strip().lower() for n in self.secoes}
        return [n for n in self.frame.audio_style if n.strip().lower() not in existentes]

    def _duracao_da_secao(self, nome):
        ticks = self.secoes[nome][0]
        return ticks / self.frame.current_midi_data.ticks_per_beat * self.frame.current_tempo / 1000000.0

    def _compassos(self, nome):
        ticks, numerador, denominador = self.secoes[nome]
        por_compasso = self.frame.current_midi_data.ticks_per_beat * numerador * 4 / denominador
        n = ticks / por_compasso
        return f"{int(round(n))}" if abs(n - round(n)) < 0.01 else f"{n:.2f}".replace(".", ",")

    def _diferenca(self, nome, audio):
        # Texto sobre o áudio não ter o tamanho da seção ("" se tiver).
        dur_audio = len(audio['pcm']) / BYTES_POR_FRAME / TAXA
        dur_secao = self._duracao_da_secao(nome)
        if abs(dur_audio - dur_secao) <= 0.05:
            return ""
        if dur_audio > dur_secao:
            return f"mais longo que a seção: será cortado em {_segundos(dur_secao)} segundos ao salvar"
        return f"mais curto que a seção: o fim será completado com silêncio até {_segundos(dur_secao)} segundos ao salvar"

    def _recarregar_secoes(self):
        self.secoes = self.frame.secoes_para_audio_style()
        for nome in self.nomes:
            self._atualizar_linha(nome)

    def _compassos_do_audio(self, pcm, numerador, denominador):
        # Quantos compassos o áudio ocupa no andamento do estilo. Sobrando
        # mais que um tiquinho além de um número inteiro (o rabo de um
        # Ending, por exemplo), arredonda pra cima: melhor completar com
        # silêncio do que cortar.
        segundos_por_compasso = self.frame.current_tempo / 1000000.0 * numerador * 4 / denominador
        n = len(pcm) / BYTES_POR_FRAME / TAXA / segundos_por_compasso
        return max(1, int(round(n)) if abs(n - round(n)) <= 0.05 else int(math.ceil(n)))

    def _aviso_de_andamento(self, nome, pcm, numerador, denominador):
        # Um loop cortado certinho dá um número inteiro de compassos no
        # andamento certo. Se não dá, o mais provável é o andamento (ou o
        # compasso) do estilo não ser o do áudio. Ending fica de fora:
        # costuma ter um rabo de som de tamanho livre.
        if nome.lower().startswith("ending"):
            return ""
        segundos_por_compasso = self.frame.current_tempo / 1000000.0 * numerador * 4 / denominador
        n = len(pcm) / BYTES_POR_FRAME / TAXA / segundos_por_compasso
        if abs(n - round(n)) <= 0.05:
            return ""
        bpm = int(round(60000000.0 / self.frame.current_tempo))
        compassos = f"{n:.2f}".replace(".", ",")
        return (f". Atenção: em {bpm} BPM e compasso {numerador} por {denominador}, este áudio dá {compassos} "
                "compassos, que não é um número inteiro - confira o andamento do estilo")

    def _secao_tem_notas(self, nome):
        inicio = next((sec.get('start') for sec in self.frame.sections_info if sec['name'] == nome), None)
        if inicio is None:
            return False
        fim = inicio + self.secoes[nome][0]
        tick = 0
        for msg in self.frame.merged_track_cache:
            tick += msg.time
            if tick >= fim:
                break
            if tick >= inicio and msg.type == 'note_on' and msg.velocity > 0:
                return True
        return False

    def _encaixar_secao(self, nome, pcm):
        # Faz a seção ter o tamanho do áudio, quando isso não estraga nada:
        # cria a seção que ainda não existe, ou ajusta uma que existe mas
        # ainda não tem nenhuma nota. Seção que já tem notas fica como
        # está (a linha dela avisa da diferença). Devolve o que foi feito,
        # em texto ("" se nada).
        frame = self.frame
        tpq = frame.current_midi_data.ticks_per_beat
        if nome not in self.secoes:
            numerador, denominador = frame.beats_per_measure, 4
            n = self._compassos_do_audio(pcm, numerador, denominador)
            frame.criar_secao_nova(nome, n, frame.ticks_por_compasso(tpq, numerador, denominador), numerador, denominador)
            self._recarregar_secoes()
            return (f"seção criada com {n} {'compasso' if n == 1 else 'compassos'}"
                    + self._aviso_de_andamento(nome, pcm, numerador, denominador))
        ticks, numerador, denominador = self.secoes[nome]
        tpm = frame.ticks_por_compasso(tpq, numerador, denominador)
        atual = max(1, int(round(ticks / tpm)))
        n = self._compassos_do_audio(pcm, numerador, denominador)
        if n == atual or self._secao_tem_notas(nome):
            return ""
        secao = next(sec for sec in frame.sections_info if sec['name'] == nome)
        frame.apply_section_resize(secao, atual, n, tpm, tpm, numerador, denominador)
        self._recarregar_secoes()
        return (f"seção ajustada de {atual} para {n} {'compasso' if n == 1 else 'compassos'}"
                + self._aviso_de_andamento(nome, pcm, numerador, denominador))

    # --- andamento pelos áudios ---
    def _bpm_do_estilo(self):
        return 60000000.0 / self.frame.current_tempo

    def _fracao_encaixa(self, duracoes):
        # Quantas seções (fora os Endings, que têm rabo) dão compassos inteiros no andamento do estilo.
        segundos_por_compasso = self.frame.current_tempo / 1000000.0 * self.frame.beats_per_measure
        itens = [d for n, d in duracoes.items() if not n.lower().startswith("ending")]
        if not itens:
            return 1, 1
        bons = sum(1 for d in itens if abs(d / segundos_por_compasso - round(d / segundos_por_compasso)) <= 0.05)
        return bons, len(itens)

    def _texto_candidatas(self, candidatas, n_audios):
        melhor = candidatas[0]
        confianca = Andamento.confianca(candidatas, n_audios)
        texto = f"{Andamento.texto_bpm(melhor['bpm'])} BPM ({Andamento.descrever(melhor)})"
        if confianca != 'alta':
            outras = [f"{Andamento.texto_bpm(c['bpm'])} BPM" for c in candidatas[1:3]]
            texto = "Não tenho certeza, mas o mais provável é " + texto
            if outras:
                texto += ". Outras possibilidades: " + ", ".join(outras)
        return texto, confianca

    def _definir_andamento(self, bpm):
        # Troca o andamento do estilo (como Ctrl+"+"/Ctrl+"-", mas em qualquer valor) e refaz o tamanho das
        # seções que têm áudio e ainda não têm nota nenhuma, que dependem dele.
        import mido
        f = self.frame
        bpm = Andamento.arredondar_bpm(bpm)
        f.current_tempo = max(1, int(round(60000000.0 / bpm)))
        achou, abs_t = False, 0
        for msg in f.merged_track_cache:
            abs_t += msg.time
            if msg.type == 'set_tempo' and abs_t == 0:
                msg.tempo = f.current_tempo
                achou = True
        if not achou:
            f.merged_track_cache.insert(0, mido.MetaMessage('set_tempo', tempo=f.current_tempo, time=0))
        f.dirty = True
        f.atualizar_titulo()
        f.rebuild_sections_from_cache()
        self._recarregar_secoes()
        for nome in self.nomes:
            audio = self._audio(nome)
            if audio and nome in self.secoes:
                self._encaixar_secao(nome, audio['pcm'])
        self._recarregar_secoes()

    def _oferecer_andamento(self, duracoes):
        # Chamada antes de colocar WAVs: se as durações não fecham em compassos inteiros no andamento do estilo
        # mas fecham em outro, pergunta se ajusta. Devolve True se ajustou. (O chamador já fez o save_state.)
        if len(duracoes) == 0:
            return False
        bons, total = self._fracao_encaixa(duracoes)
        if bons == total:
            return False
        candidatas = Andamento.estimar_andamento(duracoes, self.frame.beats_per_measure, 4)
        if not candidatas or abs(candidatas[0]['bpm'] - self._bpm_do_estilo()) < 0.3:
            return False
        texto, confianca = self._texto_candidatas(candidatas, len(duracoes))
        pergunta = (f"Pelas durações dos áudios, o andamento parece ser {texto}. O estilo está em "
                    f"{Andamento.texto_bpm(self._bpm_do_estilo())} BPM. Ajustar o andamento do estilo para "
                    f"{Andamento.texto_bpm(candidatas[0]['bpm'])} BPM antes de adicionar?")
        falar(pergunta, imediato=True)
        if wx.MessageBox(pergunta, "Áudio do Estilo - andamento", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return False
        self._definir_andamento(candidatas[0]['bpm'])
        falar(f"Andamento do estilo ajustado para {Andamento.texto_bpm(candidatas[0]['bpm'])} BPM.", imediato=True)
        return True

    def OnDescobrirAndamento(self, event):
        duracoes = {nome: len(self._audio(nome)['pcm']) / BYTES_POR_FRAME / TAXA for nome in self.nomes if self._audio(nome)}
        if not duracoes:
            falar("Nenhuma seção tem áudio ainda. Adicione os WAVs e depois use esta opção.", imediato=True)
            return
        candidatas = Andamento.estimar_andamento(duracoes, self.frame.beats_per_measure, 4)
        if not candidatas:
            falar("Não consegui achar um andamento que feche com as durações destes áudios.", imediato=True)
            return
        texto, confianca = self._texto_candidatas(candidatas, len(duracoes))
        melhor = candidatas[0]['bpm']
        atual = self._bpm_do_estilo()
        if abs(melhor - atual) < 0.3:
            falar(f"O andamento do estilo, {Andamento.texto_bpm(atual)} BPM, já é o que as durações dos áudios indicam. {texto}.", imediato=True)
            return
        pergunta = (f"Pelas durações dos áudios, o andamento parece ser {texto}. O estilo está em "
                    f"{Andamento.texto_bpm(atual)} BPM. Ajustar o andamento do estilo para "
                    f"{Andamento.texto_bpm(melhor)} BPM?")
        falar(pergunta, imediato=True)
        if wx.MessageBox(pergunta, "Áudio do Estilo - andamento", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self.frame.save_state("Ajustar Andamento pelos Áudios")
        self._definir_andamento(melhor)
        falar(f"Andamento do estilo ajustado para {Andamento.texto_bpm(melhor)} BPM. As seções que ainda não tinham notas foram refeitas com o número de compassos dos áudios.", imediato=True)

    def _linha(self, nome):
        if nome not in self.secoes:
            return f"{nome}: a seção ainda não existe no estilo. Sem áudio."
        compassos = self._compassos(nome)
        texto = (f"{nome}: {compassos} {'compasso' if compassos == '1' else 'compassos'}, "
                 f"{_segundos(self._duracao_da_secao(nome))} segundos. ")
        audio = self._audio(nome)
        if not audio:
            return texto + "Sem áudio."
        texto += f"Áudio: {audio['origem']}, {_segundos(len(audio['pcm']) / BYTES_POR_FRAME / TAXA)} segundos"
        if audio.get('volume') is not None or audio.get('pan') is not None:
            v, p = valores_da_secao(audio, getattr(self.frame, 'audio_volume', VOLUME_PADRAO), getattr(self.frame, 'audio_pan', PAN_PADRAO))
            texto += f", volume {v} e pan {p} só desta seção"
        diferenca = self._diferenca(nome, audio)
        texto += f" ({diferenca})." if diferenca else "."
        # Limites que o Audio Phraser da Yamaha impõe (manual dele): 1
        # compasso nas viradas, 32 nas outras seções. Aqui é só aviso - o
        # arquivo é gravado do mesmo jeito.
        ticks, numerador, denominador = self.secoes[nome]
        compassos = ticks / (self.frame.current_midi_data.ticks_per_beat * numerador * 4 / denominador)
        limite = 1 if nome.lower().startswith("fill") else 32
        if compassos > limite + 0.01:
            texto += f" Atenção: o Audio Phraser só aceita até {limite} compasso(s) nesta seção; teste no teclado."
        return texto

    def _selecionada(self):
        # A linha em foco.
        i = self.lista.GetSelection()
        return self.nomes[i] if 0 <= i < len(self.nomes) else None

    def _selecionadas(self):
        # As seções de caixa marcada; sem nenhuma marcada, a linha em foco.
        marcadas = [self.nomes[i] for i in sorted(self.lista.GetCheckedItems()) if 0 <= i < len(self.nomes)]
        if marcadas:
            return marcadas
        em_foco = self._selecionada()
        return [em_foco] if em_foco else []

    def _desmarcar_todas(self):
        for i in self.lista.GetCheckedItems():
            self.lista.Check(i, False)

    def _atualizar_linha(self, nome):
        # Trocar o texto de uma linha pode tirar a marca e o foco dela no
        # Windows - devolve os dois.
        i = self.nomes.index(nome)
        marcada, em_foco = self.lista.IsChecked(i), self.lista.GetSelection() == i
        self.lista.SetString(i, self._linha(nome))
        self.lista.Check(i, marcada)
        if em_foco:
            self.lista.SetSelection(i)

    def _mexeu(self):
        self.frame.dirty = True
        self.frame.atualizar_titulo()

    def _guardar(self, nome, pcm, origem):
        antiga = self._chave(nome)
        if antiga:
            del self.frame.audio_style[antiga]
        self.frame.audio_style[nome] = {'pcm': pcm, 'origem': origem, 'original': None}
        self._atualizar_linha(nome)

    def _pasta_inicial(self):
        return self.frame.config.get("last_audio_dir") or self.frame.config.get("last_open_dir", "")

    def _lembrar_pasta(self, caminho):
        self.frame.config["last_audio_dir"] = os.path.dirname(caminho)
        self.frame.save_config()

    # --- ações ---
    def OnTeclaLista(self, event):
        tecla = event.GetKeyCode()
        if tecla == wx.WXK_DELETE:
            self.OnRemover(None)
        else:
            event.Skip()

    def OnAdicionar(self, event):
        # Com várias seções marcadas, o mesmo WAV vai pra todas elas.
        nomes = self._selecionadas()
        if not nomes:
            return
        self._parar()
        titulo = f"Escolha o WAV da seção {nomes[0]}" if len(nomes) == 1 else "Escolha o WAV para as seções selecionadas"
        with wx.FileDialog(self, titulo, defaultDir=self._pasta_inicial(),
                           wildcard="Áudio WAV (*.wav)|*.wav", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        self._lembrar_pasta(caminho)
        try:
            pcm, avisos = ler_wav(caminho)
        except (ValueError, OSError) as e:
            falar(str(e), imediato=True)
            wx.MessageBox(str(e), "Áudio do Estilo", wx.OK | wx.ICON_WARNING, self)
            return
        fala = ""
        self.frame.save_state("Adicionar Áudio")
        duracao = len(pcm) / BYTES_POR_FRAME / TAXA
        if self._oferecer_andamento({nome: duracao for nome in nomes}):
            fala += "Andamento ajustado. "
        for nome in nomes:
            feito = self._encaixar_secao(nome, pcm)
            self._guardar(nome, pcm, os.path.basename(caminho))
            fala += f"Áudio adicionado à seção {nome}."
            if feito:
                fala += f" {feito.capitalize()}."
            diferenca = self._diferenca(nome, self._audio(nome))
            if diferenca:
                fala += f" Atenção: o áudio é {diferenca}."
            fala += " "
        self._mexeu()
        self._desmarcar_todas()
        if avisos:
            fala += "; ".join(avisos).capitalize() + "."
        falar(fala.strip(), imediato=True)
        self.lista.SetFocus()

    def OnAdicionarVarios(self, event):
        self._parar()
        with wx.FileDialog(self, "Escolha os WAVs (o nome de cada arquivo diz a seção: maina, fill in aa, break, introa, endinga...)",
                           defaultDir=self._pasta_inicial(), wildcard="Áudio WAV (*.wav)|*.wav",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminhos = dlg.GetPaths()
        if not caminhos:
            return
        self._lembrar_pasta(caminhos[0])
        colocados, nomes_colocados, sem_secao, com_erro = [], [], [], []
        self.frame.save_state("Adicionar Vários Áudios")
        passos_antes = len(self.frame.undo_stack)
        lidos = []
        for caminho in caminhos:
            nome = secao_pelo_nome_do_arquivo(caminho, self.nomes)
            if not nome:
                sem_secao.append(os.path.basename(caminho))
                continue
            try:
                pcm, _ = ler_wav(caminho)
            except (ValueError, OSError):
                com_erro.append(os.path.basename(caminho))
                continue
            lidos.append((caminho, nome, pcm))
        # Antes de criar/ajustar seções: o andamento do estilo tem que ser o dos áudios, senão o número de
        # compassos de cada seção sai errado.
        if lidos:
            self._oferecer_andamento({nome: len(pcm) / BYTES_POR_FRAME / TAXA for _, nome, pcm in lidos})
        for caminho, nome, pcm in lidos:
            feito = self._encaixar_secao(nome, pcm)
            self._guardar(nome, pcm, os.path.basename(caminho))
            colocados.append(f"{nome} ({feito})" if feito else nome)
            nomes_colocados.append(nome)
        if colocados:
            self._mexeu()
        elif len(self.frame.undo_stack) == passos_antes:
            self.frame.undo_stack.pop()  # nada entrou: não deixa um passo vazio no Ctrl+Z
        partes = [f"{len(colocados)} áudio(s) adicionado(s)" + (f": {', '.join(colocados)}" if colocados else "") + "."]
        if sem_secao:
            partes.append(f"Não reconheci a seção pelo nome em: {', '.join(sem_secao)}.")
        if com_erro:
            partes.append(f"Não consegui ler: {', '.join(com_erro)}.")
        diferentes = [n for n in nomes_colocados if self._diferenca(n, self._audio(n))]
        if diferentes:
            partes.append(f"Com tamanho diferente da seção: {', '.join(diferentes)} - veja a linha de cada uma.")
        mensagem = " ".join(partes)
        falar(mensagem, imediato=True)
        wx.MessageBox(mensagem, "Áudio do Estilo", wx.OK | wx.ICON_INFORMATION, self)
        self.lista.SetFocus()

    def OnRemover(self, event):
        com_audio = [nome for nome in self._selecionadas() if self._chave(nome)]
        if not com_audio:
            falar("Esta seção não tem áudio." if len(self._selecionadas()) <= 1 else "Nenhuma seção marcada tem áudio.", imediato=True)
            return
        self._parar()
        self.frame.save_state("Remover Áudio")
        for nome in com_audio:
            del self.frame.audio_style[self._chave(nome)]
            self._atualizar_linha(nome)
        self._mexeu()
        self._desmarcar_todas()
        falar(f"Áudio removido de {', '.join(com_audio)}.", imediato=True)

    def OnImportar(self, event):
        self._parar()
        with wx.FileDialog(self, "Escolha o Audio Style de onde copiar o áudio", defaultDir=self._pasta_inicial(),
                           wildcard="Audio Style Yamaha (*.aus;*.sty)|*.aus;*.sty|Todos os arquivos (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        self._lembrar_pasta(caminho)
        try:
            audios, volume, pan = ler_audio_de_arquivo_aus_completo(caminho)
        except OSError as e:
            falar(f"Não consegui abrir o arquivo. {e}", imediato=True)
            return
        if not audios:
            mensagem = "Esse arquivo não tem parte de áudio."
            falar(mensagem, imediato=True)
            wx.MessageBox(mensagem, "Áudio do Estilo", wx.OK | wx.ICON_WARNING, self)
            return
        por_chave = {n.strip().lower(): n for n in self.nomes}
        colocados, fora, ajustadas = [], [], []
        self.frame.save_state("Importar Áudio")
        passos_antes = len(self.frame.undo_stack)
        for nome_no_arquivo, audio in audios.items():
            nome = por_chave.get(nome_no_arquivo.strip().lower())
            if not nome:
                fora.append(nome_no_arquivo)
                continue
            feito = self._encaixar_secao(nome, audio['pcm'])
            antiga = self._chave(nome)
            if antiga:
                del self.frame.audio_style[antiga]
            audio['origem'] = f"importado de {os.path.basename(caminho)}"
            self.frame.audio_style[nome] = audio
            self._atualizar_linha(nome)
            colocados.append(nome)
            if feito:
                ajustadas.append(f"{nome} ({feito})")
        if not colocados and len(self.frame.undo_stack) == passos_antes:
            self.frame.undo_stack.pop()
        if colocados:
            self.frame.audio_volume = volume
            self.frame.audio_pan = pan
            self.sp_volume.SetValue(volume)
            self.sp_pan.SetValue(pan)
            self._mexeu()
        mensagem = f"{len(colocados)} áudio(s) importado(s)."
        if ajustadas:
            mensagem += f" {', '.join(ajustadas)}."
        if fora:
            mensagem += f" Ficaram de fora, por não serem seções do padrão Yamaha: {', '.join(fora)}."
        diferentes = [n for n in colocados if self._diferenca(n, self._audio(n))]
        if diferentes:
            mensagem += f" Com tamanho diferente da seção: {', '.join(diferentes)} - veja a linha de cada uma."
        falar(mensagem, imediato=True)
        wx.MessageBox(mensagem, "Áudio do Estilo", wx.OK | wx.ICON_INFORMATION, self)
        self.lista.SetFocus()

    def OnExportar(self, event):
        # Grava um WAV por seção numa pasta, com o nome da seção ("Main
        # A.wav") - o mesmo nome que "Adicionar vários WAVs pelo nome do
        # arquivo" reconhece na volta. Com caixas marcadas, só as marcadas;
        # sem nenhuma, todas as seções que têm áudio. Sai o áudio como está
        # guardado (44100 Hz, 16 bits, estéreo), sem o ajuste de tamanho
        # que o Salvar faz.
        marcadas = [self.nomes[i] for i in sorted(self.lista.GetCheckedItems()) if 0 <= i < len(self.nomes)]
        nomes = [n for n in (marcadas or self.nomes) if self._audio(n)]
        if not nomes:
            mensagem = "Nenhuma seção marcada tem áudio." if marcadas else "Este estilo não tem áudio para exportar."
            falar(mensagem, imediato=True)
            return
        self._parar()
        with wx.DirDialog(self, f"Escolha a pasta para os {len(nomes)} WAVs" if len(nomes) > 1 else "Escolha a pasta para o WAV",
                          defaultPath=self._pasta_inicial(), style=wx.DD_DEFAULT_STYLE) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            pasta = dlg.GetPath()
        existentes = [n for n in nomes if os.path.exists(os.path.join(pasta, n + ".wav"))]
        if existentes:
            pergunta = (f"Já existem nessa pasta: {', '.join(n + '.wav' for n in existentes)}.\n\n"
                        "Substituir esses arquivos?")
            if wx.MessageBox(pergunta, "Exportar áudio", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                falar("Exportação cancelada.", imediato=True)
                return
        gravados, com_erro = [], []
        for nome in nomes:
            try:
                with wave.open(os.path.join(pasta, nome + ".wav"), 'wb') as w:
                    w.setnchannels(2)
                    w.setsampwidth(2)
                    w.setframerate(TAXA)
                    w.writeframes(self._audio(nome)['pcm'])
                gravados.append(nome)
            except OSError:
                com_erro.append(nome)
        mensagem = f"{len(gravados)} WAV(s) exportado(s) para {pasta}."
        if com_erro:
            mensagem += f" Não consegui gravar: {', '.join(com_erro)}."
        falar(mensagem, imediato=True)
        wx.MessageBox(mensagem, "Exportar áudio", wx.OK | wx.ICON_INFORMATION, self)
        self.lista.SetFocus()

    def OnVolume(self, event):
        self.frame.audio_volume = self.sp_volume.GetValue()
        self._mexeu()
        self.frame._reavaliar_audio_no_play()

    def OnPan(self, event):
        self.frame.audio_pan = self.sp_pan.GetValue()
        self._mexeu()
        self.frame._reavaliar_audio_no_play()

    def OnVolumeDaSecao(self, event):
        nome = self._selecionada()
        if not nome or not self._audio(nome):
            falar("Esta seção não tem áudio.", imediato=True)
            return
        editar_volume_da_secao(self.frame, nome, self)
        self._atualizar_linha(nome)

    def OnGravarGanho(self, event):
        if gravar_ganho_nos_audios(self.frame, self):
            for nome in self.nomes:
                self._atualizar_linha(nome)
            self.sp_volume.SetValue(self.frame.audio_volume)
            self.sp_pan.SetValue(self.frame.audio_pan)

    def OnAdiantar(self, event):
        # Fica no config.json (é do computador, não do estilo); gravado só
        # ao fechar a tela, pra não escrever o arquivo a cada toque na seta.
        self.frame.config["audio_adiantar_ms"] = self.sp_adiantar.GetValue()

    # --- prévia ---
    def OnOuvir(self, event):
        nome = self._selecionada()
        if self._tocando:
            tocava = self._tocando
            self._parar()
            if tocava == nome:
                falar("Parado.", imediato=True)
                return
        audio = self._audio(nome) if nome else None
        if not audio:
            falar("Esta seção não tem áudio.", imediato=True)
            return
        try:
            import winsound
            import tempfile
            if not self._arquivo_previa:
                self._arquivo_previa = os.path.join(tempfile.gettempdir(), f"mhs_previa_audio_{os.getpid()}.wav")
            with wave.open(self._arquivo_previa, 'wb') as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(TAXA)
                w.writeframes(audio['pcm'])
            winsound.PlaySound(self._arquivo_previa, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self._tocando = nome
        except Exception as e:
            falar(f"Não foi possível tocar o áudio. {e}", imediato=True)

    def _parar(self):
        if not self._tocando:
            return
        self._tocando = None
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def OnFechar(self, event):
        self._parar()
        self.frame.save_config()
        if self._arquivo_previa:
            try:
                os.remove(self._arquivo_previa)
            except OSError:
                pass
        self.EndModal(wx.ID_CANCEL)
