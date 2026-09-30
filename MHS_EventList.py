import wx
import mido
import threading
import copy
from collections import defaultdict, deque
from MHS_Utils import (
    falar, falar_status, get_nome_nota, get_cc_name, NRPN_MSB_NAMES,
    VALOR_MIN_MIDI, VALOR_MAX_MIDI
)
from MHS_Dialogs import SubstituirNotasDialog

# --- DICIONÁRIO COMPLETO DE CONTROL CHANGES ---
CC_DICT = {
    0: "Bank Select MSB", 1: "Modulation", 2: "Breath Controller", 4: "Foot Controller",
    5: "Portamento Time", 6: "Data Entry MSB", 7: "Volume", 8: "Balance", 10: "Pan",
    11: "Expression", 12: "Effect Control 1", 13: "Effect Control 2", 64: "Sustain Pedal",
    65: "Portamento On/Off", 66: "Sostenuto", 67: "Soft Pedal", 68: "Legato", 69: "Hold 2",
    70: "Sound Variation", 71: "Sound Resonance", 72: "Release Time", 73: "Attack Time",
    74: "Cutoff", 75: "Decay Time", 76: "Vibrato Rate", 77: "Vibrato Depth", 78: "Vibrato Delay",
    84: "Portamento Control", 91: "Reverb", 92: "Tremolo", 93: "Chorus", 94: "Celeste",
    95: "Phaser", 98: "NRPN LSB", 99: "NRPN MSB", 100: "RPN LSB", 101: "RPN MSB",
    120: "All Sound Off", 121: "Reset All Controllers", 122: "Local Control", 123: "All Notes Off"
}
CC_CHOICES = [f"{CC_DICT.get(i, 'Control ' + str(i))}, {i}" for i in range(128)]

