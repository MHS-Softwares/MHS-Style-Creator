# -*- coding: utf-8 -*-
"""Janela dos One Touch Settings (OTS) de um estilo e o editor do efeito DSP de cada parte.

A janela edita uma cópia da seção OTSc (MHS_Ots.Secao); quem abre (StyleCreatorFrame.abrir_ots) grava o resultado no
estilo quando a janela fecha. Tudo que se muda é mandado na hora para a porta MIDI do OTS (Configurações > MIDI), nos
canais 1 a 4, para ouvir no teclado; a MIDI de entrada passa a tocar nessa porta enquanto a janela está aberta.
"""

import threading
import time

import mido
import wx

import MHS_Ots as O
from MHS_Utils import falar, VARIATION_EFEITOS_LIST, DSP_PARAM_NAMES, DSP_PARAM_MAX, DSP_PARAM_OPTIONS, nomes_presets

# Numerações testadas para as partes comuns (tecla U): (nome, unidades de efeito, deslocamento do número da parte)
VARIANTES = [
    ("unidades do teclado, partes 5 a 8", O.UNIDADE_INSERCAO, 0),
    ("unidades 0 a 2, partes 5 a 8", O.UNIDADE_XG_COMUM, 0),
    ("unidades 0 a 2, partes da segunda porta, 21 a 24", O.UNIDADE_XG_COMUM, 16),
    ("unidades do teclado, partes da segunda porta, 21 a 24", O.UNIDADE_INSERCAO, 16),
]
PROPRIEDADES = ["Volume", "Pan", "Reverb", "Chorus", "Bank", "Patch", "Oitava", "Efeito DSP", "Parte ligada"]
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
        self.canais = O.CANAIS_COMUNS          # tecla M troca entre as partes comuns (5 a 8) e as do teclado (1 a 4)
        self.variante = 2                      # tecla U: numeração das unidades de efeito e das partes (VARIANTES)
        v = wx.BoxSizer(wx.VERTICAL)
        self.rotulo = wx.StaticText(self, label=self._texto_titulo())
        v.Add(self.rotulo, 0, wx.ALL, 10)
        v.Add(wx.StaticText(self, label="&Partes (Cima e Baixo escolhem a parte, Esquerda e Direita a propriedade, + e - mudam, "
                                        "Enter digita, D abre o efeito DSP, 1 a 4 enviam o OTS ao teclado, S reenvia, "
                                        "Espaço toca a variação, M troca os canais de audição (partes comuns 5 a 8 ou partes do teclado 1 a 4), U muda a numeração das unidades de efeito, G liga e desliga o registro de MIDI de entrada, Esc fecha e aplica):"), 0, wx.LEFT | wx.RIGHT, 10)
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
        falar(f"One Touch Settings. OTS {self.ots + 1}, {self._nome_variacao()}. Porta do OTS: {porta_nome}. "
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
            return nome_do_efeito(d['msb'], d['lsb']) if d else "sem efeito"
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
    def unidades(self):
        return O.UNIDADE_INSERCAO if self.canais == O.CANAIS_TECLADO else VARIANTES[self.variante][1]

    @property
    def deslocamento(self):
        return 0 if self.canais == O.CANAIS_TECLADO else VARIANTES[self.variante][2]

    def parte_xg(self, i):
        # número da parte nos SysEx XG (e na ligação do efeito) da parte i do OTS
        return self.canais[i] + self.deslocamento

    def _enviar(self, *mensagens):
        porta = self.frame.porta_ots()
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
        if prop in _CC:
            self._enviar(mido.Message('control_change', channel=self.canais[i], control=_CC[prop], value=t.cc(i, _CC[prop], 0)))
        elif prop in ("Bank", "Patch"):
            msb, lsb = t.banco(i)
            canal = self.canais[i]
            self._enviar(mido.Message('control_change', channel=canal, control=0, value=msb),
                         mido.Message('control_change', channel=canal, control=32, value=lsb),
                         mido.Message('program_change', channel=canal, program=t.programa(i)))
        elif prop == "Parte ligada":
            if self.canais == O.CANAIS_TECLADO:
                self._enviar(_msg([0xF0, 0x43, 0x73, 0x01, 0x50, 0x08, i, 0x00, 127 if t.ligada(i) else 0, 0xF7]))
        elif prop == "Oitava":
            # Prévia: deslocamento de nota da parte (XG 08 pp 08: 40 = 0, 12 por oitava). O valor que vai no arquivo é outro
            # (o ajuste de oitava do OTS) e só o teclado entende quando carrega o estilo.
            self._enviar(_msg([0xF0, 0x43, 0x10, 0x4C, 0x08, self.parte_xg(i), 0x08, max(0x28, min(0x58, 0x40 + 12 * t.oitava(i))), 0xF7]))

    def enviar_ots(self, n=None):
        """Manda o OTS atual inteiro (canais 1 a 4) para a porta do OTS, sem travar a janela."""
        self._geracao += 1
        minha = self._geracao
        mensagens = [_msg(b) for b in self.trilha.mensagens_para_enviar(self.canais, self.unidades, self.deslocamento)]
        mensagens = [m for m in mensagens if m is not None]
        porta = self.frame.porta_ots()
        if porta is None:
            falar("Nenhuma porta MIDI para o OTS. Escolha uma em Configurações, MIDI.", imediato=True)
            return

        def trabalho():
            for k, m in enumerate(mensagens):
                if self._geracao != minha:
                    return
                try:
                    porta.send(m)
                except Exception:
                    return
                if k % 16 == 15:
                    time.sleep(0.004)
        threading.Thread(target=trabalho, daemon=True).start()

    def _canais_do_eco(self):
        t = self.trilha
        partes = [i for i in range(3) if t.ligada(i)] or [0]
        return [self.canais[i] for i in partes]

    def handle_midi_in(self, msg):
        # Enquanto a janela está aberta o motor MIDI desvia a MIDI de entrada para cá: o que se toca sai pela porta do
        # OTS, nas partes da mão direita que estão ligadas neste OTS (ou na Right 1, se nenhuma estiver).
        if msg.type in ('note_on', 'note_off', 'polytouch', 'aftertouch', 'pitchwheel') or \
                (msg.type == 'control_change' and msg.control in (1, 11, 64, 66, 67)):
            for ch in self._canais_do_eco():
                self._enviar(msg.copy(channel=ch))

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
        self._atualizar_linha(i)
        falar(self._texto_linha(i), imediato=True)

    def _digitar(self):
        i = self.lista.GetSelection()
        prop = PROPRIEDADES[self.prop]
        if i < 0:
            return
        if prop == "Efeito DSP":
            self.abrir_dsp()
            return
        if prop == "Parte ligada":
            self.trilha.definir_ligada(i, not self.trilha.ligada(i))
            self._enviar_param(i, prop)
            self._atualizar_linha(i)
            falar(self._texto_linha(i), imediato=True)
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
        self._atualizar_linha(i)
        falar(self._texto_linha(i), imediato=True)
        wx.CallLater(100, self.lista.SetFocus)

    def abrir_dsp(self):
        i = self.lista.GetSelection()
        if i < 0:
            return
        dlg = OtsDspDialog(self, self.trilha, i)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        self._atualizar_linha(i)
        wx.CallLater(100, self.lista.SetFocus)

    def trocar_ots(self, numero):
        if not 1 <= numero <= len(self.secao.trilhas):
            falar(f"Este estilo tem só {len(self.secao.trilhas)} OTS.", imediato=True)
            return
        self.ots = numero - 1
        self._atualizar_todas()
        self.enviar_ots()
        i = max(0, self.lista.GetSelection())
        falar(f"OTS {numero}, {self._nome_variacao()}, enviado ao teclado. {self._resumo_ligadas()} {self._texto_linha(i)}", imediato=True)

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
            novo = self.prop + (1 if k == wx.WXK_RIGHT else -1)
            if 0 <= novo < len(PROPRIEDADES):
                self.prop = novo
            i = max(0, self.lista.GetSelection())
            self._atualizar_todas()
            self.lista.SetSelection(i)
            falar(self._texto_linha(i), imediato=True)
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
        if k == ord('M'):
            self.canais = O.CANAIS_TECLADO if self.canais == O.CANAIS_COMUNS else O.CANAIS_COMUNS
            self.enviar_ots()
            falar("Partes do teclado, canais 1 a 4." if self.canais == O.CANAIS_TECLADO else
                  "Partes comuns, canais 5 a 8.", imediato=True)
            return
        if k == ord('U') and self.canais != O.CANAIS_TECLADO:
            self.variante = (self.variante + 1) % len(VARIANTES)
            self.enviar_ots()
            falar(f"Numeração {self.variante + 1} de {len(VARIANTES)}: {VARIANTES[self.variante][0]}. OTS reenviado.", imediato=True)
            return
        if k == ord('G'):
            # o menu não abre com esta janela aberta: liga/desliga o registro de MIDI de entrada (midi_in_log.txt)
            self.frame.OnToggleMidiLog(None)
            return
        if k == ord('S'):
            self.enviar_ots()
            falar(f"OTS {self.ots + 1} reenviado ao teclado.", imediato=True)
            return
        if k in (wx.WXK_UP, wx.WXK_DOWN):
            # atualiza a linha de destino ANTES de o leitor de tela lê-la (mesmo cuidado da lista de canais)
            i = self.lista.GetSelection()
            alvo = max(0, min(3, i + (1 if k == wx.WXK_DOWN else -1)))
            self.lista.SetString(alvo, self._texto_linha(alvo))
        event.Skip()


class OtsDspDialog(wx.Dialog):
    """Efeito DSP de uma parte do OTS: tipo do efeito, Dry/Wet e parâmetros. Setas escolhem a linha, + e - mudam,
    Enter digita (ou, na primeira linha, escolhe outro efeito), Esc fecha (já vale)."""

    def __init__(self, pai, trilha, parte):
        super().__init__(pai, title=f"Efeito DSP - {O.PARTES[parte]}", size=(720, 460))
        self.pai, self.trilha, self.parte = pai, trilha, parte
        d = trilha.dsp(parte) or {'msb': O.TIPO_SEM_EFEITO, 'lsb': 0, 'p': [-1] * 16}
        self.msb, self.lsb, self.p = d['msb'], d['lsb'], list(d['p'])
        v = wx.BoxSizer(wx.VERTICAL)
        v.Add(wx.StaticText(self, label="&Efeito e parâmetros (Cima e Baixo escolhem, + e - mudam, PageUp e PageDown mudam 10, "
                                        "Enter digita ou escolhe o efeito, Esc fecha):"), 0, wx.ALL, 10)
        self.lista = wx.ListBox(self, choices=[], name="Efeito DSP")
        v.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.btn = wx.Button(self, wx.ID_OK, label="&Fechar")
        v.Add(self.btn, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(v)
        self._montar()
        self.lista.SetSelection(0)
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        wx.CallLater(100, self.lista.SetFocus)
        falar(f"Efeito DSP da parte {O.PARTES[parte]}. {self._texto(0)}", imediato=True)

    # linhas: 0 = efeito; depois os parâmetros que o arquivo traz
    def _nomes(self):
        return DSP_PARAM_NAMES.get(self.msb, [])

    def _indices(self):
        if self.msb == O.TIPO_SEM_EFEITO:
            return []
        return [k for k in range(16) if self.p[k] >= 0 and not (k < len(self._nomes()) and self._nomes()[k] in ("-", ""))]

    def _montar(self, selecao=None):
        self.linhas = ['efeito'] + self._indices()
        self.lista.Set([self._texto(n) for n in range(len(self.linhas))])
        if selecao is not None and 0 <= selecao < len(self.linhas):
            self.lista.SetSelection(selecao)

    def _nome_param(self, k):
        nomes = self._nomes()
        if k == 9:
            return "Dry/Wet"
        return nomes[k] if k < len(nomes) and nomes[k] else f"Parâmetro {k + 1}"

    def _texto(self, n):
        if self.linhas[n] == 'efeito':
            return f"Efeito: {nome_do_efeito(self.msb, self.lsb)} ({self.msb}/{self.lsb})"
        k = self.linhas[n]
        from MHS_Dialogs import _rotulo_valor_dsp
        opcoes = DSP_PARAM_OPTIONS.get(self.msb, {}).get(k)
        return _rotulo_valor_dsp(self._nome_param(k), self.p[k], opcoes)

    def _maximo(self, k):
        return DSP_PARAM_MAX.get(self.msb, {}).get(k, 127)

    def _enviar(self, k=None):
        if k is None:
            self.pai._enviar(_msg([0xF0, 0x43, 0x10, 0x4C, 0x03, self.pai.unidades[self.parte], 0x0C, self.pai.parte_xg(self.parte), 0xF7]),
                             _msg([0xF0, 0x43, 0x10, 0x4C, 0x03, self.pai.unidades[self.parte], 0x00, self.msb, self.lsb, 0xF7]))
        else:
            endereco = O.Trilha._endereco_do_indice(k)
            self.pai._enviar(_msg([0xF0, 0x43, 0x10, 0x4C, 0x03, self.pai.unidades[self.parte], endereco, max(0, self.p[k]), 0xF7]))

    def _gravar(self):
        self.trilha.definir_dsp(self.parte, self.msb, self.lsb, self.p)
        # o teclado liga o efeito de inserção da parte ao gravar um OTS com efeito (e o desliga sem efeito)
        self.trilha.definir_proprio(self.parte, 0x08, 127 if self.msb != O.TIPO_SEM_EFEITO else 0)

    def _alterar(self, delta):
        n = self.lista.GetSelection()
        if n <= 0:
            if n == 0:
                falar("Aperte Enter para escolher outro efeito.", imediato=True)
            return
        k = self.linhas[n]
        novo = max(0, min(self._maximo(k), self.p[k] + delta))
        if novo == self.p[k]:
            falar(f"{self._texto(n)}, no limite.", imediato=True)
            return
        self.p[k] = novo
        self._gravar()
        self._enviar(k)
        self.lista.SetString(n, self._texto(n))
        self.lista.SetSelection(n)
        falar(self._texto(n), imediato=True)

    def _enter(self):
        n = self.lista.GetSelection()
        if n < 0:
            return
        if n == 0:
            self._escolher_efeito()
            return
        k = self.linhas[n]
        dlg = wx.TextEntryDialog(self, f"{self._nome_param(k)} (0 a {self._maximo(k)}):", "Editar parâmetro", str(self.p[k]))
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            try:
                self.p[k] = max(0, min(self._maximo(k), int(dlg.GetValue().strip())))
            except ValueError:
                falar("Digite um número.", imediato=True)
                return
        finally:
            dlg.Destroy()
        self._gravar()
        self._enviar(k)
        self.lista.SetString(n, self._texto(n))
        self.lista.SetSelection(n)
        falar(self._texto(n), imediato=True)
        wx.CallLater(100, self.lista.SetFocus)

    def _escolher_efeito(self):
        nomes = [NOMES_EFEITO[O.TIPO_SEM_EFEITO]] + [n for n, _ in VARIATION_EFEITOS_LIST]
        msbs = [O.TIPO_SEM_EFEITO] + [m for _, m in VARIATION_EFEITOS_LIST]
        atual = msbs.index(self.msb) if self.msb in msbs else 0
        dlg = wx.SingleChoiceDialog(self, "Efeito desta parte:", "Escolher o efeito DSP", nomes)
        dlg.SetSelection(atual)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            novo_msb = msbs[dlg.GetSelection()]
        finally:
            dlg.Destroy()
        novo_lsb = 0
        if novo_msb != O.TIPO_SEM_EFEITO and novo_msb in DSP_PARAM_NAMES:
            presets = nomes_presets(novo_msb)
            d2 = wx.SingleChoiceDialog(self, "Preset do efeito:", "Escolher o preset", presets)
            d2.SetSelection(self.lsb if (novo_msb == self.msb and self.lsb < len(presets)) else 0)
            try:
                if d2.ShowModal() != wx.ID_OK:
                    return
                novo_lsb = d2.GetSelection()
            finally:
                d2.Destroy()
        self.msb, self.lsb = novo_msb, novo_lsb
        if novo_msb != O.TIPO_SEM_EFEITO:
            # parâmetros que o arquivo ainda não trazia para esta parte nascem em zero; os que existiam ficam (o
            # teclado só reaplica o padrão do efeito se o arquivo não os trouxer, e isto não foi confirmado)
            nomes_p = DSP_PARAM_NAMES.get(novo_msb, [])
            for k in range(len(nomes_p)):
                if self.p[k] < 0 and nomes_p[k] not in ("-", ""):
                    self.p[k] = 0
        self._gravar()
        self._enviar(None)
        self._montar(0)
        falar(self._texto(0), imediato=True)
        wx.CallLater(100, self.lista.SetFocus)

    def _tecla(self, event):
        k = event.GetKeyCode()
        if event.ControlDown() or event.AltDown():
            event.Skip()
            return
        if k == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK)
            return
        if self.FindFocus() is not self.lista:
            event.Skip()
            return
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._enter()
            return
        if k in (wx.WXK_ADD, wx.WXK_NUMPAD_ADD) or k == ord('='):
            self._alterar(1)
            return
        if k in (wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT) or k == ord('-'):
            self._alterar(-1)
            return
        if k in (wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
            self._alterar(10 if k == wx.WXK_PAGEUP else -10)
            return
        event.Skip()
