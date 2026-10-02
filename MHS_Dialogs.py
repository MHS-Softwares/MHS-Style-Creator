import wx
import mido
import threading
import json
import os
from MHS_Utils import (
    falar, falar_status, get_nome_nota, VALOR_MAX_MIDI, rotulo_canal,
    REV_MSB_LIST, CHO_MSB_LIST, VARIATION_EFEITOS_LIST, DSP_PARAM_NAMES,
    DSP_LONG_PARAM_INDICES, DSP_PARAM_MAX, DSP_PARAM_OPTIONS, nomes_presets, YAMAHA_SECTION_ORDER,
    achar_porta_certa, verificar_nova_versao,
    listar_ins_online, pasta_ins_files, baixar_e_extrair_ins
)


def _rotulo_valor_dsp(nome, valor, opcoes):
    # Parâmetro de DSP que é uma lista curta de opções com nome (ex: "Device":
    # Transistor, Vintage Tube, ...) - fala o NOME da opção pro NVDA em vez
    # de só o número puro. `opcoes` = (valor_mínimo, [nomes]) ou None (a
    # maioria dos parâmetros é contínua e continua falando só o número).
    if opcoes:
        min_v, nomes_opcao = opcoes
        j = valor - min_v
        if 0 <= j < len(nomes_opcao):
            return f"{nome}: {nomes_opcao[j]} ({valor})"
    return f"{nome}: {valor}"