# =====================================================================
# CAIXAS DE EDIÇÃO PROFISSIONAIS (SpinCtrl e ComboBox)
# =====================================================================
class EdicaoNotaDialog(wx.Dialog):
    def __init__(self, parent, nota_val=60, vel_val=100, dur_val=240, tick_val=0, is_insert=False):
        titulo = "Inserir Nota / Peça" if is_insert else "Editar Nota / Peça"
        super().__init__(parent, title=titulo, size=(400, 350))
        self.parent_list = parent 
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_nota = wx.StaticText(self, label="Nota/Peça:")
        sizer.Add(self.lbl_nota, 0, wx.ALL, 5)
        self.sp_nota = wx.SpinCtrl(self, value=str(nota_val), min=VALOR_MIN_MIDI, max=VALOR_MAX_MIDI)
        sizer.Add(self.sp_nota, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_vel = wx.StaticText(self, label="Velocity:")
        sizer.Add(lbl_vel, 0, wx.ALL, 5)
        self.sp_vel = wx.SpinCtrl(self, value=str(vel_val), min=1, max=VALOR_MAX_MIDI)
        sizer.Add(self.sp_vel, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_dur = wx.StaticText(self, label="Duração (Ticks):")
        sizer.Add(lbl_dur, 0, wx.ALL, 5)
        self.sp_dur = wx.SpinCtrl(self, value=str(dur_val), min=1, max=99999)
        sizer.Add(self.sp_dur, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_tick = wx.StaticText(self, label="Posição (Tick Relativo à Seção):")
        sizer.Add(lbl_tick, 0, wx.ALL, 5)
        self.sp_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=9999999)
        sizer.Add(self.sp_tick, 0, wx.EXPAND | wx.ALL, 5)
        
        self.sp_nota.Bind(wx.EVT_SPINCTRL, self.on_update)
        self.sp_vel.Bind(wx.EVT_SPINCTRL, self.on_update)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.atualizar_label(falar=False)
        wx.CallLater(100, self.sp_nota.SetFocus)

    def atualizar_label(self, falar=True):
        val = self.sp_nota.GetValue()
        if hasattr(self.parent_list.parent, 'traduzir_evento_midi'):
            msg_fake = mido.Message('note_on', channel=self.parent_list.canal_idx, note=val, velocity=100)
            nome = self.parent_list.parent.traduzir_evento_midi(msg_fake, self.parent_list.canal_idx)
        else:
            nome = get_nome_nota(val)
        self.lbl_nota.SetLabel(f"Alvo: {nome}")
        if falar: falar_status(nome, imediato=True)

    def play_preview(self):
        if getattr(self.parent_list.parent, 'midi_out', None):
            self.parent_list.matar_nota_preview()
            msg = mido.Message('note_on', channel=self.parent_list.canal_idx, note=self.sp_nota.GetValue(), velocity=self.sp_vel.GetValue())
            self.parent_list.preview_note = msg
            try: self.parent_list.parent.midi_out.send(msg)
            except Exception: pass
            self.parent_list.preview_timer = threading.Timer(0.3, self.parent_list.matar_nota_preview)
            self.parent_list.preview_timer.start()
        
    def on_update(self, event):
        self.atualizar_label(falar=True)
        self.play_preview()
            
    def get_values(self):
        return self.sp_nota.GetValue(), self.sp_vel.GetValue(), self.sp_dur.GetValue(), self.sp_tick.GetValue()


class EdicaoCCDialog(wx.Dialog):
    def __init__(self, parent, cc_val=0, val_val=0, tick_val=0, is_insert=False):
        titulo = "Inserir Control Change" if is_insert else "Editar Control Change"
        super().__init__(parent, title=titulo, size=(400, 300))
        self.parent_list = parent
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_cc = wx.StaticText(self, label="Control Change (Digite a letra ou use setas):")
        sizer.Add(lbl_cc, 0, wx.ALL, 5)
        
        self.cb_cc = wx.ComboBox(self, value=CC_CHOICES[cc_val], choices=CC_CHOICES, style=wx.CB_READONLY)
        self.cb_cc.SetSelection(cc_val)
        sizer.Add(self.cb_cc, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_val = wx.StaticText(self, label=f"Valor ({VALOR_MIN_MIDI} a {VALOR_MAX_MIDI}):")
        sizer.Add(lbl_val, 0, wx.ALL, 5)
        self.sp_val = wx.SpinCtrl(self, value=str(val_val), min=VALOR_MIN_MIDI, max=VALOR_MAX_MIDI)
        sizer.Add(self.sp_val, 0, wx.EXPAND | wx.ALL, 5)

        lbl_tick = wx.StaticText(self, label="Posição (Tick Relativo à Seção):")
        sizer.Add(lbl_tick, 0, wx.ALL, 5)
        self.sp_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=9999999)
        sizer.Add(self.sp_tick, 0, wx.EXPAND | wx.ALL, 5)
        
        self.cb_cc.Bind(wx.EVT_COMBOBOX, self.on_cc_change)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.cb_cc.SetFocus)
        
    def on_cc_change(self, event):
        falar_status(self.cb_cc.GetValue(), imediato=True)
            
    def get_values(self):
        return self.cb_cc.GetSelection(), self.sp_val.GetValue(), self.sp_tick.GetValue()


class EdicaoPCDialog(wx.Dialog):
    def __init__(self, parent, bank_val=0, patch_val=0, tick_val=0, is_insert=False):
        titulo = "Inserir Program Change" if is_insert else "Editar Program Change"
        super().__init__(parent, title=titulo, size=(400, 300))
        self.parent_list = parent
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl_bank = wx.StaticText(self, label="Banco (Bank 0-16384):")
        sizer.Add(lbl_bank, 0, wx.ALL, 5)
        self.sp_bank = wx.SpinCtrl(self, value=str(bank_val), min=0, max=16384)
        sizer.Add(self.sp_bank, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lbl_patch = wx.StaticText(self, label="Patch:")
        sizer.Add(self.lbl_patch, 0, wx.ALL, 5)
        self.sp_patch = wx.SpinCtrl(self, value=str(patch_val), min=VALOR_MIN_MIDI, max=VALOR_MAX_MIDI)
        sizer.Add(self.sp_patch, 0, wx.EXPAND | wx.ALL, 5)

        lbl_tick = wx.StaticText(self, label="Posição (Tick Relativo à Seção):")
        sizer.Add(lbl_tick, 0, wx.ALL, 5)
        self.sp_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=9999999)
        sizer.Add(self.sp_tick, 0, wx.EXPAND | wx.ALL, 5)
        
        self.sp_bank.Bind(wx.EVT_SPINCTRL, self.on_update)
        self.sp_patch.Bind(wx.EVT_SPINCTRL, self.on_update)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.atualizar_label(falar=False)
        wx.CallLater(100, self.sp_bank.SetFocus)
        
    def atualizar_label(self, falar=True):
        b_val = self.sp_bank.GetValue()
        p_val = self.sp_patch.GetValue()
        nome_pc = f"Program {p_val}"
        
        if hasattr(self.parent_list.parent, 'ins_db'):
            nome_pc = self.parent_list.parent.ins_db.get(b_val, {}).get(p_val, nome_pc).replace('PSR-SX600 ', '')
            
        self.lbl_patch.SetLabel(f"Patch: {nome_pc}")
        if falar: falar_status(nome_pc, imediato=True)
        
    def on_update(self, event):
        self.atualizar_label(falar=True)
            
    def get_values(self):
        return self.sp_bank.GetValue(), self.sp_patch.GetValue(), self.sp_tick.GetValue()


class InsertEndNoteDialog(wx.Dialog):
    def __init__(self, parent_el):
        super().__init__(parent_el, title="Inserir Prato no Fim (End Note)", size=(400, 200))
        self.parent_el = parent_el
        self.last_val = None
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.lbl_note = wx.StaticText(self, label=f"Nota (Atual: {get_nome_nota(49)}):")
        self.spin_note = wx.SpinCtrl(self, value='49', min=VALOR_MIN_MIDI, max=VALOR_MAX_MIDI)
        self.spin_note.Bind(wx.EVT_SPINCTRL, self.on_change)
        self.spin_note.Bind(wx.EVT_TEXT, self.on_change)
        self.lbl_vel = wx.StaticText(self, label="Velocity:")
        self.spin_vel = wx.SpinCtrl(self, value='100', min=1, max=VALOR_MAX_MIDI)
        self.spin_vel.Bind(wx.EVT_SPINCTRL, self.on_change)
        self.spin_vel.Bind(wx.EVT_TEXT, self.on_change)
        sizer.Add(self.lbl_note, 0, wx.ALL, 5)
        sizer.Add(self.spin_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(self.lbl_vel, 0, wx.ALL, 5)
        sizer.Add(self.spin_vel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.spin_note.SetFocus()

    def on_change(self, event):
        try:
            n, v = self.spin_note.GetValue(), self.spin_vel.GetValue()
            if self.last_val == (n, v): return
            self.last_val = (n, v)
            if hasattr(self.parent_el.parent, 'traduzir_evento_midi'):
                msg_fake = mido.Message('note_on', channel=self.parent_el.canal_idx, note=n, velocity=v)
                nome = self.parent_el.parent.traduzir_evento_midi(msg_fake, self.parent_el.canal_idx)
            else:
                nome = get_nome_nota(n)
            self.lbl_note.SetLabel(f"Alvo: {nome}")
            falar(nome, imediato=True)
            msg = mido.Message('note_on', channel=self.parent_el.canal_idx, note=n, velocity=v)
            self.parent_el.tocar_nota_exata(msg, 0, 100)
        except Exception: pass
        
    def get_values(self):
        return self.spin_note.GetValue(), self.spin_vel.GetValue()


class EventListQuantizeDialog(wx.Dialog):
    def __init__(self, parent_list):
        super().__init__(parent_list, title="Quantizar Seleção", size=(400, 250))
        self.parent_list = parent_list
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.grids = [
            ("Semínima (1/4)", 480), ("Semínima Tercina (1/4T)", 320), ("Semínima Pontuada (1/4D)", 720),
            ("Colcheia (1/8)", 240), ("Colcheia Tercina (1/8T)", 160), ("Colcheia Pontuada (1/8D)", 360),
            ("Semicolcheia (1/16)", 120), ("Semicolcheia Tercina (1/16T)", 80), ("Semicolcheia Pontuada (1/16D)", 180),
            ("Fusa (1/32)", 60), ("Fusa Tercina (1/32T)", 40), ("Fusa Pontuada (1/32D)", 90)
        ]
        
        lbl_grid = wx.StaticText(self, label="Grade de Quantização:")
        sizer.Add(lbl_grid, 0, wx.ALL, 5)
        self.cb_grid = wx.ComboBox(self, value=self.grids[6][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_grid.SetSelection(6)
        sizer.Add(self.cb_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_forca = wx.StaticText(self, label="Força (%):")
        sizer.Add(lbl_forca, 0, wx.ALL, 5)
        self.sp_forca = wx.SpinCtrl(self, value="100", min=1, max=100)
        sizer.Add(self.sp_forca, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.cb_grid.Bind(wx.EVT_COMBOBOX, self.on_change)
        wx.CallLater(100, self.cb_grid.SetFocus)
        
    def on_change(self, event):
        falar_status(self.cb_grid.GetValue(), imediato=True)
        event.Skip()
        
    def get_values(self):
        base_grid = self.grids[self.cb_grid.GetSelection()][1]
        tpb = self.parent_list.tpq
        grid_ticks = int(round(base_grid * (tpb / 480.0)))
        return grid_ticks, self.sp_forca.GetValue()


class SelecaoAvancadaDialog(wx.Dialog):
    def __init__(self, parent_list):
        super().__init__(parent_list, title="Seleção Avançada", size=(450, 450))
        self.parent_list = parent_list
        sz = wx.BoxSizer(wx.VERTICAL)
        
        lbl_tipo = wx.StaticText(self, label="1. Tipo de Evento:")
        sz.Add(lbl_tipo, 0, wx.ALL, 5)
        self.cb_tipo = wx.ComboBox(self, choices=["Notas", "Control Change", "Program Change", "Pitch Wheel", "Todos"], style=wx.CB_READONLY)
        self.cb_tipo.SetSelection(0)
        sz.Add(self.cb_tipo, 0, wx.EXPAND | wx.ALL, 5)
        
        self.chk_num = wx.CheckBox(self, label="2. Filtrar por Número (Nota ou CC)")
        sz.Add(self.chk_num, 0, wx.ALL, 5)
        
        lbl_nota_min = wx.StaticText(self, label="Número Mínimo:")
        sz.Add(lbl_nota_min, 0, wx.LEFT | wx.RIGHT, 15)
        self.sp_num_min = wx.SpinCtrl(self, value="0", min=0, max=127)
        sz.Add(self.sp_num_min, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        lbl_nota_max = wx.StaticText(self, label="Número Máximo:")
        sz.Add(lbl_nota_max, 0, wx.LEFT | wx.RIGHT, 15)
        self.sp_num_max = wx.SpinCtrl(self, value="127", min=0, max=127)
        sz.Add(self.sp_num_max, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sz.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sz)
        
        self.cb_tipo.Bind(wx.EVT_COMBOBOX, self.on_tipo_change)
        wx.CallLater(100, self.cb_tipo.SetFocus)
        
    def on_tipo_change(self, event):
        falar_status(self.cb_tipo.GetValue(), imediato=True)
        event.Skip()
        
    def aplicar_selecao(self):
        tipo_sel = self.cb_tipo.GetSelection()
        usar_num = self.chk_num.GetValue()
        n_min = self.sp_num_min.GetValue()
        n_max = self.sp_num_max.GetValue()
        if n_min > n_max: n_min, n_max = n_max, n_min
            
        self.parent_list.selected_indices.clear()
        count = 0
        
        for i, ev in enumerate(self.parent_list.display_events):
            if tipo_sel == 1 and ev['type'] != 'control_change': continue
            if tipo_sel == 2 and ev['type'] != 'note': continue
            if tipo_sel == 3 and ev['type'] != 'program_change': continue
            if tipo_sel == 4 and ev['type'] != 'pitchwheel': continue
            
            passa_num = True
            if usar_num:
                num_ev = ev['msg_on'].note if ev['type'] == 'note' else (ev['msg'].control if ev['type'] == 'control_change' else (ev['msg'].program if ev['type'] == 'program_change' else 0))
                passa_num = (n_min <= num_ev <= n_max)
                
            if passa_num:
                self.parent_list.selected_indices.add(i)
                count += 1
        return count


class VirtualEventList(wx.ListCtrl):
    def __init__(self, parent, dialog_ref):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_NO_HEADER)
        self.dialog_ref = dialog_ref
        self.InsertColumn(0, "Evento", width=2000)

    def OnGetItemText(self, item, column):
        if 0 <= item < len(self.dialog_ref.display_events):
            ev = self.dialog_ref.display_events[item]
            return self.dialog_ref.gerar_fala_curta(ev)
        return ""


class EventListDialog(wx.Dialog):
    def __init__(self, parent, canal_idx, section_info, current_tempo, ticks_per_beat):
        self.canal_idx = canal_idx
        self.section_info = section_info
        self.current_tempo = current_tempo
        self.tpq = ticks_per_beat
        self.parent = parent
        
        titulo = f"Event List - {section_info['display_name']} - Canal {canal_idx+1}"
        super().__init__(parent, title=titulo, size=(600, 400), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.preview_note = None
        self.preview_timer = None
        self.modified = False
        
        self.undo_stack = []
        self.selected_indices = set()
        self.all_events = []
        self.display_events = []
        self.active_filter = 1
        self.current_idx = 0
        self.non_contiguous_mode = False
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.dummy_focus = wx.Panel(self, size=(0, 0), style=wx.WANTS_CHARS)
        sizer.Add(self.dummy_focus, 0, wx.ALL, 0)
        
        self.list_box = VirtualEventList(self, self)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
        
        self.load_events()
        self.apply_filter(falar=False)
        self.reconstruir_lista_visual()
        
        self.list_box.Bind(wx.EVT_SET_FOCUS, lambda e: self.dummy_focus.SetFocus())
        self.dummy_focus.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        wx.CallAfter(self.dummy_focus.SetFocus)
        wx.CallLater(1000, self.falar_primeira_nota)

    def on_close(self, event):
        self.matar_nota_preview()
        if self.modified:
            self.rebuild_final_midi()
            falar_status("Alterações salvas na seção.", imediato=True)
        event.Skip()

    def registrar_undo(self):
        self.undo_stack.append(copy.deepcopy(self.all_events))
        if len(self.undo_stack) > 30: self.undo_stack.pop(0)

    def load_events(self):
        self.all_events = []
        if not getattr(self.parent, 'merged_track_cache', None): return
        start_tick = self.section_info['start']
        end_tick = self.section_info['end']
        if end_tick == float('inf'): end_tick = sum(m.time for m in self.parent.merged_track_cache)
        
        abs_time = 0
        # Fila (FIFO) por nota, não um slot único - um slot único perde a
        # referência da instância anterior se a MESMA nota for retocada
        # antes do note_off dela chegar (ex.: violão com técnica de
        # "sustain": segura o acorde a seção inteira E retoca as mesmas
        # notas por cima, pra simular dedilhado/sustain) - a nota antiga
        # ficava "fantasma" na lista, com start==end (duração 0), sem
        # NENHUM jeito de o NVDA falar ela direito. Achado com o Michel no
        # violão do Pop MHS 02.sty. FIFO garante que o note_off sempre
        # fecha a instância MAIS ANTIGA ainda aberta daquela nota, que é a
        # ordem natural de qualquer sobreposição real.
        active_notes = defaultdict(deque)
        for msg in self.parent.merged_track_cache:
            abs_time += msg.time
            ch = getattr(msg, 'channel', None)
            if start_tick <= abs_time < end_tick and ch == self.canal_idx:
                if msg.type == 'note_on' and msg.velocity > 0:
                    ev = {'type': 'note', 'start': abs_time, 'end': abs_time, 'msg_on': msg, 'msg_off': None}
                    self.all_events.append(ev)
                    active_notes[msg.note].append(ev)
                elif msg.type == 'note_off' or (msg.type == 'note_on' and getattr(msg, 'velocity', 0) == 0):
                    fila = active_notes.get(msg.note)
                    if fila:
                        ev = fila.popleft()
                        ev['end'] = abs_time
                        ev['msg_off'] = msg
                    else:
                        self.all_events.append({'type': 'note_off', 'time': abs_time, 'msg': msg})
                else:
                    self.all_events.append({'type': msg.type, 'time': abs_time, 'msg': msg})
                    
        self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])

    def apply_filter(self, falar=True):
        if not hasattr(self, 'active_filter'): self.active_filter = 1
        indice_salvo = getattr(self, 'current_idx', 0)
        
        self.display_events = []
        for ev in self.all_events:
            msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
            if self.active_filter == 1: self.display_events.append(ev)
            elif self.active_filter == 2 and ev['type'] == 'note': self.display_events.append(ev)
            elif self.active_filter == 3 and msg.type == 'control_change': self.display_events.append(ev)
            elif self.active_filter == 4 and msg.type == 'program_change': self.display_events.append(ev)
            elif self.active_filter == 5 and msg.type == 'pitchwheel': self.display_events.append(ev)
            
        self.selected_indices.clear()
        
        if not falar:
            self.current_idx = max(0, min(indice_salvo, len(self.display_events) - 1)) if self.display_events else 0
        else:
            self.current_idx = 0
            
        self.reconstruir_lista_visual()
        if falar:
            nomes = {1: "Todos", 2: "Notas", 3: "CC", 4: "PC", 5: "Pitch"}
            falar_status(f"Filtro: {nomes.get(self.active_filter, '')}. {len(self.display_events)} itens.", imediato=True)

    def gerar_fala_curta(self, ev):
        msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
        rel_tick = (ev['start'] if ev['type'] == 'note' else ev['time']) - self.section_info['start']
        time_str = f"Tick: {rel_tick}"
        
        if hasattr(self.parent, 'traduzir_evento_midi'):
            texto_traduzido = self.parent.traduzir_evento_midi(msg, self.canal_idx)
            if ev['type'] == 'note':
                dur_ticks = ev['end'] - ev['start']
                return f"{texto_traduzido} | Vel: {msg.velocity}, Dur: {dur_ticks} ticks - {time_str}"
            elif msg.type == 'control_change':
                return f"{texto_traduzido} | Valor: {msg.value} - {time_str}"
            elif msg.type == 'pitchwheel':
                return f"{texto_traduzido} | Valor: {msg.pitch} - {time_str}"
            else:
                return f"{texto_traduzido} - {time_str}"
        return f"{msg.type} - {time_str}"

    def falar_primeira_nota(self):
        if self.display_events:
            falar_status(self.gerar_fala_curta(self.display_events[self.current_idx]), imediato=True)

    def reconstruir_lista_visual(self):
        self.list_box.SetItemCount(len(self.display_events))
        self.list_box.Refresh()
        self.atualizar_foco_visual()

    def atualizar_foco_visual(self):
        if not self.display_events: return
        self.list_box.Freeze()
        total = self.list_box.GetItemCount()
        selecionados = len(self.selected_indices)
        
        self.list_box.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
        if selecionados == total:
            self.list_box.SetItemState(-1, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        elif 0 < selecionados < 50:
            for idx in self.selected_indices:
                if 0 <= idx < total:
                    self.list_box.SetItemState(idx, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
                    
        if 0 <= self.current_idx < total:
            self.list_box.SetItemState(self.current_idx, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED)
            self.list_box.EnsureVisible(self.current_idx)
            
        self.list_box.Thaw()

    def speak_and_preview(self):
        if not self.display_events: return
        ev = self.display_events[self.current_idx]
        msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
        
        falar_status(self.gerar_fala_curta(ev), imediato=True)
        if ev['type'] == 'note': self.tocar_nota_exata(msg, ev['start'], ev['end'])
        
        rel_tick = (ev['start'] if ev['type'] == 'note' else ev['time']) - self.section_info['start']
        self.parent.anchor_tick = max(0, rel_tick) 
        if self.parent.playing and not self.parent.paused: 
            self.parent.force_reload_loop = True 

    def update_realtime_playhead(self, current_tick):
        if not self.display_events: return
        # `current_tick` vem do midi_worker RELATIVO ao início da seção
        # (float_tick parte de self.anchor_tick, que já é relativo - ver
        # get_current_absolute_tick), mas ev['start']/ev['time'] são
        # ticks ABSOLUTOS do arquivo - precisa somar o início da seção
        # antes de comparar, senão a comparação nunca bate direito
        # (current_tick sempre muito menor que qualquer tick absoluto) e
        # o cursor fica preso na 1ª linha durante toda a reprodução ao
        # vivo, sem acompanhar nada.
        alvo = self.section_info['start'] + current_tick
        # Fica no ÚLTIMO evento que já começou (tick <= alvo), não no
        # PRÓXIMO que ainda vai tocar - senão, ao pausar logo depois de
        # ouvir uma nota, o cursor já está silenciosamente na nota SEGUINTE
        # (a que ainda nem tocou), e descer daí pula ela inteira (achado
        # com o Michel: pausando depois da nota 38, Cima toca 38 - por
        # coincidência, já que o cursor estava em 39 - mas Baixo pulava
        # direto pra 40).
        best_idx = 0
        for i, ev in enumerate(self.display_events):
            t = ev['start'] if ev['type'] == 'note' else ev['time']
            if t <= alvo:
                best_idx = i
            else:
                break
        # Marca que o current_idx veio da reprodução (não de navegação
        # manual) - a 1ª seta de Cima depois disso não decrementa, revê a
        # nota atual (ver on_key/_boundary_pausa).
        self._boundary_pausa = True
        if best_idx != self.current_idx:
            self.current_idx = best_idx
            self.atualizar_foco_visual()

    def set_playhead_tick(self, tick):
        if not self.display_events: return
        # Mesmo raciocínio de update_realtime_playhead: fica no ÚLTIMO
        # evento que já começou até este tick, não no próximo.
        start_t = self.section_info['start']
        alvo = start_t + tick
        best_idx = 0
        for i, ev in enumerate(self.display_events):
            t = ev['start'] if ev['type'] == 'note' else ev['time']
            if t <= alvo:
                best_idx = i
            else:
                break
        # Marca que o current_idx veio da reprodução (não de navegação
        # manual) - a 1ª seta de Cima depois disso não decrementa, revê a
        # nota atual (ver on_key/_boundary_pausa).
        self._boundary_pausa = True
        self.current_idx = best_idx
        self.reconstruir_lista_visual()

    def matar_nota_preview(self):
        if getattr(self, 'preview_timer', None):
            self.preview_timer.cancel()
            self.preview_timer = None
        if getattr(self, 'preview_note', None) and getattr(self.parent, 'midi_out', None):
            try:
                msg_off = mido.Message('note_off', channel=self.preview_note.channel, note=self.preview_note.note, velocity=0)
                self.parent.midi_out.send(msg_off)
            except Exception: pass
            self.preview_note = None

    def tocar_nota_exata(self, msg, start_tick, end_tick):
        if msg.type == 'note_on' and msg.velocity > 0 and getattr(self.parent, 'midi_out', None):
            self.matar_nota_preview()
            self.preview_note = msg
            try: self.parent.midi_out.send(msg)
            except Exception: pass
            self.preview_timer = threading.Timer(0.3, self.matar_nota_preview)
            self.preview_timer.start()

    def rebuild_final_midi(self):
        nova_track = []
        start_tick = self.section_info['start']
        end_tick = self.section_info['end']
        if end_tick == float('inf'): end_tick = sum(m.time for m in self.parent.merged_track_cache)
        
        abs_time = 0
        for msg in self.parent.merged_track_cache:
            abs_time += msg.time
            ch = getattr(msg, 'channel', None)
            if start_tick <= abs_time < end_tick and ch == self.canal_idx: continue
            nova_track.append([abs_time, msg])
            
        for ev in self.all_events:
            if ev['type'] == 'note':
                nova_track.append([ev['start'], ev['msg_on']])
                if ev['msg_off']: nova_track.append([ev['end'], ev['msg_off']])
            else: 
                nova_track.append([ev['time'], ev['msg']])
                
        nova_track.sort(key=lambda x: x[0])
        self.parent.merged_track_cache = []
        last_t = 0
        for t, msg in nova_track:
            msg.time = int(round(t - last_t))
            self.parent.merged_track_cache.append(msg)
            last_t = t
            
        if hasattr(self.parent, 'rebuild_sections_from_cache'):
            self.parent.rebuild_sections_from_cache()
        self.modified = False
        if getattr(self.parent, 'playing', False) and not getattr(self.parent, 'paused', False): 
            self.parent.force_reload_loop = True

    def get_selected_events(self):
        if self.selected_indices: return [self.display_events[i] for i in sorted(self.selected_indices)]
        if self.display_events: return [self.display_events[self.current_idx]]
        return []

    def copiar_evento(self):
        evs = self.get_selected_events()
        if not evs: return
        self.parent.event_clipboard = []
        first_ticks = evs[0]['start'] if evs[0]['type'] == 'note' else evs[0]['time']
        for ev in evs:
            ev_ticks = ev['start'] if ev['type'] == 'note' else ev['time']
            offset = ev_ticks - first_ticks
            clonado = copy.deepcopy(ev)
            clonado['tick_offset'] = offset
            self.parent.event_clipboard.append(clonado)
        falar_status(f"{len(evs)} copiados.", imediato=True)

    def colar_evento(self):
        if not getattr(self.parent, 'event_clipboard', None):
            falar_status("Área de transferência vazia.", imediato=True)
            return
        self.registrar_undo()
        ev_foco = self.display_events[self.current_idx] if self.display_events else None
        base_paste = ev_foco['start'] if (ev_foco and ev_foco['type'] == 'note') else (ev_foco['time'] if ev_foco else self.section_info['start'])
        
        end_t = self.section_info['end']
        if end_t == float('inf'): end_t = sum(m.time for m in self.parent.merged_track_cache)
        
        colados = 0
        for item in self.parent.event_clipboard:
            paste_ticks = base_paste + item['tick_offset']
            if paste_ticks >= end_t: continue
            
            if item['type'] == 'note':
                dur = item['end'] - item['start']
                msg_on = item['msg_on'].copy(channel=self.canal_idx)
                msg_off = item['msg_off'].copy(channel=self.canal_idx) if item.get('msg_off') else mido.Message('note_off', channel=self.canal_idx, note=msg_on.note, velocity=0)
                self.all_events.append({'type': 'note', 'start': paste_ticks, 'end': paste_ticks + dur, 'msg_on': msg_on, 'msg_off': msg_off})
            else:
                msg = item['msg'].copy(channel=self.canal_idx) if hasattr(item['msg'], 'channel') else item['msg'].copy()
                self.all_events.append({'type': item['type'], 'time': paste_ticks, 'msg': msg})
            colados += 1
            
        self.modified = True
        self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
        self.apply_filter(falar=False)
        self.reconstruir_lista_visual()
        falar_status(f"{colados} eventos colados.", imediato=True)

    def duplicar_evento(self, flam=False):
        if not self.display_events: return
        self.registrar_undo()
        self.modified = True
        
        # --- CÁLCULO DO FLAM COM BASE EM TEMPO REAL (40ms) ---
        if flam:
            delay_sec = 0.040 # 40 milissegundos
            bpm_dur = self.current_tempo / 1000000.0
            delay_ticks = int(round((delay_sec / bpm_dur) * self.tpq))
        else:
            delay_ticks = 0
            
        ev_foco = self.display_events[self.current_idx]
        msg = ev_foco.get('msg_on') if ev_foco['type'] == 'note' else ev_foco['msg']
        abs_ticks = ev_foco['start'] if ev_foco['type'] == 'note' else ev_foco['time']

        new_start_ticks = abs_ticks + delay_ticks
        
        if ev_foco['type'] == 'note':
            dur_ticks = ev_foco['end'] - ev_foco['start']
            new_end_ticks = new_start_ticks + dur_ticks
            msg_on = ev_foco['msg_on'].copy()
            msg_off = ev_foco['msg_off'].copy() if ev_foco['msg_off'] else mido.Message('note_off', channel=msg_on.channel, note=msg_on.note, velocity=0)
            new_ev = {'type': 'note', 'start': new_start_ticks, 'end': new_end_ticks, 'msg_on': msg_on, 'msg_off': msg_off}
            self.all_events.append(new_ev)
        else:
            new_ev = {'type': ev_foco['type'], 'time': new_start_ticks, 'msg': msg.copy()}
            self.all_events.append(new_ev)
            
        falar_status(f"Flam gerado ({delay_ticks} ticks - 40ms)." if flam else "Evento duplicado.", imediato=True)
        self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
        self.apply_filter(falar=False)
        self.current_idx = min(self.current_idx + 1, len(self.display_events) - 1)
        self.atualizar_foco_visual()
        self.speak_and_preview()

    def achatar_notas_um_tick(self):
        # 'T' de Tick - reduz a DURAÇÃO de nota(s) pro mínimo possível (1
        # tick), sem mexer no início, no pitch nem na velocity. Pedido do
        # Michel pra bateria/percussão: como esses instrumentos costumam
        # ser samples de um tiro só, o note_off praticamente não importa
        # pro som terminar - deixar cada batida com 1 tick só limpa a
        # lista de eventos e evita nota "comprida" à toa arrastando note_
        # off por cima de outras batidas (mesmo tipo de bagunça que achei
        # analisando o Fill In BB do Pop MHS 02.sty).
        # Mesmo critério do 'S' (Substituir): com mais de 1 selecionado,
        # aplica só na seleção; senão, aplica em TODAS as notas da lista
        # visível (o filtro de canal/tipo continua valendo).
        evs_target = self.get_selected_events() if len(self.selected_indices) > 1 else self.display_events
        notas = [e for e in evs_target if e['type'] == 'note']
        if not notas:
            falar_status("Nenhuma nota pra achatar.", imediato=True)
            return
        self.registrar_undo()
        for e in notas:
            e['end'] = e['start'] + 1
        self.modified = True
        self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
        self.apply_filter(falar=False)
        self.atualizar_foco_visual()
        falar_status(f"{len(notas)} nota(s) achatada(s) pra 1 tick.", imediato=True)

    def insert_event(self):
        base_ticks = self.section_info['start'] + getattr(self.parent, 'anchor_tick', 0)
        dlg = wx.SingleChoiceDialog(self, "Tipo de Evento:", "Inserir", ["Nota", "Control Change (CC)", "Program Change (PC)", "Prato no Fim (End Note)"])
        
        if dlg.ShowModal() == wx.ID_OK:
            sel_idx = dlg.GetSelection()
            
            if sel_idx == 0:
                dlg_nota = EdicaoNotaDialog(self, 60, 100, 120, base_ticks - self.section_info['start'], is_insert=True)
                if dlg_nota.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    n, v, dur, rel_tick = dlg_nota.get_values()
                    abs_t = self.section_info['start'] + rel_tick
                    msg_on = mido.Message('note_on', channel=self.canal_idx, note=n, velocity=v)
                    msg_off = mido.Message('note_off', channel=self.canal_idx, note=n, velocity=0)
                    self.all_events.append({'type': 'note', 'start': abs_t, 'end': abs_t + dur, 'msg_on': msg_on, 'msg_off': msg_off})
                    self.modified = True
                dlg_nota.Destroy()
                
            elif sel_idx == 1:
                dlg_cc = EdicaoCCDialog(self, 0, 0, base_ticks - self.section_info['start'], is_insert=True)
                if dlg_cc.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    c, v, rel_tick = dlg_cc.get_values()
                    abs_t = self.section_info['start'] + rel_tick
                    msg = mido.Message('control_change', channel=self.canal_idx, control=c, value=v)
                    self.all_events.append({'type': 'control_change', 'time': abs_t, 'msg': msg})
                    self.modified = True
                dlg_cc.Destroy()
                
            elif sel_idx == 2:
                dlg_pc = EdicaoPCDialog(self, 0, 0, base_ticks - self.section_info['start'], is_insert=True)
                if dlg_pc.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    b, p, rel_tick = dlg_pc.get_values()
                    abs_t = self.section_info['start'] + rel_tick
                    msg_pc = mido.Message('program_change', channel=self.canal_idx, program=p)
                    msg_msb = mido.Message('control_change', channel=self.canal_idx, control=0, value=b // 128)
                    msg_lsb = mido.Message('control_change', channel=self.canal_idx, control=32, value=b % 128)
                    self.all_events.append({'type': 'control_change', 'time': abs_t, 'msg': msg_msb})
                    self.all_events.append({'type': 'control_change', 'time': abs_t, 'msg': msg_lsb})
                    self.all_events.append({'type': 'program_change', 'time': abs_t, 'msg': msg_pc})
                    self.modified = True
                dlg_pc.Destroy()
                
            elif sel_idx == 3: 
                dlg_end = InsertEndNoteDialog(self)
                if dlg_end.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    n, v = dlg_end.get_values()
                    end_t = self.section_info['end']
                    if end_t == float('inf'): end_t = sum(m.time for m in self.parent.merged_track_cache)
                    # O note_off (start+1) precisa ficar ESTRITAMENTE antes
                    # de end_t - se o prato começasse em end_t-1 (o tick mais
                    # tarde possível), o note_off cairia bem em end_t, que já
                    # é o primeiro tick da seção SEGUINTE (prepare_section_
                    # cache corta em ">= fim"). Isso fazia o "desligar" do
                    # prato vazar pra seção de depois, deixando ele preso
                    # (achado com o Michel: "Prato no Fim" era o que causava
                    # o vazamento nas Fills/Intros do Pop MHS 02.sty). Por
                    # isso o prato começa 1 tick mais cedo (end_t-2) - ainda
                    # é praticamente "no fim", só que agora com note_on E
                    # note_off os dois dentro da própria seção.
                    t_prato = max(self.section_info['start'], end_t - 2)
                    t_off = min(t_prato + 1, end_t - 1)
                    if t_off <= t_prato: t_off = t_prato + 1
                    msg_on = mido.Message('note_on', channel=self.canal_idx, note=n, velocity=v)
                    msg_off = mido.Message('note_off', channel=self.canal_idx, note=n, velocity=0)
                    self.all_events.append({'type': 'note', 'start': t_prato, 'end': t_off, 'msg_on': msg_on, 'msg_off': msg_off})
                    self.modified = True
                dlg_end.Destroy()

            if getattr(self, 'modified', False):
                self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
                self.apply_filter(falar=False)
                if self.display_events: self.current_idx = min(self.current_idx + 1, len(self.display_events) - 1)
                self.atualizar_foco_visual()
                self.speak_and_preview()
                falar_status("Evento inserido.", imediato=True)
                
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)

    def recortar_evento(self):
        evs = self.get_selected_events()
        if not evs: return
        self.registrar_undo()
        for ev in evs:
            if ev in self.all_events: self.all_events.remove(ev)
        self.selected_indices.clear()
        self.modified = True
        falar_status(f"{len(evs)} apagados.", imediato=True)
        self.apply_filter(falar=False)
        self.current_idx = max(0, min(self.current_idx, len(self.display_events) - 1))
        self.atualizar_foco_visual()
        self.speak_and_preview()

    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        # Capturado ANTES de qualquer ramo mexer nele - vale só pra tecla
        # de seta que está sendo processada AGORA (a que causou este
        # on_key). Um Espaço que pausa agora mesmo (mais abaixo) planta um
        # boundary NOVO pra próxima tecla, sem risco de se auto-limpar.
        veio_de_pausa = getattr(self, '_boundary_pausa', False)
        self._boundary_pausa = False

        if code == wx.WXK_SPACE:
            if ctrl: 
                self.parent.OnTogglePause(None)
                self.set_playhead_tick(self.parent.anchor_tick) 
            else: 
                if self.modified:
                    self.rebuild_final_midi()
                self.parent.OnTogglePlay(None)
                if not getattr(self.parent, 'playing', False): self.set_playhead_tick(self.parent.anchor_tick) 
            return

        if code == wx.WXK_INSERT or (code in [ord('I'), ord('i')] and ctrl):
            self.insert_event(); return
            
        if code == wx.WXK_ESCAPE:
            if shift:
                self.selected_indices.clear()
                self.non_contiguous_mode = False
                self.atualizar_foco_visual()
                falar_status("Seleções canceladas.", imediato=True)
                return
            self.Close(); return

        if code in [ord('1'), ord('2'), ord('3'), ord('4'), ord('5')] and not (ctrl or alt or shift):
            self.active_filter = code - ord('0')
            self.apply_filter(falar=True)
            return

        if not self.display_events: event.Skip(); return

        if code in [ord('Z'), ord('z')] and ctrl and not shift and not alt:
            if self.undo_stack:
                self.all_events = self.undo_stack.pop()
                self.modified = True
                self.apply_filter(falar=False)
                self.current_idx = min(self.current_idx, len(self.display_events) - 1)
                self.atualizar_foco_visual()
                self.speak_and_preview()
                falar_status("Desfeito.", imediato=True)
            return

        if code in [ord('A'), ord('a')] and ctrl and not shift and not alt:
            self.selected_indices = set(range(len(self.display_events)))
            self.atualizar_foco_visual()
            falar_status("Todos selecionados", imediato=True)
            return

        if code in [ord('A'), ord('a')] and shift and not ctrl and not alt:
            ev_ref = self.display_events[self.current_idx]
            ref_type = ev_ref['type']
            has_item_sel = len(self.selected_indices) > 1
            search_pool = self.selected_indices.copy() if has_item_sel else set(range(len(self.display_events)))
            
            self.selected_indices.clear()
            count = 0
            for i in search_pool:
                ev = self.display_events[i]
                match = False
                if ev['type'] == ref_type:
                    if ref_type == 'note':
                        if ev['msg_on'].note == ev_ref['msg_on'].note: match = True
                    elif ref_type == 'control_change':
                        if ev['msg'].control == ev_ref['msg'].control: match = True
                    else:
                        match = True
                if match:
                    self.selected_indices.add(i)
                    count += 1
            self.atualizar_foco_visual()
            falar_status(f"{count} notas iguais na seleção." if has_item_sel else f"{count} iguais na pista.", imediato=True)
            return

        if code in [wx.WXK_SPACE, 32] and shift and not ctrl and not alt:
            if not getattr(self, 'non_contiguous_mode', False):
                self.non_contiguous_mode = True
                self.selected_indices.add(self.current_idx)
                falar_status("Modo múltiplo. Selecionado.", imediato=True)
            else:
                if self.current_idx in self.selected_indices:
                    self.selected_indices.remove(self.current_idx)
                    falar_status("Removido", imediato=True)
                else:
                    self.selected_indices.add(self.current_idx)
                    falar_status("Selecionado", imediato=True)
            self.atualizar_foco_visual()
            return

        if code in [ord('Q'), ord('q')] and ctrl and not shift and not alt:
            dlg = EventListQuantizeDialog(self)
            if dlg.ShowModal() == wx.ID_OK:
                self.registrar_undo()
                grid_ticks, forca = dlg.get_values()
                evs_target = self.get_selected_events() if len(self.selected_indices) > 1 else self.display_events
                count = 0
                for ev in evs_target:
                    if ev['type'] == 'note':
                        start_tick = ev['start'] - self.section_info['start']
                        closest_grid = round(start_tick / grid_ticks) * grid_ticks
                        diff = closest_grid - start_tick
                        move_ticks = int(round(diff * (forca / 100.0)))
                        if move_ticks != 0:
                            dur = ev['end'] - ev['start']
                            ev['start'] += move_ticks
                            ev['end'] = ev['start'] + dur
                            count += 1
                self.modified = True
                falar_status(f"{count} notas quantizadas.", imediato=True)
                self.apply_filter(falar=False)
                self.speak_and_preview()
            dlg.Destroy()
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [ord('E'), ord('e')] and ctrl and shift and not alt:
            dlg = SelecaoAvancadaDialog(self)
            if dlg.ShowModal() == wx.ID_OK:
                count = dlg.aplicar_selecao()
                self.atualizar_foco_visual()
                falar_status(f"Filtro aplicado. {count} selecionados.", imediato=True)
            dlg.Destroy()
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [ord('S'), ord('s')] and not (ctrl or alt or shift):
            ev = self.display_events[self.current_idx]
            if ev['type'] == 'note':
                old_note = ev['msg_on'].note
                dlg = SubstituirNotasDialog(self, old_note)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    new_note, adj_vel, adj_dur = dlg.get_values()
                    evs_target = self.get_selected_events() if len(self.selected_indices) > 1 else self.display_events
                    count = 0
                    for e in evs_target:
                        if e['type'] == 'note' and e['msg_on'].note == old_note:
                            v = max(1, min(127, e['msg_on'].velocity + adj_vel))
                            dur = max(1, (e['end'] - e['start']) + adj_dur)
                            e['msg_on'] = e['msg_on'].copy(note=new_note, velocity=v)
                            if e['msg_off']: e['msg_off'] = e['msg_off'].copy(note=new_note)
                            e['end'] = e['start'] + dur
                            count += 1
                    self.modified = True
                    falar_status(f"{count} modificadas.", imediato=True)
                    self.apply_filter(falar=False)
                    self.speak_and_preview()
                dlg.Destroy()
            return

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and not (ctrl or alt or shift):
            ev = self.display_events[self.current_idx]
            msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
            rel_tick = (ev['start'] if ev['type'] == 'note' else ev['time']) - self.section_info['start']
            
            if ev['type'] == 'note':
                dur_ticks = ev['end'] - ev['start']
                dlg = EdicaoNotaDialog(self, msg.note, msg.velocity, dur_ticks, rel_tick, is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    n, v, d, t_new = dlg.get_values()
                    abs_t = self.section_info['start'] + t_new
                    for i in (self.selected_indices if len(self.selected_indices)>1 else [self.current_idx]):
                        e = self.display_events[i]
                        if e['type'] == 'note':
                            e['msg_on'] = e['msg_on'].copy(note=n, velocity=v)
                            if e['msg_off']: e['msg_off'] = e['msg_off'].copy(note=n)
                            e['start'] = abs_t
                            e['end'] = e['start'] + d
                    self.modified = True
                    self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
                    self.apply_filter(falar=False)
                    self.speak_and_preview()
                dlg.Destroy()
                
            elif ev['type'] == 'control_change':
                dlg = EdicaoCCDialog(self, msg.control, msg.value, tick_val=rel_tick, is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    cc_new, val_new, t_new = dlg.get_values()
                    ev['msg'] = ev['msg'].copy(control=cc_new, value=val_new)
                    ev['time'] = self.section_info['start'] + t_new
                    self.modified = True
                    self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
                    self.apply_filter(falar=False)
                    self.speak_and_preview()
                dlg.Destroy()
                
            elif ev['type'] == 'program_change':
                dlg = EdicaoPCDialog(self, 0, msg.program, tick_val=rel_tick, is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    b_new, p_new, t_new = dlg.get_values()
                    ev['msg'] = ev['msg'].copy(program=p_new)
                    ev['time'] = self.section_info['start'] + t_new
                    self.modified = True
                    self.all_events.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
                    self.apply_filter(falar=False)
                    self.speak_and_preview()
                dlg.Destroy()
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [wx.WXK_HOME, wx.WXK_END] and ctrl and not (alt or shift):
            # Ctrl+Home: primeiro evento de NOTA da lista (sem nota nenhuma
            # na lista filtrada, cai no primeiro evento). Ctrl+End: último
            # evento da lista, de qualquer tipo.
            self.selected_indices.clear()
            self.non_contiguous_mode = False
            if code == wx.WXK_HOME:
                self.current_idx = 0
                for i_ev, ev in enumerate(self.display_events):
                    if ev.get('type') == 'note':
                        self.current_idx = i_ev
                        break
                msg_fala = "Primeiro evento de nota"
            else:
                self.current_idx = len(self.display_events) - 1
                msg_fala = "Último evento da lista"
            self.atualizar_foco_visual()
            self.speak_and_preview()
            falar_status(msg_fala, imediato=False)
            return

        if code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN] and not (ctrl or alt):
            if shift:
                if not getattr(self, 'non_contiguous_mode', False): self.selected_indices.add(self.current_idx)
            else:
                self.selected_indices.clear()
                self.non_contiguous_mode = False

            # Depois de pausar (set_playhead_tick/update_realtime_playhead),
            # o cursor já fica na ÚLTIMA nota que tocou (ex.: 38) - Descer
            # (current_idx+1) já cai certinho na PRÓXIMA (39), sem precisar
            # de nada especial. Mas Subir, sem tratamento, pularia direto
            # pra 37 - o usuário nunca "revê" a 38 que acabou de ouvir.
            # Achado com o Michel: ele queria que a 1ª seta de Cima depois
            # de uma pausa trouxesse de volta a nota que tocou por último
            # (38), não pulasse pra antes dela (37) - só na 2ª tecla (ou
            # depois de qualquer outra navegação) o decremento normal volta.
            if code == wx.WXK_UP:
                if not (veio_de_pausa and not shift):
                    self.current_idx = max(0, self.current_idx - 1)
            elif code == wx.WXK_DOWN: self.current_idx = min(len(self.display_events) - 1, self.current_idx + 1)
            elif code == wx.WXK_PAGEUP: self.current_idx = max(0, self.current_idx - 10)
            elif code == wx.WXK_PAGEDOWN: self.current_idx = min(len(self.display_events) - 1, self.current_idx + 10)

            if shift:
                if not getattr(self, 'non_contiguous_mode', False): self.selected_indices.add(self.current_idx)

            self.atualizar_foco_visual()
            self.speak_and_preview()
            if shift and not getattr(self, 'non_contiguous_mode', False): falar_status("Selecionado", imediato=False)
            return  

        if code in [wx.WXK_LEFT, wx.WXK_RIGHT]:
            evs = self.get_selected_events()
            sign = -1 if code == wx.WXK_LEFT else 1
            ev_foco = self.display_events[self.current_idx]
            tipo_foco = ev_foco['type']
            mudanca_str = ""
            
            for ev in evs:
                if ev['type'] != tipo_foco: continue 
                if ev['type'] == 'note':
                    if not ctrl and not alt and not shift:
                        nova_nota = max(0, min(127, ev['msg_on'].note + sign))
                        ev['msg_on'] = ev['msg_on'].copy(note=nova_nota)
                        if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=nova_nota)
                        if ev == ev_foco: mudanca_str = f"Nota {nova_nota}"
                    elif ctrl and not alt and not shift:
                        nova_nota = max(0, min(127, ev['msg_on'].note + (sign * 12)))
                        ev['msg_on'] = ev['msg_on'].copy(note=nova_nota)
                        if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=nova_nota)
                        if ev == ev_foco: mudanca_str = f"Oitava {nova_nota}"
                    elif shift and not ctrl and not alt:
                        novo_vel = max(1, min(127, ev['msg_on'].velocity + sign))
                        ev['msg_on'] = ev['msg_on'].copy(velocity=novo_vel)
                        if ev == ev_foco: mudanca_str = f"Velocity {novo_vel}"
                    elif ctrl and shift and not alt:
                        novo_vel = max(1, min(127, ev['msg_on'].velocity + (sign * 10)))
                        ev['msg_on'] = ev['msg_on'].copy(velocity=novo_vel)
                        if ev == ev_foco: mudanca_str = f"Velocity {novo_vel}"
                    elif alt and not ctrl and not shift:
                        dur = max(1, (ev['end'] - ev['start']) + sign)
                        ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = f"Duração {dur} ticks"
                    elif ctrl and alt and not shift:
                        dur = max(1, (ev['end'] - ev['start']) + (sign * 5))
                        ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = f"Duração {dur} ticks"
                    elif shift and alt and not ctrl:
                        dur = ev['end'] - ev['start']
                        novo_start = ev['start'] + sign
                        if self.section_info['start'] <= novo_start < self.section_info['end']:
                            ev['start'] = novo_start
                            ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = "Movido"
                    elif ctrl and shift and alt:
                        dur = ev['end'] - ev['start']
                        novo_start = ev['start'] + (sign * 10)
                        if self.section_info['start'] <= novo_start < self.section_info['end']:
                            ev['start'] = novo_start
                            ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = "Movido rápido"
                elif ev['type'] == 'control_change':
                    if not ctrl and not alt and not shift:
                        novo_cc = max(0, min(127, ev['msg'].control + sign))
                        ev['msg'] = ev['msg'].copy(control=novo_cc)
                        if ev == ev_foco: mudanca_str = f"CC {novo_cc}"
                    elif ctrl and not alt and not shift:
                        novo_val = max(0, min(127, ev['msg'].value + sign))
                        ev['msg'] = ev['msg'].copy(value=novo_val)
                        if ev == ev_foco: mudanca_str = f"Valor {novo_val}"

            if mudanca_str:
                self.modified = True
                if len(self.selected_indices) > 50: self.list_box.Refresh() 
                else:
                    self.list_box.Freeze()
                    for idx in self.selected_indices:
                        if 0 <= idx < self.list_box.GetItemCount(): self.list_box.RefreshItem(idx)
                    if 0 <= self.current_idx < self.list_box.GetItemCount(): self.list_box.RefreshItem(self.current_idx)
                    self.list_box.Thaw()
                self.atualizar_foco_visual()
                falar_status(mudanca_str, imediato=True)
                if tipo_foco == 'note': self.tocar_nota_exata(ev_foco['msg_on'], ev_foco['start'], ev_foco['end'])
            return

        if code in [wx.WXK_DELETE, wx.WXK_BACK, wx.WXK_NUMPAD_DELETE]:
            self.recortar_evento()
            return

        if code in [ord('C'), ord('c')] and ctrl and not shift and not alt:
            self.copiar_evento(); return
        if code in [ord('V'), ord('v')] and ctrl and not shift and not alt:
            self.colar_evento(); return
        if code in [ord('D'), ord('d')] and not (ctrl or alt or shift):
            self.duplicar_evento(flam=False); return
        if code in [ord('F'), ord('f')] and not (ctrl or alt or shift):
            self.duplicar_evento(flam=True); return
        if code in [ord('T'), ord('t')] and not (ctrl or alt or shift):
            self.achatar_notas_um_tick(); return

        event.Skip()