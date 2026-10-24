# -*- coding: utf-8 -*-
"""One Touch Settings (OTS) de um estilo Yamaha.

Um estilo guarda os OTS numa seção "OTSc" depois do CASM (Style Files - Introduction and Details v2.1, item 4.7):
cada OTS é uma trilha MIDI comum ("MTrk"); hoje são 4 (o teclado liga o OTS 1 ao Main A, o 2 ao B, e assim por
diante, quando o OTS Link está ligado). Cada trilha guarda as 4 partes do teclado nos canais 1 a 4: Right 1, Right 2,
Right 3 e Left. Lido de arquivos reais (YASMIN SENSACAO.sty), por parte:

  CC 0 / CC 32 / Program Change          banco e timbre
  CC 7 / CC 10 / CC 91 / CC 93           volume, pan, reverb, chorus
  F0 43 73 01 50 08 pp 03 vv             oitava (vv = 64 + oitavas)       [deduzido dos valores: 64, 63 = -1, 65 = +1]
  F0 43 73 01 50 08 pp 00 vv             parte ligada (127) ou desligada  [deduzido]
  F0 43 10 4C 08 pp aa vv                parâmetros de Multi Part (os do Voice Creator), pp = 0..3
  F0 43 10 4C 03 pp aa vv                efeito DSP da parte (Insertion nn = pp): 00/01 tipo, 02..0B parâmetros 1..10
                                         (0B = Dry/Wet), 20..25 parâmetros 11..16
  F0 43 73 01 51 ...                     ajustes próprios da Yamaha em volta do DSP (não documentados; ficam como estão)

O que o programa não entende vai junto, byte a byte: uma trilha que ninguém mexeu volta ao arquivo idêntica ao original.
"""

import struct

PARTES = ["Right 1", "Right 2", "Right 3", "Left"]
# Canal MIDI (0 a 3) em que o teclado recebe cada parte quando o OTS é mandado ao vivo pela porta do OTS: Right 1 no canal 1,
# Left no 2, Right 2 no 3 e Right 3 no 4. No arquivo as partes ficam na ordem de PARTES (canais 1 a 4 da trilha do OTS).
CANAL_VIVO = (0, 2, 3, 1)
TIPO_SEM_EFEITO = 0x40            # MSB 64 = "Thru": a parte não usa efeito
CANAIS_COM_DSP = 4

_SYS_PROPRIO = bytes([0x43, 0x73, 0x01, 0x50])
_SYS_PROPRIO_DSP = bytes([0x43, 0x73, 0x01, 0x51])
_SYS_XG_PARTE = bytes([0x43, 0x10, 0x4C, 0x08])
_SYS_XG_INSERCAO = bytes([0x43, 0x10, 0x4C, 0x03])


def _vlq_ler(b, i):
    v = 0
    while True:
        c = b[i]
        i += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, i


def _vlq_escrever(n):
    partes = [n & 0x7F]
    n >>= 7
    while n:
        partes.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(partes))


class Evento(object):
    """tipo 'ch' (dados = status + 1 ou 2 bytes), 'sx' (dados = corpo do SysEx depois do F0, com o F7 no fim) ou
    'meta' (tipo_meta + dados)."""
    __slots__ = ('delta', 'tipo', 'dados', 'tipo_meta')

    def __init__(self, delta, tipo, dados, tipo_meta=None):
        self.delta, self.tipo, self.dados, self.tipo_meta = delta, tipo, bytes(dados), tipo_meta

    def para_bytes(self):
        d = _vlq_escrever(self.delta)
        if self.tipo == 'ch':
            return d + self.dados
        if self.tipo == 'sx':
            return d + b'\xF0' + _vlq_escrever(len(self.dados)) + self.dados
        return d + b'\xFF' + bytes([self.tipo_meta]) + _vlq_escrever(len(self.dados)) + self.dados


def ler_eventos(trilha):
    i, status, saida = 0, None, []
    while i < len(trilha):
        delta, i = _vlq_ler(trilha, i)
        b = trilha[i]
        if b == 0xFF:
            tp = trilha[i + 1]
            n, j = _vlq_ler(trilha, i + 2)
            saida.append(Evento(delta, 'meta', trilha[j:j + n], tp))
            i = j + n
            continue
        if b in (0xF0, 0xF7):
            n, j = _vlq_ler(trilha, i + 1)
            saida.append(Evento(delta, 'sx', trilha[j:j + n]))
            i = j + n
            continue
        if b & 0x80:
            status = b
            i += 1
        n = 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
        saida.append(Evento(delta, 'ch', bytes([status]) + trilha[i:i + n]))
        i += n
    return saida


