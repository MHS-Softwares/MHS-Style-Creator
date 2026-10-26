# -*- coding: utf-8 -*-
"""Janela dos One Touch Settings (OTS) de um estilo e o editor do efeito DSP de cada parte.

A janela edita uma cópia da seção OTSc (MHS_Ots.Secao); quem abre (StyleCreatorFrame.abrir_ots) grava o resultado no
estilo quando a janela fecha. Tudo que se muda é mandado na hora para a porta MIDI do OTS (Configurações > MIDI), nos
canais 1 a 4, para ouvir no teclado; a MIDI de entrada passa a tocar nessa porta enquanto a janela está aberta.
"""

import copy
import threading
import time

import mido
import wx

import MHS_Ots as O
from MHS_Utils import (falar, VARIATION_EFEITOS_LIST, DSP_PARAM_NAMES, DSP_PARAM_MAX, DSP_PARAM_OPTIONS, DSP_LONG_PARAM_INDICES,
                       nomes_presets)

# Numerações testadas para as partes comuns (tecla U): (nome, unidades de efeito, deslocamento do número da parte)
VARIANTES = [
    ("unidades do teclado, partes 5 a 8", O.UNIDADE_INSERCAO, 0, False),
    ("unidades 0 a 2, partes 5 a 8", O.UNIDADE_XG_COMUM, 0, False),
    ("unidades 0 a 2, partes da segunda porta, 21 a 24", O.UNIDADE_XG_COMUM, 16, False),
    ("unidades do teclado, partes da segunda porta, 21 a 24", O.UNIDADE_INSERCAO, 16, False),
    ("efeito pelo Variation, partes 5 a 8", O.UNIDADE_XG_COMUM, 0, True),
    ("efeito pelo Variation, partes da segunda porta, 21 a 24", O.UNIDADE_XG_COMUM, 16, True),
]
PROPRIEDADES = ["Volume", "Pan", "Reverb", "Chorus", "Bank", "Patch", "Oitava", "Efeito DSP", "Voice Creator", "Parte ligada"]

# Voice Creator do OTS: (tipo, chave, nome, mínimo, máximo, padrão). tipo 'nrpn' = NRPN 01/chave (como o teclado grava o vibrato e o
# EG no OTS); 'sx8' e 'sx0a' = SysEx XG de Multi Part (blocos 08 e 0A). O Note Shift (08) e o Detune (09) ficam de fora: a oitava
# tem propriedade própria e o Detune usa dois SysEx.
_NRPN_VC = [
    ('nrpn', 0x08, "Vibrato Rate (LFO Velocidade)", 0, 127, 64),
    ('nrpn', 0x09, "Vibrato Depth (LFO Intensidade)", 0, 127, 64),
    ('nrpn', 0x0A, "Vibrato Delay (LFO Atraso)", 0, 127, 64),
    ('nrpn', 0x64, "EG Decay Time (Tempo de Queda)", 0, 127, 64),
    ('nrpn', 0x66, "EG Release Time (Tempo de Relaxamento - o sustain)", 0, 127, 64),
]
_SX_EXTRAS = [
    (0x72, "EQ Bass Gain (Ganho do Grave)", 0, 127, 64),
    (0x73, "EQ Treble Gain (Ganho do Agudo)", 0, 127, 64),
]


# endereço do SysEx de Multi Part que cada NRPN faz o papel de (para a lista seguir a ordem da janela principal)
_ENDERECO_DO_NRPN = {0x08: 0x15, 0x09: 0x16, 0x0A: 0x17, 0x64: 0x1B, 0x66: 0x1C}


def parametros_voice_creator():
    from MHS_Dialogs import VOICE_CREATOR_PARAMS, VOICE_CREATOR_PARAMS_0A
    duplicados = {0x08, 0x09, 0x15, 0x16, 0x17, 0x1B, 0x1C}        # os NRPN acima (ou propriedade própria) fazem o papel deles
    itens = list(_NRPN_VC)
    itens += [('sx8', a, n, lo, hi, pd) for (a, n, lo, hi, pd) in VOICE_CREATOR_PARAMS if a not in duplicados]
    itens += [('sx8', a, n, lo, hi, pd) for (a, n, lo, hi, pd) in _SX_EXTRAS]
    itens += [('sx0a', a, n, lo, hi, pd) for (a, n, lo, hi, pd) in VOICE_CREATOR_PARAMS_0A]

    def ordem(item):
        tipo, chave = item[0], item[1]
        if tipo == 'nrpn':
            return _ENDERECO_DO_NRPN.get(chave, chave)
        return chave if tipo == 'sx8' else 0x1000 + chave
    return sorted(itens, key=ordem)
_CC = {"Volume": 7, "Pan": 10, "Reverb": 91, "Chorus": 93}
NOMES_EFEITO = {msb: nome.split(" - ", 1)[-1] for nome, msb in VARIATION_EFEITOS_LIST}
NOMES_EFEITO[O.TIPO_SEM_EFEITO] = "Sem efeito (Thru)"


def nome_do_efeito(msb, lsb):
    if msb == O.TIPO_SEM_EFEITO:
        return NOMES_EFEITO[msb]
    nome = NOMES_EFEITO.get(msb, f"Efeito {msb}")
    presets = nomes_presets(msb) if msb in DSP_PARAM_NAMES else []
    if lsb < len(presets) and " - " in presets[lsb]:
        return f"{nome}, {presets[lsb].split(' - ', 1)[1]}"
    return f"{nome}, preset {lsb}"


def _msg(dados):
    # bytes -> mido.Message, ou None se tiver byte inválido (o 0xFF de "parâmetro sem valor" não pode ir pelo cabo)
    try:
        return mido.Message.from_bytes(list(dados))
    except Exception:
        return None


