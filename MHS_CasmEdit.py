import wx
from MHS_Utils import falar

class SectionCasmDialog(wx.Dialog):
    def __init__(self, parent, section_info):
        super().__init__(parent, title=f"Casm Edit - {section_info['display_name']}", size=(700, 500), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.WANTS_CHARS)
        self.parent = parent
        self.section_info = section_info
        
        self.canal_atual = parent.canal_atual
        self.propriedade_atual = 0
        
        self.propriedades = [
            "Nome", "Mute", "Solo", "Volume", "Pan", "Expression", 
            "Bank", "Patch", "Reverb", "Chorus", "NTR", "NTT", "Bass", "High Key", 
            "Limite Grave", "Limite Agudo"
        ]

        self.ntr_lista = ["trans", "fixed", "gtr"]
        self.ntt_lista = ["bypass", "melody", "chord", "melodic minor", "melodic minor 5th", "harmonic minor", "harmonic minor 5th", "natural minor", "natural minor 5th", "dorian", "dorian 5th"]
        self.notas_lista = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.list_box = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.atualizar_lista_completa()
        self.list_box.SetSelection(self.canal_atual)
        
        self.list_box.Bind(wx.EVT_LISTBOX, self.on_select)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        wx.CallLater(100, self.list_box.SetFocus)
        falar(f"Casm Edit aberto. Seção {section_info['display_name']}.", imediato=True)

    def obter_valor_formatado(self, ch, prop):
        if prop == "Patch":
            bank_id = self.parent.canais[ch]["Bank"]
            val = self.parent.canais[ch]["Patch"]
            return self.parent.ins_db.get(bank_id, {}).get(val, f"Patch {val}").replace('PSR-SX600 ', '')
        elif prop in self.parent.canais[ch]:
            val = self.parent.canais[ch][prop]
            if isinstance(val, bool): return "Ligado" if val else "Desligado"
            return str(val)
        else:
            regras = self.parent.casm_rules[ch]
            if prop == "NTR": return regras.get('play_type', 'trans').upper()
            elif prop == "NTT": return regras.get('ntt_type', 'chord').upper()
            elif prop == "Bass": return "ON" if regras.get('ntt_bass', False) else "OFF"
            elif prop == "High Key": 
                nota_idx = regras.get('high_key', 6)
                return self.notas_lista[nota_idx % 12]
            elif prop == "Limite Grave": return str(regras.get('note_limit_low', 0))
            elif prop == "Limite Agudo": return str(regras.get('note_limit_high', 127))
        return ""

    def atualizar_lista_completa(self):
        self.list_box.Freeze()
        self.list_box.Clear()
        for ch in range(16):
            c = self.parent.canais[ch]
            status = ("[S] " if c['Solo'] else "") + ("[M] " if c['Mute'] else "")
            p = self.propriedades[self.propriedade_atual]
            val_str = self.obter_valor_formatado(ch, p)
            
            nova_string = f"{p}: {val_str}  |  {status}{c['Nome']} [C{ch+1}]"
            self.list_box.Append(nova_string)
        self.list_box.Thaw()

    def on_select(self, event):
        self.canal_atual = self.list_box.GetSelection()
        self.parent.canal_atual = self.canal_atual 
        event.Skip()

    def ler_foco_atual(self):
        ch = self.canal_atual
        p = self.propriedades[self.propriedade_atual]
        val_str = self.obter_valor_formatado(ch, p)
        falar(f"{p}: {val_str}", imediato=True)

    def alterar_valor(self, incremento):
        ch = self.canal_atual
        p = self.propriedades[self.propriedade_atual]
        
        if p in self.parent.canais[ch]:
            if p == "Nome":
                falar("Pressione Enter para editar", imediato=True)
                return
            if p in ["Mute", "Solo"]:
                self.parent.toggle_propriedade_direta(p)
            else:
                max_val = 16384 if p == "Bank" else 127
                self.parent.canais[ch][p] = max(0, min(max_val, self.parent.canais[ch][p] + incremento))
                self.parent.enviar_midi_param(p, self.parent.canais[ch][p], ch)
        else:
            regras = self.parent.casm_rules[ch]
            if p == "NTR":
                atual = regras.get('play_type', 'trans')
                idx = self.ntr_lista.index(atual) if atual in self.ntr_lista else 0
                idx = (idx + incremento) % len(self.ntr_lista)
                regras['play_type'] = self.ntr_lista[idx]
            elif p == "NTT":
                atual = regras.get('ntt_type', 'chord')
                idx = self.ntt_lista.index(atual) if atual in self.ntt_lista else 0
                idx = (idx + incremento) % len(self.ntt_lista)
                regras['ntt_type'] = self.ntt_lista[idx]
            elif p == "Bass":
                regras['ntt_bass'] = not regras.get('ntt_bass', False)
            elif p == "High Key":
                regras['high_key'] = max(0, min(11, regras.get('high_key', 6) + incremento))
            elif p == "Limite Grave":
                regras['note_limit_low'] = max(0, min(127, regras.get('note_limit_low', 0) + incremento))
            elif p == "Limite Agudo":
                regras['note_limit_high'] = max(0, min(127, regras.get('note_limit_high', 127) + incremento))

        self.atualizar_lista_completa()
        self.list_box.SetSelection(ch)
        self.ler_foco_atual()

    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        
        if code == wx.WXK_ESCAPE:
            self.parent.update_mixer_list()
            self.Close()
            return
            
        if code == wx.WXK_SPACE:
            if ctrl: self.parent.OnTogglePause(None)
            else: self.parent.OnTogglePlay(None)
            return

        if code == wx.WXK_LEFT:
            if self.propriedade_atual > 0:
                self.propriedade_atual -= 1
                self.atualizar_lista_completa()
                self.list_box.SetSelection(self.canal_atual)
                self.ler_foco_atual()
            return
            
        if code == wx.WXK_RIGHT:
            if self.propriedade_atual < len(self.propriedades) - 1:
                self.propriedade_atual += 1
                self.atualizar_lista_completa()
                self.list_box.SetSelection(self.canal_atual)
                self.ler_foco_atual()
            return

        if code in [wx.WXK_ADD, wx.WXK_NUMPAD_ADD] or code == ord('='):
            self.alterar_valor(1)
            return
            
        if code in [wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT] or code == ord('-'):
            self.alterar_valor(-1)
            return
            
        if code == wx.WXK_RETURN:
            p = self.propriedades[self.propriedade_atual]
            ch = self.canal_atual
            if p == "Nome":
                dlg = wx.TextEntryDialog(self, f"Nome para o canal {ch+1}:", "Editar Nome", str(self.parent.canais[ch][p]))
                if dlg.ShowModal() == wx.ID_OK:
                    self.parent.canais[ch][p] = dlg.GetValue()
                    self.atualizar_lista_completa()
                    self.list_box.SetSelection(ch)
                    falar(f"Nome alterado para {self.parent.canais[ch][p]}", imediato=True)
                dlg.Destroy()
            elif p not in ["Mute", "Solo", "NTR", "NTT", "Bass"]:
                if p in self.parent.canais[ch]: val_atual = self.parent.canais[ch][p]
                elif p == "High Key": val_atual = self.parent.casm_rules[ch].get('high_key', 6)
                elif p == "Limite Grave": val_atual = self.parent.casm_rules[ch].get('note_limit_low', 0)
                elif p == "Limite Agudo": val_atual = self.parent.casm_rules[ch].get('note_limit_high', 127)

                dlg = wx.TextEntryDialog(self, f"Valor para {p}:", "Editar", str(val_atual))
                if dlg.ShowModal() == wx.ID_OK:
                    try:
                        v = int(dlg.GetValue())
                        if p in self.parent.canais[ch]:
                            max_val = 16384 if p == "Bank" else 127
                            v = max(0, min(max_val, v))
                            self.parent.canais[ch][p] = v
                            self.parent.enviar_midi_param(p, v, ch)
                        else:
                            regras = self.parent.casm_rules[ch]
                            if p == "High Key": regras['high_key'] = max(0, min(11, v))
                            elif p == "Limite Grave": regras['note_limit_low'] = max(0, min(127, v))
                            elif p == "Limite Agudo": regras['note_limit_high'] = max(0, min(127, v))
                        self.atualizar_lista_completa()
                        self.list_box.SetSelection(ch)
                        falar(f"{p} alterado para {v}", imediato=True)
                    except: pass
                dlg.Destroy()
            return
            
        event.Skip()