class Trilha(object):
    """Um OTS (uma trilha MIDI). `original` é o MTrk exatamente como veio; enquanto ninguém mexe, volta igual."""

    def __init__(self, mtrk_completo):
        self.original = bytes(mtrk_completo)
        self.eventos = ler_eventos(self.original[8:])
        self.alterada = False

    # ---- bytes
    def para_bytes(self):
        if not self.alterada:
            return self.original
        corpo = b''.join(e.para_bytes() for e in self.eventos)
        return b'MTrk' + struct.pack('>I', len(corpo)) + corpo

    # ---- mensagens de canal
    def _achar_cc(self, canal, controle):
        achado = None
        for i, e in enumerate(self.eventos):
            if e.tipo == 'ch' and e.dados[0] == (0xB0 | canal) and e.dados[1] == controle:
                achado = i
        return achado

    def cc(self, canal, controle, padrao=None):
        i = self._achar_cc(canal, controle)
        return self.eventos[i].dados[2] if i is not None else padrao

    def _achar_pc(self, canal):
        for i, e in enumerate(self.eventos):
            if e.tipo == 'ch' and e.dados[0] == (0xC0 | canal):
                return i
        return None

    def programa(self, canal, padrao=0):
        i = self._achar_pc(canal)
        return self.eventos[i].dados[1] if i is not None else padrao

    def definir_cc(self, canal, controle, valor):
        valor = max(0, min(127, int(valor)))
        i = self._achar_cc(canal, controle)
        if i is not None:
            if self.eventos[i].dados[2] != valor:
                self.eventos[i].dados = bytes([0xB0 | canal, controle, valor])
                self.alterada = True
            return
        novo = Evento(0, 'ch', bytes([0xB0 | canal, controle, valor]))
        pc = self._achar_pc(canal)
        if controle in (0, 32) and pc is not None:
            self.eventos.insert(pc, novo)          # banco sempre antes do Program Change
        else:
            ult = max([k for k, e in enumerate(self.eventos) if e.tipo == 'ch' and (e.dados[0] & 0x0F) == canal] or [len(self.eventos) - 1])
            self.eventos.insert(ult + 1, novo)
        self.alterada = True

    def definir_programa(self, canal, valor):
        valor = max(0, min(127, int(valor)))
        i = self._achar_pc(canal)
        if i is not None:
            if self.eventos[i].dados[1] != valor:
                self.eventos[i].dados = bytes([0xC0 | canal, valor])
                self.alterada = True
            return
        ult = max([k for k, e in enumerate(self.eventos) if e.tipo == 'ch' and (e.dados[0] & 0x0F) == canal] or [-1])
        self.eventos.insert(ult + 1, Evento(0, 'ch', bytes([0xC0 | canal, valor])))
        self.alterada = True

    def banco(self, canal):
        return self.cc(canal, 0, 0), self.cc(canal, 32, 0)

    # ---- SysEx próprios da Yamaha por parte (43 73 01 50 08 pp param valor)
    def _achar_proprio(self, parte, parametro):
        achado = None
        for i, e in enumerate(self.eventos):
            d = e.dados
            if e.tipo == 'sx' and d[:4] == _SYS_PROPRIO and len(d) >= 9 and d[4] == 0x08 and d[5] == parte and d[6] == parametro:
                achado = i
        return achado

    def proprio(self, parte, parametro, padrao=None):
        i = self._achar_proprio(parte, parametro)
        return self.eventos[i].dados[7] if i is not None else padrao

    def definir_proprio(self, parte, parametro, valor):
        valor = max(0, min(127, int(valor)))
        i = self._achar_proprio(parte, parametro)
        if i is not None:
            if self.eventos[i].dados[7] != valor:
                self.eventos[i].dados = _SYS_PROPRIO + bytes([0x08, parte, parametro, valor, 0xF7])
                self.alterada = True
            return
        # vizinho do mesmo grupo: logo depois do último ajuste próprio desta parte
        ult = max([k for k, e in enumerate(self.eventos) if e.tipo == 'sx' and e.dados[:4] == _SYS_PROPRIO
                   and len(e.dados) >= 9 and e.dados[4] == 0x08 and e.dados[5] == parte] or [len(self.eventos) - 1])
        self.eventos.insert(ult + 1, Evento(0, 'sx', _SYS_PROPRIO + bytes([0x08, parte, parametro, valor, 0xF7])))
        self.alterada = True

    def oitava(self, parte):
        return self.proprio(parte, 0x03, 64) - 64

    def definir_oitava(self, parte, oitavas):
        self.definir_proprio(parte, 0x03, 64 + max(-3, min(3, int(oitavas))))

    def ligada(self, parte):
        return (self.proprio(parte, 0x00, 0) or 0) > 0

    def definir_ligada(self, parte, ligada):
        self.definir_proprio(parte, 0x00, 127 if ligada else 0)

    def efeito_ligado(self, parte):
        # `43 73 01 50 08 pp 08`: o efeito de inserção da parte está em uso (o teclado ligou-o ao gravar o OTS)
        return (self.proprio(parte, 0x08, 0) or 0) > 0

    # ---- efeito DSP da parte (Insertion nn = parte)
    @staticmethod
    def _indice_do_endereco(endereco):
        if 0x02 <= endereco <= 0x0B:
            return endereco - 0x02
        if 0x20 <= endereco <= 0x25:
            return 10 + (endereco - 0x20)
        return None

    @staticmethod
    def _endereco_do_indice(indice):
        return 0x02 + indice if indice <= 9 else 0x20 + (indice - 10)

    def _eventos_dsp(self, parte):
        return [i for i, e in enumerate(self.eventos)
                if e.tipo == 'sx' and e.dados[:4] == _SYS_XG_INSERCAO and len(e.dados) >= 8 and e.dados[4] == parte]

    def dsp(self, parte):
        """{'msb', 'lsb', 'p': [16 valores, -1 = o arquivo não traz]} ou None se a parte não tem efeito."""
        idx = self._eventos_dsp(parte)
        if not idx:
            return None
        res = {'msb': 0, 'lsb': 0, 'p': [-1] * 16}
        tem_tipo = False
        for i in idx:
            d = self.eventos[i].dados
            endereco, valor = d[5], d[6]
            if endereco == 0x00:
                # o tipo do efeito vai numa mensagem só, com dois bytes: MSB e LSB
                res['msb'] = valor
                res['lsb'] = d[7] if len(d) >= 9 else 0
                tem_tipo = True
            elif endereco == 0x01:
                res['lsb'] = valor
            else:
                k = self._indice_do_endereco(endereco)
                if k is not None:
                    res['p'][k] = -1 if valor > 127 else valor      # 0xFF no arquivo = "este parâmetro não vale"
        return res if tem_tipo else None

    def definir_dsp(self, parte, msb, lsb, p):
        """Grava o efeito da parte. `p`: 16 valores (-1 = não escrever). Eventos que já existiam são alterados no lugar;
        os que faltam entram junto dos outros do efeito (ou no fim das mensagens da parte, se a parte não tinha)."""
        idx = self._eventos_dsp(parte)
        por_endereco = {self.eventos[i].dados[5]: i for i in idx}

        def poe(endereco, valor, valor2=None):
            valor = max(0, min(127, int(valor)))
            dados = bytes([valor]) if valor2 is None else bytes([valor, max(0, min(127, int(valor2)))])
            corpo = _SYS_XG_INSERCAO + bytes([parte, endereco]) + dados + bytes([0xF7])
            if endereco in por_endereco:
                e = self.eventos[por_endereco[endereco]]
                if e.dados != corpo:
                    e.dados = corpo
                    self.alterada = True
                return
            if por_endereco:
                pos = max(por_endereco.values()) + 1
            else:
                ult = [k for k, e in enumerate(self.eventos) if e.tipo in ('ch', 'sx') and not (e.tipo == 'sx' and e.dados[:4] == _SYS_PROPRIO_DSP)]
                pos = (max(ult) + 1) if ult else len(self.eventos)
                fim_meta = [k for k, e in enumerate(self.eventos) if e.tipo == 'meta' and e.tipo_meta == 0x2F]
                if fim_meta:
                    pos = min(pos, fim_meta[0])
            self.eventos.insert(pos, Evento(0, 'sx', corpo))
            # reindexa
            por_endereco.clear()
            for i in self._eventos_dsp(parte):
                por_endereco[self.eventos[i].dados[5]] = i
            self.alterada = True

        poe(0x00, msb, lsb)
        for k, v in enumerate(p):
            if v is not None and v >= 0:
                poe(self._endereco_do_indice(k), v)

    # ---- o que vai para o teclado quando se escolhe este OTS
    def mensagens_para_enviar(self):
        """Lista de bytes (cada item: uma mensagem completa, sysex com F0 e F7) do que vai para o teclado quando se escolhe
        este OTS: as mensagens de canal e os SysEx XG, já nos canais de CANAL_VIVO. Antes do efeito de inserção de cada
        parte vai a ligação do efeito à parte (XG 03 nn 0C: o canal da parte, ou 7F se o efeito não está em uso), sem a qual
        o teclado não aplica o efeito. Os ajustes próprios da Yamaha (43 73) e as metas ficam de fora: só o teclado os
        entende como arquivo."""
        saida = []
        ligados = set()
        for e in self.eventos:
            if e.tipo == 'ch':
                canal = e.dados[0] & 0x0F
                if canal < 4:
                    saida.append(bytes([(e.dados[0] & 0xF0) | CANAL_VIVO[canal]]) + e.dados[1:])
                else:
                    saida.append(e.dados)
            elif e.tipo == 'sx' and e.dados[:3] == bytes([0x43, 0x10, 0x4C]) and len(e.dados) >= 6:
                d = e.dados
                bloco, parte = d[3], d[4]
                if any(b > 0x7F for b in d[:-1]):
                    continue                    # 0xFF = "este parâmetro não vale": não pode ir pelo cabo
                if bloco in (0x08, 0x0A) and parte < 4:
                    d = d[:4] + bytes([CANAL_VIVO[parte]]) + d[5:]
                elif bloco == 0x03 and parte < 4 and parte not in ligados:
                    ligados.add(parte)
                    alvo = CANAL_VIVO[parte] if self.efeito_ligado(parte) else 0x7F
                    saida.append(b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x03, parte, 0x0C, alvo, 0xF7]))
                saida.append(b'\xF0' + d)
        return saida