class SectionLengthDialog(wx.Dialog):
    # Denominadores permitidos - as figuras de compasso reais que existem
    # (potências de 2, como todo compasso de verdade: 2, 4, 8, 16, 32).
    DENOMINADORES = [2, 4, 8, 16, 32]

    def __init__(self, parent, section_name, current_measures, numerador_atual=4, denominador_atual=4):
        super().__init__(parent, title=f"Tamanho da Seção: {section_name}", size=(320, 230))
        self.val = current_measures
        self.numerador_atual = numerador_atual
        self.denominador_atual = denominador_atual
        self.InitUI()

    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label="Número de compassos:"), 0, wx.ALL, 10)
        self.spin_ctrl = wx.SpinCtrl(self, value=str(self.val), min=1, max=128)
        vbox.Add(self.spin_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # A FIGURA DE COMPASSO - recurso que já existe nos SX mais novos:
        # cada seção pode ter sua própria (3/4, 5/4, 6/8, 7/8...), em vez de
        # ficar preso na figura global do estilo inteiro.
        vbox.Add(wx.StaticText(self, label="Figura de compasso (numerador):"), 0, wx.ALL, 10)
        # 255 é o teto real do formato (numerador do 'time_signature' MIDI
        # é 1 byte só) - não há limite específico documentado no Style
        # File da Yamaha nem no Data List oficial além disso. O max=32
        # antigo era arbitrário (o próprio Michel já tinha conseguido
        # passar dele digitando direto no campo).
        self.spin_num = wx.SpinCtrl(self, value=str(self.numerador_atual), min=1, max=255)
        self.spin_num.SetName("Figura de compasso, numerador")
        vbox.Add(self.spin_num, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        vbox.Add(wx.StaticText(self, label="Figura de compasso (denominador):"), 0, wx.ALL, 10)
        self.choice_den = wx.Choice(self, choices=[str(d) for d in self.DENOMINADORES])
        self.choice_den.SetName("Figura de compasso, denominador")
        try:
            idx_den = self.DENOMINADORES.index(self.denominador_atual)
        except ValueError:
            idx_den = self.DENOMINADORES.index(4)
        self.choice_den.SetSelection(idx_den)
        vbox.Add(self.choice_den, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btnsizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(btnsizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 10)
        self.SetSizer(vbox)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.spin_ctrl.SetFocus()

    def GetValues(self):
        numerador = self.spin_num.GetValue()
        denominador = self.DENOMINADORES[self.choice_den.GetSelection()]
        return self.spin_ctrl.GetValue(), numerador, denominador

class StyleSettingsDialog(wx.Dialog):
    def __init__(self, parent, current_beats=4):
        super().__init__(parent, title="Configurações do estilo", size=(300, 250))
        self.beats = current_beats
        self.InitUI()

    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label="Figura de Tempo (Compasso, numerador):"), 0, wx.ALL, 10)
        # Caixinha digitável e deslizante (não mais só 2/3/4/6 fixos) -
        # pedido do Michel depois de confirmar que o numerador de um
        # 'time_signature' MIDI é só 1 byte (0-255, sem limite específico
        # documentado no formato de Style File da Yamaha nem no Data List
        # oficial) - 255 é o teto real do próprio formato.
        self.spin_beats = wx.SpinCtrl(self, value=str(self.beats), min=1, max=255)
        self.spin_beats.SetName("Figura de Tempo (Compasso), numerador")
        vbox.Add(self.spin_beats, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        btnsizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(btnsizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 20)
        self.SetSizer(vbox)
        wx.CallLater(100, self.spin_beats.SetFocus)

    def GetValues(self):
        return self.spin_beats.GetValue()

class QuantizacaoRealTimeDialog(wx.Dialog):
    def __init__(self, parent, enabled_atual, res_atual):
        super().__init__(parent, title="Quantização em Tempo Real (Input)", size=(380, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.resolucoes = [
            ("1/1 (Semibreve)", 1), ("1/2 (Mínima)", 2), ("1/2T (Mínima Tercina)", 3),
            ("1/4 (Semínima)", 4), ("1/4D (Semínima Pontuada)", 8/3.0), ("1/4T (Semínima Tercina)", 6),
            ("1/8 (Colcheia)", 8), ("1/8D (Colcheia Pontuada)", 16/3.0), ("1/8T (Colcheia Tercina)", 12),
            ("1/16 (Semicolcheia)", 16), ("1/16D (Semicolcheia Pontuada)", 32/3.0), ("1/16T (Semicolcheia Tercina)", 24),
            ("1/32 (Fusa)", 32), ("1/32T (Fusa Tercina)", 48), ("1/64 (Semifusa)", 64)
        ]
        self.chk_enable = wx.CheckBox(self, label="Gravar Quantizando")
        self.chk_enable.SetValue(enabled_atual)
        sizer.Add(self.chk_enable, 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, label="Grade de Quantização:"), 0, wx.ALL, 5)
        self.combo_res = wx.ComboBox(self, choices=[r[0] for r in self.resolucoes], style=wx.CB_READONLY)
        idx = 9
        for i, r in enumerate(self.resolucoes):
            if abs(r[1] - res_atual) < 0.001:
                idx = i
                break
        self.combo_res.SetSelection(idx)
        sizer.Add(self.combo_res, 0, wx.EXPAND | wx.ALL, 5)
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.chk_enable.SetFocus()

    def get_valores(self):
        return self.chk_enable.GetValue(), self.resolucoes[self.combo_res.GetSelection()][1]

class QuantizarOfflineDialog(wx.Dialog):
    # Tela própria pro Ctrl+Q (Quantizar Offline) - antes reaproveitava a
    # QuantizacaoRealTimeDialog inteira, inclusive o texto e o checkbox
    # "Gravar Quantizando" (que só faz sentido pro Q sozinho, de gravação em
    # tempo real). Isso fazia parecer que Ctrl+Q tinha caído na tela errada.
    def __init__(self, parent, res_atual):
        super().__init__(parent, title="Quantizar Offline (Canal Atual)", size=(380, 180))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.resolucoes = [
            ("1/1 (Semibreve)", 1), ("1/2 (Mínima)", 2), ("1/2T (Mínima Tercina)", 3),
            ("1/4 (Semínima)", 4), ("1/4D (Semínima Pontuada)", 8/3.0), ("1/4T (Semínima Tercina)", 6),
            ("1/8 (Colcheia)", 8), ("1/8D (Colcheia Pontuada)", 16/3.0), ("1/8T (Colcheia Tercina)", 12),
            ("1/16 (Semicolcheia)", 16), ("1/16D (Semicolcheia Pontuada)", 32/3.0), ("1/16T (Semicolcheia Tercina)", 24),
            ("1/32 (Fusa)", 32), ("1/32T (Fusa Tercina)", 48), ("1/64 (Semifusa)", 64)
        ]
        sizer.Add(wx.StaticText(self, label="Grade de Quantização:"), 0, wx.ALL, 5)
        self.combo_res = wx.ComboBox(self, choices=[r[0] for r in self.resolucoes], style=wx.CB_READONLY)
        idx = 9
        for i, r in enumerate(self.resolucoes):
            if abs(r[1] - res_atual) < 0.001:
                idx = i
                break
        self.combo_res.SetSelection(idx)
        sizer.Add(self.combo_res, 0, wx.EXPAND | wx.ALL, 5)
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.combo_res.SetFocus()

    def get_valores(self):
        return self.resolucoes[self.combo_res.GetSelection()][1]

class VelocityControlDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Velocity Midi Control", size=(400, 300))
        self.parent = parent
        self.orig_on = parent.in_vel_ctrl_on
        self.orig_min = parent.in_vel_min
        self.orig_max = parent.in_vel_max
        self.timer_nota = None
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.chk_enable = wx.CheckBox(self, label="Ativar Controle de Velocity")
        self.chk_enable.SetValue(self.orig_on)
        sizer.Add(self.chk_enable, 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, label=f"Velocity Mínimo (1-{VALOR_MAX_MIDI}):"), 0, wx.ALL, 5)
        self.sl_min = wx.Slider(self, value=self.orig_min, minValue=1, maxValue=VALOR_MAX_MIDI, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.sl_min.SetPageSize(1)
        self.sl_min.SetLineSize(1)
        sizer.Add(self.sl_min, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        sizer.Add(wx.StaticText(self, label=f"Velocity Máximo (1-{VALOR_MAX_MIDI}):"), 0, wx.ALL, 5)
        self.sl_max = wx.Slider(self, value=self.orig_max, minValue=1, maxValue=VALOR_MAX_MIDI, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.sl_max.SetPageSize(1)
        self.sl_max.SetLineSize(1)
        sizer.Add(self.sl_max, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.chk_enable.Bind(wx.EVT_CHECKBOX, self.on_change_enable)
        self.sl_min.Bind(wx.EVT_SLIDER, self.on_slider_min)
        self.sl_max.Bind(wx.EVT_SLIDER, self.on_slider_max)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.chk_enable.SetFocus()

    def tocar_nota_preview(self, vel):
        # Toca um C4 no canal atual, na velocity escolhida, pra dar pra ouvir
        # na hora onde fica o ponto de troca de camada de um MegaVoice.
        if not self.parent.midi_out: return
        ch = getattr(self.parent, 'canal_atual', 0)
        nota = 60
        try: self.parent.midi_out.send(mido.Message('note_off', channel=ch, note=nota, velocity=0))
        except Exception: pass
        try: self.parent.midi_out.send(mido.Message('note_on', channel=ch, note=nota, velocity=vel))
        except Exception: pass
        if self.timer_nota:
            self.timer_nota.cancel()
        def apagar():
            if self.parent.midi_out:
                try: self.parent.midi_out.send(mido.Message('note_off', channel=ch, note=nota, velocity=0))
                except Exception: pass
        self.timer_nota = threading.Timer(0.3, apagar)
        self.timer_nota.start()

    def on_change_enable(self, event):
        v_on = self.chk_enable.GetValue()
        self.parent.in_vel_ctrl_on = v_on
        estado = "Ativado" if v_on else "Desativado"
        falar(f"Controle {estado}", imediato=True)

    def on_slider_min(self, event):
        val = self.sl_min.GetValue()
        if val > self.sl_max.GetValue():
            self.sl_max.SetValue(val)
        self.parent.in_vel_min = self.sl_min.GetValue()
        self.parent.in_vel_max = self.sl_max.GetValue()
        self.tocar_nota_preview(val)
        falar(f"Mínimo {val}", imediato=True)

    def on_slider_max(self, event):
        val = self.sl_max.GetValue()
        if val < self.sl_min.GetValue():
            self.sl_min.SetValue(val)
        self.parent.in_vel_min = self.sl_min.GetValue()
        self.parent.in_vel_max = self.sl_max.GetValue()
        self.tocar_nota_preview(val)
        falar(f"Máximo {val}", imediato=True)

    def on_key(self, event):
        code = event.GetKeyCode()
        foco = wx.Window.FindFocus()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            if isinstance(foco, wx.Button) and foco.GetId() == wx.ID_CANCEL:
                self.EndModal(wx.ID_CANCEL)
            else:
                self.EndModal(wx.ID_OK)
            return
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def restaurar(self):
        self.parent.in_vel_ctrl_on = self.orig_on
        self.parent.in_vel_min = self.orig_min
        self.parent.in_vel_max = self.orig_max

class SubstituirNotasDialog(wx.Dialog):
    def __init__(self, parent, old_note):
        super().__init__(parent.parent, title=f"Substituição em Massa: {get_nome_nota(old_note)}", size=(400, 350))
        self.parent_list = parent 
        self.old_note = old_note
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=f"1. Nova Nota (Atual: {get_nome_nota(old_note)}):"), 0, wx.ALL, 5)
        self.sl_note = wx.Slider(self, value=old_note, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        sizer.Add(self.sl_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_note.Bind(wx.EVT_SLIDER, self.on_note_change)
        sizer.Add(wx.StaticText(self, label="2. Ajustar Velocity (-127 a +127):"), 0, wx.ALL, 5)
        self.sl_vel = wx.Slider(self, value=0, minValue=-127, maxValue=127, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        sizer.Add(self.sl_vel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_vel.Bind(wx.EVT_SLIDER, self.on_vel_change)
        sizer.Add(wx.StaticText(self, label="3. Ajustar Duração em ms (-1000 a +1000):"), 0, wx.ALL, 5)
        self.sl_dur = wx.Slider(self, value=0, minValue=-1000, maxValue=1000, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        sizer.Add(self.sl_dur, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_dur.Bind(wx.EVT_SLIDER, self.on_dur_change)
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.sl_note.SetFocus)

    def on_note_change(self, event):
        v = self.sl_note.GetValue()
        falar_status(f"Nota {get_nome_nota(v)}", imediato=True)
        if self.parent_list.parent.midi_out:
            self.parent_list.matar_nota_preview()
            msg = mido.Message('note_on', channel=self.parent_list.canal_idx, note=v, velocity=100)
            self.parent_list.preview_note = msg
            self.parent_list.parent.midi_out.send(msg)
            self.parent_list.preview_timer = threading.Timer(0.3, self.parent_list.matar_nota_preview)
            self.parent_list.preview_timer.start()

    def on_vel_change(self, event):
        v = self.sl_vel.GetValue()
        sinal = "+" if v > 0 else ""
        falar_status(f"Velocity {sinal}{v}", imediato=True)

    def on_dur_change(self, event):
        v = self.sl_dur.GetValue()
        sinal = "+" if v > 0 else ""
        falar_status(f"Duração {sinal}{v} milissegundos", imediato=True)

    def get_values(self):
        return self.sl_note.GetValue(), self.sl_vel.GetValue(), self.sl_dur.GetValue()

class MidiRouterDialog(wx.Dialog):
    def __init__(self, parent, rotas_atuais):
        super().__init__(parent, title="Conversor MIDI (Midi Convert to CC)", size=(500, 350))
        self.parent = parent
        self.rotas = rotas_atuais
            
        self.opcoes_cc = ["Pitch Bend"] + [f"CC {i}" for i in range(128)]
        self.mapa_opcoes = {"PB": 0}
        for i in range(128): self.mapa_opcoes[str(i)] = i + 1
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.chks = []
        self.cb_src = []
        self.cb_dst = []
        self.panels = []
        
        for i in range(4):
            sz_linha = wx.BoxSizer(wx.VERTICAL)
            chk = wx.CheckBox(self, label=f"Ativar Rota {i+1}")
            chk.SetValue(self.rotas[i]['active'])
            sz_linha.Add(chk, 0, wx.ALL, 5)
            
            panel_combos = wx.Panel(self)
            sz_combos = wx.BoxSizer(wx.HORIZONTAL)
            
            cb_s = wx.ComboBox(panel_combos, choices=self.opcoes_cc, style=wx.CB_READONLY)
            idx_s = self.mapa_opcoes.get(self.rotas[i]['src'], 1)
            cb_s.SetSelection(idx_s)
            
            cb_d = wx.ComboBox(panel_combos, choices=self.opcoes_cc, style=wx.CB_READONLY)
            idx_d = self.mapa_opcoes.get(self.rotas[i]['dst'], 1)
            cb_d.SetSelection(idx_d)
            
            sz_combos.Add(wx.StaticText(panel_combos, label="Origem: "), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
            sz_combos.Add(cb_s, 1, wx.EXPAND|wx.RIGHT, 15)
            sz_combos.Add(wx.StaticText(panel_combos, label="Destino: "), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
            sz_combos.Add(cb_d, 1, wx.EXPAND)
            
            panel_combos.SetSizer(sz_combos)
            sz_linha.Add(panel_combos, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
            
            if not chk.GetValue():
                panel_combos.Hide()
                
            chk.Bind(wx.EVT_CHECKBOX, lambda e, p=panel_combos, c=chk, num=i+1: self.on_chk_toggle(e, p, c, num))
            
            self.chks.append(chk)
            self.cb_src.append(cb_s)
            self.cb_dst.append(cb_d)
            self.panels.append(panel_combos)
            
            sizer.Add(sz_linha, 0, wx.EXPAND|wx.BOTTOM, 5)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.chks[0].SetFocus)
        
    def on_chk_toggle(self, event, panel, chk, num):
        if chk.GetValue():
            panel.Show()
            falar(f"Rota {num} ativada", imediato=True)
        else:
            panel.Hide()
            falar(f"Rota {num} desativada", imediato=True)
        self.Layout()
        
    def get_valores(self):
        vals = []
        for i in range(4):
            src_val = "PB" if self.cb_src[i].GetSelection() == 0 else str(self.cb_src[i].GetSelection() - 1)
            dst_val = "PB" if self.cb_dst[i].GetSelection() == 0 else str(self.cb_dst[i].GetSelection() - 1)
            vals.append({
                'active': self.chks[i].GetValue(),
                'src': src_val,
                'dst': dst_val
            })
        return vals

class BaixarInsDialog(wx.Dialog):
    # Varre a página jososoft.dk, lista os teclados Yamaha que têm .ins
    # disponível, e baixa/extrai o escolhido na pasta "Ins files" do
    # programa. Ao terminar com sucesso fecha sozinha (ID_OK) devolvendo os
    # caminhos em self.arquivos_baixados - quem abriu já adiciona/seleciona
    # na lista de Instrumentos, só falta o usuário confirmar com OK.
    def __init__(self, parent):
        super().__init__(parent, title="Baixar arquivos .ins da Internet", size=(540, 480))
        self.arquivos_baixados = []
        self._entradas = []
        self._ocupado = False

        vbox = wx.BoxSizer(wx.VERTICAL)
        self.lbl_status = wx.StaticText(self, label="Procurando a lista de teclados no site jososoft.dk...")
        vbox.Add(self.lbl_status, 0, wx.ALL, 10)
        vbox.Add(wx.StaticText(self, label="&Teclados disponíveis (digite o nome para ir direto; Tab vai ao botão Baixar):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, style=wx.LB_SINGLE, name="Teclados disponíveis")
        vbox.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        bs = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_baixar = wx.Button(self, label="&Baixar")
        self.btn_baixar.Disable()
        self.btn_baixar.SetDefault()
        self.btn_fechar = wx.Button(self, wx.ID_CANCEL, label="&Fechar")
        bs.Add(self.btn_baixar, 0, wx.ALL, 5)
        bs.Add(self.btn_fechar, 0, wx.ALL, 5)
        vbox.Add(bs, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        self.SetSizer(vbox)

        self.btn_baixar.Bind(wx.EVT_BUTTON, self.OnBaixar)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self.OnBaixar)
        falar("Procurando a lista de teclados no site.", imediato=True)
        threading.Thread(target=self._carregar_lista_thread, daemon=True).start()

    def _carregar_lista_thread(self):
        try:
            entradas = listar_ins_online()
        except Exception as e:
            wx.CallAfter(self._lista_falhou, str(e))
            return
        wx.CallAfter(self._lista_pronta, entradas)

    def _lista_falhou(self, motivo):
        if not self:
            return
        msg = "Não foi possível acessar o site agora. Confira sua conexão com a internet e tente de novo."
        self.lbl_status.SetLabel(msg)
        falar(msg, imediato=True)

    def _lista_pronta(self, entradas):
        if not self:
            return
        self._entradas = entradas
        self.lista.Set([f"{e['nome']} ({e['grupo']})" for e in entradas])
        if not entradas:
            msg = "O site respondeu, mas nenhum arquivo .ins foi encontrado."
            self.lbl_status.SetLabel(msg)
            falar(msg, imediato=True)
            return
        self.lista.SetSelection(0)
        self.lista.SetFocus()
        self.btn_baixar.Enable()
        msg = f"{len(entradas)} teclados encontrados. Escolha o seu e aperte Enter, ou Tab até o botão Baixar."
        self.lbl_status.SetLabel(msg)
        falar(msg, imediato=True)

    def OnBaixar(self, event):
        if self._ocupado or not self._entradas:
            return
        sel = self.lista.GetSelection()
        if sel == wx.NOT_FOUND:
            falar("Escolha um teclado na lista primeiro.", imediato=True)
            return
        entrada = self._entradas[sel]
        self._ocupado = True
        self.btn_baixar.Disable()
        msg = f"Baixando o arquivo de {entrada['nome']}, aguarde..."
        self.lbl_status.SetLabel(msg)
        falar(msg, imediato=True)
        threading.Thread(target=self._baixar_thread, args=(entrada,), daemon=True).start()

    def _baixar_thread(self, entrada):
        try:
            pasta = pasta_ins_files()
            arquivos = baixar_e_extrair_ins(entrada['url'], pasta)
        except Exception as e:
            wx.CallAfter(self._baixar_falhou, entrada, str(e))
            return
        wx.CallAfter(self._baixar_ok, entrada, pasta, arquivos)

    def _baixar_falhou(self, entrada, motivo):
        if not self:
            return
        self._ocupado = False
        self.btn_baixar.Enable()
        msg = f"Não foi possível baixar o arquivo de {entrada['nome']}. Confira sua conexão e tente de novo."
        self.lbl_status.SetLabel(msg)
        falar(msg, imediato=True)

    def _baixar_ok(self, entrada, pasta, arquivos):
        if not self:
            return
        self.arquivos_baixados = arquivos
        self._pasta = pasta
        self._nome = entrada['nome']
        self.EndModal(wx.ID_OK)


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, current_config, versao_atual=None, repo_github=None):
        super().__init__(parent, title="Configurações MHS", size=(500, 550))
        self.config = current_config
        self.versao_atual = versao_atual or "?"
        self.repo_github = repo_github or "MHS-Style-Creator"
        self.InitUI()

    def InitUI(self):
        main_vbox = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(self)

        self.midi_page = wx.Panel(self.notebook)
        midi_sizer = wx.BoxSizer(wx.VERTICAL)

        portas_out = mido.get_output_names()
        portas_in = mido.get_input_names()

        # Porta(s) MIDI de Entrada primeiro (pedido do Michel) - uma ou
        # mais de uma vez, igual ao MIDI Sequencer: CheckListBox em vez de
        # uma escolha única. As portas salvas ("midi_in" - lista; uma
        # string solta de um config mais antigo também é aceita) são
        # pré-marcadas usando achar_porta_certa, a mesma função que a
        # reconexão de verdade usa - se o Windows renumerou a porta desde
        # a última vez, a marcação já aparece no lugar certo.
        midi_sizer.Add(wx.StaticText(self.midi_page, label="Porta(s) MIDI de Entrada (uma ou mais):"), 0, wx.ALL, 5)
        self.midi_in_list = wx.CheckListBox(self.midi_page, choices=portas_in if portas_in else ["Sem portas"], size=(-1, 90))
        salvas_in = self.config.get("midi_in", [])
        if isinstance(salvas_in, str):
            salvas_in = [salvas_in] if salvas_in and salvas_in != "Sem portas" else []
        for nome_salvo in salvas_in:
            porta_certa = achar_porta_certa(nome_salvo, portas_in)
            if porta_certa:
                self.midi_in_list.Check(portas_in.index(porta_certa))
        midi_sizer.Add(self.midi_in_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        midi_sizer.Add(wx.StaticText(self.midi_page, label="Porta MIDI de Saída:"), 0, wx.TOP | wx.LEFT, 15)
        self.midi_out_choice = wx.Choice(self.midi_page, choices=portas_out if portas_out else ["Sem portas"])
        porta_out_certa = achar_porta_certa(self.config.get("midi_out"), portas_out)
        if porta_out_certa:
            self.midi_out_choice.SetStringSelection(porta_out_certa)
        midi_sizer.Add(self.midi_out_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Teste pedido pelo Michel: mandar o metrônomo (canal 10, notas
        # 21/22) pra um dispositivo MIDI SEPARADO do resto do estilo -
        # deixar em branco ("mesma porta principal") volta exatamente ao
        # comportamento de sempre (tudo pela mesma porta de saída).
        midi_sizer.Add(wx.StaticText(self.midi_page, label="Porta MIDI do Metrônomo (canal 10, dispositivo à parte):"), 0, wx.TOP | wx.LEFT, 15)
        opcoes_metro = ["(mesma porta principal)"] + (portas_out if portas_out else [])
        self.midi_metro_choice = wx.Choice(self.midi_page, choices=opcoes_metro)
        porta_metro_certa = achar_porta_certa(self.config.get("midi_out_metronomo"), portas_out)
        if porta_metro_certa:
            self.midi_metro_choice.SetStringSelection(porta_metro_certa)
        else:
            self.midi_metro_choice.SetSelection(0)
        midi_sizer.Add(self.midi_metro_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        midi_sizer.Add(wx.StaticText(self.midi_page, label="Volume do Metrônomo:"), 0, wx.TOP | wx.LEFT, 15)
        self.sp_volume_metro = wx.SpinCtrl(self.midi_page, value=str(self.config.get("metronomo_volume", 100)), min=0, max=127)
        midi_sizer.Add(self.sp_volume_metro, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.midi_page.SetSizer(midi_sizer)

        self.ins_page = wx.Panel(self.notebook)
        ins_sizer = wx.BoxSizer(wx.VERTICAL)
        ins_sizer.Add(wx.StaticText(self.ins_page, label="Arquivos .ins:"), 0, wx.ALL, 10)
        self.ins_listbox = wx.ListBox(self.ins_page, style=wx.LB_SINGLE, size=(-1, 150))
        self.ins_listbox.AppendItems(self.config.get("ins_files", []))
        if self.config.get("selected_ins_idx", 0) < self.ins_listbox.GetCount():
            self.ins_listbox.SetSelection(self.config.get("selected_ins_idx", 0))
        ins_sizer.Add(self.ins_listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self.ins_page, label="Adicionar")
        self.btn_remove = wx.Button(self.ins_page, label="Remover")
        self.btn_baixar_ins = wx.Button(self.ins_page, label="Baixar da &Internet...")
        btn_sizer.Add(self.btn_add, 0, wx.ALL, 5)
        btn_sizer.Add(self.btn_remove, 0, wx.ALL, 5)
        btn_sizer.Add(self.btn_baixar_ins, 0, wx.ALL, 5)
        ins_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 10)
        self.ins_page.SetSizer(ins_sizer)

        # Aba de Pastas de Trabalho - pedido do Michel: pasta padrão FIXA
        # pra abrir/salvar, igual já existe no MIDI Sequencer. Tem prioridade
        # sobre o "lembra a última pasta usada" (last_open_dir/last_save_dir)
        # quando preenchida - ver OnOpen/OnSaveAs em MHS_MainFrame.py.
        self.pastas_page = wx.Panel(self.notebook)
        pastas_sizer = wx.BoxSizer(wx.VERTICAL)

        pastas_sizer.Add(wx.StaticText(self.pastas_page, label="Pasta Padrão para Abrir:"), 0, wx.ALL, 5)
        sz_abrir = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_pasta_abrir = wx.TextCtrl(self.pastas_page, value=self.config.get('pasta_abrir', ''))
        btn_pasta_abrir = wx.Button(self.pastas_page, label="Alterar Pasta de Abertura")
        sz_abrir.Add(self.txt_pasta_abrir, 1, wx.EXPAND | wx.RIGHT, 5)
        sz_abrir.Add(btn_pasta_abrir, 0)
        pastas_sizer.Add(sz_abrir, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        btn_pasta_abrir.Bind(wx.EVT_BUTTON, self.OnAlterarPastaAbrir)

        pastas_sizer.Add(wx.StaticText(self.pastas_page, label="Pasta Padrão para Salvar:"), 0, wx.ALL, 5)
        sz_salvar = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_pasta_salvar = wx.TextCtrl(self.pastas_page, value=self.config.get('pasta_salvar', ''))
        btn_pasta_salvar = wx.Button(self.pastas_page, label="Alterar Pasta de Salvamento")
        sz_salvar.Add(self.txt_pasta_salvar, 1, wx.EXPAND | wx.RIGHT, 5)
        sz_salvar.Add(btn_pasta_salvar, 0)
        pastas_sizer.Add(sz_salvar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        btn_pasta_salvar.Bind(wx.EVT_BUTTON, self.OnAlterarPastaSalvar)

        pastas_sizer.Add(wx.StaticText(self.pastas_page, label="(Deixe em branco para usar sempre a última pasta utilizada.)"), 0, wx.ALL, 5)
        self.pastas_page.SetSizer(pastas_sizer)

        # Aba de Atualizações - pedido do Michel: checagem automática opcional
        # ao iniciar (checkbox) + botão pra checar na hora, sempre disponível
        # independente da checkbox estar marcada ou não.
        self.updates_page = wx.Panel(self.notebook)
        updates_sizer = wx.BoxSizer(wx.VERTICAL)
        updates_sizer.Add(wx.StaticText(self.updates_page, label=f"Versão instalada: {self.versao_atual}"), 0, wx.ALL, 10)
        self.chk_verificar_atualizacoes = wx.CheckBox(self.updates_page, label="&Verificar atualizações automaticamente ao iniciar o programa")
        self.chk_verificar_atualizacoes.SetValue(self.config.get('verificar_atualizacoes', True))
        updates_sizer.Add(self.chk_verificar_atualizacoes, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.btn_verificar_agora = wx.Button(self.updates_page, label="&Procurar Atualizações Agora")
        self.btn_verificar_agora.Bind(wx.EVT_BUTTON, self.OnVerificarAtualizacoesAgora)
        updates_sizer.Add(self.btn_verificar_agora, 0, wx.ALL, 10)
        self.updates_page.SetSizer(updates_sizer)

        self.notebook.AddPage(self.midi_page, "MIDI")
        self.notebook.AddPage(self.ins_page, "Instrumentos")
        self.notebook.AddPage(self.pastas_page, "Pastas de Trabalho")
        self.notebook.AddPage(self.updates_page, "Atualizações")

        main_vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        btnsizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_vbox.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        self.SetSizer(main_vbox)

        self.btn_add.Bind(wx.EVT_BUTTON, self.OnAddIns)
        self.btn_remove.Bind(wx.EVT_BUTTON, self.OnRemoveIns)
        self.btn_baixar_ins.Bind(wx.EVT_BUTTON, self.OnBaixarIns)

        # Sem isso, o foco inicial cai no botão OK (primeiro widget na
        # ordem de tabulação que aceita foco de verdade) - o mesmo ajuste
        # já feito em outras telas desta sessão.
        wx.CallLater(100, self.midi_in_list.SetFocus)

    def OnAddIns(self, event):
        dlg = wx.FileDialog(self, "Selecionar .ins", wildcard="*.ins", style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            if path not in self.ins_listbox.GetStrings():
                self.ins_listbox.Append(path)
        dlg.Destroy()

    def OnRemoveIns(self, event):
        idx = self.ins_listbox.GetSelection()
        if idx != -1: self.ins_listbox.Delete(idx)

    def OnBaixarIns(self, event):
        dlg = BaixarInsDialog(self)
        if dlg.ShowModal() == wx.ID_OK and dlg.arquivos_baixados:
            existentes = [p.lower() for p in self.ins_listbox.GetStrings()]
            for p in dlg.arquivos_baixados:
                if p.lower() not in existentes:
                    self.ins_listbox.Append(p)
            alvo = dlg.arquivos_baixados[0]
            idx = next((i for i, p in enumerate(self.ins_listbox.GetStrings()) if p.lower() == alvo.lower()), wx.NOT_FOUND)
            if idx != wx.NOT_FOUND:
                self.ins_listbox.SetSelection(idx)
            falar(f"Arquivo de {dlg._nome} baixado, salvo em {dlg._pasta} e já definido como instrumento. Clique em OK para confirmar.", imediato=True)
            self.ins_listbox.SetFocus()
        dlg.Destroy()

    def OnAlterarPastaAbrir(self, event):
        with wx.DirDialog(self, "Escolha a pasta padrão para Abrir", defaultPath=self.txt_pasta_abrir.GetValue()) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txt_pasta_abrir.SetValue(dlg.GetPath())
                falar("Pasta de abertura selecionada.", imediato=True)

    def OnAlterarPastaSalvar(self, event):
        with wx.DirDialog(self, "Escolha a pasta padrão para Salvar", defaultPath=self.txt_pasta_salvar.GetValue()) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txt_pasta_salvar.SetValue(dlg.GetPath())
                falar("Pasta de salvamento selecionada.", imediato=True)

    def OnVerificarAtualizacoesAgora(self, event):
        self.btn_verificar_agora.Disable()
        self.btn_verificar_agora.SetLabel("Procurando...")
        falar("Procurando atualizações...", imediato=True)
        threading.Thread(target=self._checar_atualizacao_thread, daemon=True).start()

    def _checar_atualizacao_thread(self):
        tem, versao_nova, url = verificar_nova_versao(self.repo_github, self.versao_atual)
        wx.CallAfter(self._mostrar_resultado_atualizacao, tem, versao_nova, url)

    def _mostrar_resultado_atualizacao(self, tem, versao_nova, url):
        if not self:
            return
        self.btn_verificar_agora.Enable()
        self.btn_verificar_agora.SetLabel("&Procurar Atualizações Agora")
        if versao_nova is None:
            wx.MessageBox("Não foi possível verificar atualizações agora. Confira sua conexão com a internet.", "Atualizações", wx.OK | wx.ICON_WARNING, self)
        elif tem:
            resp = wx.MessageBox(
                f"Uma nova versão está disponível: {versao_nova} (você está usando a {self.versao_atual}).\n\nDeseja abrir a página de download agora?",
                "Atualização disponível", wx.YES_NO | wx.ICON_INFORMATION, self)
            if resp == wx.YES:
                import webbrowser
                webbrowser.open(url)
        else:
            wx.MessageBox("Você já está com a versão mais recente.", "Atualizações", wx.OK | wx.ICON_INFORMATION, self)

    def GetValues(self):
        metro_sel = self.midi_metro_choice.GetStringSelection()
        return {
            "midi_out": self.midi_out_choice.GetStringSelection(),
            "midi_in": [self.midi_in_list.GetString(i) for i in self.midi_in_list.GetCheckedItems()],
            "midi_out_metronomo": "" if metro_sel == "(mesma porta principal)" else metro_sel,
            "metronomo_volume": self.sp_volume_metro.GetValue(),
            "ins_files": self.ins_listbox.GetStrings(),
            "selected_ins_idx": self.ins_listbox.GetSelection(),
            "verificar_atualizacoes": self.chk_verificar_atualizacoes.GetValue(),
            "pasta_abrir": self.txt_pasta_abrir.GetValue(),
            "pasta_salvar": self.txt_pasta_salvar.GetValue()
        }

class EditNoteDialog(wx.Dialog):
    def __init__(self, parent, note_val, vel_val, dur_ticks, tick_val):
        super().__init__(parent, title="Editar Nota Completa", size=(350, 300))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Nota (0-127):"), 0, wx.ALL, 5)
        self.sc_note = wx.SpinCtrl(self, value=str(note_val), min=0, max=127)
        sizer.Add(self.sc_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        sizer.Add(wx.StaticText(self, label="Velocity (1-127):"), 0, wx.ALL, 5)
        self.sc_vel = wx.SpinCtrl(self, value=str(vel_val), min=1, max=127)
        sizer.Add(self.sc_vel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        sizer.Add(wx.StaticText(self, label="Duração (Ticks):"), 0, wx.ALL, 5)
        self.sc_dur = wx.SpinCtrl(self, value=str(dur_ticks), min=1, max=99999)
        sizer.Add(self.sc_dur, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        sizer.Add(wx.StaticText(self, label="Posição (Tick Relativo à Seção):"), 0, wx.ALL, 5)
        self.sc_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=999999)
        sizer.Add(self.sc_tick, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.sc_note.SetFocus)

    def get_values(self):
        return self.sc_note.GetValue(), self.sc_vel.GetValue(), self.sc_dur.GetValue(), self.sc_tick.GetValue()

class GlobalDSPDialog(wx.Dialog):
    # DSP Global (Reverb e Chorus) - trazido do MHS MIDI Sequencer, endereços
    # confirmados (bloco 02 01, 00-0D Reverb, 20-2D Chorus - Data List
    # oficial do PSR-SX600, página 65). Cada efeito tem os mesmos 16
    # parâmetros + Return que a Variation já tinha, com o mesmo modelo de
    # "-1 = não usar" (ver EditorParametrosVariationDialog).
    def __init__(self, parent):
        super().__init__(parent, title="Efeitos DSP Globais (Yamaha XG)", size=(480, 560))
        self.parent = parent
        self.orig = dict(parent.dsp_global)
        cache = parent.dsp_global

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(panel)

        rev_msb_val = REV_MSB_LIST[cache.get('rev_msb_idx', 1)][1] if cache.get('rev_msb_idx', 1) < len(REV_MSB_LIST) else 1
        rev_scr, self.rev_msb_choice, self.rev_lsb_choice, self.rev_ret_spin, self.rev_modulos = self._monta_pagina(
            notebook, "Reverb", rev_msb_val, REV_MSB_LIST, cache.get('rev_msb_idx', 1),
            cache.get('rev_lsb_idx', 0), cache.get('rev_ret', 64), cache.get('rev_p', [-1] * 16))
        notebook.AddPage(rev_scr.GetParent(), "Reverb Global")

        cho_msb_val = CHO_MSB_LIST[cache.get('cho_msb_idx', 1)][1] if cache.get('cho_msb_idx', 1) < len(CHO_MSB_LIST) else 65
        cho_scr, self.cho_msb_choice, self.cho_lsb_choice, self.cho_ret_spin, self.cho_modulos = self._monta_pagina(
            notebook, "Chorus", cho_msb_val, CHO_MSB_LIST, cache.get('cho_msb_idx', 1),
            cache.get('cho_lsb_idx', 0), cache.get('cho_ret', 64), cache.get('cho_p', [-1] * 16))
        notebook.AddPage(cho_scr.GetParent(), "Chorus Global")

        vbox.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)
        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Aplicar")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btns.AddButton(self.btn_ok)
        btns.AddButton(self.btn_cancel)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.rev_msb_choice.Bind(wx.EVT_CHOICE, self.on_rev_msb_change)
        self.cho_msb_choice.Bind(wx.EVT_CHOICE, self.on_cho_msb_change)
        for ctrl in ([self.rev_lsb_choice, self.rev_ret_spin] + [m for m in self.rev_modulos if m is not None]
                     + [self.cho_lsb_choice, self.cho_ret_spin] + [m for m in self.cho_modulos if m is not None]):
            ctrl.Bind(wx.EVT_CHOICE if isinstance(ctrl, wx.Choice) else wx.EVT_SPINCTRL, self.on_change)
        wx.CallLater(100, self.rev_msb_choice.SetFocus)

    def _monta_pagina(self, notebook, rotulo, msb_val, msb_list, msb_idx, lsb_idx, ret_val, p_salvos):
        # Monta uma página (Reverb ou Chorus) com Categoria, Preset (com
        # nome de verdade via nomes_presets), Return e os até 16
        # parâmetros nomeados via DSP_PARAM_NAMES - mesmo esquema visual
        # da Variation, dentro de uma área rolável (16 campos não cabem
        # de uma vez na tela).
        pai = wx.Panel(notebook)
        scr = wx.ScrolledWindow(pai, style=wx.VSCROLL)
        scr.SetScrollRate(0, 20)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(scr, label=f"Categoria do {rotulo}:"), 0, wx.LEFT | wx.TOP, 10)
        msb_choice = wx.Choice(scr, choices=[item[0] for item in msb_list])
        msb_choice.SetSelection(msb_idx)
        msb_choice.SetName(f"Categoria do {rotulo}")
        sizer.Add(msb_choice, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Add(wx.StaticText(scr, label=f"Preset do {rotulo}:"), 0, wx.LEFT | wx.TOP, 10)
        lsb_choice = wx.Choice(scr, choices=nomes_presets(msb_val))
        lsb_choice.SetSelection(lsb_idx if 0 <= lsb_idx < lsb_choice.GetCount() else wx.NOT_FOUND)
        lsb_choice.SetName(f"Preset do {rotulo}")
        sizer.Add(lsb_choice, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Add(wx.StaticText(scr, label="Return / Dry-Wet Balance (0 a 127):"), 0, wx.LEFT | wx.TOP, 10)
        ret_spin = wx.SpinCtrl(scr, value=str(ret_val), min=0, max=127)
        ret_spin.SetName(f"Return do {rotulo}")
        sizer.Add(ret_spin, 0, wx.EXPAND | wx.ALL, 5)

        nomes = DSP_PARAM_NAMES.get(msb_val, [f"Parâmetro {i + 1}" for i in range(16)])
        maximos_msb = DSP_PARAM_MAX.get(msb_val, {})
        modulos = [None] * 16
        for i in range(16):
            if i >= len(nomes) or nomes[i] == "-":
                continue
            # Alguns parâmetros são uma lista curta de opções com nome (ex:
            # "Input Mode: Mono, Stereo") em vez de 0-127 livre - o Data List
            # documenta o valor máximo real, então o slider para no último
            # nome em vez de rolar até 127 à toa.
            max_i = maximos_msb.get(i, 127)
            sizer.Add(wx.StaticText(scr, label=f"{nomes[i]} (0 a {max_i}, -1 = não usar):"), 0, wx.LEFT | wx.TOP, 10)
            sl = wx.SpinCtrl(scr, value=str(p_salvos[i] if i < len(p_salvos) else -1), min=-1, max=max_i)
            sl.SetName(nomes[i])
            sl._opcoes_dsp = DSP_PARAM_OPTIONS.get(msb_val, {}).get(i)
            sizer.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            modulos[i] = sl

        scr.SetSizer(sizer)
        pai_sizer = wx.BoxSizer(wx.VERTICAL)
        pai_sizer.Add(scr, 1, wx.EXPAND)
        pai.SetSizer(pai_sizer)
        return scr, msb_choice, lsb_choice, ret_spin, modulos

    def on_rev_msb_change(self, event):
        msb_sel = self.rev_msb_choice.GetSelection()
        msb_val = REV_MSB_LIST[msb_sel][1] if msb_sel != wx.NOT_FOUND and msb_sel < len(REV_MSB_LIST) else 1
        self.rev_lsb_choice.Set(nomes_presets(msb_val))
        self.rev_lsb_choice.SetSelection(0)
        self.on_change(event)

    def on_cho_msb_change(self, event):
        msb_sel = self.cho_msb_choice.GetSelection()
        msb_val = CHO_MSB_LIST[msb_sel][1] if msb_sel != wx.NOT_FOUND and msb_sel < len(CHO_MSB_LIST) else 65
        self.cho_lsb_choice.Set(nomes_presets(msb_val))
        self.cho_lsb_choice.SetSelection(0)
        self.on_change(event)

    def on_change(self, event=None, obj=None):
        c = self.parent.dsp_global
        c['active'] = True
        c['rev_msb_idx'] = self.rev_msb_choice.GetSelection()
        c['rev_lsb_idx'] = self.rev_lsb_choice.GetSelection()
        c['rev_ret'] = self.rev_ret_spin.GetValue()
        c['rev_p'] = [m.GetValue() if m else -1 for m in self.rev_modulos]
        c['cho_msb_idx'] = self.cho_msb_choice.GetSelection()
        c['cho_lsb_idx'] = self.cho_lsb_choice.GetSelection()
        c['cho_ret'] = self.cho_ret_spin.GetValue()
        c['cho_p'] = [m.GetValue() if m else -1 for m in self.cho_modulos]
        self.parent.enviar_dsp_global()
        if obj is None and event is not None:
            obj = event.GetEventObject()
        if obj is not None and hasattr(obj, 'GetName'):
            nome = obj.GetName()
            if isinstance(obj, wx.Choice):
                falar(f"{nome}: {obj.GetStringSelection()}", imediato=True)
            elif isinstance(obj, wx.SpinCtrl):
                falar(_rotulo_valor_dsp(nome, obj.GetValue(), getattr(obj, '_opcoes_dsp', None)), imediato=True)
        if event is not None:
            event.Skip()

    def restaurar(self):
        self.parent.dsp_global.update(self.orig)
        self.parent.enviar_dsp_global()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE: self.EndModal(wx.ID_CANCEL); return
        # Barra de espaço = Tocar/Parar, Ctrl+Espaço = Tocar/Pausar - igual
        # ao editor de DSP do MHS MIDI Sequencer, pra poder ouvir o estilo
        # tocando enquanto ajusta o efeito, sem fechar essa tela.
        if code == wx.WXK_SPACE:
            if event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePause(None); return
            if not event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePlay(None); return
        obj = self.FindFocus()
        if isinstance(obj, wx.SpinCtrl):
            val, max_v, min_v = obj.GetValue(), obj.GetMax(), obj.GetMin()
            mudou = False
            if code == wx.WXK_HOME: val = max_v; mudou = True
            elif code == wx.WXK_END: val = min_v; mudou = True
            elif code in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP): val = min(max_v, val + 10); mudou = True
            elif code in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN): val = max(min_v, val - 10); mudou = True
            if mudou:
                obj.SetValue(val)
                self.on_change(None, obj)
                return
        event.Skip()

class SelecionarEfeitoVariationDialog(wx.Dialog):
    # Passo 1: escolhe os canais, família e preset do único efeito de
    # inserção que o Style Creator edita ("Variation", bloco 43 10 4C 02
    # 01) - o Data List oficial do PSR-SX600 confirma que o teclado real
    # só tem essa gaveta editável por SysEx de estilo; times com teclados
    # de mais gavetas usam o MHS MIDI Sequencer pra isso. Vários canais
    # marcados aqui tocam o MESMO efeito ao mesmo tempo - a "Conexão" vai
    # sempre em SYSTEM, e cada canal marcado manda seu próprio "Variation
    # Send Level" (ver sincronizar_dsp_no_track no MainFrame).
    def __init__(self, parent, canal_inicial):
        super().__init__(parent, title="Efeito de Inserção (DSP Variation)", size=(420, 460))
        self.parent = parent
        self.lsb_original = 0
        self.efeito_removido = False

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(panel, label="1. Canais que vão passar pelo efeito (marque quantos quiser):"), 0, wx.ALL, 5)
        self.clb_canais = wx.CheckListBox(panel, choices=[rotulo_canal(i) for i in range(16)])
        vbox.Add(self.clb_canais, 1, wx.EXPAND | wx.ALL, 5)

        vbox.Add(wx.StaticText(panel, label="2. Família do Efeito:"), 0, wx.ALL, 5)
        self.cb_msb = wx.Choice(panel, choices=[item[0] for item in VARIATION_EFEITOS_LIST])
        vbox.Add(self.cb_msb, 0, wx.EXPAND | wx.ALL, 5)

        v = parent.dsp_variation
        msb_atual = v.get('msb_val', 0)
        vbox.Add(wx.StaticText(panel, label="3. Preset (Variação):"), 0, wx.ALL, 5)
        self.cb_lsb = wx.Choice(panel, choices=nomes_presets(msb_atual))
        vbox.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)

        self.cb_msb.SetSelection(v.get('msb_idx', 0))
        # Guarda o valor de verdade à parte - o LSB real do protocolo XG vai
        # de 0 a 127, e essa lista agora mostra até 40 presets nomeados via
        # nomes_presets(). Um arquivo genuíno (ex: Força.sty) pode trazer um
        # LSB fora desse intervalo - SetSelection com um índice inválido não
        # seleciona nada, e dava wx.NOT_FOUND (-1) na volta, que quebrava o
        # SysEx na hora de gravar (mido não aceita byte negativo). Sem esse
        # valor original, reabrir e fechar de novo sem mexer nesse campo
        # corrompia o preset pra sempre.
        self.lsb_original = v.get('lsb_idx', 0)
        self.cb_lsb.SetSelection(self.lsb_original if 0 <= self.lsb_original < self.cb_lsb.GetCount() else wx.NOT_FOUND)
        canais_marcados = list(v.get('chs', {}).keys()) if v.get('active', False) else [max(0, min(15, canal_inicial))]
        for ch in canais_marcados:
            if 0 <= ch < 16:
                self.clb_canais.Check(ch, True)
        self.cb_msb.Bind(wx.EVT_CHOICE, self.on_msb_mudou)

        self.btn_remover = wx.Button(panel, wx.ID_ANY, "Remover Efeito Existente")
        self.btn_remover.Enable(v.get('active', False))
        vbox.Add(self.btn_remover, 0, wx.EXPAND | wx.ALL, 5)
        self.btn_remover.Bind(wx.EVT_BUTTON, self.on_remover)

        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Avançar para Edição")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btns.AddButton(self.btn_ok)
        btns.AddButton(self.btn_cancel)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.clb_canais.SetFocus)

    def on_remover(self, event):
        v = self.parent.dsp_variation
        if not v.get('active', False):
            falar("Não tem nenhum efeito configurado agora.", imediato=True)
            return
        canais_removidos = ", ".join(str(c + 1) for c in v.get('chs', {}).keys())
        # Manda Bypass (tipo 0) ao vivo primeiro - só apagar do dicionário
        # não desliga o que o teclado já recebeu antes; isso desconecta os
        # canais do efeito de verdade, agora.
        v['msb_val'] = 0
        v['lsb_idx'] = 0
        self.parent.enviar_dsp_variation()
        # Só agora reseta pro padrão (equivalente a nunca ter configurado
        # nada) e sincroniza, pra tirar de vez o SysEx do arquivo.
        v.clear()
        v.update(self.parent._dsp_variation_padrao())
        self.parent.sincronizar_dsp_no_track()
        falar(f"Efeito removido. Canais que estavam ativos: {canais_removidos or 'nenhum'}.", imediato=True)
        self.efeito_removido = True
        self.EndModal(wx.ID_CANCEL)

    def on_msb_mudou(self, event):
        # Cada família tem seus próprios presets nomeados - troca a lista do
        # Preset pra corresponder à família recém-escolhida, em vez de
        # deixar nomes da família anterior por engano.
        msb_sel = self.cb_msb.GetSelection()
        msb_val = VARIATION_EFEITOS_LIST[msb_sel][1] if msb_sel != wx.NOT_FOUND else 0
        self.cb_lsb.Set(nomes_presets(msb_val))
        self.cb_lsb.SetSelection(0)
        event.Skip()

    def get_valores(self):
        msb_idx = self.cb_msb.GetSelection()
        msb_val = VARIATION_EFEITOS_LIST[msb_idx][1]
        sel_lsb = self.cb_lsb.GetSelection()
        # Se o controle não tem seleção válida (o valor real veio de fora
        # do intervalo mostrado aqui), mantém o valor original em vez de
        # gravar wx.NOT_FOUND (-1) por cima dele.
        lsb_idx = sel_lsb if sel_lsb != wx.NOT_FOUND else self.lsb_original
        canais_idx = [i for i in range(16) if self.clb_canais.IsChecked(i)]
        return canais_idx, msb_idx, msb_val, lsb_idx

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE: self.EndModal(wx.ID_CANCEL); return
        # Barra de espaço = Tocar/Parar, Ctrl+Espaço = Tocar/Pausar - igual
        # ao MHS MIDI Sequencer. O Espaço sozinho não mexe quando o foco
        # está na lista de canais (lá o Espaço já marca/desmarca a caixa).
        if code == wx.WXK_SPACE:
            if event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePause(None); return
            if not event.ControlDown() and not event.AltDown() and not event.ShiftDown() and self.FindFocus() is not self.clb_canais:
                self.parent.OnTogglePlay(None); return
        event.Skip()

class EditorParametrosVariationDialog(wx.Dialog):
    # Passo 2: os parâmetros do efeito escolhido, mais o Return/Dry-Wet.
    # O índice 9 (a 10ª posição) nunca vira um controle próprio - em todo
    # efeito ele é o "Dry/Wet Balance", e esse já é o Return abaixo (mesmo
    # endereço 0x54 no protocolo, ver enviar_dsp_variation). canais_idx é a
    # lista de canais marcados no passo 1 - todos tocam o mesmo efeito.
    def __init__(self, parent, canais_idx, msb_val, msb_idx, lsb_idx):
        rotulo_canais = ", ".join(str(c + 1) for c in canais_idx) if canais_idx else "nenhum"
        super().__init__(parent, title=f"Parâmetros do Efeito - Canais {rotulo_canais}", size=(450, 650))
        self.parent = parent
        self.canais_idx = canais_idx
        self.msb_val = msb_val

        self.cache = parent.dsp_variation
        # Preserva o nível de envio já configurado de cada canal (se já
        # existia) em vez de zerar tudo pro padrão de novo.
        chs_existentes = self.cache.get('chs', {})
        novo_chs = {ch: chs_existentes.get(ch, 127) for ch in canais_idx}
        self.cache.update({'active': True, 'chs': novo_chs, 'msb_idx': msb_idx, 'msb_val': msb_val, 'lsb_idx': lsb_idx})

        nomes = DSP_PARAM_NAMES.get(msb_val, [f"Parâmetro {i+1}" for i in range(16)])

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scr.SetScrollRate(0, 20)
        scrsz = wx.BoxSizer(wx.VERTICAL)

        # Preset aqui dentro também, além do passo 1 - assim dá pra ir
        # trocando e já ouvir na hora, sem precisar voltar pra tela
        # anterior toda vez.
        scrsz.Add(wx.StaticText(scr, label="Preset (Variação):"), 0, wx.LEFT | wx.TOP, 10)
        self.cb_lsb = wx.Choice(scr, choices=nomes_presets(msb_val))
        self.cb_lsb.SetName("Preset")
        # O LSB de verdade vai de 0 a 127; nomes_presets() já cobre até 40 -
        # se o valor vier de fora desse intervalo, mantém o original sem
        # mostrar nada selecionado em vez de forçar um valor errado.
        self.lsb_original = lsb_idx
        self.cb_lsb.SetSelection(lsb_idx if 0 <= lsb_idx < self.cb_lsb.GetCount() else wx.NOT_FOUND)
        scrsz.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)
        self.cb_lsb.Bind(wx.EVT_CHOICE, self.on_preset_mudou)

        scrsz.Add(wx.StaticText(scr, label="Return / Dry-Wet Balance (0 a 127):"), 0, wx.LEFT | wx.TOP, 10)
        self.sl_ret = wx.SpinCtrl(scr, value=str(self.cache.get('ret', 64)), min=0, max=127)
        self.sl_ret.SetName("Return / Dry-Wet Balance")
        scrsz.Add(self.sl_ret, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_ret.Bind(wx.EVT_SPINCTRL, self.enviar)

        # Com 2 ou mais canais, a Conexão vira SYSTEM (ver
        # sincronizar_dsp_no_track) - nesse modo o Return é o volume geral
        # do efeito, e quem controla o quanto CADA canal manda sinal pra
        # ele é o nível de envio individual (0-127), igual ao Reverb/
        # Chorus. Com só 1 canal, o modo INSERTION antigo já resolve isso
        # sozinho com o Return, então esses campos nem aparecem.
        self.sl_canais = {}
        if len(canais_idx) > 1:
            scrsz.Add(wx.StaticText(scr, label="Nível de envio de cada canal pro efeito (0 a 127):"), 0, wx.LEFT | wx.TOP, 10)
            for ch in canais_idx:
                rotulo = rotulo_canal(ch)
                lbl = wx.StaticText(scr, label=f"{rotulo} (0 a 127):")
                scrsz.Add(lbl, 0, wx.LEFT | wx.TOP, 10)
                sl = wx.SpinCtrl(scr, value=str(novo_chs.get(ch, 127)), min=0, max=127)
                sl.SetName(f"Envio do canal {rotulo}")
                scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
                sl.Bind(wx.EVT_SPINCTRL, self.enviar)
                self.sl_canais[ch] = sl

        # Famílias de Delay/Echo/Cross Delay (msb 5,6,7,8) têm alguns
        # parâmetros em milissegundos (até 7150) em vez do 0-127 normal -
        # essa lista diz quais índices são esses, pra cada família.
        indices_longos = DSP_LONG_PARAM_INDICES.get(msb_val, [])
        maximos_msb = DSP_PARAM_MAX.get(msb_val, {})
        self.modulos = [None] * 16
        parametros_salvos = self.cache.get('p', [-1] * 16)
        for i in range(16):
            if i == 9 or i >= len(nomes) or nomes[i] == "-":
                continue
            # Alguns parâmetros são uma lista curta de opções com nome (ex:
            # "Device: Transistor, Vintage Tube, Dist1, Dist2, Fuzz") - o Data
            # List documenta o valor máximo real, então o slider para no
            # último nome em vez de rolar até 127 à toa.
            limite = 7150 if i in indices_longos else maximos_msb.get(i, 127)
            unidade = "ms" if i in indices_longos else ""
            scrsz.Add(wx.StaticText(scr, label=f"{nomes[i]} (0 a {limite}{unidade}, -1 = não usar):"), 0, wx.LEFT | wx.TOP, 10)
            sl = wx.SpinCtrl(scr, value=str(parametros_salvos[i]), min=-1, max=limite)
            sl.SetName(nomes[i])
            sl._opcoes_dsp = None if i in indices_longos else DSP_PARAM_OPTIONS.get(msb_val, {}).get(i)
            scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            sl.Bind(wx.EVT_SPINCTRL, self.enviar)
            self.modulos[i] = sl

        scr.SetSizer(scrsz)
        vbox.Add(scr, 1, wx.EXPAND | wx.ALL, 5)
        # Id proposital NÃO é wx.ID_OK - um botão com esse id especial tem
        # comportamento nativo do Windows que fecha o diálogo por fora do
        # nosso Bind, sem rodar fechar_salvando() - foi por causa disso que
        # sincronizar_dsp_no_track() não era chamado ao clicar aqui, mesmo
        # com os valores certos já capturados (confirmado pelo log do NVDA).
        btn_ok = wx.Button(panel, wx.ID_ANY, "Fechar e Manter")
        vbox.Add(btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)
        self.btn_ok = btn_ok

        btn_ok.Bind(wx.EVT_BUTTON, self.on_ok_button)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallLater(100, self.sl_ret.SetFocus)
        self.enviar(None)

    def fechar_salvando(self):
        # Lê o valor ATUAL de cada SpinCtrl direto (GetValue), em vez de
        # confiar só no que o EVT_SPINCTRL já capturou - digitar um número e
        # dar Tab não dispara EVT_SPINCTRL de forma confiável no wx (só
        # clique nas setinhas ou Enter dentro do campo garantem isso), então
        # sem essa leitura final um valor digitado (ex: 127) nunca chegava a
        # entrar no cache e a gravação no arquivo saía sem os parâmetros -
        # exatamente o "voltou tudo pro padrão -1" relatado depois de salvar.
        #
        # Ainda falta um detalhe: o SpinCtrl só VALIDA de verdade o número
        # digitado quando perde o foco - se o campo que você acabou de
        # digitar ainda estava em foco no instante de fechar, GetValue()
        # podia devolver o valor de ANTES da digitação. Forçando o foco pro
        # botão OK primeiro, o campo perde o foco (e valida) antes da gente
        # ler os valores.
        foco = self.FindFocus()
        if foco is not None and foco is not self.btn_ok:
            self.btn_ok.SetFocus()
        self.enviar(None)
        usados = [v for v in self.cache['p'] if v != -1]
        falar(f"Fechando. Return {self.cache['ret']}. {len(usados)} parâmetro(s) com valor: {', '.join(str(v) for v in usados)}." if usados else f"Fechando. Return {self.cache['ret']}. Nenhum parâmetro com valor definido.", imediato=True)
        # Chamar sincronizar_dsp_no_track() daqui de dentro (antes do
        # EndModal) travava o programa inteiro - voltou a ser
        # responsabilidade do MainFrame (abrir_dsp_variation), chamado
        # incondicionalmente depois do ShowModal(), sem depender do valor
        # de retorno (ver comentário lá).
        self.EndModal(wx.ID_OK)

    def on_ok_button(self, event):
        self.fechar_salvando()

    def on_close(self, event):
        # Fechar pelo X da janela (ou Alt+F4) usava o EVT_CLOSE padrão do
        # wx.Dialog, que dá EndModal(ID_CANCEL) - e abrir_dsp_variation só
        # chama sincronizar_dsp_no_track() quando ShowModal() volta ID_OK.
        # Esse editor não tem um "cancelar" de verdade (Enter e Esc também
        # mantêm os valores), então os três jeitos de fechar têm que salvar
        # igual.
        self.fechar_salvando()

    def on_preset_mudou(self, event):
        # Cada Preset tem seus próprios valores de fábrica pros parâmetros
        # dentro do teclado - mas se um campo aqui já estivesse com um
        # número fixo (não em "-1 = não usar"), ele continuava sendo
        # mandado igual, não importa o preset escolhido, atropelando o
        # padrão de fábrica de cada um. Por isso, toda vez que troca o
        # Preset, os parâmetros voltam pra "-1 = não usar" primeiro, pra
        # você ouvir o preset puro; se quiser, ajusta de novo depois.
        for sl in self.modulos:
            if sl is not None:
                # SetValue(-1) (int) só atualiza o valor por baixo dos
                # panos - o texto do campo (o que o NVDA lê ao entrar nele)
                # só é atualizado de verdade passando a string mesmo.
                sl.SetValue("-1")
        self.enviar(event)

    def enviar(self, event=None, obj=None):
        sel_lsb = self.cb_lsb.GetSelection()
        # Mesma regra do passo 1: sem seleção válida (LSB original fora de
        # 0-15), mantém o valor original em vez de gravar wx.NOT_FOUND (-1).
        self.cache['lsb_idx'] = sel_lsb if sel_lsb != wx.NOT_FOUND else self.lsb_original
        self.cache['ret'] = self.sl_ret.GetValue()
        self.cache['p'] = [m.GetValue() if m else -1 for m in self.modulos]
        for ch, sl in self.sl_canais.items():
            self.cache['chs'][ch] = sl.GetValue()
        self.parent.enviar_dsp_variation()
        alvo = obj if obj is not None else (event.GetEventObject() if event is not None else None)
        if isinstance(alvo, wx.Choice):
            falar(f"{alvo.GetName()}: {alvo.GetStringSelection()}", imediato=True)
        elif alvo is not None and hasattr(alvo, 'GetName'):
            falar(_rotulo_valor_dsp(alvo.GetName(), alvo.GetValue(), getattr(alvo, '_opcoes_dsp', None)), imediato=True)

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: self.fechar_salvando(); return
        if code == wx.WXK_ESCAPE: self.fechar_salvando(); return
        # Barra de espaço = Tocar/Parar, Ctrl+Espaço = Tocar/Pausar - igual
        # ao editor de DSP do MHS MIDI Sequencer, pra poder ouvir o estilo
        # tocando enquanto ajusta os parâmetros, sem fechar essa tela.
        if code == wx.WXK_SPACE:
            if event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePause(None); return
            if not event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePlay(None); return
        obj = self.FindFocus()
        if isinstance(obj, wx.SpinCtrl):
            val, max_v, min_v = obj.GetValue(), obj.GetMax(), obj.GetMin()
            passo = 100 if max_v > 127 else 10
            mudou = False
            if code == wx.WXK_HOME: val = max_v; mudou = True
            elif code == wx.WXK_END: val = min_v; mudou = True
            elif code in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP): val = min(max_v, val + passo); mudou = True
            elif code in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN): val = max(min_v, val - passo); mudou = True
            if mudou:
                obj.SetValue(val)
                self.enviar(None, obj)
                return
        event.Skip()

class ExportarCanalDialog(wx.Dialog):
    # Exporta TODO o conteúdo de um canal (notas + CC + program change etc,
    # em todas as seções do estilo) para um ou mais canais de destino, com
    # transposição opcional em semitons - pensado pro caso de canais de
    # acorde gravados como nota única (ex: ritmos com loop de guitarra tipo
    # "Arrocha.sty" do Alex, que grava só a raiz e deixa o NTT harmonizar).
    # O CASM do canal de origem também é copiado (igual ao "Exportar CASM"
    # de dentro de Editar Seção), mas sem transpor - regras de NTT/Play
    # Type continuam as mesmas, só o "Redirecionar Para" é forçado a
    # apontar pro próprio canal de destino (senão o áudio saía redirecionado
    # de volta pro canal de origem).
    def __init__(self, parent, canal_origem):
        super().__init__(parent, title=f"Exportar Canal {rotulo_canal(canal_origem)}", size=(420, 480))
        self.parent = parent
        self.canal_origem = canal_origem
        self.canais_lista = [c for c in range(16) if c != canal_origem]

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(panel, label=f"Exportar todo o conteúdo (notas e CASM) do canal {rotulo_canal(canal_origem)} para os canais marcados abaixo:"), 0, wx.ALL, 5)
        self.clb_canais = wx.CheckListBox(panel, choices=[rotulo_canal(c) for c in self.canais_lista])
        vbox.Add(self.clb_canais, 1, wx.EXPAND | wx.ALL, 5)

        vbox.Add(wx.StaticText(panel, label="Transposição (semitons, -24 a +24):"), 0, wx.LEFT | wx.TOP, 5)
        self.sp_transpor = wx.SpinCtrl(panel, value="0", min=-24, max=24)
        self.sp_transpor.SetName("Transposição em semitons")
        vbox.Add(self.sp_transpor, 0, wx.EXPAND | wx.ALL, 5)

        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Exportar")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btns.AddButton(self.btn_ok)
        btns.AddButton(self.btn_cancel)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.sp_transpor.Bind(wx.EVT_SPINCTRL, self.on_transpor_change)
        wx.CallLater(100, self.clb_canais.SetFocus)

    def on_transpor_change(self, event):
        val = self.sp_transpor.GetValue()
        falar(f"Transposição: {val} semitons" if val != 0 else "Transposição: nenhuma", imediato=True)

    def get_valores(self):
        marcados = [self.canais_lista[i] for i in self.clb_canais.GetCheckedItems()]
        return marcados, self.sp_transpor.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL); return
        if self.FindFocus() is self.sp_transpor:
            if code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEUP, wx.WXK_NUMPAD_PAGEDOWN]:
                val, max_v, min_v = self.sp_transpor.GetValue(), self.sp_transpor.GetMax(), self.sp_transpor.GetMin()
                if code == wx.WXK_HOME: val = max_v
                elif code == wx.WXK_END: val = min_v
                elif code in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP): val = min(max_v, val + 10)
                elif code in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN): val = max(min_v, val - 10)
                self.sp_transpor.SetValue(val)
                self.on_transpor_change(None)
                return
        event.Skip()

class ClonarConfigCanalDialog(wx.Dialog):
    # Copia a CONFIGURAÇÃO de um canal (Volume, Pan, Expression, Reverb,
    # Chorus, Grave, Agudo, Bank, Patch + Drum Setup e Voice Creator, se
    # houver) pra um ou mais canais marcados - igual ao "Clonar
    # Configurações" do MHS MIDI Sequencer, só que com vários destinos.
    def __init__(self, parent, canal_origem):
        super().__init__(parent, title=f"Copiar Configurações do Canal {rotulo_canal(canal_origem)}", size=(420, 480))
        self.canal_origem = canal_origem
        self.canais_lista = [c for c in range(16) if c != canal_origem]

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(panel, label=f"Copiar toda a configuração do canal {rotulo_canal(canal_origem)} para os canais marcados abaixo:"), 0, wx.ALL, 5)
        self.clb_canais = wx.CheckListBox(panel, choices=[rotulo_canal(c) for c in self.canais_lista])
        self.clb_canais.SetName("Canais de destino")
        vbox.Add(self.clb_canais, 1, wx.EXPAND | wx.ALL, 5)

        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Copiar")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btns.AddButton(self.btn_ok)
        btns.AddButton(self.btn_cancel)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.clb_canais.SetFocus)

    def get_alvos(self):
        return [self.canais_lista[i] for i in self.clb_canais.GetCheckedItems()]

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL); return
        if code == ord('A') and event.ControlDown():
            self.clb_canais.SetCheckedItems(list(range(len(self.canais_lista)))); return
        event.Skip()


class CopiarCanalEntreSecoesDialog(wx.Dialog):
    # Copia o conteúdo de UM canal, de UMA seção específica (de qualquer
    # aba aberta - inclusive outras seções desta mesma aba), pra uma ou
    # mais seções de destino em qualquer aba - trazendo notas, CASM e as
    # propriedades de timbre/mixagem junto (mesmo espírito do "Exportar
    # CASM" de dentro de Editar Seção, só que também com o conteúdo
    # gravado e o timbre, não só as regras de CASM).
    def __init__(self, parent, canal_origem, nome_secao_origem, abas, aba_atual):
        super().__init__(parent, title=f"Copiar Canal {rotulo_canal(canal_origem)} ({nome_secao_origem}) Entre Seções", size=(460, 560))
        self.parent = parent
        self.canal_origem = canal_origem

        # Um grupo (com sua própria lista de marcação) por aba - a atual
        # primeiro, depois cada outra aba aberta. Antes era uma lista só,
        # gigante, com o nome da aba repetido na frente de cada seção; o
        # NVDA lia tudo isso item por item, uma "listona" só. Agora cada
        # grupo tem seu próprio título (falado uma vez, ao entrar nele com
        # Tab) e os itens dentro dele são só o nome da seção +
        # marcado/desmarcado (que o NVDA já fala sozinho, nativo do
        # CheckListBox).
        # A seção de origem NÃO é mais escondida da lista de destino - antes
        # era, pensando só no caso "copiar pra OUTRA seção", mas isso
        # bloqueava um uso legítimo: copiar um canal pra OUTRO CANAL dentro
        # da MESMA seção (ex.: duplicar Chord 2 pro Chord 3 pra trabalhar
        # loops de guitarra, pedido do Michel). Como o canal de destino é
        # escolhido à parte (combo abaixo), não tem como saber aqui se vai
        # dar canal_origem==canal_destino - e mesmo nesse caso extremo
        # (mesma seção E mesmo canal) o algoritmo não quebra, só re-cola o
        # mesmo conteúdo que acabou de tirar (sem efeito prático).
        itens_aba_atual = [(None, n) for n in YAMAHA_SECTION_ORDER]
        self.grupos = [("Aba atual", itens_aba_atual)]
        for i, aba in enumerate(abas):
            if i == aba_atual:
                continue
            self.grupos.append((aba['titulo'], [(i, n) for n in YAMAHA_SECTION_ORDER]))

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(panel, label="Marque as seções de destino (de qualquer aba aberta) que devem receber esse canal:"), 0, wx.ALL, 5)

        self.clbs_grupos = []
        for titulo_grupo, itens_grupo in self.grupos:
            vbox.Add(wx.StaticText(panel, label=titulo_grupo), 0, wx.LEFT | wx.TOP, 5)
            clb = wx.CheckListBox(panel, choices=[n for _, n in itens_grupo], size=(-1, 120))
            clb.SetName(f"Grupo {titulo_grupo}")
            clb.Bind(wx.EVT_SET_FOCUS, self._on_foco_grupo(titulo_grupo))
            vbox.Add(clb, 1, wx.EXPAND | wx.ALL, 5)
            self.clbs_grupos.append(clb)

        vbox.Add(wx.StaticText(panel, label="Canal de destino:"), 0, wx.LEFT | wx.TOP, 5)
        self.cb_canal_destino = wx.Choice(panel, choices=[rotulo_canal(c) for c in range(16)])
        self.cb_canal_destino.SetName("Canal de destino")
        self.cb_canal_destino.SetSelection(canal_origem)
        vbox.Add(self.cb_canal_destino, 0, wx.EXPAND | wx.ALL, 5)

        vbox.Add(wx.StaticText(panel, label="Transposição (semitons, -24 a +24):"), 0, wx.LEFT | wx.TOP, 5)
        self.sp_transpor = wx.SpinCtrl(panel, value="0", min=-24, max=24)
        self.sp_transpor.SetName("Transposição em semitons")
        vbox.Add(self.sp_transpor, 0, wx.EXPAND | wx.ALL, 5)

        btns = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Copiar")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btns.AddButton(self.btn_ok)
        btns.AddButton(self.btn_cancel)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.sp_transpor.Bind(wx.EVT_SPINCTRL, self.on_transpor_change)
        wx.CallLater(100, self.clbs_grupos[0].SetFocus)

    def _on_foco_grupo(self, titulo_grupo):
        # Fábrica de handler pra cada grupo já "amarrar" o próprio título -
        # sem isso, todos os binds do for de cima acabariam falando só o
        # título do ÚLTIMO grupo (efeito colateral clássico de lambda
        # dentro de laço em Python).
        def handler(event):
            falar(f"Grupo: {titulo_grupo}", imediato=True)
            event.Skip()
        return handler

    def on_transpor_change(self, event):
        val = self.sp_transpor.GetValue()
        falar(f"Transposição: {val} semitons" if val != 0 else "Transposição: nenhuma", imediato=True)

    def get_valores(self):
        marcados = []
        for (_, itens_grupo), clb in zip(self.grupos, self.clbs_grupos):
            for idx in clb.GetCheckedItems():
                marcados.append(itens_grupo[idx])
        return marcados, self.cb_canal_destino.GetSelection(), self.sp_transpor.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL); return
        if self.FindFocus() is self.sp_transpor:
            if code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEUP, wx.WXK_NUMPAD_PAGEDOWN]:
                val, max_v, min_v = self.sp_transpor.GetValue(), self.sp_transpor.GetMax(), self.sp_transpor.GetMin()
                if code == wx.WXK_HOME: val = max_v
                elif code == wx.WXK_END: val = min_v
                elif code in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP): val = min(max_v, val + 10)
                elif code in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN): val = max(min_v, val - 10)
                self.sp_transpor.SetValue(val)
                self.on_transpor_change(None)
                return
        event.Skip()


class FadeDialog(wx.Dialog):
    # Trazido do MHS MIDI Sequencer, a pedido do Michel - mesma ideia: uma
    # rampa de CC 11 (Expression) entre as marcas de Entrada/Saída, pra não
    # mexer no Volume principal (CC 7) da mixagem.
    def __init__(self, parent):
        super().__init__(parent, title="Fade In / Fade Out (Expression)", size=(380, 250))

        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_info = wx.StaticText(self, label="O Fade utilizará o CC 11 (Expression) para preservar\no volume principal (CC 7) da sua mixagem.")
        sizer.Add(lbl_info, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.radio_box = wx.RadioBox(self, label="Tipo de Fade:", choices=["Fade In (0 ao Máximo)", "Fade Out (Máximo ao 0)"], majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.radio_box.SetSelection(1)
        sizer.Add(self.radio_box, 0, wx.EXPAND | wx.ALL, 10)

        self.chk_todos = wx.CheckBox(self, label="Aplicar Master Fade (Em todos os canais)")
        self.chk_todos.SetValue(True)
        sizer.Add(self.chk_todos, 0, wx.ALL, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

        wx.CallLater(100, self.radio_box.SetFocus)

    def get_valores(self):
        return self.radio_box.GetSelection(), self.chk_todos.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()


# As mesmas figuras/ticks (base 480) das 3 abas de Efeitos MIDI Offline.
MIDI_EFFECT_GRIDS = [
    ("Semínima (1/4)", 480), ("Semínima Tercina (1/4T)", 320),
    ("Colcheia (1/8)", 240), ("Colcheia Tercina (1/8T)", 160),
    ("Semicolcheia (1/16)", 120), ("Semicolcheia Tercina (1/16T)", 80),
    ("Fusa (1/32)", 60), ("Fusa Tercina (1/32T)", 40), ("Semifusa (1/64)", 30),
]


# --- PRESETS DE BATERIA (rufos/desenhos prontos) ---
# Notas GM/XG padrão de bateria usadas nos presets - mesma numeração em
# qualquer teclado GM/XG (não depende do Drum Setup do canal).
NOTA_CAIXA_AC = 38     # Acoustic Snare
NOTA_CAIXA_EL = 40     # Electric Snare
NOTA_CRASH_1 = 49      # Crash Cymbal 1
NOTA_CRASH_2 = 57      # Crash Cymbal 2
NOTA_CHINESE = 52      # Chinese Cymbal
NOTA_SPLASH = 55       # Splash Cymbal
NOTA_RIDE_1 = 51       # Ride Cymbal 1
NOTA_RIDE_BELL = 53    # Ride Bell
NOTA_RIDE_2 = 59       # Ride Cymbal 2
NOTA_HIHAT_FECHADO = 42
NOTA_HIHAT_PEDAL = 44
NOTA_HIHAT_ABERTO = 46
NOTA_TOM_GRAVE_1 = 41  # Low Floor Tom
NOTA_TOM_GRAVE_2 = 43  # High Floor Tom
NOTA_TOM_MEDIO_1 = 45  # Low Tom
NOTA_TOM_MEDIO_2 = 47  # Low-Mid Tom
NOTA_TOM_AGUDO_1 = 48  # Hi-Mid Tom
NOTA_TOM_AGUDO_2 = 50  # High Tom

def _rufo(nota, duracao_beats, subdivisao_ticks, vel_inicial, vel_final, nota_alternada=None, curva='linear'):
    # Gera um rufo/roll: uma sequência de batidas igualmente espaçadas
    # (subdivisao_ticks, na escala de 480 ticks por tempo, igual ao
    # MIDI_EFFECT_GRIDS acima), com velocity variando em RAMPA de
    # vel_inicial até vel_final ao longo da duração - é assim que se faz o
    # "começa bem baixinho e vai aumentando até bater no máximo" pedido
    # pelo Michel, só invertendo vel_inicial/vel_final pra decrescendo.
    # `curva='exponencial'`: a variação de velocity acelera em vez de ser
    # constante (fica mais "natural"/dramática - quase parada no início,
    # disparando rápido só perto do fim, igual um rufo de orquestra de
    # verdade em vez de uma rampa robótica).
    # `nota_alternada`: se dado, alterna entre `nota` e ela a cada batida
    # (ex.: Caixa Acústica/Elétrica, ou Crash/Chinês).
    total_ticks = int(round(480 * duracao_beats))
    n = max(2, int(round(total_ticks / subdivisao_ticks)))
    eventos = []
    for i in range(n):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        if curva == 'exponencial':
            frac = frac ** 2
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = nota if (nota_alternada is None or i % 2 == 0) else nota_alternada
        eventos.append((t, nt, v))
    return eventos

def _rufo_acelerando(nota, duracao_beats, subdivisao_inicial_ticks, subdivisao_final_ticks, vel_inicial, vel_final, nota_alternada=None):
    # Rufo onde a DENSIDADE das batidas também muda ao longo do tempo (não
    # só a velocity) - começa espaçado e vai "acelerando" até ficar bem
    # cerrado no fim (ou o contrário), tipo um rufo militar/de tambor de
    # verdade em vez de subdivisão fixa.
    total_ticks = int(round(480 * duracao_beats))
    eventos = []
    t = 0.0
    i = 0
    while t < total_ticks:
        frac = t / max(1, total_ticks)
        subdiv = subdivisao_inicial_ticks + (subdivisao_final_ticks - subdivisao_inicial_ticks) * frac
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = nota if (nota_alternada is None or i % 2 == 0) else nota_alternada
        eventos.append((int(round(t)), nt, v))
        t += max(5.0, subdiv)
        i += 1
    return eventos

def _rufo_ciclo(notas, duracao_beats, subdivisao_ticks, vel_inicial, vel_final):
    # Igual ao _rufo, mas girando por uma LISTA de notas em ciclo (ex.: os
    # 6 toms em sequência) em vez de só alternar entre 2 - um "giro" de
    # verdade, tipo roto-tom, em vez de ping-pong entre duas peças.
    total_ticks = int(round(480 * duracao_beats))
    n = max(2, int(round(total_ticks / subdivisao_ticks)))
    eventos = []
    for i in range(n):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = notas[i % len(notas)]
        eventos.append((t, nt, v))
    return eventos

def _virada_toms(duracao_beats, notas_em_ordem, vel_inicial=95, vel_final=118):
    # Virada clássica de toms - uma batida por tom da lista, igualmente
    # espaçada ao longo da duração, com crescendo leve de velocity (a
    # última batida da lista costuma ser um prato, propositalmente mais
    # forte que os toms).
    total_ticks = int(round(480 * duracao_beats))
    n = len(notas_em_ordem)
    eventos = []
    for i, nota in enumerate(notas_em_ordem):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        eventos.append((t, nota, v))
    return eventos

# Cada preset: (nome, categoria, duração em tempos/beats, eventos)
# eventos = lista de (offset_ticks_a_480_por_tempo, nota_midi, velocity)
BATERIA_PRESETS = [
    # --- Rufos de Caixa ---
    ("Rufo de Caixa Curto - 1/2 tempo", "Rufos de Caixa", 0.5,
        _rufo(NOTA_CAIXA_AC, 0.5, 40, 85, 127)),
    ("Rufo de Caixa - 1 tempo", "Rufos de Caixa", 1,
        _rufo(NOTA_CAIXA_AC, 1, 60, 70, 122)),
    ("Rufo de Caixa - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 60, 124)),
    ("Rufo de Caixa - 3 tempos", "Rufos de Caixa", 3,
        _rufo(NOTA_CAIXA_AC, 3, 60, 55, 126)),
    ("Rufo de Caixa Longo - 4 tempos", "Rufos de Caixa", 4,
        _rufo(NOTA_CAIXA_AC, 4, 60, 45, 127)),
    ("Rufo de Caixa Dupla (Acústica/Elétrica) - 1 tempo", "Rufos de Caixa", 1,
        _rufo(NOTA_CAIXA_AC, 1, 60, 70, 120, nota_alternada=NOTA_CAIXA_EL)),
    ("Rufo de Caixa Dupla (Acústica/Elétrica) - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 65, 124, nota_alternada=NOTA_CAIXA_EL)),
    ("Rufo de Caixa Curva Natural - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 55, 127, curva='exponencial')),
    ("Rufo de Caixa Curva Natural - 4 tempos", "Rufos de Caixa", 4,
        _rufo(NOTA_CAIXA_AC, 4, 60, 40, 127, curva='exponencial')),
    ("Rufo de Caixa Militar Acelerando - 2 tempos", "Rufos de Caixa", 2,
        _rufo_acelerando(NOTA_CAIXA_AC, 2, 150, 30, 60, 127)),
    ("Rufo de Caixa Militar Acelerando - 4 tempos", "Rufos de Caixa", 4,
        _rufo_acelerando(NOTA_CAIXA_AC, 4, 180, 25, 50, 127)),
    # --- Rufos de Prato ---
    ("Rufo de Prato Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_1, 1, 60, 30, 127)),
    ("Rufo de Prato Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 25, 127)),
    ("Rufo de Prato Crescendo - 3 tempos", "Rufos de Prato", 3,
        _rufo(NOTA_CRASH_1, 3, 60, 20, 127)),
    ("Rufo de Prato Crescendo Longo - 4 tempos", "Rufos de Prato", 4,
        _rufo(NOTA_CRASH_1, 4, 60, 15, 127)),
    ("Rufo de Prato Chinês Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 25, 127)),
    ("Rufo Duplo de Pratos (Crash/Chinês) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 25, 127, nota_alternada=NOTA_CHINESE)),
    ("Rufo de Prato Decrescendo (Máximo ao Silêncio) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 127, 20)),
    ("Rufo de Prato Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato Curva Natural Longo - 4 tempos", "Rufos de Prato", 4,
        _rufo(NOTA_CRASH_1, 4, 60, 10, 127, curva='exponencial')),
    ("Rufo de Prato Splash Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_SPLASH, 1, 60, 35, 127)),
    ("Rufo de Prato Acelerando - 3 tempos", "Rufos de Prato", 3,
        _rufo_acelerando(NOTA_CRASH_1, 3, 160, 40, 30, 127, nota_alternada=NOTA_CHINESE)),
    # Mesmos rufos, agora nas outras peças de prato (Ride 1, Crash 2,
    # Chinês, Splash) - pedido do Michel: "os rufos de prato só tem na
    # nota 49, quero os mesmos rufos também com as outras notas".
    ("Rufo de Prato (Ride 1) Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_RIDE_1, 1, 60, 30, 127)),
    ("Rufo de Prato (Ride 1) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 25, 127)),
    ("Rufo de Prato (Ride 1) Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato (Crash 2) Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_2, 1, 60, 30, 127)),
    ("Rufo de Prato (Crash 2) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 25, 127)),
    ("Rufo de Prato (Crash 2) Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato (Crash 2) Decrescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 127, 20)),
    ("Rufo de Prato Chinês Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato Chinês Decrescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 127, 20)),
    ("Rufo de Prato Splash - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_SPLASH, 2, 60, 30, 127)),
    ("Rufo de Prato Splash Curva Natural - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_SPLASH, 1, 60, 30, 127, curva='exponencial')),
    # Intercalados entre peças diferentes de prato.
    ("Rufo Intercalado (Crash 1 / Crash 2) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 30, 127, nota_alternada=NOTA_CRASH_2)),
    ("Rufo Intercalado (Crash 1 / Splash) - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_1, 1, 60, 40, 122, nota_alternada=NOTA_SPLASH)),
    ("Rufo Intercalado (Ride 1 / Chinês) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 35, 124, nota_alternada=NOTA_CHINESE)),
    # --- Rufos de Tom ---
    ("Rufo de Tom Grave - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_GRAVE_1, 1, 80, 70, 122)),
    ("Rufo de Tom Médio - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_MEDIO_1, 1, 80, 70, 122)),
    ("Rufo de Tom Agudo - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_AGUDO_2, 1, 80, 70, 122)),
    ("Rufo de Toms Alternado (Grave/Agudo) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_GRAVE_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Alternado Curva Natural - 3 tempos", "Rufos de Tom", 3,
        _rufo(NOTA_TOM_GRAVE_2, 3, 80, 50, 127, nota_alternada=NOTA_TOM_AGUDO_1, curva='exponencial')),
    # As outras peças de tom individualmente, mais combinações intercaladas
    # e uma versão girando pelos 6 - mesmo pedido do Michel pros pratos,
    # aplicado aqui também.
    ("Rufo de Tom Grave 2 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_GRAVE_2, 1, 80, 70, 122)),
    ("Rufo de Tom Médio 2 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_MEDIO_2, 1, 80, 70, 122)),
    ("Rufo de Tom Agudo 1 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_AGUDO_1, 1, 80, 70, 122)),
    ("Rufo de Toms Alternado (Grave 1 / Grave 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_GRAVE_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_GRAVE_2)),
    ("Rufo de Toms Alternado (Médio 1 / Médio 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_MEDIO_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_MEDIO_2)),
    ("Rufo de Toms Alternado (Agudo 1 / Agudo 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_AGUDO_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Decrescendo (Agudo) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_AGUDO_2, 2, 80, 127, 30)),
    ("Rufo Giratório de Toms (Todos os 6) - 2 tempos", "Rufos de Tom", 2,
        _rufo_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 2, 60, 60, 124)),
    ("Rufo Giratório de Toms (Todos os 6) - 4 tempos", "Rufos de Tom", 4,
        _rufo_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 4, 60, 50, 127)),
    # --- Viradas de Tom (fill clássico descendo/subindo) ---
    ("Virada de Toms Descendo - 1 tempo", "Viradas de Tom", 1,
        _virada_toms(1, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1])),
    ("Virada de Toms Descendo com Prato Final - 2 tempos", "Viradas de Tom", 2,
        _virada_toms(1.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_1])
        + [(1920, NOTA_CRASH_1, 127)]),
    ("Virada de Toms Subindo - 1 tempo", "Viradas de Tom", 1,
        _virada_toms(1, [NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2])),
    ("Virada de Toms Longa Descendo com Prato Final - 4 tempos", "Viradas de Tom", 4,
        _virada_toms(3.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1] * 3)
        + [(1920, NOTA_CRASH_2, 127)]),

    # --- Brincadeiras de Hi-Hat ---
    ("Brincadeira de Hi-Hat (Aberto/Fechado) - 1 tempo", "Brincadeiras de Hi-Hat", 1, [
        (0, NOTA_HIHAT_FECHADO, 90), (120, NOTA_HIHAT_FECHADO, 75), (240, NOTA_HIHAT_ABERTO, 100), (360, NOTA_HIHAT_PEDAL, 80),
    ]),
    ("Brincadeira de Hi-Hat (Aberto/Fechado) - 2 tempos", "Brincadeiras de Hi-Hat", 2, [
        (0, NOTA_HIHAT_FECHADO, 90), (120, NOTA_HIHAT_FECHADO, 75), (240, NOTA_HIHAT_FECHADO, 90), (360, NOTA_HIHAT_ABERTO, 105),
        (480, NOTA_HIHAT_PEDAL, 80), (600, NOTA_HIHAT_FECHADO, 90), (720, NOTA_HIHAT_ABERTO, 100), (840, NOTA_HIHAT_PEDAL, 80),
    ]),

    # --- Brincadeiras de Prato (Ride/Bell/Ride 2) ---
    ("Brincadeira de Prato - 1 tempo", "Brincadeiras de Prato", 1, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 90), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_2, 95),
    ]),
    ("Brincadeira de Prato - 2 tempos", "Brincadeiras de Prato", 2, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 88), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 92),
        (480, NOTA_RIDE_2, 96), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 90), (840, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato Sincopada - 2 tempos", "Brincadeiras de Prato", 2, [
        (0, NOTA_RIDE_1, 100), (160, NOTA_RIDE_BELL, 85), (320, NOTA_RIDE_2, 95), (400, NOTA_RIDE_BELL, 80),
        (480, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 90), (880, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato - 3 tempos", "Brincadeiras de Prato", 3, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 88), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 90),
        (480, NOTA_RIDE_2, 96), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 88), (840, NOTA_RIDE_1, 100),
        (960, NOTA_RIDE_BELL, 92), (1080, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato Longa - 4 tempos", "Brincadeiras de Prato", 4, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 85), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 88),
        (480, NOTA_RIDE_2, 92), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 85), (840, NOTA_RIDE_2, 96),
        (960, NOTA_RIDE_1, 100), (1080, NOTA_RIDE_BELL, 88), (1200, NOTA_RIDE_1, 100), (1320, NOTA_RIDE_BELL, 90),
        (1440, NOTA_RIDE_2, 100), (1560, NOTA_RIDE_1, 100), (1680, NOTA_RIDE_BELL, 92), (1800, NOTA_RIDE_2, 110),
    ]),

    # --- Combinados (Caixa + Prato + Toms, fill "completo") ---
    ("Fill Completo (Caixa + Prato) - 2 tempos", "Combinados", 2,
        _rufo(NOTA_CAIXA_AC, 1.5, 60, 60, 122) + [(720, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Prato) - 4 tempos", "Combinados", 4,
        _rufo(NOTA_CAIXA_AC, 3.5, 60, 50, 125) + [(1680, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Toms + Prato) - 2 tempos", "Combinados", 2,
        _rufo(NOTA_CAIXA_AC, 1, 60, 65, 122)
        + [(t + 480, n, v) for t, n, v in _virada_toms(0.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_1], vel_inicial=100, vel_final=120)]
        + [(840, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Toms + Prato) - 4 tempos", "Combinados", 4,
        _rufo(NOTA_CAIXA_AC, 2, 60, 55, 120)
        + [(t + 960, n, v) for t, n, v in _virada_toms(1, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1], vel_inicial=95, vel_final=122)]
        + [(1920, NOTA_CRASH_1, 127)]),
    ("Fill Completo Acelerando (Caixa Militar + Prato) - 4 tempos", "Combinados", 4,
        _rufo_acelerando(NOTA_CAIXA_AC, 3.75, 160, 30, 45, 125)
        + [(1920, NOTA_CRASH_2, 127)]),
]

def _spec_simples(nota, subdiv, vel_ini, nota_alt=None):
    return lambda duracao: _rufo(nota, duracao, subdiv, vel_ini, 127, nota_alternada=nota_alt)

def _spec_ciclo(notas, subdiv, vel_ini):
    return lambda duracao: _rufo_ciclo(notas, duracao, subdiv, vel_ini, 127)

# Cada rufo "Rápido"/"Super Rápido" (incluindo intercalados e o giratório
# de toms) ganha automaticamente as versões de 1, 2 E 4 tempos - pedido do
# Michel depois de já termos as versões de 1 tempo prontas ("adicione as
# versões de dois e 4 tempos pra todo mundo"). Gerado a partir desta
# tabela em vez de escrito na mão pra não arriscar nome duplicado/
# divergente entre as 3 durações do mesmo desenho.
_RUFOS_RAPIDOS_SPEC = [
    ("Rufo de Caixa Rápido", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 30, 45)),
    ("Rufo de Caixa Super Rápido", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 20, 60)),
    ("Rufo de Caixa Rápido Intercalado (Acústica/Elétrica)", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 30, 50, NOTA_CAIXA_EL)),
    ("Rufo de Caixa Super Rápido Intercalado (Acústica/Elétrica)", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 20, 60, NOTA_CAIXA_EL)),

    ("Rufo de Prato Rápido (Crash 1)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 30, 40)),
    ("Rufo de Prato Super Rápido (Crash 1)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 55)),
    ("Rufo de Prato Rápido (Chinês)", "Rufos de Prato", _spec_simples(NOTA_CHINESE, 30, 40)),
    ("Rufo de Prato Super Rápido (Chinês)", "Rufos de Prato", _spec_simples(NOTA_CHINESE, 20, 55)),
    ("Rufo de Prato Rápido (Ride 1)", "Rufos de Prato", _spec_simples(NOTA_RIDE_1, 30, 40)),
    ("Rufo de Prato Rápido (Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_2, 30, 40)),
    ("Rufo de Prato Super Rápido (Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_2, 20, 55)),
    ("Rufo de Prato Rápido (Splash)", "Rufos de Prato", _spec_simples(NOTA_SPLASH, 30, 45)),
    ("Rufo de Prato Rápido Intercalado (Crash 1 / Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 30, 45, NOTA_CRASH_2)),
    ("Rufo de Prato Super Rápido Intercalado (Crash 1 / Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 60, NOTA_CRASH_2)),
    ("Rufo de Prato Rápido Intercalado (Ride 1 / Chinês)", "Rufos de Prato", _spec_simples(NOTA_RIDE_1, 30, 45, NOTA_CHINESE)),
    ("Rufo de Prato Super Rápido Intercalado (Crash 1 / Splash)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 55, NOTA_SPLASH)),

    ("Rufo de Toms Rápido (Grave)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 40, 55)),
    ("Rufo de Toms Super Rápido (Grave)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 30, 60)),
    ("Rufo de Toms Rápido (Médio)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 40, 55)),
    ("Rufo de Toms Super Rápido (Médio)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 30, 60)),
    ("Rufo de Toms Rápido (Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_AGUDO_2, 40, 55)),
    ("Rufo de Toms Super Rápido (Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_AGUDO_2, 30, 60)),
    ("Rufo de Toms Rápido Intercalado (Grave/Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 40, 50, NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Super Rápido Intercalado (Grave/Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 30, 60, NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Rápido Intercalado (Médio 1 / Médio 2)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 40, 50, NOTA_TOM_MEDIO_2)),
    ("Rufo Giratório de Toms Rápido (Todos os 6)", "Rufos de Tom",
        _spec_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 40, 60)),
    ("Rufo Giratório de Toms Super Rápido (Todos os 6)", "Rufos de Tom",
        _spec_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 30, 70)),
]

def _gerar_variantes_rapidas():
    novos = []
    for nome_base, categoria, gerador in _RUFOS_RAPIDOS_SPEC:
        for duracao in (1, 2, 4):
            tempo_str = f"{duracao} tempo" + ("" if duracao == 1 else "s")
            novos.append((f"{nome_base} - {tempo_str}", categoria, duracao, gerador(duracao)))
    return novos

BATERIA_PRESETS += _gerar_variantes_rapidas()

BATERIA_CATEGORIAS = ["Todos"] + sorted(set(p[1] for p in BATERIA_PRESETS), key=lambda c: [i for i, p in enumerate(BATERIA_PRESETS) if p[1] == c][0])


class MidiEffectsDialog(wx.Dialog):
    # Trazido do MHS MIDI Sequencer (lá é Ctrl+K), a pedido do Michel - a
    # mesma tela com as 3 abas: Arpejador, MIDI Delay e Harpa / Strum.
    # Opera no trecho marcado com Entrada (I) / Saída (O), nos canais
    # selecionados (ou no canal atual). Preview ao vivo pelo player real do
    # Style Creator (barra de Espaço toca/para), OK confirma o que está
    # tocando, Esc/Cancelar desfaz.
    def __init__(self, parent):
        super().__init__(parent, title="Efeitos MIDI Offline (Arpejo, Delay e Strum/Harpa)", size=(460, 540))
        self.parent = parent
        self.restaurado = False
        self.grids = MIDI_EFFECT_GRIDS

        # Backup do trecho pro preview e pro Cancelar (mesmo esquema do
        # Humanizar deste programa).
        self.original_cache = [m.copy() for m in self.parent.merged_track_cache]

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        aviso = wx.StaticText(self, label="Marque um trecho com Entrada (I) e Saída (O) antes de aplicar!")
        main_sizer.Add(aviso, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.notebook = wx.Notebook(self)

        # --- ABA 1: ARPEJADOR ---
        self.tab_arp = wx.Panel(self.notebook)
        sz_arp = wx.BoxSizer(wx.VERTICAL)
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Resolução do Arpejo:"), 0, wx.ALL, 5)
        self.cb_arp_grid = wx.ComboBox(self.tab_arp, value=self.grids[4][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_arp_grid.SetSelection(4)
        sz_arp.Add(self.cb_arp_grid, 0, wx.EXPAND | wx.ALL, 5)
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Direção:"), 0, wx.ALL, 5)
        self.cb_arp_dir = wx.ComboBox(self.tab_arp, choices=["Acima (Up)", "Abaixo (Down)", "Alternado (Up/Down)", "Ordem Tocada (As Played)", "Aleatório (Random)"], style=wx.CB_READONLY)
        self.cb_arp_dir.SetSelection(0)
        sz_arp.Add(self.cb_arp_dir, 0, wx.EXPAND | wx.ALL, 5)
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Oitavas (1 a 10):"), 0, wx.ALL, 5)
        self.sp_arp_oct = wx.SpinCtrl(self.tab_arp, value="1", min=1, max=10)
        sz_arp.Add(self.sp_arp_oct, 0, wx.EXPAND | wx.ALL, 5)
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Duração da Nota / Gate (%):"), 0, wx.ALL, 5)
        self.sp_arp_gate = wx.SpinCtrl(self.tab_arp, value="80", min=10, max=100)
        sz_arp.Add(self.sp_arp_gate, 0, wx.EXPAND | wx.ALL, 5)
        self.tab_arp.SetSizer(sz_arp)

        # --- ABA 2: MIDI DELAY ---
        self.tab_del = wx.Panel(self.notebook)
        sz_del = wx.BoxSizer(wx.VERTICAL)
        sz_del.Add(wx.StaticText(self.tab_del, label="Resolução do Eco (Intervalo):"), 0, wx.ALL, 5)
        self.cb_del_grid = wx.ComboBox(self.tab_del, value=self.grids[4][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_del_grid.SetSelection(4)
        sz_del.Add(self.cb_del_grid, 0, wx.EXPAND | wx.ALL, 5)
        sz_del.Add(wx.StaticText(self.tab_del, label="Repetições (Ecos):"), 0, wx.ALL, 5)
        self.sp_del_rep = wx.SpinCtrl(self.tab_del, value="3", min=1, max=20)
        sz_del.Add(self.sp_del_rep, 0, wx.EXPAND | wx.ALL, 5)
        sz_del.Add(wx.StaticText(self.tab_del, label="Decaimento de Velocity (% por repetição):"), 0, wx.ALL, 5)
        self.sp_del_dec = wx.SpinCtrl(self.tab_del, value="75", min=10, max=100)
        sz_del.Add(self.sp_del_dec, 0, wx.EXPAND | wx.ALL, 5)
        self.tab_del.SetSizer(sz_del)

        # --- ABA 3: HARPA / STRUM ---
        self.tab_harp = wx.Panel(self.notebook)
        sz_harp = wx.BoxSizer(wx.VERTICAL)
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Direção do Arrastão:"), 0, wx.ALL, 5)
        self.cb_harp_dir = wx.ComboBox(self.tab_harp, choices=["Subindo (Grave para Agudo)", "Descendo (Agudo para Grave)", "Vai e Volta (Sobe e Desce)"], style=wx.CB_READONLY)
        self.cb_harp_dir.SetSelection(0)
        sz_harp.Add(self.cb_harp_dir, 0, wx.EXPAND | wx.ALL, 5)
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Velocidade da Palhetada/Dedilhado:"), 0, wx.ALL, 5)
        self.estilos_harp = [
            ("Strum Hiper Rápido (Flamenco)", 8),
            ("Strum Rápido (Violão Base)", 15),
            ("Dedilhado Médio (Piano Roll)", 30),
            ("Harpa Lenta (Cascata Mágica)", 60),
            ("Sincronizado na Resolução do Grid Abaixo", 0),
        ]
        self.cb_harp_estilo = wx.ComboBox(self.tab_harp, choices=[e[0] for e in self.estilos_harp], style=wx.CB_READONLY)
        self.cb_harp_estilo.SetSelection(1)
        sz_harp.Add(self.cb_harp_estilo, 0, wx.EXPAND | wx.ALL, 5)
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Resolução do Grid (Apenas se sincronizado):"), 0, wx.ALL, 5)
        self.cb_harp_grid = wx.ComboBox(self.tab_harp, value=self.grids[6][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_harp_grid.SetSelection(6)
        sz_harp.Add(self.cb_harp_grid, 0, wx.EXPAND | wx.ALL, 5)
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Extensão do Acorde (Clonar em Oitavas):"), 0, wx.ALL, 5)
        self.sp_harp_oct = wx.SpinCtrl(self.tab_harp, value="1", min=1, max=4)
        sz_harp.Add(self.sp_harp_oct, 0, wx.EXPAND | wx.ALL, 5)
        self.tab_harp.SetSizer(sz_harp)

        # --- ABA 4: BATERIA (PRESETS) ---
        # Desenhos prontos de bateria (rufos de caixa, rufos de prato,
        # brincadeiras de prato) pra INSERIR no canal em foco, diferente das
        # outras 3 abas (que transformam notas já existentes no trecho
        # marcado). Mesma mecânica de preview/OK/Cancel das outras - ver
        # get_valores() e aplicar_efeito_midi (tipo 'bateria_preset').
        self.tab_bat = wx.Panel(self.notebook)
        sz_bat = wx.BoxSizer(wx.VERTICAL)
        sz_bat.Add(wx.StaticText(self.tab_bat, label="Categoria:"), 0, wx.ALL, 5)
        self.cb_bat_cat = wx.ComboBox(self.tab_bat, value=BATERIA_CATEGORIAS[0], choices=BATERIA_CATEGORIAS, style=wx.CB_READONLY)
        self.cb_bat_cat.SetSelection(0)
        sz_bat.Add(self.cb_bat_cat, 0, wx.EXPAND | wx.ALL, 5)
        sz_bat.Add(wx.StaticText(self.tab_bat, label="Desenho (Seta Cima/Baixo escolhe e já ouve; Espaço toca/para; OK grava no canal em foco):"), 0, wx.ALL, 5)
        self.list_bat = wx.ListBox(self.tab_bat, style=wx.LB_SINGLE)
        sz_bat.Add(self.list_bat, 1, wx.EXPAND | wx.ALL, 5)
        self.tab_bat.SetSizer(sz_bat)
        self._bateria_indices = []
        self._popular_lista_bateria()

        self.notebook.AddPage(self.tab_arp, "Arpejador")
        self.notebook.AddPage(self.tab_del, "MIDI Delay")
        self.notebook.AddPage(self.tab_harp, "Harpa / Strum")
        self.notebook.AddPage(self.tab_bat, "Bateria (Presets)")
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        lbl_ajuda = wx.StaticText(self, label="Barra de Espaço: tocar/parar o preview.  Ctrl+Tab: trocar de aba.\nOK confirma o que está tocando; Esc/Cancelar desfaz.")
        main_sizer.Add(lbl_ajuda, 0, wx.ALL | wx.ALIGN_CENTER, 8)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(main_sizer)

        for ctrl in (self.cb_arp_grid, self.cb_arp_dir, self.sp_arp_oct, self.sp_arp_gate,
                     self.cb_del_grid, self.sp_del_rep, self.sp_del_dec,
                     self.cb_harp_dir, self.cb_harp_estilo, self.cb_harp_grid, self.sp_harp_oct):
            ctrl.Bind(wx.EVT_COMBOBOX, self.on_change)
            ctrl.Bind(wx.EVT_SPINCTRL, self.on_change)
            ctrl.Bind(wx.EVT_TEXT, self.on_change)
        self.cb_bat_cat.Bind(wx.EVT_COMBOBOX, self.on_bat_categoria_change)
        self.list_bat.Bind(wx.EVT_LISTBOX, self.on_bat_preset_change)

        self.timer_debounce = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.executar_preview, self.timer_debounce)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_BUTTON, self.on_btn_click)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        wx.CallLater(100, self.cb_arp_grid.SetFocus)
        wx.CallLater(250, lambda: self.timer_debounce.Start(50, oneShot=True))

    # ---------- Preview ----------
    def on_change(self, event):
        self.timer_debounce.Start(120, oneShot=True)
        event.Skip()

    def _popular_lista_bateria(self):
        # Reconstrói a lista de presets filtrada pela categoria escolhida -
        # `self._bateria_indices[i]` guarda o índice REAL em BATERIA_PRESETS
        # pra cada linha `i` da lista filtrada (get_valores usa isso).
        cat = self.cb_bat_cat.GetStringSelection() or "Todos"
        self._bateria_indices = [i for i, p in enumerate(BATERIA_PRESETS) if cat == "Todos" or p[1] == cat]
        rotulos = []
        for i in self._bateria_indices:
            nome, categoria, duracao, _ = BATERIA_PRESETS[i]
            tempo_str = f"{duracao:g} tempo" + ("" if duracao == 1 else "s")
            rotulos.append(f"{nome} ({tempo_str})")
        self.list_bat.Set(rotulos)
        if rotulos:
            self.list_bat.SetSelection(0)

    def on_bat_categoria_change(self, event):
        self._popular_lista_bateria()
        self.on_bat_preset_change(event)

    def on_bat_preset_change(self, event):
        # Andar com Seta Cima/Baixo na lista: toca o DESENHO SOZINHO, na
        # hora, direto pela porta MIDI (sem precisar de Play nem de mexer
        # no trecho de verdade) - só pra ouvir rapidinho qual é qual. O
        # Espaço continua tocando o trecho de verdade JÁ COM o desenho
        # aplicado por cima (ver on_key/executar_preview) - por isso ainda
        # chama on_change() aqui embaixo, pra manter isso atualizado
        # também, mesmo sem apertar Espaço ainda.
        sel = self.list_bat.GetSelection()
        if sel != wx.NOT_FOUND and self._bateria_indices:
            self.tocar_preview_isolado_bateria(self._bateria_indices[sel])
        self.on_change(event)

    def tocar_preview_isolado_bateria(self, preset_idx):
        porta = getattr(self.parent, 'midi_out', None)
        if not porta or not (0 <= preset_idx < len(BATERIA_PRESETS)):
            return
        # Token em vez de cancelar Timers um a um: se o Michel passar rápido
        # por vários presets, cada nova chamada invalida os note_on/note_off
        # ainda pendentes da anterior (eles conferem o token antes de
        # mandar qualquer coisa) - evita bateria "grudada" tocando notas de
        # presets que ele já passou.
        self._bat_preview_token = getattr(self, '_bat_preview_token', 0) + 1
        meu_token = self._bat_preview_token
        _, _, _, eventos_preset = BATERIA_PRESETS[preset_idx]
        midi_data = getattr(self.parent, 'current_midi_data', None)
        tpb = getattr(midi_data, 'ticks_per_beat', 480) if midi_data else 480
        tempo_us = getattr(self.parent, 'current_tempo', 500000) or 500000
        escala = tpb / 480.0
        seg_por_tick = (tempo_us / 1000000.0) / max(1, tpb)
        ch = self.parent.canal_atual
        gate_ticks = max(1, int(round(30 * escala)))

        def _enviar(msg, token):
            if token != self._bat_preview_token:
                return
            try:
                porta.send(msg)
            except Exception:
                pass

        for offset480, nota, vel in eventos_preset:
            t_ticks = int(round(offset480 * escala))
            atraso_on = t_ticks * seg_por_tick
            atraso_off = (t_ticks + gate_ticks) * seg_por_tick
            msg_on = mido.Message('note_on', channel=ch, note=nota, velocity=vel)
            msg_off = mido.Message('note_off', channel=ch, note=nota, velocity=0)
            threading.Timer(atraso_on, _enviar, args=(msg_on, meu_token)).start()
            threading.Timer(atraso_off, _enviar, args=(msg_off, meu_token)).start()

    def on_tab_change(self, event):
        self.timer_debounce.Start(60, oneShot=True)
        try:
            falar(self.notebook.GetPageText(self.notebook.GetSelection()), imediato=True)
        except Exception:
            pass
        event.Skip()

    def executar_preview(self, event=None):
        tipo, params = self.get_valores()
        self.parent.merged_track_cache = [m.copy() for m in self.original_cache]
        self.parent.aplicar_efeito_midi(tipo, params, is_preview=True)

    def restaurar_original(self):
        if self.restaurado:
            return
        self.restaurado = True
        self.parent.merged_track_cache = [m.copy() for m in self.original_cache]
        self.parent.prepare_section_cache()
        if getattr(self.parent, 'playing', False):
            self.parent.anchor_tick = self.parent.current_accumulated_ticks
            self.parent.force_reload_loop = True

    # ---------- Botões / teclas ----------
    def on_btn_click(self, event):
        if event.GetId() == wx.ID_OK:
            self.EndModal(wx.ID_OK)
        elif event.GetId() == wx.ID_CANCEL:
            self.restaurar_original()
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def on_close(self, event):
        self.restaurar_original()
        event.Skip()

    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        if code == wx.WXK_SPACE and not event.AltDown() and not event.ShiftDown():
            if ctrl:
                self.parent.OnTogglePause(None)
            else:
                self.parent.OnTogglePlay(None)
            return
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
            return
        if code == wx.WXK_ESCAPE:
            self.restaurar_original()
            self.EndModal(wx.ID_CANCEL)
            return
        if code in [wx.WXK_TAB, ord('\t')] and ctrl:
            total = self.notebook.GetPageCount()
            cur = self.notebook.GetSelection()
            self.notebook.SetSelection((cur - 1) % total if event.ShiftDown() else (cur + 1) % total)
            return
        event.Skip()

    def get_valores(self):
        tab = self.notebook.GetSelection()
        params = {}
        if tab == 0:
            tipo = "arpejo"
            params['grid'] = self.grids[self.cb_arp_grid.GetSelection()][1]
            params['direction'] = self.cb_arp_dir.GetSelection()
            params['octaves'] = self.sp_arp_oct.GetValue()
            params['gate'] = self.sp_arp_gate.GetValue()
        elif tab == 1:
            tipo = "delay"
            params['grid'] = self.grids[self.cb_del_grid.GetSelection()][1]
            params['repeats'] = self.sp_del_rep.GetValue()
            params['decay'] = self.sp_del_dec.GetValue()
        elif tab == 2:
            tipo = "harpa"
            estilo_val = self.estilos_harp[self.cb_harp_estilo.GetSelection()][1]
            grid_val = self.grids[self.cb_harp_grid.GetSelection()][1]
            params['direction'] = self.cb_harp_dir.GetSelection()
            params['delay_ticks'] = estilo_val if estilo_val > 0 else grid_val
            params['octaves'] = self.sp_harp_oct.GetValue()
        else:
            tipo = "bateria_preset"
            sel = self.list_bat.GetSelection()
            params['preset_idx'] = self._bateria_indices[sel] if sel != wx.NOT_FOUND and self._bateria_indices else None
        return tipo, params


# Lista oficial da Síntese XG (Multi Part Parameter Change, endereço 0x4C 0x08)
# - a mesma do Voice Creator do MHS MIDI Sequencer. Cada tupla:
# (endereço, nome, mínimo, máximo, valor de fábrica). Conferida parâmetro a
# parâmetro contra o Data List oficial (MULTI PART, pág. 65) - 7 que
# faltavam foram acrescentados (0x0C/0x0D/0x0F/0x10/0x26/0x27/0x28) e o
# Detune (0x09) deixou de ser 2 sliders soltos ("Coarse"/"Fine" 0-127 cada,
# formato errado) e virou 1 slider só com o valor JÁ COMBINADO (ver
# detune_combinar/detune_separar em MHS_Utils.py - o Data List mostra que é
# 1 parâmetro de 2 bytes, cada um limitado a um nibble 0x00-0x0F, não 2
# parâmetros independentes de 0-127).
VOICE_CREATOR_PARAMS = [
    (0x08, "Note Shift (Transposição Fina)", 0, 127, 64),
    (0x09, "Detune (Desafinação Fina - 128=Centro)", 0, 255, 128),
    (0x0C, "Velocity Sense Depth (Sensib. de Toque no Volume)", 0, 127, 64),
    (0x0D, "Velocity Sense Offset (Sensib. de Toque - Piso)", 0, 127, 64),
    (0x0F, "Note Limit Low (Nota Mínima da Tessitura)", 0, 127, 0),
    (0x10, "Note Limit High (Nota Máxima da Tessitura)", 0, 127, 127),
    (0x11, "Dry Level (Amplitude)", 0, 127, 127),
    (0x15, "Vibrato Rate (LFO Velocidade)", 0, 127, 64),
    (0x16, "Vibrato Depth (LFO Intensidade)", 0, 127, 64),
    (0x17, "Vibrato Delay (LFO Atraso)", 0, 127, 64),
    (0x18, "Filter Cutoff (Frequência - Brilho)", 0, 127, 64),
    (0x19, "Filter Resonance (Ressonância - Wah)", 0, 127, 64),
    (0x1A, "EG Attack Time (Tempo de Ataque)", 0, 127, 64),
    (0x1B, "EG Decay Time (Tempo de Queda)", 0, 127, 64),
    (0x1C, "EG Release Time (Tempo de Relaxamento)", 0, 127, 64),
    (0x1D, "MW Pitch Control (Roda - Afinação)", 0, 127, 64),
    (0x1E, "MW Filter Control (Roda - Filtro)", 0, 127, 64),
    (0x1F, "MW Amplitude Control (Roda - Tremolo)", 0, 127, 64),
    (0x20, "MW LFO Pitch Depth (Roda - Vibrato)", 0, 127, 10),
    (0x21, "MW LFO Filter Depth (Roda - Wah)", 0, 127, 0),
    (0x22, "MW LFO Amp Depth (Roda - Tremolo)", 0, 127, 0),
    (0x23, "Bend Pitch Control (Alavanca Padrão)", 0, 127, 66),  # 66 = +2 semitons
    (0x24, "Bend Filter Control (Alavanca - Wah)", 0, 127, 64),
    (0x25, "Bend Amplitude Control (Alavanca - Vol)", 0, 127, 64),
    (0x26, "Bend LFO Pitch Depth (Alavanca - Vibrato)", 0, 127, 0),
    (0x27, "Bend LFO Filter Depth (Alavanca - Wah)", 0, 127, 0),
    (0x28, "Bend LFO Amp Depth (Alavanca - Tremolo)", 0, 127, 0),
    (0x4d, "CAT Pitch Control (Pressão de Canal - Afinação)", 0, 127, 64),
    (0x4e, "CAT Filter Control (Pressão de Canal - Filtro)", 0, 127, 64),
    (0x4f, "CAT Amplitude Control (Pressão de Canal - Volume)", 0, 127, 64),
    (0x50, "CAT LFO Pitch Depth (Pressão de Canal - Vibrato)", 0, 127, 0),
    (0x51, "CAT LFO Filter Depth (Pressão de Canal - Wah)", 0, 127, 0),
    (0x52, "CAT LFO Amp Depth (Pressão de Canal - Tremolo)", 0, 127, 0),
    (0x5a, "AC1 Pitch Control (Controle Assinável 1 - Afinação)", 0, 127, 64),
    (0x5b, "AC1 Filter Control (Controle Assinável 1 - Filtro)", 0, 127, 64),
    (0x5c, "AC1 Amplitude Control (Controle Assinável 1 - Volume)", 0, 127, 64),
    (0x5d, "AC1 LFO Pitch Depth (Controle Assinável 1 - Vibrato)", 0, 127, 0),
    (0x5e, "AC1 LFO Filter Depth (Controle Assinável 1 - Wah)", 0, 127, 0),
    (0x5f, "AC1 LFO Amp Depth (Controle Assinável 1 - Tremolo)", 0, 127, 0),
    (0x69, "Pitch EG Initial Level (Envelope de Afinação - Nível Inicial)", 0, 127, 64),
    (0x6a, "Pitch EG Attack Time (Envelope de Afinação - Ataque)", 0, 127, 64),
    (0x6b, "Pitch EG Release Level (Envelope de Afinação - Nível Final)", 0, 127, 64),
    (0x6c, "Pitch EG Release Time (Envelope de Afinação - Relaxamento)", 0, 127, 64),
    (0x6d, "Velocity Limit Low (Velocidade Mínima que Toca)", 1, 127, 1),
    (0x6e, "Velocity Limit High (Velocidade Máxima que Toca)", 1, 127, 127),
    (0x76, "EQ Bass Frequency (Frequência do Grave - 4 a 40)", 4, 40, 12),
    (0x77, "EQ Treble Frequency (Frequência do Agudo - 28 a 58)", 28, 58, 54),
]
# Portamento Switch/Time (endereços SysEx 0x67/0x68 do bloco 0x08, "MULTI
# PART" - primeira tentativa) FORAM TESTADOS DE VERDADE pelo Michel no SX
# e NÃO tiveram efeito nenhum no som - o teclado real não honra esses
# endereços apesar de estarem no Data List oficial. Achado depois de um
# dump real do teclado ligando o Portamento pelo próprio painel: o que
# funciona é o CC 65 (Portamento Switch, padrão MIDI) + CC 5 (Portamento
# Time) - exatamente o mesmo mecanismo que o MHS MIDI Sequencer já usa
# (campo "Porta Time"). Por isso o controle de Liga/Desliga+Tempo do
# Portamento NÃO é mais um parâmetro SysEx da lista acima - é o campo
# especial "Portamento (Tempo)" tratado à parte em VoiceCreatorDialog
# (manda CC 5 + CC 65 de verdade, não SysEx 0x67/0x68).

# 3 parâmetros de Portamento que moram numa tabela SEPARADA do Data List
# oficial (nn=PART NUMBER, logo depois da tabela MULTI PART - "MIDI
# Parameter Change table" sem nome próprio na documentação) - SysEx
# **43 1n 4C 0A pp aa vv**, com bloco 0x0A em vez do 0x08 de sempre. Os
# endereços 0x01/0x02/0x03 aqui NÃO têm relação com Bank Select MSB/LSB/
# Program Number do bloco 0x08 (mesmo valor de byte, bloco diferente) -
# e não há ambiguidade real na chave dentro do dict VoiceCreator porque
# esses 3 endereços já são RESERVADOS (nunca capturados) no bloco 0x08.
VOICE_CREATOR_PARAMS_0A = [
    (0x01, "Mono Priority - Prioridade no Modo Mono (0=Última nota 1=Nota mais aguda)", 0, 1, 0),
    (0x02, "Portamento Mode - Modo do Portamento (0=Normal 1=Pitch Poly 2=Cross Fade)", 0, 2, 0),
    (0x03, "Portamento Time Mode - Modo do Tempo (0=Rate/Velocidade 1=Time/Tempo Fixo)", 0, 1, 0),
]

VOICE_CREATOR_ADDRS = frozenset(p[0] for p in VOICE_CREATOR_PARAMS)
VOICE_CREATOR_ADDRS_0A = frozenset(p[0] for p in VOICE_CREATOR_PARAMS_0A)


class VoiceCreatorDialog(wx.Dialog):
    # Trazido do MHS MIDI Sequencer (lá é Ctrl+T; aqui, como Ctrl+T já é
    # "Alterar Tamanho da Seção", ficou em Ctrl+Shift+T). Edita o timbre de
    # UM canal via SysEx XG de Multi Part (F0 43 10 4C 08 <canal> <end> <val>
    # F7), mandando ao vivo pro teclado a cada mexida e guardando os valores
    # no canal pra gravar dentro do .sty.
    def __init__(self, parent, canal_idx, valores_atuais):
        super().__init__(parent, title=f"Voice Creator (Synth Pro) - Canal {canal_idx + 1}", size=(450, 750))
        self.parent = parent
        self.canal_idx = canal_idx
        import copy
        # "porta_time" (Portamento) é uma chave STRING de propósito (ver
        # comentário mais abaixo) - só os endereços SysEx de verdade (0x00-
        # 0x7F) precisam virar int aqui.
        self.valores = {(k if isinstance(k, str) else int(k)): v for k, v in copy.deepcopy(valores_atuais).items()}
        self.modulos = {}
        self.parametros = list(VOICE_CREATOR_PARAMS) + list(VOICE_CREATOR_PARAMS_0A)
        # Qual bloco SysEx (0x08 de sempre, ou 0x0A do Portamento) cada
        # endereço usa na hora de mandar pro teclado - ver comentário perto
        # de VOICE_CREATOR_PARAMS_0A.
        self.bloco_do_param = {p[0]: 0x08 for p in VOICE_CREATOR_PARAMS}
        self.bloco_do_param.update({p[0]: 0x0A for p in VOICE_CREATOR_PARAMS_0A})

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self.scr.SetScrollRate(0, 20)
        scrsz = wx.BoxSizer(wx.VERTICAL)

        for addr, nome, min_v, max_v, default_v in self.parametros:
            lbl = wx.StaticText(self.scr, label=f"{nome}:")
            scrsz.Add(lbl, 0, wx.LEFT | wx.TOP, 10)
            sl = wx.SpinCtrl(self.scr, value=str(self.valores.get(addr, default_v)), min=min_v, max=max_v)
            sl.SetName(nome)
            scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            self.modulos[addr] = sl
            sl.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)

        # Portamento (Tempo + Liga/Desliga) - especial, chave string
        # "porta_time" (nunca colide com os endereços inteiros 0x00-0x7F
        # de cima) - manda CC 5 + CC 65 de verdade, não SysEx (ver
        # comentário perto de VOICE_CREATOR_PARAMS e em _enviar_sysex).
        lbl_porta = wx.StaticText(self.scr, label="Portamento (Tempo - 0=Desligado):")
        scrsz.Add(lbl_porta, 0, wx.LEFT | wx.TOP, 10)
        sl_porta = wx.SpinCtrl(self.scr, value=str(self.valores.get("porta_time", 0)), min=0, max=127)
        sl_porta.SetName("Portamento (Tempo - 0=Desligado)")
        scrsz.Add(sl_porta, 0, wx.EXPAND | wx.ALL, 5)
        self.modulos["porta_time"] = sl_porta
        sl_porta.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)

        self.scr.SetSizer(scrsz)
        vbox.Add(self.scr, 1, wx.EXPAND | wx.ALL, 5)

        btn_ok = wx.Button(panel, wx.ID_OK, "Fechar e Manter")
        vbox.Add(btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        wx.CallLater(100, list(self.modulos.values())[0].SetFocus)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

    def _enviar_sysex(self, addr, val):
        # Detune (0x09) é o único parâmetro combinado de 2 bytes desta lista -
        # o valor na tela é o JÁ COMBINADO (0-255), mas o teclado precisa das
        # 2 mensagens físicas separadas (0x09=nibble alto, 0x0A=nibble baixo).
        porta = getattr(self.parent, 'midi_out', None)
        if not porta:
            return
        if addr == "porta_time":
            # Portamento (Tempo + Liga/Desliga derivado) - NÃO é SysEx, é CC
            # 5 (Portamento Time) + CC 65 (Portamento Switch, ligado sempre
            # que o Tempo > 0) - o mecanismo confirmado funcionando de
            # verdade no teclado do Michel (ver comentário perto de
            # VOICE_CREATOR_PARAMS).
            try:
                porta.send(mido.Message('control_change', channel=self.canal_idx, control=5, value=val))
                porta.send(mido.Message('control_change', channel=self.canal_idx, control=65, value=127 if val > 0 else 0))
            except Exception:
                pass
            return
        if addr == 0x09:
            from MHS_Utils import detune_separar
            alto, baixo = detune_separar(val)
            pares = [(0x09, alto), (0x0A, baixo)]
        else:
            pares = [(addr, val)]
        for a, v in pares:
            # Detune (0x09/0x0A) sempre vai pro bloco 0x08 de sempre -
            # bloco_do_param só tem entrada pros endereços 0x01-0x03 do
            # Portamento (bloco 0x0A de verdade); .get(a, 0x08) cai no
            # padrão certo pra Detune e pra tudo mais.
            bloco = getattr(self, 'bloco_do_param', {}).get(a, 0x08)
            msg = [0xF0, 0x43, 0x10, 0x4C, bloco, self.canal_idx, a, v, 0xF7]
            try:
                porta.send(mido.Message.from_bytes(msg))
            except Exception:
                pass

    def enviar_para_teclado(self, event=None):
        addr_to_send = None
        if event:
            foco = event.GetEventObject()
            for a, sl in self.modulos.items():
                if sl == foco:
                    addr_to_send = a
                    break
        if addr_to_send is not None:
            v = self.modulos[addr_to_send].GetValue()
            self.valores[addr_to_send] = v
            self._enviar_sysex(addr_to_send, v)

    def get_valores(self):
        return self.valores

    def handle_midi_in(self, msg):
        # Enquanto esta tela está aberta, self.parent.active_midi_dialog
        # aponta pra ela - o MidiEngine desvia TODA a MIDI IN pra cá (ver
        # midi_in_handler), em vez do caminho normal de captura. Feedback em
        # tempo real: qualquer SysEx/CC/NRPN que o teclado mandar mudando um
        # parâmetro desta tela atualiza o slider na hora, sem precisar
        # fechar/reabrir - o mesmo que o Michel já esperava (e que, junto,
        # descobrimos que também nunca tinha sido ligado no editor de DSP).
        import MHS_MidiEngine as _me
        porta = getattr(self.parent, 'midi_out', None)

        if msg.type in ('note_on', 'note_off', 'polytouch'):
            # Deixa continuar ouvindo o timbre sendo editado ao vivo.
            if porta:
                try: porta.send(msg.copy(channel=self.canal_idx))
                except Exception: pass
            return

        addr, val = None, None
        if msg.type == 'sysex':
            d = list(msg.data)
            if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08:
                addr, val = d[5], d[6]
            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x0A and d[5] in VOICE_CREATOR_ADDRS_0A:
                # Portamento (Mono Priority/Modo/Modo do Tempo) - bloco
                # SEPARADO (0x0A), não o 0x08 de sempre - ver comentário
                # perto de VOICE_CREATOR_PARAMS_0A.
                addr, val = d[5], d[6]
            else:
                # Outra SysEx (DSP, Drum Setup etc) - ecoa pro sintetizador,
                # não mexe no Voice Creator.
                if porta:
                    try: porta.send(msg)
                    except Exception: pass
                return
        elif msg.type == 'control_change':
            cc, v = msg.control, msg.value
            if cc == 5:
                # Portamento Time - o mecanismo que funciona de verdade (CC
                # 5 + CC 65 derivado), não os endereços SysEx 0x67/0x68 que
                # o Michel já testou e não tiveram efeito nenhum no som.
                addr, val = "porta_time", v
            elif cc in _me._CC_SOUND_MP:
                addr, val = _me._CC_SOUND_MP[cc], v
            elif cc in (99, 98, 6, 38):
                if not hasattr(self, '_nrpn_in'):
                    self._nrpn_in = {'msb': None, 'lsb': None}
                st = self._nrpn_in
                if cc == 99: st['msb'] = v
                elif cc == 98: st['lsb'] = v
                elif cc == 6 and st['msb'] is not None and st['lsb'] is not None:
                    endereco = _me._NRPN_SOUND_MP.get((st['msb'], st['lsb']))
                    if endereco is not None:
                        addr, val = endereco, v
                if addr is None:
                    return
            else:
                return
        else:
            return

        if addr in (0x09, 0x0A):
            from MHS_Utils import detune_combinar
            if not hasattr(self, '_detune_nibbles_tela'):
                self._detune_nibbles_tela = [0x08, 0x00]
            par = self._detune_nibbles_tela
            if addr == 0x09: par[0] = val & 0x0F
            else: par[1] = val & 0x0F
            addr, val = 0x09, detune_combinar(par[0], par[1])

        sl = self.modulos.get(addr)
        if sl is not None and sl.GetValue() != val:
            self.valores[addr] = val
            sl.SetValue(val)

    def on_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        elif code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        elif code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN]:
            foco = wx.Window.FindFocus()
            if foco and isinstance(foco, wx.SpinCtrl) and foco in self.modulos.values():
                val = foco.GetValue()
                v_min, v_max = foco.GetMin(), foco.GetMax()
                passo = 6 if v_max <= 127 else 12
                if code == wx.WXK_HOME: val = v_max
                elif code == wx.WXK_END: val = v_min
                elif code == wx.WXK_PAGEUP: val = min(v_max, val + passo)
                elif code == wx.WXK_PAGEDOWN: val = max(v_min, val - passo)
                foco.SetValue(val)
                addr_to_send = None
                for a, sl in self.modulos.items():
                    if sl == foco:
                        addr_to_send = a
                        break
                if addr_to_send is not None:
                    self.valores[addr_to_send] = val
                    self._enviar_sysex(addr_to_send, val)
                falar(str(val), imediato=True)
            else:
                event.Skip()
        else:
            event.Skip()


class ChangelogDialog(wx.Dialog):
    # Aparece SOZINHA, uma única vez por versão nova instalada (ver
    # mostrar_changelog_se_necessario em MHS_MainFrame.py) - mostra o que
    # mudou nesta versão e, no fim, um convite pra contribuir. Texto num
    # wx.TextCtrl multi-linha SOMENTE LEITURA (não um wx.MessageBox, que
    # trunca texto longo e não dá pra navegar linha a linha/copiar com o
    # NVDA) - o foco já entra direto nele, pronto pra ler com as setas.
    def __init__(self, parent, versao, texto):
        super().__init__(parent, title=f"Novidades da versão {versao}",
                          size=(620, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label=f"O que mudou na versão {versao}:"), 0, wx.ALL, 10)
        self.txt = wx.TextCtrl(self, value=texto,
                                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP)
        self.txt.SetName(f"Novidades da versão {versao}")
        vbox.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        btnsizer = self.CreateButtonSizer(wx.OK)
        vbox.Add(btnsizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 12)
        self.SetSizer(vbox)
        wx.CallLater(150, self.txt.SetFocus)


class AlterarLSBDialog(wx.Dialog):
    # Usada tanto por "Alterar LSB do Ritmo Atual" quanto por "Alterar LSB
    # de Ritmos em Massa" (MHS_MainFrame.py) - mostra o relatório do que foi
    # encontrado (quantos canais/arquivos em cada LSB) e deixa escolher pra
    # qual LSB trocar. Pedido explícito do Michel: dois modos, escolhidos
    # com as setas - só um LSB de origem específico (não mexe no resto,
    # já que programadores diferentes às vezes misturam LSBs no mesmo
    # arquivo - confirmado analisando ritmos reais dele) ou TODAS as
    # ocorrências de uma vez.
    def __init__(self, parent, titulo, relatorio_texto, lsb_origem_sugerido=0):
        super().__init__(parent, title=titulo, size=(560, 520),
                          style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label="Resultado do scaneamento:"), 0, wx.ALL, 10)
        self.txt_relatorio = wx.TextCtrl(self, value=relatorio_texto,
                                          style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 160))
        self.txt_relatorio.SetName("Resultado do scaneamento")
        vbox.Add(self.txt_relatorio, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.radio_modo = wx.RadioBox(
            self, label="Quais ocorrências alterar?",
            choices=["Só as que estão no LSB de origem escolhido abaixo",
                     "TODAS as ocorrências, não importa o valor atual"],
            style=wx.RA_SPECIFY_ROWS)
        vbox.Add(self.radio_modo, 0, wx.EXPAND | wx.ALL, 10)
        self.radio_modo.Bind(wx.EVT_RADIOBOX, self.on_modo_change)

        vbox.Add(wx.StaticText(self, label="LSB de origem a substituir (000-127):"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.spin_origem = wx.SpinCtrl(self, min=0, max=127, initial=lsb_origem_sugerido)
        self.spin_origem.SetName("LSB de origem a substituir")
        vbox.Add(self.spin_origem, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        vbox.Add(wx.StaticText(self, label="Alterar para qual LSB (000-127):"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.spin_destino = wx.SpinCtrl(self, min=0, max=127, initial=0)
        self.spin_destino.SetName("Alterar para qual LSB")
        vbox.Add(self.spin_destino, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btnsizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(btnsizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 12)
        self.SetSizer(vbox)
        wx.CallLater(150, self.txt_relatorio.SetFocus)

    def on_modo_change(self, event):
        self.spin_origem.Enable(self.radio_modo.GetSelection() == 0)

    def get_valores(self):
        # (lsb_destino, lsb_origem_ou_None) - None = modo "todas as ocorrências"
        somente_origem = self.radio_modo.GetSelection() == 0
        return self.spin_destino.GetValue(), (self.spin_origem.GetValue() if somente_origem else None)