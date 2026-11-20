# -*- coding: utf-8 -*-
"""Volume percebido (LUFS) dos áudios de um Audio Style, em Python puro (o programa compilado não leva o numpy).

Medida do padrão ITU-R BS.1770-4 / EBU R128, a mesma dos medidores de rádio, TV e streaming:
  1. filtro "K" (realce dos agudos + corte dos graves, como o ouvido sente);
  2. energia em blocos de 400 ms que andam de 100 em 100 ms;
  3. descarta os blocos muito baixos (silêncio abaixo de -70 LUFS e tudo que está 10 LU abaixo da média);
  4. volume integrado = média da energia dos blocos que sobraram.

O filtro (a parte lenta, uns 9 segundos para um minuto e meio de áudio) passa UMA vez por áudio e guarda a energia de cada
trecho de 100 ms, separada em esquerdo e direito. Depois o volume e o pan de cada seção entram só como ganho sobre essa
energia, então trocar o volume e medir de novo é instantâneo. Os blocos de uma seção não atravessam a seguinte: cada
seção é medida sozinha e os blocos de todas entram juntos no mesmo "gate" - o volume do CONJUNTO, não de cada seção.
"""
import array
import math
import sys
import zlib

TAXA = 44100
PASSO = TAXA // 10               # 100 ms
BLOCO = 4                        # 4 passos = 400 ms, com 75% de sobreposição

_cache = {}                      # (tamanho, crc32 do PCM) -> medida; só guarda números, não o áudio


def _coeficientes():
    # estágio 1: realce de agudos (shelving)
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / TAXA)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = ((Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0)
    a1 = (2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0)
    # estágio 2: passa-altas
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / TAXA)
    a0 = 1 + K / Q + K * K
    a2 = (2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0)
    return b1, a1, a2


_B1, _A1, _A2 = _coeficientes()


def _energias_do_canal(x, n_frames):
    """energia (soma dos quadrados, na escala dos inteiros de 16 bits) de cada trecho de 100 ms, depois do filtro K"""
    b0, b1, b2 = _B1
    a1, a2 = _A1
    c1, c2 = _A2
    s1a = s1b = s2a = s2b = 0.0
    saida = []
    for ini in range(0, n_frames - PASSO + 1, PASSO):
        acc = 0.0
        for v in x[ini:ini + PASSO]:
            y = b0 * v + s1a
            s1a = b1 * v - a1 * y + s1b
            s1b = b2 * v - a2 * y
            w = y + s2a
            s2a = -2.0 * y - c1 * w + s2b
            s2b = y - c2 * w
            acc += w * w
        saida.append(acc)
    return saida


def medir_pcm(pcm, progresso=None):
    """pcm: 16 bits estéreo 44100 Hz. -> {'el': [...], 'er': [...]} (energia de cada 100 ms). Guarda em cache pelo conteúdo."""
    chave = (len(pcm), zlib.crc32(pcm))
    achada = _cache.get(chave)
    if achada is not None:
        return achada
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) // 4 * 4])
    if sys.byteorder == 'big':
        a.byteswap()
    n_frames = len(a) // 2
    medida = {'el': _energias_do_canal(a[0::2], n_frames), 'er': _energias_do_canal(a[1::2], n_frames)}
    if len(_cache) > 200:
        _cache.clear()
    _cache[chave] = medida
    return medida


def lufs_do_conjunto(itens):
    """itens: [(medida, ganho_esquerdo, ganho_direito)] -> volume integrado em LUFS (None se tudo é silêncio).
    Os ganhos são os do volume e do pan de cada seção (1.0 = sem mudança)."""
    escala = 4.0 * PASSO * 32768.0 * 32768.0
    potencias = []
    for medida, gl, gr in itens:
        el, er = medida['el'], medida['er']
        gl2, gr2 = gl * gl, gr * gr
        for i in range(len(el) - BLOCO + 1):
            potencias.append((gl2 * (el[i] + el[i + 1] + el[i + 2] + el[i + 3])
                              + gr2 * (er[i] + er[i + 1] + er[i + 2] + er[i + 3])) / escala)
    if not potencias:
        return None
    limite_abs = 10 ** ((-70.0 + 0.691) / 10)
    acima = [p for p in potencias if p > limite_abs]
    if not acima:
        return None
    relativo = -0.691 + 10 * math.log10(sum(acima) / len(acima)) - 10.0
    limite = max(limite_abs, 10 ** ((relativo + 0.691) / 10))
    ok = [p for p in potencias if p > limite]
    if not ok:
        return None
    return -0.691 + 10 * math.log10(sum(ok) / len(ok))


def lufs_do_pcm(pcm, ganho_esquerdo=1.0, ganho_direito=1.0):
    return lufs_do_conjunto([(medir_pcm(pcm), ganho_esquerdo, ganho_direito)])


def pico_dbfs(pcm, ganho=1.0):
    """pico em dBFS (valor absoluto da maior amostra, depois do ganho)"""
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) // 2 * 2])
    if sys.byteorder == 'big':
        a.byteswap()
    pico = max(max(a), -min(a)) if len(a) else 0
    return 20 * math.log10(max(pico * ganho, 1e-9) / 32768.0)
