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
# Canais das partes do teclado na porta principal, na ordem das partes do arquivo (Right 1, Right 2, Right 3, Left): o registro de MIDI
# de entrada do OTS 4 mostrou o teclado transmitindo a Right 1 no canal 1 (índice 0), a Right 2 no 2 e a Left no 3.
CANAIS_TECLADO = (0, 1, 3, 2)
CANAL_VIVO = CANAIS_TECLADO
# Modo "partes comuns": as mesmas 4 partes tocadas em canais comuns da porta do OTS (5 a 8), que não passam pelo split, pela
# oitava, pelo transpose nem pelos botões de parte do painel. Foi o que o registro de MIDI de entrada mostrou: pelos canais
# 1 a 4 o que se toca sofre a oitava e o transpose do painel duas vezes (o teclado já os aplica à nota que transmite).
CANAIS_COMUNS = (4, 5, 6, 7)
# Unidade de efeito de inserção (XG 03 nn) em que cada parte do arquivo vai ao teclado ao vivo. O teclado liga cada unidade à parte que
# usa o efeito (03 nn 0C <parte>): no OTS 4 mandou a unidade 2 para a parte 0 (Right 1) e a 1 para a parte 1 (Right 2); a Left usa a 0.
UNIDADE_INSERCAO = (2, 1, 3, 0)
UNIDADE_XG_COMUM = (0, 1, 2, 2)
# Ajustes próprios da Yamaha por parte (43 73 01 50 08 pp <parâmetro> <valor>) que vão ao teclado nas partes do teclado: 00 = parte
# ligada, 01 = Panel Sustain, 02 = Left Hold (só a Left), 03 = oitava da parte (64 = 0), 08 = DSP ligado. São as funções "Part
# On/Off", "Panel Sustain", "Part Octave" e "DSP On/Off" da tabela de parâmetros do Data List.
PARAMETROS_PROPRIOS = (0x00, 0x01, 0x02, 0x03, 0x08)
# Efeitos cujos parâmetros 1 a 10 o teclado recebe em dois bytes, nos endereços 30 a 42 (Data List do SX600, "Type MSB of the effect
# types that require Parameter MSB"); para os outros valem os endereços 02 a 0B, de um byte.
MSB_DOIS_BYTES = (5, 6, 7, 8, 95, 96, 97, 98, 104)
# No arquivo do OTS, o teclado grava em dois bytes (30 a 42) só os efeitos de delay (5 a 8); os demais, como o Multi FX 95, saem de um byte
MSB_DOIS_BYTES_NO_ARQUIVO = (5, 6, 7, 8)
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

    def _achar_nrpn(self, canal, lsb):
        """Índice (em self.eventos) do CC 6 do NRPN 01/`lsb` do canal, ou None."""
        achado = None
        seq = [(i, e.dados) for i, e in enumerate(self.eventos)
               if e.tipo == 'ch' and (e.dados[0] & 0x0F) == canal and (e.dados[0] & 0xF0) == 0xB0]
        for k in range(2, len(seq)):
            if seq[k][1][1] == 0x06 and seq[k - 1][1][1] == 0x62 and seq[k - 1][1][2] == lsb \
                    and seq[k - 2][1][1] == 0x63 and seq[k - 2][1][2] == 0x01:
                achado = seq[k][0]
        return achado

    def definir_nrpn(self, canal, lsb, valor):
        valor = max(0, min(127, int(valor)))
        i = self._achar_nrpn(canal, lsb)
        if i is not None:
            if self.eventos[i].dados[2] != valor:
                self.eventos[i].dados = bytes([0xB0 | canal, 0x06, valor])
                self.alterada = True
            return
        ult = max([k for k, e in enumerate(self.eventos) if e.tipo == 'ch' and (e.dados[0] & 0x0F) == canal] or [-1])
        for n, ev in enumerate((bytes([0xB0 | canal, 0x63, 0x01]), bytes([0xB0 | canal, 0x62, lsb]), bytes([0xB0 | canal, 0x06, valor]))):
            self.eventos.insert(ult + 1 + n, Evento(0, 'ch', ev))
        self.alterada = True

    def sx(self, parte, bloco, endereco, padrao=None):
        """Valor do SysEx XG `43 10 4C <bloco> <parte> <endereço> <valor>` (bloco 08 ou 0A), ou `padrao`."""
        achado = padrao
        for e in self.eventos:
            d = e.dados
            if e.tipo == 'sx' and d[:3] == bytes([0x43, 0x10, 0x4C]) and len(d) >= 8 and d[3] == bloco and d[4] == parte and d[5] == endereco:
                achado = d[6]
        return achado

    def definir_sx(self, parte, bloco, endereco, valor):
        valor = max(0, min(127, int(valor)))
        achado = None
        for i, e in enumerate(self.eventos):
            d = e.dados
            if e.tipo == 'sx' and d[:3] == bytes([0x43, 0x10, 0x4C]) and len(d) >= 8 and d[3] == bloco and d[4] == parte and d[5] == endereco:
                achado = i
        corpo = bytes([0x43, 0x10, 0x4C, bloco, parte, endereco, valor, 0xF7])
        if achado is not None:
            if self.eventos[achado].dados != corpo:
                self.eventos[achado].dados = corpo
                self.alterada = True
            return
        ult = max([k for k, e in enumerate(self.eventos) if e.tipo == 'sx' and e.dados[:4] == bytes([0x43, 0x10, 0x4C, 0x08])
                   and len(e.dados) >= 8 and e.dados[4] == parte] or [len(self.eventos) - 1])
        self.eventos.insert(ult + 1, Evento(0, 'sx', corpo))
        self.alterada = True

    def nrpn(self, canal, lsb, padrao=None):
        """Valor do CC 6 do NRPN 01/`lsb` do canal (Voice Creator: 08 vibrato rate, 09 depth, 0A delay, 63 attack, 64 decay,
        66 release), ou `padrao`."""
        ev = [e.dados for e in self.eventos if e.tipo == 'ch' and (e.dados[0] & 0x0F) == canal and (e.dados[0] & 0xF0) == 0xB0]
        achado = padrao
        for k in range(2, len(ev)):
            if ev[k][1] == 0x06 and ev[k - 1][1] == 0x62 and ev[k - 1][2] == lsb and ev[k - 2][1] == 0x63 and ev[k - 2][2] == 0x01:
                achado = ev[k][2]
        return achado

    def no_teclado(self, parte):
        """Se a parte vai como parte do teclado (porta principal) no modo híbrido: a Right 1 sempre; a Right 2 e a Left só quando
        têm efeito DSP em uso, porque só como parte do teclado o efeito se liga a elas. As outras vão em canais comuns."""
        if parte == 0:
            return True
        if parte in (1, 3) and self.efeito_ligado(parte):
            d = self.dsp(parte)
            return bool(d) and d['msb'] != TIPO_SEM_EFEITO
        return False

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

    @staticmethod
    def _indice_do_endereco2(endereco):
        """Índice do parâmetro (0 a 9) de um endereço de dois bytes (30 a 42, só pares), ou None."""
        if 0x30 <= endereco <= 0x42 and endereco % 2 == 0:
            return (endereco - 0x30) // 2
        return None

    @staticmethod
    def bytes_param_dsp_ao_vivo(msb, unidade, indice, valor):
        """Mensagem XG (com F0 e F7) do parâmetro `indice` (0 a 15) do efeito `msb` na `unidade`, no formato que o teclado recebe:
        dois bytes (30 a 42, valor // 128 e valor % 128) para os efeitos que exigem MSB, um byte (02 a 0B e 20 a 25) para os outros."""
        valor = max(0, int(valor))
        if indice <= 9 and msb in MSB_DOIS_BYTES:
            v = min(valor, 0x3FFF)
            return b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x03, unidade, 0x30 + 2 * indice, v >> 7, v & 0x7F, 0xF7])
        return b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x03, unidade, Trilha._endereco_do_indice(indice), min(valor, 127), 0xF7])

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
            elif len(d) >= 9 and self._indice_do_endereco2(endereco) is not None:
                # parâmetro de dois bytes (efeitos de delay): o arquivo guarda o valor de 16 bits, byte alto e byte baixo
                res['p'][self._indice_do_endereco2(endereco)] = (d[6] << 8) | d[7]
            else:
                k = self._indice_do_endereco(endereco)
                if k is not None:
                    res['p'][k] = -1 if valor > 127 else valor      # 0xFF no arquivo = "este parâmetro não vale"
        return res if tem_tipo else None

    def definir_dsp(self, parte, msb, lsb, p):
        """Grava o efeito da parte. `p`: 16 valores (-1 = não escrever). Eventos que já existiam são alterados no lugar;
        os que faltam entram junto dos outros do efeito (ou no fim das mensagens da parte, se a parte não tinha)."""
        idx = self._eventos_dsp(parte)
        # o formato dos parâmetros 1 a 10 no arquivo (um byte, 02 a 0B; ou dois, 30 a 42) é o do tipo do efeito: dois bytes nos delays
        # (5 a 8), um byte nos demais. Ao mudar de formato, os parâmetros do formato antigo saem.
        tem_dois = any(self._indice_do_endereco2(self.eventos[i].dados[5]) is not None for i in idx)
        tem_um = any(0x02 <= self.eventos[i].dados[5] <= 0x0B for i in idx)
        dois = msb in MSB_DOIS_BYTES_NO_ARQUIVO
        if dois != tem_dois and (tem_dois or tem_um):
            sobra = [i for i in idx if (self._indice_do_endereco2(self.eventos[i].dados[5]) is not None
                                          or 0x02 <= self.eventos[i].dados[5] <= 0x0B)]
            for i in sorted(sobra, reverse=True):
                del self.eventos[i]
            self.alterada = True
            idx = self._eventos_dsp(parte)
        por_endereco = {self.eventos[i].dados[5]: i for i in idx}

        def poe(endereco, valor, valor2=None):
            if valor2 is not None and endereco >= 0x30:
                # valor de 16 bits, byte alto e byte baixo (assim o teclado o grava no OTS)
                v16 = max(0, min(0x3FFF, (int(valor) << 8) | int(valor2)))
                dados = bytes([v16 >> 8, v16 & 0xFF])
            else:
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
                if dois and k <= 9:
                    poe(0x30 + 2 * k, v >> 8, v & 0xFF)
                else:
                    poe(self._endereco_do_indice(k), v)

    def mensagens_hibrido(self, canais=CANAIS_COMUNS, deslocamento=16):
        """Modo híbrido: (para a porta principal, para a porta do OTS). A Right 1, e a Right 2 e a Left quando têm DSP em uso, vão
        como partes do teclado na porta principal (canais 1, 2 e 3), com o efeito ligado à parte (unidade, 03 nn 0C) e os ajustes
        próprios da Yamaha; as demais partes vão em canais comuns da porta do OTS, onde o timbre obedece e o programa decide quem toca."""
        no_tec = [p for p in range(4) if self.no_teclado(p)]
        canais_tec = {CANAIS_TECLADO[p] for p in no_tec}
        unidades_tec = {UNIDADE_INSERCAO[p] for p in no_tec}
        comuns = [p for p in (1, 2, 3) if p not in no_tec]
        canais_com = {canais[p] for p in comuns}
        partes_com = {canais[p] + deslocamento for p in comuns}

        def do_teclado(m):
            if 0x80 <= m[0] < 0xF0:
                return (m[0] & 0x0F) in canais_tec
            if m[:4] == b'\xF0\x43\x10\x4C':
                if m[4] == 0x03:
                    return m[5] in unidades_tec or (m[6] == 0x0C and m[7] == 0x7F)
                return m[4] in (0x08, 0x0A) and m[5] in canais_tec
            if m[:5] == b'\xF0\x43\x73\x01\x50':
                return m[5] == 0x08 and m[6] in no_tec
            return False

        def das_comuns(m):
            if 0x80 <= m[0] < 0xF0:
                return (m[0] & 0x0F) in canais_com
            if m[:4] == b'\xF0\x43\x10\x4C':
                return m[4] in (0x08, 0x0A) and m[5] in partes_com
            return False

        tec = [m for m in self.mensagens_para_enviar(CANAIS_TECLADO) if do_teclado(m)]
        # Quem decide se a Right 1 toca é o programa (a nota só vai para ela se estiver ligada no OTS); o liga/desliga dela fica sempre
        # ligado no teclado, para não calar as outras partes.
        tec = [m[:8] + b'\x7F' + m[9:] if m[:5] == b'\xF0\x43\x73\x01\x50' and m[6] == 0 and m[7] == 0x00 else m for m in tec]
        com = [m for m in self.mensagens_para_enviar(canais, UNIDADE_XG_COMUM, deslocamento) if das_comuns(m)]
        return tec, com

    def _variation_como_insercao(self, canais, deslocamento):
        """O efeito da primeira parte com efeito em uso, mandado pelo bloco Variation (XG 02 01) ligado a essa parte como
        inserção (5A = 0, 5B = parte), na mesma ordem e com os mesmos endereços que o MHS MIDI Sequencer usa e que
        funcionam no teclado. Só cabe um efeito: o Variation é um só."""
        for parte in range(4):
            d = self.dsp(parte)
            if d is None or not self.efeito_ligado(parte) or d['msb'] == TIPO_SEM_EFEITO:
                continue
            ini = b'\xF0\x43\x10\x4C\x02\x01'
            msgs = [ini + bytes([0x5A, 0x00, 0xF7]),
                    ini + bytes([0x5B, canais[parte] + deslocamento, 0xF7]),
                    ini + bytes([0x40, d['msb'], d['lsb'], 0xF7])]
            p = d['p']
            dois_bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
            um_byte = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
            ret = p[9]
            if ret >= 0:
                msgs.append(ini + bytes([0x56, ret, 0xF7]))
            for i in range(16):
                if p[i] < 0 or (i == 9 and ret >= 0):
                    continue
                if i < 10:
                    msgs.append(ini + bytes([dois_bytes[i], p[i] // 128, p[i] % 128, 0xF7]))
                else:
                    msgs.append(ini + bytes([um_byte[i - 10], p[i] & 0x7F, 0xF7]))
            return msgs
        return []

    # ---- o que vai para o teclado quando se escolhe este OTS
    def mensagens_para_enviar(self, canais=CANAIS_TECLADO, unidades=UNIDADE_INSERCAO, deslocamento=0, via_variation=False):
        """Lista de bytes (cada item: uma mensagem completa, sysex com F0 e F7) do que vai para o teclado quando se escolhe
        este OTS: as mensagens de canal e os SysEx XG, já nos canais de `canais` (`deslocamento` soma ao número da parte dos SysEx e da ligação do efeito: 16 para as partes
        da segunda porta, se o teclado as numera de 17 a 32; `unidades`: a unidade de efeito de cada parte). Antes do efeito de inserção de cada
        parte vai a ligação do efeito à parte (XG 03 nn 0C: o canal da parte, ou 7F se o efeito não está em uso), sem a qual
        o teclado não aplica o efeito. Dos ajustes próprios da Yamaha (43 73) só vai o liga/desliga de cada parte, que é
        o que o teclado usa para decidir quais partes respondem ao que se toca; as metas ficam de fora."""
        saida = []
        ligados = set()
        tipo_do_efeito = {p: (self.dsp(p) or {}).get('msb') for p in range(4)}
        no_teclado = tuple(canais) == CANAIS_TECLADO
        for e in self.eventos:
            if e.tipo == 'sx' and e.dados[:4] == _SYS_PROPRIO and not no_teclado:
                continue
            if e.tipo == 'sx' and e.dados[:4] == _SYS_PROPRIO and len(e.dados) >= 9 and e.dados[4] == 0x08 and e.dados[6] in PARAMETROS_PROPRIOS:
                saida.append(b'\xF0' + e.dados)
            elif e.tipo == 'ch':
                canal = e.dados[0] & 0x0F
                dados = e.dados
                if dados[0] & 0xF0 == 0xB0 and dados[1] == 0x48 and canal < 4:
                    # O CC 72 do arquivo (perto de 100 em quase todo OTS) não é o release que o teclado aplica: o teclado
                    # transmite no CC 72 o valor do release do Voice Creator (NRPN 01/66). Mandar o do arquivo deixava o
                    # timbre com release comprido ("sustain").
                    rel = self.nrpn(canal, 0x66)
                    if rel is None:
                        continue
                    dados = dados[:2] + bytes([rel])
                if canal < 4:
                    saida.append(bytes([(dados[0] & 0xF0) | canais[canal]]) + dados[1:])
                else:
                    saida.append(e.dados)
            elif e.tipo == 'sx' and e.dados[:3] == bytes([0x43, 0x10, 0x4C]) and len(e.dados) >= 6:
                d = e.dados
                bloco, parte = d[3], d[4]
                if bloco == 0x03 and parte < 4 and len(d) >= 8:
                    # parâmetro de efeito: manda no formato que o teclado recebe (ver bytes_param_dsp_ao_vivo)
                    msb = tipo_do_efeito.get(parte)
                    endereco = d[5]
                    k = self._indice_do_endereco2(endereco) if len(d) >= 9 else None
                    if k is None and 0x02 <= endereco <= 0x0B:
                        k = endereco - 0x02
                    if k is not None and msb in MSB_DOIS_BYTES:
                        v = ((d[6] << 8) | d[7]) if len(d) >= 9 and endereco >= 0x30 else d[6]
                        if d[6] == 0xFF and endereco < 0x30:
                            continue
                        d = bytes(bytes_param_dsp_ao_vivo_(msb, unidades[parte] if not via_variation else parte, k, v)[1:])
                    elif endereco >= 0x30 and len(d) >= 9 and msb not in MSB_DOIS_BYTES:
                        continue
                if any(b > 0x7F for b in d[:-1]):
                    continue                    # 0xFF = "este parâmetro não vale": não pode ir pelo cabo
                if bloco in (0x08, 0x0A) and parte < 4:
                    d = d[:4] + bytes([canais[parte] + deslocamento]) + d[5:]
                elif bloco == 0x03 and parte < 4 and via_variation:
                    continue
                elif bloco == 0x03 and parte < 4:
                    conexao = b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x03, unidades[parte], 0x0C,
                                               canais[parte] + deslocamento if self.efeito_ligado(parte) else 0x7F, 0xF7])
                    d = d[:4] + bytes([unidades[parte]]) + d[5:]
                    if no_teclado:
                        # na ordem do teclado: o tipo do efeito e logo depois a ligação à parte
                        saida.append(b'\xF0' + d)
                        if parte not in ligados and d[5] == 0x00:
                            ligados.add(parte)
                            saida.append(conexao)
                        continue
                    if parte not in ligados:
                        ligados.add(parte)
                        saida.append(conexao)
                saida.append(b'\xF0' + d)
        if no_teclado and not via_variation:
            # parte do teclado sem efeito no arquivo: desliga o DSP que o OTS anterior deixou ligado a ela
            for p in (0, 1, 3):
                if p not in ligados:
                    saida.append(b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x03, unidades[p], 0x0C, 0x7F, 0xF7]))
        if via_variation:
            saida.extend(self._variation_como_insercao(canais, deslocamento))
        if not no_teclado:
            # nos canais comuns a oitava do OTS é o deslocamento de nota da parte (XG 08 pp 08, 40 = 0, 12 por oitava)
            for parte in range(4):
                saida.append(b'\xF0' + bytes([0x43, 0x10, 0x4C, 0x08, canais[parte] + deslocamento, 0x08,
                                              max(0x28, min(0x58, 0x40 + 12 * self.oitava(parte))), 0xF7]))
        return saida