class Secao(object):
    """A seção OTSc inteira (etiqueta + tamanho + trilhas)."""

    def __init__(self, bloco):
        self.original = bytes(bloco)
        corpo = self.original[8:]
        self.trilhas = []
        i = 0
        while i + 8 <= len(corpo) and corpo[i:i + 4] == b'MTrk':
            n = struct.unpack('>I', corpo[i + 4:i + 8])[0]
            self.trilhas.append(Trilha(corpo[i:i + 8 + n]))
            i += 8 + n
        self.resto = corpo[i:]            # o que sobrar depois das trilhas (não deveria haver)

    @property
    def alterada(self):
        return any(t.alterada for t in self.trilhas)

    def para_bytes(self):
        if not self.alterada:
            return self.original
        corpo = b''.join(t.para_bytes() for t in self.trilhas) + self.resto
        return b'OTSc' + struct.pack('>I', len(corpo)) + corpo


def achar_secao_ots(dados_apos_o_casm):
    """Dado o texto de bytes que vem depois do CASM (ver secoes_apos_o_casm), devolve (Secao ou None)."""
    i = 0
    d = dados_apos_o_casm
    while i + 8 <= len(d):
        tag = d[i:i + 4]
        n = struct.unpack('>I', d[i + 4:i + 8])[0]
        if i + 8 + n > len(d):
            break
        if tag == b'OTSc':
            return Secao(d[i:i + 8 + n])
        i += 8 + n
    return None


def trocar_secao(dados_apos_o_casm, bloco_novo):
    """Troca (ou acrescenta, se não existia) a seção OTSc no meio das seções que vêm depois do CASM."""
    d = dados_apos_o_casm
    i = 0
    saida = bytearray()
    trocou = False
    while i + 8 <= len(d):
        tag = d[i:i + 4]
        n = struct.unpack('>I', d[i + 4:i + 8])[0]
        fim = i + 8 + n
        if fim > len(d):
            break
        if tag == b'OTSc':
            saida += bloco_novo
            trocou = True
        else:
            saida += d[i:fim]
        i = fim
    saida += d[i:]
    if not trocou:
        saida = bytearray(bloco_novo) + saida
    return bytes(saida)
