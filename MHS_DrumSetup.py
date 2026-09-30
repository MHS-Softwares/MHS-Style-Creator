import wx
from MHS_Utils import DRUM_NRPN_PARAMS, DRUM_NRPN_DEFAULTS

class DrumSetupDialog(wx.Dialog):
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title="Yamaha XG Drum Setup (Modo SysEx)", size=(500, 500))
        self.parent = parent
        self.canal_idx = canal_idx
        self.preview_timer = None

        self.drum_params = self.parent.canais[canal_idx].get("DrumParams", {}).copy()
        self.custom_maps = self.parent.canais[canal_idx].get("CustomDrumMap", {}).copy()
        # Guia 3 (NRPN): mesma ideia da Guia 1, mas por NRPN padrão MIDI
        # (control_change 99/98/6) em vez de SysEx exclusiva da Yamaha -
        # funciona em qualquer sintetizador XG/GS, não só no teclado real.
        self.drum_params_nrpn = self.parent.canais[canal_idx].get("DrumParamsNRPN", {}).copy()
        self.removido = False
        
        # Cada nome já traz o & do atalho Alt+letra embutido - assim toda
        # vez que o rótulo é reescrito (SetLabel, ao trocar de peça ou
        # mudar o valor) o atalho continua funcionando, sem precisar
        # lembrar de reincluir o & em cada lugar que reconstrói o texto.
        # Letras escolhidas sem repetir dentro desta aba e evitando o R
        # (já usado pelo botão Remover, sempre visível nas duas abas).
        # Cada item é (endereço, nome, mínimo, máximo) - os 5 últimos
        # (Envio de Variação e o EQ Grave/Agudo por peça, com ganho e
        # frequência) foram achados no Data List oficial do PSR-SX600
        # (MIDI Parameter Change table, DRUM SETUP) e ainda não existiam
        # aqui - a frequência tem faixa própria, mais estreita que 0-127.
        self.sysex_params = [
            (0x02, "&Volume da Peça (Level)", 0, 127), (0x04, "&Panorâmico (Pan)", 0, 127),
            (0x05, "R&everb Send", 0, 127), (0x06, "C&horus Send", 0, 127),
            (0x07, "Envio de Variação (&Insertion)", 0, 127),
            (0x0B, "C&utoff (Filtro)", 0, 127), (0x0C, "Re&ssonância (Filtro)", 0, 127), (0x0D, "&Ataque (Attack)", 0, 127),
            (0x0E, "&Decay 1 (Soco/Corpo)", 0, 127), (0x0F, "Decay &2 (Cauda/Release)", 0, 127),
            (0x00, "Afinação em Semitons (C&oarse)", 0, 127), (0x01, "Afinação Fina em Cents (&Fine)", 0, 127),
            (0x03, "A&grupamento (Alt Group - 0=Desligado)", 0, 127), (0x08, "&Key Assign (0=Single, 1=Multi)", 0, 127),
            (0x20, "Grave da Peça (E&Q Bass)", 0, 127), (0x21, "Agudo da Peça (EQ &Treble)", 0, 127),
            (0x24, "Frequência do Grave (EQ &Bass)", 4, 40), (0x25, "Frequência do Agudo (Treb&le)", 28, 58),
        ]
        self.sliders = {}
        self.labels = {}
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(self)
        
        # --- GUIA 1: EDIÇÃO DE PARÂMETROS (SYSEX PURO) ---
        self.tab_params = wx.Panel(self.notebook)
        sz_params = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_nota = wx.StaticText(self.tab_params, label="Peça (&Nota) a ser editada:")
        sz_params.Add(self.lbl_nota, 0, wx.ALL, 5)
        
        self.sl_nota = wx.Slider(self.tab_params, value=38, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça a ser editada")
        sz_params.Add(self.sl_nota, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_nota.Bind(wx.EVT_SLIDER, self.on_nota_change)
        
        # Padrão de fábrica só pras 2 frequências de EQ (faixa própria, mais
        # estreita que o 64 central usado no resto) - conferido no Data
        # List oficial (0x24=0x0C, 0x25=0x36).
        self._padrao_por_param = {0x24: 12, 0x25: 54}
        for param_id, name, min_v, max_v in self.sysex_params:
            init_val = self.drum_params.get((38, param_id), self._padrao_por_param.get(param_id, 64))
            lbl = wx.StaticText(self.tab_params, label=f"{name}: {init_val}")
            sz_params.Add(lbl, 0, wx.ALL, 2)

            sl = wx.SpinCtrl(self.tab_params, value=str(init_val), min=min_v, max=max_v, name=name)
            sz_params.Add(sl, 0, wx.EXPAND | wx.ALL, 2)
            
            sl.Bind(wx.EVT_SPINCTRL, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change(e, p, s, l))
            sl.Bind(wx.EVT_TEXT, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change(e, p, s, l))
            
            self.sliders[param_id] = sl
            self.labels[param_id] = lbl
            
        self.tab_params.SetSizer(sz_params)
        
        # --- GUIA 2: MAPEDADOR AVANÇADO ---
        self.tab_map = wx.Panel(self.notebook)
        sz_map = wx.BoxSizer(wx.VERTICAL)
        
        lbl_aviso = wx.StaticText(self.tab_map, label="Mapeador de Bateria (Puxar peças de outros Kits do SX600)")
        sz_map.Add(lbl_aviso, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        # Valor inicial de verdade da Guia 2 (peça 38, o padrão) - lido de
        # self.custom_maps ANTES de construir os widgets, e passado direto
        # no parâmetro `value=` de cada um (nunca via `.SetValue()` depois
        # de já estarem com o evento ligado - ver "Como reverter"/histórico
        # desta correção: uma tentativa anterior usou `.SetValue()` pós-
        # construção e isso disparou on_map_param_change em cascata, com
        # estados intermediários, quebrando o Drum Setup de vez). Sem isso,
        # os 3 controles nasciam com os valores de fábrica (16256/0/38),
        # nunca com o mapeamento REAL já salvo pra peça 38 - e como
        # get_values() sempre comita o que estiver nos controles no
        # instante do OK (rede de segurança de _comitar_mapeamento_atual),
        # confirmar a tela SEM NUNCA tocar na Guia 2 sobrescrevia o
        # mapeamento real da peça 38 com Patch=0 - confirmado reproduzindo
        # com o arquivo real do Michel (Country MHS.sty): abrir e fechar o
        # Drum Setup sem editar nada já derrubava o Patch=91 da peça 38.
        _peca_inicial = 38
        if _peca_inicial in self.custom_maps:
            _m_inicial = self.custom_maps[_peca_inicial]
            _bank_inicial = _m_inicial['bank']
            _patch_inicial = _m_inicial['patch']
            _dest_inicial = _m_inicial['dest_note']
        else:
            _bank_inicial = self.parent.canais[canal_idx].get("Bank", 16256)
            _patch_inicial = self.parent.canais[canal_idx].get("Patch", 0)
            _dest_inicial = _peca_inicial

        self.lbl_map_orig = wx.StaticText(self.tab_map, label="1. Peça (&Nota) Alvo a ser trocada:")
        sz_map.Add(self.lbl_map_orig, 0, wx.ALL, 5)
        self.sl_map_orig = wx.Slider(self.tab_map, value=_peca_inicial, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça Alvo")
        sz_map.Add(self.sl_map_orig, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_bank = wx.StaticText(self.tab_map, label="2. &Banco do Kit Doador (ex: 16256):")
        sz_map.Add(self.lbl_map_bank, 0, wx.ALL, 5)
        self.sp_map_bank = wx.SpinCtrl(self.tab_map, value=str(_bank_inicial), min=0, max=16384, name="Banco do Kit Doador")
        sz_map.Add(self.sp_map_bank, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_patch = wx.StaticText(self.tab_map, label="3. Pa&tch do Kit Doador (0 a 127):")
        sz_map.Add(self.lbl_map_patch, 0, wx.ALL, 5)
        self.sl_map_patch = wx.SpinCtrl(self.tab_map, value=str(_patch_inicial), min=0, max=127, name="Patch do Kit Doador")
        sz_map.Add(self.sl_map_patch, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_dest = wx.StaticText(self.tab_map, label="4. Peça do Kit &Doador (O novo som):")
        sz_map.Add(self.lbl_map_dest, 0, wx.ALL, 5)
        self.sl_map_dest = wx.Slider(self.tab_map, value=_dest_inicial, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça do Kit Doador")
        sz_map.Add(self.sl_map_dest, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_aplicar_custom = wx.Button(self.tab_map, label="&Aplicar Mapeamento desta Peça")
        sz_map.Add(self.btn_aplicar_custom, 0, wx.ALL | wx.ALIGN_CENTER, 15)
        self.btn_aplicar_custom.Bind(wx.EVT_BUTTON, self.on_aplicar_custom)
        
        self.tab_map.SetSizer(sz_map)

        # --- GUIA 3: EDIÇÃO VIA NRPN (PADRÃO MIDI, NÃO SÓ YAMAHA) ---
        # Mesma ideia da Guia 1 (uma peça de cada vez, um slider por
        # parâmetro), mas gravando NRPN puro (control_change 99=parâmetro,
        # 98=peça, 6=valor) em vez da SysEx `43 1n 4C` - funciona em
        # qualquer sintetizador XG/GS (é o mesmo protocolo que o Sonar usava
        # no Event List em 2011), não só no teclado Yamaha real. Uma
        # ScrolledWindow (a Guia 1 não tem - 15 parâmetros não cabem sem
        # rolar, mesmo com a janela no tamanho normal).
        self.tab_nrpn = wx.Panel(self.notebook)
        sz_nrpn_outer = wx.BoxSizer(wx.VERTICAL)
        scr_nrpn = wx.ScrolledWindow(self.tab_nrpn, style=wx.VSCROLL)
        scr_nrpn.SetScrollRate(0, 20)
        sz_nrpn = wx.BoxSizer(wx.VERTICAL)

        self.lbl_nota_nrpn = wx.StaticText(scr_nrpn, label="Peça (&Nota) a ser editada:")
        sz_nrpn.Add(self.lbl_nota_nrpn, 0, wx.ALL, 5)

        self.sl_nota_nrpn = wx.Slider(scr_nrpn, value=38, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça a ser editada (NRPN)")
        sz_nrpn.Add(self.sl_nota_nrpn, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_nota_nrpn.Bind(wx.EVT_SLIDER, self.on_nota_change_nrpn)

        self.sliders_nrpn = {}
        self.labels_nrpn = {}
        for param_id, name, min_v, max_v in DRUM_NRPN_PARAMS:
            init_val = self.drum_params_nrpn.get((38, param_id), DRUM_NRPN_DEFAULTS.get(param_id, 64))
            lbl = wx.StaticText(scr_nrpn, label=f"{name}: {init_val}")
            sz_nrpn.Add(lbl, 0, wx.ALL, 2)

            sl = wx.SpinCtrl(scr_nrpn, value=str(init_val), min=min_v, max=max_v, name=name)
            sz_nrpn.Add(sl, 0, wx.EXPAND | wx.ALL, 2)

            sl.Bind(wx.EVT_SPINCTRL, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change_nrpn(e, p, s, l))
            sl.Bind(wx.EVT_TEXT, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change_nrpn(e, p, s, l))

            self.sliders_nrpn[param_id] = sl
            self.labels_nrpn[param_id] = lbl

        scr_nrpn.SetSizer(sz_nrpn)
        sz_nrpn_outer.Add(scr_nrpn, 1, wx.EXPAND)
        self.tab_nrpn.SetSizer(sz_nrpn_outer)

        self.notebook.AddPage(self.tab_params, "Edição e Filtros (SysEx)")
        self.notebook.AddPage(self.tab_map, "Montagem de Kit (Custom)")
        self.notebook.AddPage(self.tab_nrpn, "Edição via NRPN (Padrão MIDI)")
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Mesma ideia do "Remover Efeito Existente" da Variation - apaga TODA
        # a edição de Drum Setup deste canal (parâmetros por peça e
        # mapeamentos de kit), de uma vez, em vez de precisar zerar peça por
        # peça na mão.
        self.btn_remover = wx.Button(self, label="&Remover Toda a Configuração de Bateria deste Canal")
        main_sizer.Add(self.btn_remover, 0, wx.EXPAND | wx.ALL, 5)
        self.btn_remover.Bind(wx.EVT_BUTTON, self.on_remover)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
        self.Layout()
        
        self.sl_map_orig.Bind(wx.EVT_SLIDER, self.on_map_orig_change)
        self.sp_map_bank.Bind(wx.EVT_SPINCTRL, self.on_map_param_change)
        self.sp_map_bank.Bind(wx.EVT_TEXT, self.on_map_param_change)
        
        self.sl_map_patch.Bind(wx.EVT_SPINCTRL, self.on_map_param_change)
        self.sl_map_patch.Bind(wx.EVT_TEXT, self.on_map_param_change)
        
        self.sl_map_dest.Bind(wx.EVT_SLIDER, self.on_map_param_change)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        self.update_nota_label()
        self.update_map_labels()
        self.update_nota_label_nrpn()

        wx.CallLater(100, self.sl_nota.SetFocus)

    def update_map_labels(self):
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        dest = self.sl_map_dest.GetValue()
        
        ch_bank = self.parent.canais[self.canal_idx].get("Bank", 16256)
        ch_patch = self.parent.canais[self.canal_idx].get("Patch", 0)
        self.lbl_map_orig.SetLabel(f"1. Peça (&Nota) Alvo: {self.parent.obter_nome_peca_bateria(ch_bank, ch_patch, orig)} ({orig})")
        self.lbl_map_bank.SetLabel(f"2. &Banco do Kit Doador: {b}")

        nome_kit = f"Kit {p}"
        if hasattr(self.parent, 'ins_db'):
            nome_kit = self.parent.ins_db.get(b, {}).get(p, nome_kit)

        self.lbl_map_patch.SetLabel(f"3. Pa&tch do Kit Doador: {nome_kit} ({p})")
        self.lbl_map_dest.SetLabel(f"4. Peça do Kit &Doador: {self.parent.obter_nome_peca_bateria(b, p, dest)} ({dest})")

    def on_map_orig_change(self, event):
        orig = self.sl_map_orig.GetValue()
        from MHS_Utils import falar_status
        ch_bank = self.parent.canais[self.canal_idx].get("Bank", 16256)
        ch_patch = self.parent.canais[self.canal_idx].get("Patch", 0)
        falar_status(f"Alvo: {self.parent.obter_nome_peca_bateria(ch_bank, ch_patch, orig)} ({orig})", imediato=True)

        if orig in self.custom_maps:
            m = self.custom_maps[orig]
            self.sp_map_bank.SetValue(m['bank'])
            self.sl_map_patch.SetValue(m['patch'])
            self.sl_map_dest.SetValue(m['dest_note'])
        else:
            ch = self.canal_idx
            b_atual = self.parent.canais[ch].get("Bank", 16256)
            p_atual = self.parent.canais[ch].get("Patch", 0)
            self.sp_map_bank.SetValue(b_atual)
            self.sl_map_patch.SetValue(p_atual)
            self.sl_map_dest.SetValue(orig)

        self.update_map_labels()
        self.play_preview_direct(orig)

    def _comitar_mapeamento_atual(self):
        # Grava de verdade (em self.custom_maps, o que get_values() devolve
        # pro OK) o mapeamento que está nos controles AGORA - a Guia 1 já
        # grava sozinha a cada mudança de valor (on_param_change); esta guia
        # só gravava quando alguém clicava o botão "Aplicar Mapeamento", e
        # o preview ao vivo (que já soa certo ao mexer no slider) mascarava
        # isso - dava pra ouvir tudo certo, clicar OK sem nunca ter clicado
        # o botão, e a troca de peça sumia (só o que a Guia 1 mexeu ficava).
        # Chamado a cada mudança de valor aqui também, pra ficar do mesmo
        # jeito que a Guia 1.
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        d = self.sl_map_dest.GetValue()
        self.custom_maps[orig] = {'bank': b, 'patch': p, 'dest_note': d}
        self.parent.canais[self.canal_idx]["CustomDrumMap"] = self.custom_maps

    def on_aplicar_custom(self, event):
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        d = self.sl_map_dest.GetValue()

        self._comitar_mapeamento_atual()

        from MHS_Utils import falar_status

        porta = getattr(self.parent, 'midi_out', None)
        if not porta:
            falar_status("Aviso: nenhuma porta MIDI de saída está conectada agora. O SysEx não foi enviado.", imediato=True)
        else:
            import mido
            ch = self.canal_idx
            part_byte = 0x30 if ch == 9 else 0x31
            b_msb = min(127, b // 128)
            syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig, 0x70, b_msb, b % 128, p, d, 0xF7]
            try:
                porta.send(mido.Message.from_bytes(syx_data))
                falar_status("SysEx de mapeamento enviado com sucesso.", imediato=True)
            except Exception as e:
                falar_status(f"Erro ao enviar SysEx: {e}", imediato=True)
            
        self.play_preview_direct(orig)
        
        falar_status(f"Mapeamento aplicado. Testando a peça {self.parent.obter_nome_peca_bateria(b, p, orig)}.", imediato=True)
    def play_preview_map(self):
        if not self.parent.midi_out: return
        import mido
        import threading
        
        if getattr(self, 'preview_timer', None): 
            self.preview_timer.cancel()
            
        ch = self.canal_idx
        b_atual = self.parent.canais[ch].get("Bank", 16256)
        p_atual = self.parent.canais[ch].get("Patch", 0)
        
        b_novo = self.sp_map_bank.GetValue()
        p_novo = self.sl_map_patch.GetValue()
        nota_nova = self.sl_map_dest.GetValue()
        
        try:
            self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=123, value=0))
            
            self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=0, value=b_novo // 128))
            self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=32, value=b_novo % 128))
            self.parent.midi_out.send(mido.Message('program_change', channel=ch, program=p_novo))
            self.parent.midi_out.send(mido.Message('note_on', channel=ch, note=nota_nova, velocity=100))
            
            def restaurar_e_parar():
                if getattr(self.parent, 'midi_out', None):
                    try:
                        self.parent.midi_out.send(mido.Message('note_off', channel=ch, note=nota_nova, velocity=0))
                        self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=0, value=b_atual // 128))
                        self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=32, value=b_atual % 128))
                        self.parent.midi_out.send(mido.Message('program_change', channel=ch, program=p_atual))
                    except: pass
                    
            self.preview_timer = threading.Timer(0.4, restaurar_e_parar)
            self.preview_timer.start()
        except: pass

    def update_nota_label(self):
        v = self.sl_nota.GetValue()
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        name = self.parent.obter_nome_peca_bateria(b, p, v)
        self.lbl_nota.SetLabel(f"Peça (&Nota) a ser editada: {name}")

    def on_nota_change(self, event):
        note = self.sl_nota.GetValue()
        self.update_nota_label()
        
        for param_id, slider in self.sliders.items():
            val = self.drum_params.get((note, param_id), self._padrao_por_param.get(param_id, 64))
            slider.SetValue(val)
            name = next(n for c, n, mn, mx in self.sysex_params if c == param_id)
            self.labels[param_id].SetLabel(f"{name}: {val}")
            
        self.play_preview_direct(note)
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        from MHS_Utils import falar_status
        name = self.parent.obter_nome_peca_bateria(b, p, note)
        falar_status(f"{name} ({note})", imediato=True)

    def on_param_change(self, event, param_id, slider, label):
        try:
            val = int(slider.GetValue()) 
        except ValueError:
            return 
            
        note = self.sl_nota.GetValue()
        
        if self.drum_params.get((note, param_id)) == val:
            return
        
        self.drum_params[(note, param_id)] = val
        self.parent.canais[self.canal_idx]["DrumParams"] = self.drum_params
        
        name = next(n for c, n, mn, mx in self.sysex_params if c == param_id)
        label.SetLabel(f"{name}: {val}")
        
        self.enviar_sysex_combo(note)
        self.play_preview_direct(note)

    def update_nota_label_nrpn(self):
        v = self.sl_nota_nrpn.GetValue()
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        name = self.parent.obter_nome_peca_bateria(b, p, v)
        self.lbl_nota_nrpn.SetLabel(f"Peça (&Nota) a ser editada: {name}")

    def on_nota_change_nrpn(self, event):
        note = self.sl_nota_nrpn.GetValue()
        self.update_nota_label_nrpn()

        for param_id, slider in self.sliders_nrpn.items():
            val = self.drum_params_nrpn.get((note, param_id), DRUM_NRPN_DEFAULTS.get(param_id, 64))
            slider.SetValue(val)
            name = next(n for c, n, mn, mx in DRUM_NRPN_PARAMS if c == param_id)
            self.labels_nrpn[param_id].SetLabel(f"{name}: {val}")

        self.play_preview_direct(note)
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        from MHS_Utils import falar_status
        name = self.parent.obter_nome_peca_bateria(b, p, note)
        falar_status(f"{name} ({note})", imediato=True)

    def on_param_change_nrpn(self, event, param_id, slider, label):
        try:
            val = int(slider.GetValue())
        except ValueError:
            return

        note = self.sl_nota_nrpn.GetValue()

        if self.drum_params_nrpn.get((note, param_id)) == val:
            return

        self.drum_params_nrpn[(note, param_id)] = val
        self.parent.canais[self.canal_idx]["DrumParamsNRPN"] = self.drum_params_nrpn

        name = next(n for c, n, mn, mx in DRUM_NRPN_PARAMS if c == param_id)
        label.SetLabel(f"{name}: {val}")

        self.enviar_nrpn_combo(note)
        self.play_preview_direct(note)

    def enviar_nrpn_combo(self, note):
        # NRPN puro: 99=MSB (o parâmetro), 98=LSB (a peça/nota), 6=valor. O
        # Data List oficial diz que a LSB do Data Entry (CC38) é ignorada
        # pra esse bloco - só manda os 3 CCs de verdade.
        if not self.parent.midi_out: return
        import mido
        ch = self.canal_idx
        for (n, p_id), val in self.drum_params_nrpn.items():
            if n == note:
                for msg in (mido.Message('control_change', channel=ch, control=99, value=p_id),
                            mido.Message('control_change', channel=ch, control=98, value=note),
                            mido.Message('control_change', channel=ch, control=6, value=val)):
                    try: self.parent.midi_out.send(msg)
                    except: pass

    def on_map_param_change(self, event):
        try:
            b = int(self.sp_map_bank.GetValue())
            p = int(self.sl_map_patch.GetValue())
            d = int(self.sl_map_dest.GetValue())
        except ValueError:
            return
            
        estado_atual = (b, p, d)
        if getattr(self, 'ultimo_estado_map', None) == estado_atual:
            return
        self.ultimo_estado_map = estado_atual
        
        from MHS_Utils import falar_status
        obj = event.GetEventObject()
        if obj == self.sp_map_bank:
            falar_status(f"Banco Doador: {b}", imediato=True)
        elif obj == self.sl_map_patch:
            nome_kit = f"Kit {p}"
            if hasattr(self.parent, 'ins_db'):
                nome_kit = self.parent.ins_db.get(b, {}).get(p, nome_kit)
            falar_status(f"Patch: {nome_kit} ({p})", imediato=True)
        elif obj == self.sl_map_dest:
            falar_status(f"Nova Peça: {self.parent.obter_nome_peca_bateria(b, p, d)} ({d})", imediato=True)

        self.update_map_labels()
        # NÃO comita aqui - só o botão "&Aplicar Mapeamento desta Peça"
        # comita de verdade (mesmo comportamento da versão comprovada,
        # antes de uma tentativa de "rede de segurança" que comitava a
        # cada mudança de valor e no próprio OK - isso fazia o Drum Setup
        # sobrescrever o mapeamento de QUALQUER peça, mesmo sem editar
        # nada, só de abrir e fechar a tela). Só o preview ao vivo mesmo,
        # pra poder ouvir a peça antes de decidir aplicar de verdade.
        self.play_preview_map()

    def enviar_sysex_combo(self, note):
        if not self.parent.midi_out: return
        import mido
        ch = self.canal_idx
        part_byte = 0x30 if ch == 9 else 0x31
        
        if note in self.custom_maps:
            m = self.custom_maps[note]
            syx_map = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, 0x70, m['bank']//128, m['bank']%128, m['patch'], m['dest_note'], 0xF7]
            try: self.parent.midi_out.send(mido.Message.from_bytes(syx_map))
            except: pass
            
        for (n, p_id), val in self.drum_params.items():
            if n == note:
                syx_param = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, p_id, val, 0xF7]
                try: self.parent.midi_out.send(mido.Message.from_bytes(syx_param))
                except: pass

    def play_preview_direct(self, note):
        if not self.parent.midi_out: return
        import mido
        import threading
        
        if getattr(self, 'preview_timer', None): 
            self.preview_timer.cancel()
        
        ch = self.canal_idx
        
        try:
            self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=123, value=0))
            self.parent.midi_out.send(mido.Message('note_on', channel=ch, note=note, velocity=100))
            
            def stop_note():
                if getattr(self.parent, 'midi_out', None):
                    try: self.parent.midi_out.send(mido.Message('note_off', channel=ch, note=note, velocity=0))
                    except: pass
                    
            self.preview_timer = threading.Timer(0.4, stop_note)
            self.preview_timer.start()
        except: pass

    def handle_midi_in(self, msg):
        if not getattr(self.parent, 'midi_out', None): return
        import mido
        
        if msg.type in ['note_on', 'note_off', 'polytouch']:
            is_hit = (msg.type == 'note_on' and msg.velocity > 0)
            orig_note = msg.note
            ch = self.canal_idx
            
            if is_hit:
                self.enviar_sysex_combo(orig_note)
                self.enviar_nrpn_combo(orig_note)

            out_msg = msg.copy(channel=ch)
            try: self.parent.midi_out.send(out_msg)
            except: pass

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        
        if code == wx.WXK_SPACE:
            if ctrl: self.parent.OnTogglePause(None)
            else: self.parent.OnTogglePlay(None)
            # O arquivo ainda não tem a edição desta tela (só é gravado de
            # verdade no OK) - o Play, tocando o arquivo do jeito que ele
            # ainda está, manda o Banco/Patch e o SysEx por peça ANTIGOS
            # logo na entrada da seção, o que reseta a peça pro padrão do
            # kit. Reenviar por cima (com os valores novos) precisa chegar
            # DEPOIS desse envio antigo (senão o antigo reset o que acabou
            # de chegar) mas ANTES da primeira nota - como os dois lados
            # dessa corrida acontecem quase juntos, uma tentativa só (150ms)
            # às vezes perdia a primeira batida quando ela caía bem no
            # começo da seção. Várias tentativas num intervalo curto cobrem
            # essa margem sem apostar tudo num único palpite de tempo.
            for atraso in (20, 60, 150):
                wx.CallLater(atraso, self.reapply_preview_state)
            return

        focus = wx.Window.FindFocus()
        if focus:
            spin = focus if isinstance(focus, wx.SpinCtrl) else focus.GetParent()
            
            if isinstance(spin, wx.SpinCtrl):
                if code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN]:
                    val = spin.GetValue()
                    min_val = spin.GetMin()
                    max_val = spin.GetMax()
                    
                    step = 10 if max_val <= 127 else 1000 
                    
                    if code == wx.WXK_HOME:
                        novo_val = max_val  
                    elif code == wx.WXK_END:
                        novo_val = min_val  
                    elif code == wx.WXK_PAGEUP:
                        novo_val = min(max_val, val + step)
                    elif code == wx.WXK_PAGEDOWN:
                        novo_val = max(min_val, val - step)
                        
                    spin.SetValue(int(novo_val))
                    
                    evt = wx.CommandEvent(wx.wxEVT_TEXT, spin.GetId())
                    evt.SetEventObject(spin)
                    spin.GetEventHandler().ProcessEvent(evt)
                    
                    return 

        event.Skip()
    def reapply_preview_state(self):
        if not self.parent.midi_out: return
        import mido
        ch = self.canal_idx
        part_byte = 0x30 if ch == 9 else 0x31
        
        for orig_note, m in self.custom_maps.items():
            syx_map = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig_note, 0x70, m['bank']//128, m['bank']%128, m['patch'], m['dest_note'], 0xF7]
            try: self.parent.midi_out.send(mido.Message.from_bytes(syx_map))
            except: pass

        for (note, param_id), val in self.drum_params.items():
            syx_param = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, param_id, val, 0xF7]
            try: self.parent.midi_out.send(mido.Message.from_bytes(syx_param))
            except: pass

        for (note, param_id), val in self.drum_params_nrpn.items():
            for msg in (mido.Message('control_change', channel=ch, control=99, value=param_id),
                        mido.Message('control_change', channel=ch, control=98, value=note),
                        mido.Message('control_change', channel=ch, control=6, value=val)):
                try: self.parent.midi_out.send(msg)
                except: pass

    def on_remover(self, event):
        from MHS_Utils import falar_status
        if not self.drum_params and not self.custom_maps and not self.drum_params_nrpn:
            falar_status("Este canal não tem nenhuma configuração de bateria personalizada.", imediato=True)
            return

        self.drum_params = {}
        self.custom_maps = {}
        self.drum_params_nrpn = {}
        self.parent.canais[self.canal_idx]["DrumParams"] = {}
        self.parent.canais[self.canal_idx]["CustomDrumMap"] = {}
        self.parent.canais[self.canal_idx]["DrumParamsNRPN"] = {}

        # Reseta ao vivo pra você já ouvir o kit voltando ao padrão de
        # fábrica, sem precisar fechar e reabrir. All Sound Off sozinho não
        # bastava - só limpa as notas que já estavam soando, mas não desfaz
        # a afinação/pan/nível por nota que o SysEx de Drum Setup já tinha
        # aplicado no kit. Reenviar o mesmo Banco+Patch é o que realmente
        # reseta isso - selecionar o kit de novo (mesmo que seja o mesmo)
        # é o próprio gatilho de reset que causou todo o problema original
        # do Drum Setup "voltando ao padrão sozinho" - aqui é exatamente
        # esse comportamento que a gente quer provocar de propósito.
        if getattr(self.parent, 'midi_out', None):
            import mido
            ch = self.canal_idx
            try:
                self.parent.midi_out.send(mido.Message('control_change', channel=ch, control=123, value=0))
            except: pass
            c = self.parent.canais[ch]
            try:
                self.parent.enviar_midi_param("Bank", c["Bank"], ch)
                self.parent.enviar_midi_param("Patch", c["Patch"], ch)
            except: pass

        self.removido = True
        falar_status("Toda a configuração de bateria deste canal foi removida.", imediato=True)
        self.EndModal(wx.ID_OK)

    def get_values(self):
        # SEM rede de segurança aqui - devolve exatamente o que já foi
        # comitado de verdade (só pelo botão "Aplicar Mapeamento desta
        # Peça", ver on_aplicar_custom). Uma versão anterior comitava aqui
        # incondicionalmente (o que estivesse nos controles da Guia 2 no
        # instante do OK) - como o valor padrão dos controles ao ABRIR a
        # tela é sempre a peça 38 (o valor inicial fixo de sl_map_orig),
        # confirmar a tela SEM NUNCA ter tocado na Guia 2 sobrescrevia o
        # mapeamento real da peça 38 com o que estivesse ali (às vezes o
        # valor certo, às vezes não) - confirmado com o arquivo real do
        # Michel que só abrir e fechar já derrubava a peça 38. Restaurado
        # pro comportamento comprovado (cópia de backup de 07/09): só o
        # que o usuário confirma explicitamente pelo botão é gravado.
        return self.drum_params, self.custom_maps, self.drum_params_nrpn