# Valores de fábrica dos SysEx de Multi Part (08 e 0A) de uma parte do OTS (o que o Voice Creator mostra como padrão)
_SX08_PADRAO = {0x05: 1, 0x0C: 64, 0x0D: 64, 0x1E: 64, 0x20: 10, 0x21: 0, 0x22: 0, 0x4E: 64, 0x50: 0, 0x51: 0, 0x52: 0,
                0x5B: 64, 0x5D: 0, 0x5E: 0, 0x5F: 0, 0x72: 64, 0x73: 64, 0x76: 12, 0x77: 54}
_SX0A_PADRAO = {0x02: 0, 0x03: 0, 0x40: 64, 0x42: 64, 0x44: 64}


def _parte_do_evento(e):
    """Número da parte (0 a 3) a que o evento pertence, ou None se for geral."""
    d = e.dados
    if e.tipo == 'ch':
        return d[0] & 0x0F
    if e.tipo != 'sx':
        return None
    if d[:3] == bytes([0x43, 0x10, 0x4C]) and len(d) >= 6 and d[3] in (0x03, 0x08, 0x0A):
        return d[4]
    if d[:3] == bytes([0x43, 0x73, 0x01]) and len(d) >= 7 and d[3] in (0x50, 0x51) and d[4] == 0x08:
        return d[5]
    if d[:4] == bytes([0x43, 0x10, 0x52, 0x28]) and len(d) >= 7 and d[4] == 0x10:
        return d[5]
    return None