class OtsDialog(wx.Dialog):
    def __init__(self, frame, secao, ots=0):
        super().__init__(frame, title="One Touch Settings (OTS)", size=(760, 430))
        self.frame = frame
        self.secao = secao
        self.ots = max(0, min(len(secao.trilhas) - 1, ots))
        self.prop = 0
        self._geracao = 0
        # tecla M: 0 = híbrido (a Right 1 como parte do teclado na porta principal, com o DSP; as outras em canais comuns da porta
        # do OTS); 1 = todas as partes em canais comuns da porta do OTS
        self.modo = 0
        self.canais = O.CANAIS_COMUNS
        self._ultima_troca_de_timbre = 0.0        # quando o teclado mandou o último Program Change (a captura do DSP vem logo depois)
        self._ultima_troca_parte = 0              # parte do teclado (canal) que recebeu esse Program Change
        self._notas_ativas = {}                   # (parte, nota tocada) -> nota enviada (a oitava da parte pode mudar com a nota soando)
        self._dsp_do_teclado = {}                 # unidade -> o efeito que o teclado está montando (tipo, parâmetros, ligação)
        self._dsp_timer = None
        self.variante = 2                      # tecla U: numeração das unidades de efeito e das partes (VARIANTES)
        v = wx.BoxSizer(wx.VERTICAL)
        self.rotulo = wx.StaticText(self, label=self._texto_titulo())
        v.Add(self.rotulo, 0, wx.ALL, 10)
        v.Add(wx.StaticText(self, label="&Partes (Cima e Baixo escolhem a parte, Esquerda e Direita a propriedade, + e - mudam, "
                                        "Enter digita, L liga e desliga a parte, D abre o efeito DSP, V abre o Voice Creator da parte, 1 a 4 enviam o OTS ao teclado, S reenvia, "
                                        "Espaço toca a variação, a numeração das unidades de efeito, G liga e desliga o registro de MIDI de entrada, Esc fecha e aplica):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, choices=[self._texto_linha(i) for i in range(4)], name="Partes do OTS")
        self.lista.SetSelection(0)
        v.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        self.btn_ok = wx.Button(self, wx.ID_OK, label="&Aplicar e fechar")
        v.Add(self.btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(v)
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.lista.Bind(wx.EVT_LISTBOX, self._ao_escolher_parte)
        wx.CallLater(100, self.lista.SetFocus)
        porta_nome = frame.config.get("midi_out_ots") or "a porta principal"
        reparadas = secao.reparar_dsp_proprio()
        aviso = (f"{reparadas} efeito{'s' if reparadas != 1 else ''} DSP deste estilo foram corrigidos para o teclado carregar. "
                 if reparadas else "")
        falar(f"One Touch Settings. OTS {self.ots + 1}, {self._nome_variacao()}. Porta do OTS: {porta_nome}. {aviso}"
              f"{self._resumo_ligadas()} {self._texto_linha(0)}", imediato=True)

    # ------------------------------------------------------------ texto
    def _nome_variacao(self):
        return "Main " + "ABCD"[self.ots] if self.ots < 4 else f"OTS {self.ots + 1}"

    def _texto_titulo(self):
        return f"OTS {self.ots + 1} ({self._nome_variacao()}) - {len(self.secao.trilhas)} OTS neste estilo"

    @property
    def trilha(self):
        return self.secao.trilhas[self.ots]

    def _banco_id(self, i):
        msb, lsb = self.trilha.banco(i)
        return msb * 128 + lsb

    def _valor_texto(self, i, prop):
        t = self.trilha
        if prop in _CC:
            return str(t.cc(i, _CC[prop], 0))
        if prop == "Bank":
            banco = self._banco_id(i)
            nome = getattr(self.frame, 'bank_names', {}).get(banco, "")
            return f"{banco} ({nome.replace('PSR-SX600 ', '')})" if nome else str(banco)
        if prop == "Patch":
            prog = t.programa(i)
            nome = getattr(self.frame, 'ins_db', {}).get(self._banco_id(i), {}).get(prog, f"Patch {prog}")
            return nome.replace('PSR-SX600 ', '')
        if prop == "Oitava":
            o = t.oitava(i)
            return f"{o:+d}" if o else "0"
        if prop == "Efeito DSP":
            d = t.dsp(i)
            return nome_do_efeito(d['msb'], d['lsb']) if d and d['msb'] != O.TIPO_SEM_EFEITO else "sem efeito (Enter escolhe um)"
        if prop == "Voice Creator":
            return "Enter ou V abre os parâmetros do timbre"
        if prop == "Parte ligada":
            return "sim" if t.ligada(i) else "não"
        return ""

    def _resumo_ligadas(self):
        nomes = [O.PARTES[i] for i in range(4) if self.trilha.ligada(i)]
        return "Partes ligadas: " + (", ".join(nomes) if nomes else "nenhuma") + "."

    def _texto_linha(self, i):
        prop = PROPRIEDADES[self.prop]
        ligada = "" if self.trilha.ligada(i) else " (desligada)"
        return f"{O.PARTES[i]}{ligada}  |  {prop} {self._valor_texto(i, prop)}"

    def _falar_prop(self, i):
        """A fala de quem muda de propriedade ou de valor: só a propriedade e o valor, uma vez (a parte só é dita ao subir e descer)."""
        prop = PROPRIEDADES[self.prop]
        falar(f"{prop} {self._valor_texto(i, prop)}", imediato=True)

    def _atualizar_linha(self, i):
        texto = self._texto_linha(i)
        if self.lista.GetString(i) != texto:
            self.lista.SetString(i, texto)
            self.lista.SetSelection(i)

    def _atualizar_todas(self):
        self.rotulo.SetLabel(self._texto_titulo())
        for i in range(4):
            self.lista.SetString(i, self._texto_linha(i))

    # ------------------------------------------------------------ porta e envio
    @property
    def hibrido(self):
        return self.modo == 0

    def destino(self, i):
        """(principal, canal, parte XG, é parte do teclado) da parte i do OTS."""
        if self.hibrido and self.trilha.no_teclado(i):
            return True, O.CANAIS_TECLADO[i], O.CANAIS_TECLADO[i], True
        return False, self.canais[i], self.canais[i] + self.deslocamento, False

    @property
    def unidades(self):
        return VARIANTES[self.variante][1]

    @property
    def deslocamento(self):
        return VARIANTES[self.variante][2]

    @property
    def via_variation(self):
        return self.modo == 1 and VARIANTES[self.variante][3]

    def parte_xg(self, i):
        # número da parte nos SysEx XG (e na ligação do efeito) da parte i do OTS
        return self.destino(i)[2]

    def _porta(self, principal=False):
        return self.frame.midi_out if principal else self.frame.porta_ots()

    def _enviar(self, *mensagens, principal=False):
        porta = self._porta(principal)
        if porta is None:
            return
        for m in mensagens:
            if m is None:
                continue
            try:
                porta.send(m)
            except Exception:
                pass

    def _enviar_param(self, i, prop):
        t = self.trilha
        principal, canal, parte_xg, teclado = self.destino(i)
        if prop in _CC:
            self._enviar(mido.Message('control_change', channel=canal, control=_CC[prop], value=t.cc(i, _CC[prop], 0)), principal=principal)
        elif prop in ("Bank", "Patch"):
            msb, lsb = t.banco(i)
            self._enviar(mido.Message('control_change', channel=canal, control=0, value=msb),
                         mido.Message('control_change', channel=canal, control=32, value=lsb),
                         mido.Message('program_change', channel=canal, program=t.programa(i)), principal=principal)
        elif prop == "Parte ligada":
            pass            # as partes do teclado ficam sempre ligadas no teclado: quem decide quem toca é o eco do programa
        elif prop == "Oitava":
            # Right 1: deslocamento de nota da parte (XG 08 pp 08: 40 = 0, 12 por oitava), que é por parte, ao contrário da mensagem
            # própria da Yamaha (43 73 ... 03), que no teclado mexia na oitava de todas as partes. As outras partes não obedecem ao
            # Note Shift: a oitava delas o programa faz nas notas tocadas (_nota_da_parte).
            if i == 0:
                self._enviar(_msg([0xF0, 0x43, 0x10, 0x4C, 0x08, parte_xg, 0x08, max(0x28, min(0x58, 0x40 + 12 * t.oitava(i))), 0xF7]),
                             principal=principal)

    def enviar_ots(self, n=None):
        """Manda o OTS atual inteiro (canais 1 a 4) para a porta do OTS, sem travar a janela."""
        self._geracao += 1
        minha = self._geracao
        if self.hibrido:
            tec, com = self.trilha.mensagens_hibrido(self.canais, self.deslocamento)
            mensagens = [(True, _msg(b)) for b in tec] + [(False, _msg(b)) for b in com]
        else:
            mensagens = [(False, _msg(b)) for b in
                         self.trilha.mensagens_para_enviar(self.canais, self.unidades, self.deslocamento, self.via_variation)]
        mensagens = [(p, m) for p, m in mensagens if m is not None]
        portas = {True: self._porta(True), False: self._porta(False)}
        if portas[False] is None or (self.hibrido and portas[True] is None):
            falar("Nenhuma porta MIDI para o OTS. Escolha uma em Configurações, MIDI.", imediato=True)
            return

        def trabalho():
            for k, (principal, m) in enumerate(mensagens):
                if self._geracao != minha:
                    return
                try:
                    portas[principal].send(m)
                except Exception:
                    return
                if k % 16 == 15:
                    time.sleep(0.004)
        threading.Thread(target=trabalho, daemon=True).start()

    def _destinos_do_eco(self):
        t = self.trilha
        partes = [i for i in range(4) if t.ligada(i)] or [0]
        return [(i,) + self.destino(i)[:2] for i in partes]

    def _nota_da_parte(self, i, msg):
        """A nota que vai à parte i: a tocada mais 12 por oitava da parte (a Right 1 faz a oitava no teclado, pelo Note Shift XG).
        O desligar de uma nota usa a mesma nota do ligar, mesmo que a oitava mude no meio. None se sair da faixa de 0 a 127."""
        desloc = 0 if i == 0 else 12 * self.trilha.oitava(i)
        chave = (i, msg.note)
        if msg.type == 'note_on' and msg.velocity > 0:
            nota = msg.note + desloc
            if 0 <= nota <= 127:
                self._notas_ativas[chave] = nota
        elif msg.type in ('note_on', 'note_off'):
            nota = self._notas_ativas.pop(chave, msg.note + desloc)
        else:
            nota = self._notas_ativas.get(chave, msg.note + desloc)
        return nota if 0 <= nota <= 127 else None

    def _timbre_do_teclado(self, msg):
        # Trocar o timbre no teclado (Bank e Program Change) muda o timbre da parte escolhida na lista
        i = self.lista.GetSelection()
        if i < 0:
            i = 0
        t = self.trilha
        if msg.type == 'control_change':
            if msg.control == 0:
                t.definir_cc(i, 0, msg.value)
            else:
                t.definir_cc(i, 32, msg.value)
            return
        t.definir_programa(i, msg.program)
        self._ultima_troca_de_timbre = time.time()
        self._ultima_troca_parte = getattr(msg, 'channel', 0)
        self._enviar_param(i, "Patch")
        falar(f"Bank {self._valor_texto(i, 'Bank')}, {self._valor_texto(i, 'Patch')}", imediato=True)

    def _dsp_do_timbre(self, dados):
        """SysEx de efeito que o teclado manda ao trocar de timbre: a Inserção (43 10 4C 03 nn ...) e o Variation (43 10 4C 02 01 ...).
        Junta tipo, parâmetros e ligação de cada bloco; quando a rajada acaba, o efeito que está ligado à parte do teclado que
        trocou de timbre vai para a parte escolhida na lista, junto do timbre."""
        if time.time() - self._ultima_troca_de_timbre > 3.0 or len(dados) < 7:
            return
        if dados[3] == 0x02 and dados[4] == 0x01:
            chave, endereco, variation = ('v', 0), dados[5], True
        elif dados[3] == 0x03:
            chave, endereco, variation = ('i', dados[4]), dados[5], False
        else:
            return
        b = self._dsp_do_teclado.setdefault(chave, {'msb': None, 'lsb': 0, 'p': [-1] * 16, 'ligacao': None, 'sistema': False})
        if variation:
            if endereco == 0x40 and len(dados) >= 8:
                b['msb'], b['lsb'] = dados[6], dados[7]
            elif endereco == 0x5B:
                b['ligacao'] = dados[6]
            elif endereco == 0x5A:
                b['sistema'] = dados[6] == 1            # ligado em SYSTEM: vale para todas as partes, não é deste timbre
            elif 0x42 <= endereco <= 0x54 and endereco % 2 == 0 and len(dados) >= 8:
                b['p'][(endereco - 0x42) // 2] = dados[6] * 128 + dados[7]
            elif 0x70 <= endereco <= 0x75:
                b['p'][10 + endereco - 0x70] = dados[6]
        else:
            if endereco == 0x00 and len(dados) >= 8:
                b['msb'], b['lsb'] = dados[6], dados[7]
            elif endereco == 0x0C:
                b['ligacao'] = dados[6]
            elif 0x30 <= endereco <= 0x4E and endereco % 2 == 0 and len(dados) >= 8:
                b['p'][(endereco - 0x30) // 2] = dados[6] * 128 + dados[7]
            elif 0x02 <= endereco <= 0x0B:
                b['p'][endereco - 0x02] = dados[6]
            elif 0x20 <= endereco <= 0x25:
                b['p'][10 + endereco - 0x20] = dados[6]
        if self._dsp_timer is not None:
            try:
                self._dsp_timer.Stop()
            except Exception:
                pass
        self._dsp_timer = wx.CallLater(350, self._aplicar_dsp_do_timbre)

    def _efeito_da_parte_que_trocou(self, efeitos):
        """O bloco ligado à parte do teclado que trocou de timbre (nunca o de outra parte, que o teclado manda na mesma rajada).
        Devolve (bloco, desligou): `desligou` quando o teclado soltou o efeito dessa parte."""
        parte = self._ultima_troca_parte
        proprios = [b for b in efeitos.values() if b['msb'] is not None and b['ligacao'] == parte and not b['sistema']]
        if proprios:
            return proprios[-1], False
        # nenhum efeito ligado a essa parte: se o teclado soltou uma unidade (ligação 7F), o timbre ficou sem efeito
        return None, any(b['ligacao'] == 0x7F for b in efeitos.values())

    def _aplicar_dsp_do_timbre(self):
        efeitos, self._dsp_do_teclado = self._dsp_do_teclado, {}
        self._dsp_timer = None
        i = self.lista.GetSelection()
        if i < 0:
            i = 0
        t = self.trilha
        b, desligou = self._efeito_da_parte_que_trocou(efeitos)
        if b is not None:
            if b['msb'] == O.TIPO_SEM_EFEITO:
                t.definir_dsp(i, O.TIPO_SEM_EFEITO, 0, [-1] * 9 + [0] + [-1] * 6, limpar=True)
                t.definir_proprio(i, 0x08, 0)
                texto = "sem efeito DSP"
            else:
                padrao = O.parametros_padrao_dsp(b['msb'], b['lsb'])
                completo = [b['p'][k] if b['p'][k] >= 0 else padrao[k] for k in range(16)]      # o teclado manda só parte deles
                t.definir_dsp(i, b['msb'], b['lsb'], completo, limpar=True)
                t.definir_proprio(i, 0x08, 127)
                texto = nome_do_efeito(b['msb'], b['lsb'])
        elif desligou and t.efeito_ligado(i):
            t.definir_proprio(i, 0x08, 0)       # o teclado desligou o efeito deste timbre
            texto = "sem efeito DSP"
        else:
            return
        falar(f"Efeito DSP, {texto}", imediato=True)
        self.enviar_ots()           # a parte pode ter mudado de caminho (teclado ou canal comum)

    def handle_midi_in(self, msg):
        # Enquanto a janela está aberta o motor MIDI desvia a MIDI de entrada para cá: o que se toca sai pela porta do
        # OTS, nas partes da mão direita que estão ligadas neste OTS (ou na Right 1, se nenhuma estiver).
        if msg.type == 'sysex' and (tuple(msg.data[:4]) == (0x43, 0x10, 0x4C, 0x03) or tuple(msg.data[:5]) == (0x43, 0x10, 0x4C, 0x02, 0x01)):
            self._dsp_do_timbre(tuple(msg.data))
            return
        if msg.type == 'program_change' or (msg.type == 'control_change' and msg.control in (0, 32)):
            self._timbre_do_teclado(msg)
            return
        if msg.type in ('note_on', 'note_off', 'polytouch'):
            for i, principal, ch in self._destinos_do_eco():
                nota = self._nota_da_parte(i, msg)
                if nota is not None:
                    self._enviar(msg.copy(channel=ch, note=nota), principal=principal)
            return
        if msg.type in ('aftertouch', 'pitchwheel') or \
                (msg.type == 'control_change' and msg.control in (1, 11, 64, 66, 67)):
            for i, principal, ch in self._destinos_do_eco():
                self._enviar(msg.copy(channel=ch), principal=principal)

    # ------------------------------------------------------------ edição
    def _alterar(self, delta):
        i = self.lista.GetSelection()
        if i < 0:
            return
        prop = PROPRIEDADES[self.prop]
        t = self.trilha
        if prop in _CC:
            t.definir_cc(i, _CC[prop], max(0, min(127, t.cc(i, _CC[prop], 0) + delta)))
        elif prop == "Bank":
            novo = max(0, min(16383, self._banco_id(i) + delta))
            t.definir_cc(i, 0, novo // 128)
            t.definir_cc(i, 32, novo % 128)
        elif prop == "Patch":
            t.definir_programa(i, max(0, min(127, t.programa(i) + delta)))
        elif prop == "Oitava":
            t.definir_oitava(i, max(-3, min(3, t.oitava(i) + delta)))
        elif prop == "Parte ligada":
            t.definir_ligada(i, delta > 0)
        else:
            falar("Aperte Enter para editar o efeito DSP desta parte.", imediato=True)
            return
        self._enviar_param(i, prop)
        self._falar_prop(i)

    def _digitar(self):
        i = self.lista.GetSelection()
        prop = PROPRIEDADES[self.prop]
        if i < 0:
            return
        if prop == "Efeito DSP":
            self.abrir_dsp()
            return
        if prop == "Voice Creator":
            self.abrir_voice_creator()
            return
        if prop == "Parte ligada":
            self.trilha.definir_ligada(i, not self.trilha.ligada(i))
            self._enviar_param(i, prop)
            self._falar_prop(i)
            return
        t = self.trilha
        if prop in _CC:
            atual, minimo, maximo = t.cc(i, _CC[prop], 0), 0, 127
        elif prop == "Bank":
            atual, minimo, maximo = self._banco_id(i), 0, 16383
        elif prop == "Patch":
            atual, minimo, maximo = t.programa(i) + 1, 1, 128
        else:
            atual, minimo, maximo = t.oitava(i), -3, 3
        dlg = wx.TextEntryDialog(self, f"{prop} da parte {O.PARTES[i]} ({minimo} a {maximo}):", f"Editar {prop}", str(atual))
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            try:
                novo = max(minimo, min(maximo, int(dlg.GetValue().strip())))
            except ValueError:
                falar(f"Digite um número de {minimo} a {maximo}.", imediato=True)
                return
        finally:
            dlg.Destroy()
        if prop in _CC:
            t.definir_cc(i, _CC[prop], novo)
        elif prop == "Bank":
            t.definir_cc(i, 0, novo // 128)
            t.definir_cc(i, 32, novo % 128)
        elif prop == "Patch":
            t.definir_programa(i, novo - 1)
        else:
            t.definir_oitava(i, novo)
        self._enviar_param(i, prop)
        self._falar_prop(i)
        wx.CallLater(100, self.lista.SetFocus)

    def abrir_voice_creator(self):
        i = self.lista.GetSelection()
        if i < 0:
            return
        dlg = OtsVoiceDialog(self, self.trilha, i)
        try:
            ok = dlg.ShowModal() == wx.ID_OK
        finally:
            dlg.Destroy()
        if not ok:
            self.enviar_ots()          # descartou: o teclado volta ao timbre que a parte tinha
        wx.CallLater(100, self.lista.SetFocus)

    def abrir_dsp(self):
        """Igual ao Efeito de Inserção da janela principal: primeiro o efeito e o preset da parte escolhida na lista, depois os
        parâmetros (Tab anda, setas mudam, Enter confirma, Esc cancela e volta ao que estava)."""
        i = self.lista.GetSelection()
        if i < 0:
            return
        escolha = OtsDspEscolherDialog(self, self.trilha, i)
        try:
            ok = escolha.ShowModal() == wx.ID_OK
            msb, lsb = escolha.get_valores()
        finally:
            escolha.Destroy()
        if ok:
            editor = OtsDspEditorDialog(self, self.trilha, i, msb, lsb)
            try:
                editor.ShowModal()
                self._atualizar_linha(i)        # com a tela ainda aberta, para o leitor ler a linha só quando o foco voltar
            finally:
                editor.Destroy()
            self.enviar_ots()          # escolher ou tirar o efeito muda por onde a parte vai (teclado ou canal comum)
        wx.CallLater(100, self.lista.SetFocus)

    def trocar_ots(self, numero):
        if not 1 <= numero <= len(self.secao.trilhas):
            falar(f"Este estilo tem só {len(self.secao.trilhas)} OTS.", imediato=True)
            return
        self.ots = numero - 1
        self._atualizar_todas()
        self.enviar_ots()
        i = max(0, self.lista.GetSelection())
        falar(f"OTS {numero}, {self._nome_variacao()}, enviado ao teclado. {self._resumo_ligadas()}", imediato=True)

    # ------------------------------------------------------------ teclas
    def _ao_escolher_parte(self, event):
        i = self.lista.GetSelection()
        if i >= 0:
            self._atualizar_linha(i)

    def _tecla(self, event):
        k = event.GetKeyCode()
        if event.ControlDown() or event.AltDown():
            event.Skip()
            return
        foco = self.FindFocus()
        if foco is not self.lista and foco is not None and not isinstance(foco, wx.Button):
            event.Skip()
            return
        if k == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK)
            return
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and foco is self.lista:
            self._digitar()
            return
        if foco is not self.lista:
            event.Skip()
            return
        if k in (wx.WXK_LEFT, wx.WXK_RIGHT):
            # como na janela principal: não mexe em nenhuma linha da lista, só fala a propriedade e o valor (uma vez); a linha de
            # destino é atualizada antes de Cima/Baixo chegarem nela
            novo = self.prop + (1 if k == wx.WXK_RIGHT else -1)
            if 0 <= novo < len(PROPRIEDADES):
                self.prop = novo
                self._falar_prop(max(0, self.lista.GetSelection()))
            return
        if k in (wx.WXK_ADD, wx.WXK_NUMPAD_ADD) or k == ord('='):
            self._alterar(10 if event.ShiftDown() else 1)
            return
        if k in (wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT) or k == ord('-'):
            self._alterar(-10 if event.ShiftDown() else -1)
            return
        if k in (wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
            self._alterar(10 if k == wx.WXK_PAGEUP else -10)
            return
        if k == wx.WXK_SPACE:
            self.frame.OnTogglePlay(None)
            return
        if ord('1') <= k <= ord('4') or wx.WXK_NUMPAD1 <= k <= wx.WXK_NUMPAD4:
            self.trocar_ots(k - ord('1') + 1 if k <= ord('9') else k - wx.WXK_NUMPAD1 + 1)
            return
        if k == ord('D'):
            self.abrir_dsp()
            return
        if k == ord('V'):
            self.abrir_voice_creator()
            return
        if k == ord('L'):
            i = self.lista.GetSelection()
            if i >= 0:
                self.trilha.definir_ligada(i, not self.trilha.ligada(i))
                self._enviar_param(i, "Parte ligada")
                falar(f"{'Ligada' if self.trilha.ligada(i) else 'Desligada'}. {self._resumo_ligadas()}", imediato=True)
            return
        if k == ord('G'):
            # o menu não abre com esta janela aberta: liga/desliga o registro de MIDI de entrada (midi_in_log.txt)
            self.frame.OnToggleMidiLog(None)
            return
        if k == ord('S'):
            self.enviar_ots()
            falar(f"OTS {self.ots + 1} reenviado ao teclado.", imediato=True)
            return
        if k in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME, wx.WXK_END):
            # atualiza só a linha de destino ANTES de o leitor de tela lê-la (como a lista de canais da janela principal): o leitor
            # fala a linha inteira, com o nome da parte, uma vez
            i = self.lista.GetSelection()
            if k == wx.WXK_HOME:
                alvo = 0
            elif k == wx.WXK_END:
                alvo = 3
            else:
                alvo = max(0, min(3, i + (1 if k == wx.WXK_DOWN else -1)))
            if alvo != i or self.lista.GetString(alvo) != self._texto_linha(alvo):
                self.lista.SetString(alvo, self._texto_linha(alvo))
        event.Skip()


class OtsVoiceDialog(wx.Dialog):
    """Voice Creator de uma parte do OTS, igual ao da janela principal e ao do MIDI Sequencer: um campo para cada parâmetro do timbre
    (Tab anda, as setas mudam 1, Home vai ao máximo, End ao mínimo, PageUp e PageDown mudam 6, ou 12 nos de faixa maior). Cada mudança
    toca na hora no teclado. Enter confirma e fecha; Esc descarta e a parte volta ao timbre que tinha."""

    def __init__(self, pai, trilha, parte):
        super().__init__(pai, title=f"Voice Creator (Synth Pro) - {O.PARTES[parte]}", size=(450, 750))
        self.pai, self.trilha, self.parte = pai, trilha, parte
        self.foto = (copy.deepcopy(trilha.eventos), trilha.alterada)       # para o Esc desfazer o que se fez aqui
        self.itens = parametros_voice_creator()
        self.modulos = []
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scr.SetScrollRate(0, 20)
        sz = wx.BoxSizer(wx.VERTICAL)
        for n, (_tipo, _chave, nome, lo, hi, _pd) in enumerate(self.itens):
            sz.Add(wx.StaticText(scr, label=f"{nome}:"), 0, wx.LEFT | wx.TOP, 10)
            sl = wx.SpinCtrl(scr, value=str(max(lo, min(hi, self._valor(n)))), min=lo, max=hi, name=nome)
            sl.Bind(wx.EVT_SPINCTRL, lambda e, n=n, sl=sl: self._mudou(n, sl.GetValue()))
            sz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            self.modulos.append(sl)
        scr.SetSizer(sz)
        vbox.Add(scr, 1, wx.EXPAND | wx.ALL, 5)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        # ids próprios: um botão com wx.ID_OK/ID_CANCEL fecha por fora do nosso tratamento de teclas
        self.btn_ok = wx.Button(panel, wx.ID_ANY, "Fechar e Manter")
        self.btn_cancel = wx.Button(panel, wx.ID_ANY, "Cancelar")
        botoes.Add(self.btn_ok, 0, wx.ALL, 5)
        botoes.Add(self.btn_cancel, 0, wx.ALL, 5)
        vbox.Add(botoes, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)
        self.btn_ok.Bind(wx.EVT_BUTTON, lambda e: self.confirmar())
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: self.cancelar())
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.Bind(wx.EVT_CLOSE, lambda e: self.cancelar())
        wx.CallLater(100, self.modulos[0].SetFocus)

    def _valor(self, n):
        tipo, chave, _nome, _lo, _hi, padrao = self.itens[n]
        if tipo == 'nrpn':
            return self.trilha.nrpn(self.parte, chave, padrao)
        return self.trilha.sx(self.parte, 0x08 if tipo == 'sx8' else 0x0A, chave, padrao)

    def _gravar(self, n, valor):
        tipo, chave = self.itens[n][0], self.itens[n][1]
        if tipo == 'nrpn':
            self.trilha.definir_nrpn(self.parte, chave, valor)
        else:
            self.trilha.definir_sx(self.parte, 0x08 if tipo == 'sx8' else 0x0A, chave, valor)

    def _enviar(self, n):
        tipo, chave = self.itens[n][0], self.itens[n][1]
        valor = self._valor(n)
        principal, canal, parte_xg, _teclado = self.pai.destino(self.parte)
        if tipo == 'nrpn':
            msgs = [mido.Message('control_change', channel=canal, control=99, value=1),
                    mido.Message('control_change', channel=canal, control=98, value=chave),
                    mido.Message('control_change', channel=canal, control=6, value=valor)]
            if chave == 0x66:                      # o release também vai no CC 72, que é como o teclado o transmite
                msgs.append(mido.Message('control_change', channel=canal, control=72, value=valor))
            self.pai._enviar(*msgs, principal=principal)
        else:
            self.pai._enviar(_msg([0xF0, 0x43, 0x10, 0x4C, 0x08 if tipo == 'sx8' else 0x0A, parte_xg, chave, valor, 0xF7]), principal=principal)

    def _mudou(self, n, valor):
        if valor == self._valor(n):
            return
        self._gravar(n, valor)
        self._enviar(n)

    def _ler_campos(self):
        # lê o valor de cada campo na hora de fechar (digitar um número e dar Tab nem sempre dispara o evento do campo)
        foco = self.FindFocus()
        if foco is not None and foco is not self.btn_ok:
            self.btn_ok.SetFocus()
        for n, sl in enumerate(self.modulos):
            self._mudou(n, sl.GetValue())

    def confirmar(self):
        self._ler_campos()
        falar("Timbre salvo na parte.", imediato=True)
        self.EndModal(wx.ID_OK)

    def cancelar(self):
        self.trilha.eventos[:] = self.foto[0]
        self.trilha.alterada = self.foto[1]
        falar("Alterações de timbre descartadas.", imediato=True)
        self.EndModal(wx.ID_CANCEL)

    def _tecla(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_ESCAPE:
            self.cancelar()
            return
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.FindFocus() is self.btn_cancel:
                self.cancelar()
            else:
                self.confirmar()
            return
        if k in (wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
            foco = self.FindFocus()
            if isinstance(foco, wx.SpinCtrl) and foco in self.modulos:
                val, v_min, v_max = foco.GetValue(), foco.GetMin(), foco.GetMax()
                passo = 6 if v_max <= 127 else 12
                if k == wx.WXK_HOME:
                    val = v_max
                elif k == wx.WXK_END:
                    val = v_min
                elif k == wx.WXK_PAGEUP:
                    val = min(v_max, val + passo)
                else:
                    val = max(v_min, val - passo)
                foco.SetValue(val)
                self._mudou(self.modulos.index(foco), val)
                falar(str(val), imediato=True)
                return
        event.Skip()


def _gravar_dsp(trilha, parte, msb, lsb, p, limpar=False):
    trilha.definir_dsp(parte, msb, lsb, p, limpar=limpar)
    # o teclado liga o efeito de inserção da parte ao gravar um OTS com efeito (e o desliga sem efeito)
    trilha.definir_proprio(parte, 0x08, 127 if msb != O.TIPO_SEM_EFEITO else 0)


def _enviar_dsp(pai, trilha, parte, msb, lsb, p, k=None):
    """Manda ao teclado o efeito da parte (k=None: tipo e ligação) ou só o parâmetro k."""
    if pai.hibrido and not pai.destino(parte)[3]:
        return                      # só o DSP das partes que vão como partes do teclado chega ao teclado
    if pai.hibrido and msb != O.TIPO_SEM_EFEITO:
        # só o "DSP ligado"; o desligado não vai (a mensagem própria age como global no teclado): tirar o efeito desliga a unidade
        pai._enviar(_msg([0xF0, 0x43, 0x73, 0x01, 0x50, 0x08, parte, 0x08, 127, 0xF7]), principal=True)
    if pai.via_variation:
        pai._enviar(*[_msg(list(b)) for b in trilha._variation_como_insercao(pai.canais, pai.deslocamento)])
        return
    unidade = O.UNIDADE_INSERCAO[parte] if pai.hibrido else pai.unidades[parte]
    if k is None:
        tipo = _msg([0xF0, 0x43, 0x10, 0x4C, 0x03, unidade, 0x00, msb, lsb, 0xF7])
        ligacao = _msg([0xF0, 0x43, 0x10, 0x4C, 0x03, unidade, 0x0C, pai.parte_xg(parte) if msb != O.TIPO_SEM_EFEITO else 0x7F, 0xF7])
        if pai.hibrido:
            pai._enviar(tipo, ligacao, principal=True)     # ordem do teclado: tipo e depois a ligação
        else:
            pai._enviar(ligacao, tipo)
    else:
        pai._enviar(_msg(list(O.Trilha.bytes_param_dsp_ao_vivo(msb, unidade, k, p[k]))), principal=pai.hibrido)


class _TeclasDsp(object):
    """Enter, Esc, Espaço e Home/End/PageUp/PageDown dos campos de número, como nas telas de DSP da janela principal."""

    def _espaco(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_SPACE and not event.AltDown() and not event.ShiftDown():
            frame = self.pai.frame
            (frame.OnTogglePause if event.ControlDown() else frame.OnTogglePlay)(None)
            return True
        return False

    def _numero(self, event, ao_mudar):
        obj = self.FindFocus()
        if not isinstance(obj, wx.SpinCtrl):
            return False
        k = event.GetKeyCode()
        val, max_v, min_v = obj.GetValue(), obj.GetMax(), obj.GetMin()
        passo = 100 if max_v > 127 else 10
        if k == wx.WXK_HOME:
            val = max_v
        elif k == wx.WXK_END:
            val = min_v
        elif k in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP):
            val = min(max_v, val + passo)
        elif k in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN):
            val = max(min_v, val - passo)
        else:
            return False
        obj.SetValue(val)
        ao_mudar(obj)
        return True


class OtsDspEscolherDialog(_TeclasDsp, wx.Dialog):
    """Passo 1 do efeito DSP de uma parte do OTS: a família do efeito e o preset. A "gaveta" é a parte que estava escolhida na lista."""

    def __init__(self, pai, trilha, parte):
        super().__init__(pai, title=f"Efeito DSP - {O.PARTES[parte]}", size=(420, 330))
        self.pai, self.trilha, self.parte = pai, trilha, parte
        d = trilha.dsp(parte) or {'msb': O.TIPO_SEM_EFEITO, 'lsb': 0}
        self.nomes = [NOMES_EFEITO[O.TIPO_SEM_EFEITO]] + [n for n, _ in VARIATION_EFEITOS_LIST]
        self.msbs = [O.TIPO_SEM_EFEITO] + [m for _, m in VARIATION_EFEITOS_LIST]
        v = wx.BoxSizer(wx.VERTICAL)
        v.Add(wx.StaticText(self, label="1. Família do Efeito:"), 0, wx.ALL, 5)
        self.cb_msb = wx.Choice(self, choices=self.nomes, name="Família do Efeito")
        v.Add(self.cb_msb, 0, wx.EXPAND | wx.ALL, 5)
        v.Add(wx.StaticText(self, label="2. Preset (Variação):"), 0, wx.ALL, 5)
        self.cb_lsb = wx.Choice(self, choices=[], name="Preset")
        v.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)
        self.lsb_original = d['lsb']
        atual = self.msbs.index(d['msb']) if d['msb'] in self.msbs else 0
        self.cb_msb.SetSelection(atual)
        self._presets(self.msbs[atual], d['lsb'])
        self.cb_msb.Bind(wx.EVT_CHOICE, self._familia_mudou)
        botoes = wx.StdDialogButtonSizer()
        # ids próprios: um botão com wx.ID_OK/ID_CANCEL fecha por fora do nosso tratamento de teclas
        self.btn_ok = wx.Button(self, wx.ID_ANY, "Avançar para Edição")
        self.btn_cancel = wx.Button(self, wx.ID_ANY, "Cancelar")
        botoes.AddButton(self.btn_ok)
        botoes.AddButton(self.btn_cancel)
        botoes.Realize()
        v.Add(botoes, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(v)
        self.btn_ok.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        wx.CallLater(100, self.cb_msb.SetFocus)

    def _presets(self, msb, lsb):
        if msb == O.TIPO_SEM_EFEITO or msb not in DSP_PARAM_NAMES:
            self.cb_lsb.Set([])
            self.cb_lsb.Enable(False)
            return
        nomes = nomes_presets(msb)
        self.cb_lsb.Enable(True)
        self.cb_lsb.Set(nomes)
        self.cb_lsb.SetSelection(lsb if 0 <= lsb < len(nomes) else wx.NOT_FOUND)

    def _familia_mudou(self, event):
        self._presets(self.msbs[self.cb_msb.GetSelection()], 0)
        self.lsb_original = 0
        event.Skip()

    def get_valores(self):
        msb = self.msbs[self.cb_msb.GetSelection()] if self.cb_msb.GetSelection() != wx.NOT_FOUND else O.TIPO_SEM_EFEITO
        if msb == O.TIPO_SEM_EFEITO or msb not in DSP_PARAM_NAMES:
            return msb, 0
        sel = self.cb_lsb.GetSelection()
        return msb, (sel if sel != wx.NOT_FOUND else self.lsb_original)

    def _tecla(self, event):
        k = event.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.FindFocus() is self.btn_cancel:
                self.EndModal(wx.ID_CANCEL)
            else:
                self.EndModal(wx.ID_OK)
            return
        if k == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        if self._espaco(event):
            return
        event.Skip()


class OtsDspEditorDialog(_TeclasDsp, wx.Dialog):
    """Passo 2: Dry/Wet e os parâmetros do efeito da parte. Tab anda pelos campos, setas mudam, Home vai ao máximo, End ao mínimo
    (-1 = não usar), PageUp e PageDown mudam 10. Cada mudança toca na hora no teclado. Enter confirma e fecha; Esc cancela e volta
    ao efeito que a parte tinha antes."""

    def __init__(self, pai, trilha, parte, msb, lsb):
        super().__init__(pai, title=f"Parâmetros do Efeito - {O.PARTES[parte]}", size=(450, 650))
        self.pai, self.trilha, self.parte, self.msb, self.lsb = pai, trilha, parte, msb, lsb
        self.foto = (copy.deepcopy(trilha.eventos), trilha.alterada)       # para o Esc desfazer tudo o que se fez aqui
        antes = trilha.dsp(parte)
        # o mesmo efeito e preset conserva os valores que a parte já tinha; efeito ou preset novo começa nos padrões dele, como o teclado
        # grava (o Dry/Wet e os demais parâmetros precisam estar no arquivo para o teclado carregar o efeito)
        if antes and (antes['msb'], antes['lsb']) == (msb, lsb):
            self.p = list(antes['p'])
        else:
            self.p = O.parametros_padrao_dsp(msb, lsb)
        self.lsb_original = lsb
        self.modulos = [None] * 16
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scr.SetScrollRate(0, 20)
        sz = wx.BoxSizer(wx.VERTICAL)
        self.cb_lsb = None
        if msb != O.TIPO_SEM_EFEITO and msb in DSP_PARAM_NAMES:
            sz.Add(wx.StaticText(scr, label="Preset (Variação):"), 0, wx.LEFT | wx.TOP, 10)
            nomes_p = nomes_presets(msb)
            self.cb_lsb = wx.Choice(scr, choices=nomes_p, name="Preset")
            self.cb_lsb.SetSelection(lsb if 0 <= lsb < len(nomes_p) else wx.NOT_FOUND)
            self.cb_lsb.Bind(wx.EVT_CHOICE, self._preset_mudou)
            sz.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_ret = None
        if msb != O.TIPO_SEM_EFEITO:
            sz.Add(wx.StaticText(scr, label="Return / Dry-Wet Balance (0 a 127, -1 = não usar):"), 0, wx.LEFT | wx.TOP, 10)
            self.sl_ret = wx.SpinCtrl(scr, value=str(self.p[9]), min=-1, max=127, name="Return / Dry-Wet Balance")
            self.sl_ret.Bind(wx.EVT_SPINCTRL, lambda e: self._mudou(self.sl_ret, 9))
            sz.Add(self.sl_ret, 0, wx.EXPAND | wx.ALL, 5)
            nomes = DSP_PARAM_NAMES.get(msb, [f"Parâmetro {k + 1}" for k in range(16)])
            longos = DSP_LONG_PARAM_INDICES.get(msb, [])
            maximos = DSP_PARAM_MAX.get(msb, {})
            for k in range(16):
                if k == 9 or k >= len(nomes) or nomes[k] in ("-", ""):
                    continue
                limite = max(7150 if k in longos else maximos.get(k, 127), self.p[k])
                unidade = "ms" if k in longos else ""
                sz.Add(wx.StaticText(scr, label=f"{nomes[k]} (0 a {limite}{unidade}, -1 = não usar):"), 0, wx.LEFT | wx.TOP, 10)
                sl = wx.SpinCtrl(scr, value=str(self.p[k]), min=-1, max=limite, name=nomes[k])
                sl._opcoes_dsp = None if k in longos else DSP_PARAM_OPTIONS.get(msb, {}).get(k)
                sl.Bind(wx.EVT_SPINCTRL, lambda e, k=k, sl=sl: self._mudou(sl, k))
                sz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
                self.modulos[k] = sl
        else:
            sz.Add(wx.StaticText(scr, label="Sem efeito: esta parte não passa por nenhum efeito DSP. Enter confirma."), 0, wx.ALL, 10)
        scr.SetSizer(sz)
        vbox.Add(scr, 1, wx.EXPAND | wx.ALL, 5)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        # ids próprios: um botão com wx.ID_OK/ID_CANCEL fecha por fora do nosso tratamento de teclas
        self.btn_ok = wx.Button(panel, wx.ID_ANY, "Confirmar")
        self.btn_cancel = wx.Button(panel, wx.ID_ANY, "Cancelar")
        botoes.Add(self.btn_ok, 0, wx.ALL, 5)
        botoes.Add(self.btn_cancel, 0, wx.ALL, 5)
        vbox.Add(botoes, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)
        self.btn_ok.Bind(wx.EVT_BUTTON, lambda e: self.confirmar())
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: self.cancelar())
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.Bind(wx.EVT_CLOSE, lambda e: self.cancelar())
        primeiro = self.sl_ret or self.btn_ok
        wx.CallLater(100, primeiro.SetFocus)
        self._aplicar_tudo()
        falar(f"{nome_do_efeito(msb, self.lsb)}.", imediato=True)

    def _aplicar_tudo(self):
        """O efeito escolhido (e os valores que a parte já tinha) vai para a trilha e para o teclado."""
        _gravar_dsp(self.trilha, self.parte, self.msb, self.lsb, self.p, limpar=True)
        _enviar_dsp(self.pai, self.trilha, self.parte, self.msb, self.lsb, self.p)
        if self.msb != O.TIPO_SEM_EFEITO:
            for k in range(16):
                if self.p[k] >= 0:
                    _enviar_dsp(self.pai, self.trilha, self.parte, self.msb, self.lsb, self.p, k)

    def _mudou(self, sl, k):
        self.p[k] = sl.GetValue()
        _gravar_dsp(self.trilha, self.parte, self.msb, self.lsb, self.p, limpar=self.p[k] < 0)
        if self.p[k] >= 0:
            _enviar_dsp(self.pai, self.trilha, self.parte, self.msb, self.lsb, self.p, k)
        from MHS_Dialogs import _rotulo_valor_dsp
        falar(_rotulo_valor_dsp(sl.GetName(), sl.GetValue(), getattr(sl, '_opcoes_dsp', None)), imediato=True)

    def _preset_mudou(self, event):
        sel = self.cb_lsb.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        self.lsb = sel
        # cada preset tem os próprios valores de fábrica: os campos passam a mostrá-los
        self.p = O.parametros_padrao_dsp(self.msb, sel)
        for k, sl in enumerate(self.modulos):
            if sl is not None:
                if self.p[k] > sl.GetMax():
                    sl.SetRange(-1, self.p[k])
                sl.SetValue(str(self.p[k]))
        if self.sl_ret is not None:
            self.sl_ret.SetValue(str(self.p[9]))
        self._aplicar_tudo()
        falar(f"Preset: {self.cb_lsb.GetStringSelection()}", imediato=True)

    def _ler_campos(self):
        # lê o valor de cada campo na hora de fechar (digitar um número e dar Tab nem sempre dispara o evento do campo)
        foco = self.FindFocus()
        if foco is not None and foco is not self.btn_ok:
            self.btn_ok.SetFocus()
        if self.sl_ret is not None:
            self.p[9] = self.sl_ret.GetValue()
        for k, sl in enumerate(self.modulos):
            if sl is not None:
                self.p[k] = sl.GetValue()

    def confirmar(self):
        self._ler_campos()
        _gravar_dsp(self.trilha, self.parte, self.msb, self.lsb, self.p, limpar=True)
        usados = [v for v in self.p if v >= 0]
        if self.msb == O.TIPO_SEM_EFEITO:
            falar("Fechando. Sem efeito DSP.", imediato=True)
        else:
            falar(f"Fechando. {len(usados)} valor(es) definido(s).", imediato=True)
        self.EndModal(wx.ID_OK)

    def cancelar(self):
        self.trilha.eventos[:] = self.foto[0]
        self.trilha.alterada = self.foto[1]
        falar("Cancelado. O efeito da parte voltou ao que estava.", imediato=True)
        self.EndModal(wx.ID_CANCEL)

    def _tecla(self, event):
        k = event.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.FindFocus() is self.btn_cancel:
                self.cancelar()
            else:
                self.confirmar()
            return
        if k == wx.WXK_ESCAPE:
            self.cancelar()
            return
        if self._espaco(event):
            return
        if self._numero(event, lambda obj: self._mudou(obj, self.modulos.index(obj) if obj in self.modulos else 9)):
            return
        event.Skip()