def _clone_para_parte(e, parte):
    d = bytearray(e.dados)
    if e.tipo == 'ch':
        d[0] = (d[0] & 0xF0) | parte
    elif d[:3] == bytes([0x43, 0x10, 0x4C]):
        d[4] = parte
    else:
        d[5] = parte
    return Evento(e.delta, e.tipo, bytes(d), e.tipo_meta)


def _runs(eventos, parte):
    """Trechos contíguos de índices dos eventos da parte."""
    runs, atual = [], []
    for i, e in enumerate(eventos):
        if _parte_do_evento(e) == parte:
            atual.append(i)
        elif atual:
            runs.append(atual)
            atual = []
    if atual:
        runs.append(atual)
    return runs


# (Bank MSB, Bank LSB, Program, Volume) das 4 partes de um OTS novo: piano na Right 1 (ligada); as outras desligadas
_VOZES_PADRAO = ((0, 0, 0, 100), (0, 0, 48, 100), (0, 0, 0, 127), (0, 0, 32, 100))


def _restaurar_padrao(self):
    """Deixa a trilha como um OTS novo: Right 1 ligada com piano, as outras desligadas, sem efeito, tudo nos valores de fábrica.
    Parte da trilha-modelo: as partes 0, 1 e 3 são refeitas como cópias da parte 2, que no modelo está em branco."""
    # fotografa a parte em branco antes de mexer: os índices mudam a cada troca
    origem = [[self.eventos[i] for i in run] for run in _runs(self.eventos, 2)]
    for destino in (0, 1, 3):
        alvo = _runs(self.eventos, destino)
        if len(alvo) != len(origem):
            continue
        # troca de trás para frente para os índices não mudarem
        for run_dest, run_orig in reversed(list(zip(alvo, origem))):
            clones = [_clone_para_parte(e, destino) for e in run_orig]
            self.eventos[run_dest[0]:run_dest[-1] + 1] = clones
    for p, (msb, lsb, pc, vol) in enumerate(_VOZES_PADRAO):
        self.definir_cc(p, 0, msb)
        self.definir_cc(p, 32, lsb)
        self.definir_programa(p, pc)
        self.definir_cc(p, 7, vol)
        self.definir_cc(p, 10, 64)
        self.definir_cc(p, 91, 40)
        self.definir_cc(p, 93, 0)
        self.definir_proprio(p, 0x04, vol)
        self.definir_ligada(p, p == 0)
    self.alterada = True


Trilha.restaurar_padrao = _restaurar_padrao


def secao_padrao(n=4):
    """Uma seção OTSc nova, com `n` One Touch Settings padrão (feitos da trilha-modelo MHS_OtsPadrao)."""
    import MHS_OtsPadrao
    modelo = MHS_OtsPadrao.modelo()
    trilhas = []
    for _ in range(n):
        t = Trilha(modelo)
        t.restaurar_padrao()
        trilhas.append(t.para_bytes())
    corpo = b''.join(trilhas)
    return Secao(b'OTSc' + struct.pack('>I', len(corpo)) + corpo)


def bytes_param_dsp_ao_vivo_(msb, unidade, indice, valor):
    return Trilha.bytes_param_dsp_ao_vivo(msb, unidade, indice, valor)


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
