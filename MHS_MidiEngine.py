import wx
import mido
import time
import threading
from MHS_Utils import (
    TOTAL_CANAIS, CANAL_METRONOMO, NOTA_METRONOMO_FORTE,
    NOTA_METRONOMO_FRACA, CC_ALL_NOTES_OFF, CC_SUSTAIN,
    CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION,
    CC_REVERB, CC_CHORUS, CC_RESET_ALL, CC_LOCAL_CONTROL, REV_MSB_LIST, CHO_MSB_LIST,
    OFFSETS_VAR_2BYTES, OFFSETS_VAR_1BYTE,
    OFFSETS_REV_PARAMS, OFFSETS_CHO_PARAMS, VARIATION_EFEITOS_LIST,
    detune_combinar
)

# --- Captura de timbre/DSP do teclado ---
# Endereços do efeito de Inserção XG (43 10 4C 03 nn PP) -> índice de
# parâmetro 0-15 (params 1-10 em 0x02-0x0B, 11-16 em 0x20-0x25).
_INS_ADDR_IDX = {a: i for i, a in enumerate(
    [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25])}
# CC de forma de onda -> endereço Multi Part equivalente. Conferido byte a
# byte contra o Data List oficial do PSR-SX600 (MIDI Parameter Change table,
# MULTI PART, pág. 65) - a tabela antiga (0x60/0x61/0x63/0x64/0x66/0x20/0x21/
# 0x22, "a conferir no hardware") apontava pros endereços ERRADOS, o mesmo
# bug já achado e corrigido no MHS MIDI Sequencer (causava o timbre
# "distorcido" ao salvar/reabrir - o CC76/Vibrato Rate ia parar em "MW LFO
# PMOD Depth" (0x20) em vez de "Vibrato Rate" (0x15) de verdade). Nunca
# tinha sido replicado aqui no Style Creator.
_CC_SOUND_MP = {74: 0x18, 71: 0x19, 73: 0x1A, 75: 0x1B, 72: 0x1C, 76: 0x15, 77: 0x16, 78: 0x17}
_NRPN_SOUND_MP = {(1, 0x08): 0x15, (1, 0x09): 0x16, (1, 0x0A): 0x17, (1, 0x20): 0x18, (1, 0x21): 0x19,
                  (1, 0x63): 0x1A, (1, 0x64): 0x1B, (1, 0x66): 0x1C}
# Endereços Multi Part que NÃO vão pro dict VoiceCreator (já têm dono no
# modelo, ou não são parâmetro de voz de verdade) - mesma lista conferida
# contra o Data List oficial usada no MHS MIDI Sequencer: 0x00=Element
# Reserve (gerência interna de polifonia); 0x04-0x07=Rcv Channel/Mono-Poly
# Mode/Key Assign/Part Mode (config de PARTE, não de SOM); 0x0A é o 2º byte
# do Detune (nunca vira entrada própria - ver detune_combinar/detune_separar,
# o valor combinado mora só na chave 0x09); 0x14=Variation Send Level (envio
# pro efeito de Inserção/Variation, tratado à parte); 0x30-0x3F=flags "Rcv X
# OFF/ON".
_MP_RESERVADOS = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0A, 0x0B, 0x0E, 0x12,
    0x13, 0x14, 0x72, 0x73,
} | set(range(0x30, 0x40))

class MidiEngine:
    def __init__(self, main_frame):
        self.main = main_frame
        self.midi_out = None
        self.midi_ins = []
        # Teste pedido pelo Michel: porta MIDI separada só pro metrônomo
        # (continua no canal 10, mas pode ir pra outro dispositivo). None =
        # usa self.midi_out normalmente, igual sempre foi.
        self.midi_out_metronomo = None


        # Estados de Transporte
        self.playing = False
        self.paused = False
        self.gravando = False
        self.use_metronome = False

        # Sincronização
        self.force_reload_loop = False
        self.anchor_tick = 0
        self.current_accumulated_ticks = 0
        self.recorded_events = []
        # Geração da thread de reprodução - ver start_worker/midi_worker.
        # Confirmado com o Michel: sem isso, um Play/Stop (ou auto-punch)
        # rápido demais podia criar uma thread midi_worker NOVA antes da
        # ANTIGA notar que self.playing virou False (a flag é compartilhada
        # e pode oscilar mais rápido do que o Python agenda a outra thread
        # pra checar) - as duas ficavam rodando ao mesmo tempo, brigando
        # pelo GIL, e cada nova sessão de gravação piorava mais (medido:
        # até 25 SEGUNDOS de atraso pra thread nova sequer começar a rodar,
        # de tanta zumbi acumulada). Cada thread carrega o número da sua
        # própria geração e só continua rodando enquanto for a mais atual.
        self._play_generation = 0
        self.worker_thread = None
        
        # Interatividade
        self.active_keys = set()
        self.live_physical_keys = set()
        self.chord_timer = None
        self._auto_punching = False

        # Captura de timbre/DSP do teclado (troca de voz pela MIDI IN).
        self._captura_dsp = None
        self._captura_dsp_timer = None
        self._dsp_teclado_chs = set()   # canais cuja Variation foi roteada pelo teclado
        self._dsp_teclado_vc = {}       # canal -> set(endereços Multi Part que o teclado mandou)

    def setup_midi_in(self):
        # Uma ou mais portas de entrada ao mesmo tempo - igual ao MIDI
        # Sequencer (checkboxes na tela de Configurações, "midi_in" agora
        # é uma LISTA de nomes salvos). Uma string solta (config antigo,
        # de antes desta mudança) ainda é aceita, virando uma lista de 1.
        for porta in self.midi_ins:
            try: porta.close()
            except Exception: pass
        self.midi_ins.clear()

        nomes_in = self.main.config.get("midi_in")
        if isinstance(nomes_in, str):
            nomes_in = [nomes_in] if nomes_in and nomes_in != "Sem portas" else []
        elif not nomes_in:
            nomes_in = []

        from MHS_Utils import achar_porta_certa
        disponiveis = mido.get_input_names()
        for nome_in in nomes_in:
            try:
                porta_certa = achar_porta_certa(nome_in, disponiveis)
                if porta_certa:
                    self.midi_ins.append(mido.open_input(porta_certa, callback=self.midi_in_handler))
            except Exception:
                pass

    def silence_channel(self, channel):
        if self.midi_out:
            try:
                self.midi_out.send(mido.Message('control_change', channel=channel, control=CC_ALL_NOTES_OFF, value=0))
                self.midi_out.send(mido.Message('control_change', channel=channel, control=CC_SUSTAIN, value=0))
            except Exception: 
                pass

    def panic_reset(self):
        if self.midi_out:
            for ch in range(TOTAL_CANAIS):
                try:
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_ALL_NOTES_OFF, value=0))
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_SUSTAIN, value=0))
                except Exception:
                    pass

    def set_local_control(self, ligado):
        # Manda o Local Control (CC 122) pro estado pedido, sem depender do
        # que estava antes - usado tanto pelo F8 (que alterna) quanto pelo
        # liga/desliga automático ao abrir/fechar o programa.
        self.local_control_on = ligado
        val = 127 if ligado else 0
        if self.midi_out:
            for ch in range(TOTAL_CANAIS):
                try:
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_LOCAL_CONTROL, value=val))
                except Exception:
                    pass
        return self.local_control_on

    def toggle_local_control(self):
        # Local Control (CC 122) - trazido do MHS MIDI Sequencer (tecla F8).
        # Desliga o "som direto" do teclado (o instrumento continua
        # recebendo e tocando via MIDI normalmente, só para de soar quando
        # tocado nas teclas físicas) - útil pra quem quer ouvir só o que o
        # Style Creator está mandando, sem o próprio teclado se metendo.
        return self.set_local_control(not getattr(self, 'local_control_on', True))

    def reset_fisico_teclado(self):
        # Zeramento de verdade do hardware - trazido do MHS MIDI Sequencer.
        # Diferente do panic_reset (só apaga nota presa ao parar a
        # reprodução), esse aqui é pra usar antes de trocar de aba / abrir
        # outro estilo: sem isso, resquício de Bank/Patch/CC do ritmo
        # anterior podia vazar pro que acabou de ser carregado.
        self.panic_reset()
        if not self.midi_out:
            return
        try:
            self.midi_out.send(mido.Message('sysex', data=(0x7E, 0x7F, 0x09, 0x01)))
            # A mesma pausa que send_initial_setup já usa depois do GM Reset -
            # sem ela, o SysEx de Part Mode que vem logo depois (bateria nos
            # canais 9/10) chegava cedo demais e se perdia.
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00)))
            # O mesmo respiro que o próprio SX600 precisa entre o GM Reset e
            # o XG System On - sem ele, a troca de aba engasgava.
            time.sleep(0.25)
        except Exception:
            pass
        for ch in range(TOTAL_CANAIS):
            try:
                self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_RESET_ALL, value=0))
            except Exception:
                pass

    def enviar_midi_param(self, prop, val, canal):
        if not self.midi_out: return
        if prop == "Bank":
            msb, lsb = val // 128, val % 128
            self.midi_out.send(mido.Message('control_change', channel=canal, control=CC_BANK_MSB, value=msb))
            self.midi_out.send(mido.Message('control_change', channel=canal, control=CC_BANK_LSB, value=lsb))
        elif prop == "Patch":
            self.midi_out.send(mido.Message('program_change', channel=canal, program=val))
        elif prop in ["Volume", "Pan", "Expression", "Reverb", "Chorus"]:
            cc_map = {"Volume": CC_VOLUME, "Pan": CC_PAN, "Expression": CC_EXPRESSION, "Reverb": CC_REVERB, "Chorus": CC_CHORUS}
            self.midi_out.send(mido.Message('control_change', channel=canal, control=cc_map[prop], value=val))
        elif prop in ["Grave", "Agudo"]:
            # Equalização de 2 bandas do Multi Part (achado comparando um
            # ritmo original com a edição de um cliente/programador
            # terceiro: "Grave" = Bass Gain, "Agudo" = Treble Gain, cada um
            # por canal - 64 é o centro/neutro, igual o Pan). Vai por SysEx
            # Multi Part, não por CC (não existe CC padrão pra isso no XG).
            addr = 0x72 if prop == "Grave" else 0x73
            self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, canal, addr, val)))

    def enviar_setup_metronomo(self):
        # Teste pedido pelo Michel: quando ele escolhe uma porta MIDI
        # separada pro metrônomo (canal 10 continua o mesmo, só o
        # dispositivo de saída muda), manda pra ELA uma configuração fixa -
        # Bank 16256, Patch 0, Reverb 0, Chorus 0 e o "Volume do
        # Metrônomo" escolhido nas Configurações. Esse canal, nessa porta
        # separada, é um dispositivo à parte - não é o Rhythm2 do próprio
        # estilo, que continua intocado, do jeito que sempre foi, na porta
        # principal (self.midi_out).
        porta = self.midi_out_metronomo
        if not porta:
            return
        volume = self.main.config.get("metronomo_volume", 100)
        bank = 16256
        try:
            porta.send(mido.Message('control_change', channel=CANAL_METRONOMO, control=CC_BANK_MSB, value=bank // 128))
            porta.send(mido.Message('control_change', channel=CANAL_METRONOMO, control=CC_BANK_LSB, value=bank % 128))
            porta.send(mido.Message('program_change', channel=CANAL_METRONOMO, program=0))
            porta.send(mido.Message('control_change', channel=CANAL_METRONOMO, control=CC_VOLUME, value=volume))
            porta.send(mido.Message('control_change', channel=CANAL_METRONOMO, control=CC_REVERB, value=0))
            porta.send(mido.Message('control_change', channel=CANAL_METRONOMO, control=CC_CHORUS, value=0))
        except Exception:
            pass

    def send_initial_setup(self):
        if self.midi_out:
            import time
            for msg in getattr(self.main, 'midi_setup_msgs', []):
                try:
                    self.midi_out.send(msg)
                except Exception:
                    pass
                if msg.type == 'sysex':
                    d = bytes(msg.data)
                    if len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x00:
                        time.sleep(0.05)
                    elif len(d) == 4 and tuple(d) == (0x7E, 0x7F, 0x09, 0x01):
                        # A mesma pausa que o próprio SX600 dá entre o GM Reset e o XG System On.
                        time.sleep(0.03)
                        
            from MHS_Utils import TOTAL_CANAIS, CANAL_BATERIA_1, CANAL_BATERIA_2
            for ch in range(TOTAL_CANAIS):
                c = self.main.canais[ch]
                self.enviar_midi_param("Bank", c["Bank"], ch)
                self.enviar_midi_param("Patch", c["Patch"], ch)
                for prop in ["Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo"]:
                    self.enviar_midi_param(prop, c[prop], ch)
                    
            try:
                self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_1, 0x07, 0x03)))
                self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_2, 0x07, 0x02)))
            except Exception:
                pass
                    
            for msg in getattr(self.main, 'midi_setup_msgs', []):
                if msg.type == 'sysex':
                    d = bytes(msg.data)
                    if len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] in (0x30, 0x31):
                        try:
                            self.midi_out.send(msg)
                        except Exception:
                            pass

            # Mesma reaplicação acima, mas pra Guia 3 do Drum Setup (NRPN
            # puro em vez de SysEx) - sem isso, a trinca 99/98/6 até saía na
            # primeira passada (linha ~198), mas o Bank/Patch reenviado logo
            # depois reseleciona o kit e reseta a afinação por nota de volta
            # ao padrão de fábrica no teclado real (mesmo motivo documentado
            # em aplicar_drum_setup) - a peça tocava com a afinação original
            # mesmo com o arquivo/canais lidos certinho.
            for ch in range(TOTAL_CANAIS):
                for (nota, param_id), valor in self.main.canais[ch].get("DrumParamsNRPN", {}).items():
                    try:
                        self.midi_out.send(mido.Message('control_change', channel=ch, control=99, value=param_id))
                        self.midi_out.send(mido.Message('control_change', channel=ch, control=98, value=nota))
                        self.midi_out.send(mido.Message('control_change', channel=ch, control=6, value=valor))
                    except Exception:
                        pass

            self.enviar_dsp_global()
            self.enviar_dsp_variation()
            time.sleep(0.1)

    def resetar_ccs_padrao_secao(self, canais_alvo=None):
        # Confirmado com o Michel (Bolero MHS.sty, Ending com Fade Out): no
        # SX600 de verdade, o bloco SInt é reexecutado toda vez que uma
        # seção (re)começa - repetindo o loop da mesma seção ou trocando
        # pra outra -, restaurando Volume/Pan/Expression/Reverb/Chorus pro
        # "normal" de cada canal ANTES do conteúdo da seção em si tocar.
        # Sem isso, um Fade Out (Expression baixando até quase 0 no fim de
        # uma seção) ficava "grudado" baixo ao voltar o loop ou trocar de
        # seção - CC é ESTADO, não um evento isolado, e nada mais mandava
        # um valor novo até a próxima automação explícita da seção.
        # Chamado no início de CADA passagem pela seção (ver midi_worker) -
        # só as CCs em si (rápido, sem SysEx nem pausa nenhuma), nunca o
        # reset pesado de GM/XG que send_initial_setup faz (esse é só pra
        # abrir o arquivo, daria um "engasgo" audível se repetisse a cada
        # loop).
        #
        # `canais_alvo` (None = todos os 16, o padrão/mais seguro): o
        # Michel notou que o metrônomo (numa porta MIDI separada) soava
        # ANTES da própria cabeça da seção - um "flam" de poucos ms. Causa:
        # esta função sempre mandava 16 canais x 5 CCs (80 mensagens) pela
        # porta PRINCIPAL, incondicionalmente, bem antes do 1º clique/nota
        # da passagem nova - e como o metrônomo sai por uma porta
        # SEPARADA, ele não espera essa fila, chegando primeiro. `midi_
        # worker` agora só pede reforço pros canais que REALMENTE tiveram
        # automação de CC (7/10/11/91/93) na passagem que acabou de tocar
        # (os únicos cuja "memória" no teclado pode ter saído do padrão) -
        # numa passagem comum, sem fade/automação nenhuma, isso reduz o
        # reforço pra ZERO mensagens, sem nenhum risco pro caso que
        # motivou este recurso (o Fade Out do Ending continua sendo
        # detectado e reforçado, já que ele USA CC de verdade).
        if not self.midi_out:
            return
        alvo = range(TOTAL_CANAIS) if canais_alvo is None else canais_alvo
        for ch in alvo:
            c = self.main.canais[ch]
            for prop in ["Volume", "Pan", "Expression", "Reverb", "Chorus"]:
                self.enviar_midi_param(prop, c[prop], ch)
            # Pitch Bend sempre volta pro centro (0) - diferente das CCs
            # acima, não existe "valor normal do canal" salvo em canais[ch]
            # pra ele (nunca teve tela dedicada), e centro é o único valor
            # que faz sentido como padrão de descanso. Se a própria cabeça
            # da seção declarar um Pitch Bend diferente de propósito, o
            # conteúdo normal dela reafirma isso logo em seguida, na hora
            # certa - isto aqui é só a "rede de segurança" contra o valor
            # ter ficado curvado da passagem anterior.
            try:
                self.midi_out.send(mido.Message('pitchwheel', channel=ch, pitch=0))
            except Exception:
                pass

    def enviar_dsp_global(self):
        # Reverb e Chorus globais (bloco 02 01, endereços 00-0C e 20-2C) -
        # confirmado contra o MHS MIDI Sequencer.
        if not self.midi_out:
            return
        c = getattr(self.main, 'dsp_global', None)
        if not c or not c.get('active', False):
            return
        r_msb = REV_MSB_LIST[c.get('rev_msb_idx', 1)][1] if c.get('rev_msb_idx', 1) < len(REV_MSB_LIST) else 1
        c_msb = CHO_MSB_LIST[c.get('cho_msb_idx', 1)][1] if c.get('cho_msb_idx', 1) < len(CHO_MSB_LIST) else 65
        sysex_data = [
            (0x02, 0x01, 0x00, r_msb, c.get('rev_lsb_idx', 0)),
            (0x02, 0x01, 0x0C, c.get('rev_ret', 64)),
            (0x02, 0x01, 0x20, c_msb, c.get('cho_lsb_idx', 0)),
            (0x02, 0x01, 0x2C, c.get('cho_ret', 64)),
        ]
        rev_p = c.get('rev_p', [-1] * 16)
        for i in range(16):
            if rev_p[i] != -1:
                sysex_data.append((0x02, 0x01, OFFSETS_REV_PARAMS[i], rev_p[i] & 0x7F))
        cho_p = c.get('cho_p', [-1] * 16)
        for i in range(16):
            if cho_p[i] != -1:
                sysex_data.append((0x02, 0x01, OFFSETS_CHO_PARAMS[i], cho_p[i] & 0x7F))
        for data in sysex_data:
            try:
                self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C) + data))
                # O mesmo fôlego que o sequenciador usa pro teclado alocar o
                # Reverb e o Chorus.
                if data[2] in (0x00, 0x20):
                    time.sleep(0.25)
            except Exception:
                pass

    def enviar_dsp_variation(self):
        # Efeito de Inserção "Variation" (gaveta 1, bloco 02 01, endereços
        # 40-75) - confirmado contra o Força.sty (Auto Wah 2 no canal 13).
        if not self.midi_out:
            return
        v = getattr(self.main, 'dsp_variation', None)
        if not v or not v.get('active', False):
            return
        msb_val = v.get('msb_val', 0)
        lsb_val = max(0, min(127, v.get('lsb_idx', 0)))
        # Ordem Tipo -> Return -> parâmetros -> Conexão por ÚLTIMO, igual ao
        # arquivo genuíno do Alex Oliveira (ver sincronizar_dsp_no_track).
        msgs = [
            (0x02, 0x01, 0x40, msb_val, lsb_val),
            (0x02, 0x01, 0x54, 0x00, v.get('ret', 64)),
        ]
        p_list = v.get('p', [-1] * 16)
        for i in range(16):
            if p_list[i] == -1:
                continue
            if i < 10:
                # MSB/LSB de verdade - os tempos de Delay/Echo (até 7150ms)
                # não cabem só no byte baixo. Valores <128 saem iguais a
                # antes (MSB 0).
                valor = max(0, min(16383, p_list[i]))
                msgs.append((0x02, 0x01, OFFSETS_VAR_2BYTES[i], valor // 128, valor % 128))
            else:
                msgs.append((0x02, 0x01, OFFSETS_VAR_1BYTE[i - 10], p_list[i] & 0x7F))
        chs = {ch: niv for ch, niv in v.get('chs', {}).items() if 0 <= ch < TOTAL_CANAIS}
        if len(chs) <= 1:
            # Um canal só (ou nenhum): modo INSERTION com Part Number direto
            # (0x5B) - único jeito confirmado contra hardware real até agora
            # (Força.sty, Auto Wah 2).
            part_val = next(iter(chs), 0x7F)
            msgs.append((0x02, 0x01, 0x5A, 0x00))
            msgs.append((0x02, 0x01, 0x5B, part_val))
        else:
            # Dois ou mais canais: Conexão em SYSTEM (0x5A=1) + Control
            # Change 94 ("Variation Send Level") por canal - confirmado em
            # dois arquivos genuínos (Teclado.sty, Rock.sty), mesma família
            # do Reverb Send (CC91)/Chorus Send (CC93). A SysEx de Multi
            # Part que eu tinha tentado antes nunca soou no teclado real.
            msgs.append((0x02, 0x01, 0x5A, 0x01))
            msgs.append((0x02, 0x01, 0x5B, 0x7F))
        for data in msgs:
            try:
                self.midi_out.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C) + data))
                if data[2] in (0x40,):
                    time.sleep(0.05)
            except Exception:
                pass
        if len(chs) > 1:
            for ch, niv in chs.items():
                try:
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=94, value=max(0, min(127, niv))))
                except Exception:
                    pass

    def processar_roteamento(self, msg):
        for rota in self.main.rotas_midi:
            if not rota.get('active', False): continue
            src, dst = rota['src'], rota['dst']
            is_match = False
            if src == 'PB' and msg.type == 'pitchwheel': is_match = True
            elif src != 'PB' and msg.type == 'control_change' and msg.control == int(src): is_match = True
            if is_match:
                val = msg.pitch if msg.type == 'pitchwheel' else msg.value
                if dst == 'PB':
                    if msg.type == 'control_change':
                        return msg.copy(type='pitchwheel', pitch=int(round((val / 127.0) * 16383 - 8192)))
                    else: return msg 
                else:
                    dst_cc = int(dst)
                    if msg.type == 'pitchwheel':
                        return mido.Message('control_change', channel=msg.channel, control=dst_cc, value=int(round((val + 8192) / 16383.0 * 127)), time=msg.time)
                    else: return msg.copy(control=dst_cc)
        return msg

    def _exec_auto_punch(self):
        self._auto_punching = False
        if not self.playing: self.main.OnTogglePlay(None)

    def midi_in_handler(self, msg):
        if getattr(self.main, '_log_midi_in', False):
            try:
                with open(self.main._midi_log_path, "a", encoding="utf-8") as _f:
                    _f.write(str(msg) + "\n")
            except Exception:
                pass

        dialog = getattr(self.main, 'active_midi_dialog', None)
        if dialog:
            try:
                ainda_valido = bool(dialog) and dialog.IsShown()
            except RuntimeError:
                ainda_valido = False
            if ainda_valido and hasattr(dialog, 'handle_midi_in'):
                wx.CallAfter(dialog.handle_midi_in, msg)
                return
            else:
                self.main.active_midi_dialog = None
            
        msg = self.processar_roteamento(msg)
        
        if msg.type in ['note_on', 'note_off']:
            oct_shift = getattr(self.main, 'midi_in_octave', 0) * 12
            semi_shift = getattr(self.main, 'midi_in_semitone', 0)
            total_shift = oct_shift + semi_shift
            if total_shift != 0:
                nova_nota = max(0, min(127, msg.note + total_shift))
                msg = msg.copy(note=nova_nota)
        
        if self.main.in_vel_ctrl_on and msg.type == 'note_on' and msg.velocity > 0:
            new_vel = int(round(self.main.in_vel_min + (msg.velocity - 1) * (self.main.in_vel_max - self.main.in_vel_min) / 126.0))
            msg = msg.copy(velocity=max(1, min(127, new_vel)))
            
        if msg.type == 'note_on' and msg.velocity > 0: self.live_physical_keys.add((msg.channel, msg.note))
        elif msg.type in ['note_off', 'note_on']:
            if (msg.channel, msg.note) in self.live_physical_keys: self.live_physical_keys.remove((msg.channel, msg.note))
            else: return
                
        is_auto_punch = False
        if self.gravando and not self.playing:
            if msg.type in ['note_on', 'control_change', 'pitchwheel']:
                if not self._auto_punching:
                    self._auto_punching = True
                    # NÃO reiniciar anchor_tick/current_accumulated_ticks pro
                    # começo da seção aqui - isso descartava, em silêncio, a
                    # posição pra onde o usuário já tinha navegado (ex.: Page
                    # Down até o compasso 5) antes de armar e tocar a nota.
                    # A reprodução (Espaço/toque de tecla) passava a tocar do
                    # ZERO da seção mesmo com o cursor mostrando outro
                    # compasso - e a nota gravada logo em seguida (abaixo,
                    # ramo is_auto_punch) usava só o início bruto da seção,
                    # sem somar essa posição - achado com o Michel gravando
                    # no compasso 5 do Main C e a nota saindo do lugar certo.
                    wx.CallAfter(self._exec_auto_punch)
                is_auto_punch = True
                
        # Barreira de Volume/Expression na troca de timbre: o CC7/CC11 que o
        # timbre carrega não pode mudar o som nem a coluna. Vale por ~0,4s
        # depois de um Program Change; logo depois o Volume/Expression da
        # coluna é reafirmado pro sintetizador.
        agora = time.time()
        if msg.type == 'program_change':
            self._pc_burst_ate = agora + 0.4
        if (msg.type == 'control_change' and msg.control in (CC_VOLUME, CC_EXPRESSION)
                and agora < getattr(self, '_pc_burst_ate', 0)):
            return

        # --- Captura de timbre/DSP do teclado ---
        # Bank/Program abrem a janela da rajada; SysEx e CCs de forma de onda
        # são absorvidos pelo modelo do estilo (a única Variation + Voice
        # Creator), sempre no canal em foco. SysEx é sempre ecoado pro
        # sintetizador (antes o Style Creator dropava todo SysEx de entrada).
        if msg.type == 'program_change' or (msg.type == 'control_change' and msg.control in (0, 32)):
            self._cap_dsp_abrir()
        if msg.type == 'sysex':
            if getattr(self, '_captura_dsp', None) is not None:
                self._cap_dsp_sysex(list(msg.data))
            if self.midi_out:
                try: self.midi_out.send(msg)
                except Exception: pass
            return
        if msg.type == 'control_change' and getattr(self, '_captura_dsp', None) is not None:
            self._cap_dsp_cc(msg)

        if msg.type in ['note_on', 'note_off', 'control_change', 'pitchwheel', 'program_change']:
            alvos = [i for i in range(TOTAL_CANAIS) if self.main.canais[i]["Arm"]]
            if not alvos: alvos = [self.main.canal_atual]
            for ch in alvos:
                msg_mapped = msg.copy(channel=ch)

                if msg.type == 'program_change':
                    self.main.canais[ch]["Patch"] = msg.program
                    wx.CallAfter(self.main.atualizar_apos_midi_in, ch, "Patch")
                elif msg.type == 'control_change' and msg.control in (0, 32):
                    if not hasattr(self, '_live_bank_msb'): self._live_bank_msb = {i: 0 for i in range(TOTAL_CANAIS)}
                    if not hasattr(self, '_live_bank_lsb'): self._live_bank_lsb = {i: 0 for i in range(TOTAL_CANAIS)}
                    if msg.control == 0: self._live_bank_msb[ch] = msg.value
                    else: self._live_bank_lsb[ch] = msg.value
                    self.main.canais[ch]["Bank"] = (self._live_bank_msb[ch] * 128) + self._live_bank_lsb[ch]
                    wx.CallAfter(self.main.atualizar_apos_midi_in, ch, "Bank")
                
                if self.gravando and (self.playing or is_auto_punch):
                    if is_auto_punch:
                        idx = getattr(self.main, '_active_section_idx', 0)
                        secs = getattr(self.main, 'sections_info', [])
                        # Blindagem (índice fora do alcance): esta função
                        # roda na thread de entrada MIDI - lendo `idx`/
                        # `sections_info` sem trava nenhuma, um índice de
                        # uma aba/estado anterior pode não bater mais com a
                        # lista atual num instante de troca de aba/arquivo.
                        # Ver o mesmo cuidado em midi_worker.
                        if idx != wx.NOT_FOUND and secs and 0 <= idx < len(secs):
                            inicio_secao = secs[idx].get('start', 0)
                            if inicio_secao is None: inicio_secao = 0
                            # Soma a posição pra onde o usuário já tinha
                            # navegado (Page Down/Up, Home/End) ANTES de
                            # armar - sem isso, a nota sempre caía bem no
                            # início da seção, não importa onde o cursor
                            # estivesse (self.anchor_tick, preservado desde
                            # a correção acima).
                            abs_tick = inicio_secao + getattr(self, 'anchor_tick', 0)
                        else: abs_tick = 0
                    else: abs_tick = self.main.get_current_absolute_tick()
                    self.recorded_events.append((abs_tick, msg_mapped))
                if self.midi_out:
                    try: self.midi_out.send(msg_mapped)
                    except Exception: pass

            if msg.type == 'program_change':
                self._agendar_reafirmar_vol_expr(list(alvos))

    # ================= CAPTURA DE TIMBRE/DSP DO TECLADO =================
    def _cap_dsp_abrir(self):
        import copy
        if not getattr(self.main, '_captura_dsp_ligada', True):
            return
        ch = self.main.canal_atual
        if not (0 <= ch < TOTAL_CANAIS):
            return
        if not hasattr(self, '_dsp_teclado_chs'):
            self._dsp_teclado_chs = set()
            self._dsp_teclado_vc = {}
        cap = getattr(self, '_captura_dsp', None)
        if cap is None or cap.get('ch') != ch:
            self._captura_dsp_timer = getattr(self, '_captura_dsp_timer', None)
            self._captura_dsp = {
                'ch': ch,
                'insertion': False,
                'visto_vc': set(),
                'prev_vc': set(self._dsp_teclado_vc.get(ch, set())),
                'era_roteado': ch in self._dsp_teclado_chs,
                # fotos do estado ANTES da rajada, pro Ctrl+Z (baratas - dicts pequenos)
                'dsp_var_antes': copy.deepcopy(self.main.dsp_variation),
                'dsp_glob_antes': copy.deepcopy(self.main.dsp_global),
                'canal_antes': copy.deepcopy(self.main.canais[ch]),
            }
            wx.CallAfter(self._cap_dsp_agendar_fecho)
        self._captura_dsp['ate'] = time.time() + 0.45

    def _cap_dsp_agendar_fecho(self):
        if self._captura_dsp_timer:
            try: self._captura_dsp_timer.Stop()
            except Exception: pass
        self._captura_dsp_timer = wx.CallLater(550, self._cap_dsp_verificar)

    def _cap_dsp_verificar(self):
        cap = self._captura_dsp
        if not cap:
            return
        if time.time() < cap.get('ate', 0):
            self._captura_dsp_timer = wx.CallLater(150, self._cap_dsp_verificar)
            return
        self._cap_dsp_finalizar()

    def _cap_dsp_finalizar(self):
        cap = self._captura_dsp
        self._captura_dsp = None
        self._captura_dsp_timer = None
        if not cap:
            return
        ch = cap['ch']
        v = self.main.dsp_variation

        # Voice Creator: endereços que o teclado tinha e agora não reenviou saem do modelo.
        if 0 <= ch < TOTAL_CANAIS:
            vc = self.main.canais[ch].get("VoiceCreator", {})
            for addr in cap['prev_vc'] - cap['visto_vc']:
                vc.pop(addr, None)
        self._dsp_teclado_vc[ch] = set(cap['visto_vc'])

        # Roteamento da Variation (Opção A): o timbre novo vira a Variation do
        # estilo e continua valendo pros canais que já estavam roteados.
        removeu_rota = False
        if cap['insertion']:
            self._dsp_teclado_chs.add(ch)
        elif cap['era_roteado']:
            # o timbre novo não trouxe DSP nenhum: tira só este canal da Variation.
            self._dsp_teclado_chs.discard(ch)
            if isinstance(v.get('chs'), dict) and v['chs'].pop(ch, None) is not None:
                removeu_rota = True
            if not v.get('chs'):
                v['active'] = False

        atual = self.main.canais[ch] if 0 <= ch < TOTAL_CANAIS else {}
        # O timbre (Banco/Peça) mudou? -> tem que valer pra TODAS as seções,
        # igual quando se edita pelas colunas Bank/Patch (esse era o bug: pelo
        # teclado o timbre mudava ao vivo mas a seção voltava pro original).
        timbre_mudou = (atual.get("Patch") != cap['canal_antes'].get("Patch")
                        or atual.get("Bank") != cap['canal_antes'].get("Bank"))
        # O DSP/EQ/Voice Creator mudou de verdade? -> assa a Variation no estilo.
        _keys = ("Grave", "Agudo", "Pan", "Reverb", "Chorus", "VoiceCreator")
        dsp_mudou = (cap['insertion'] or removeu_rota
                     or v != cap['dsp_var_antes']
                     or any(atual.get(k) != cap['canal_antes'].get(k) for k in _keys))

        if not (timbre_mudou or dsp_mudou):
            return

        wx.CallAfter(self.main._aplicar_captura_dsp_teclado,
                     cap['dsp_var_antes'], cap['dsp_glob_antes'], cap['canal_antes'], ch, dsp_mudou)

    def _cap_dsp_sysex(self, d):
        if len(d) < 6 or d[0] != 0x43 or d[2] != 0x4C:
            return
        ch = self.main.canal_atual
        if not (0 <= ch < TOTAL_CANAIS):
            return
        cap = self._captura_dsp
        high = d[3]

        # Inserção 43 10 4C 03 nn -> traduz pra Variation (a única do estilo).
        if high == 0x03 and len(d) >= 7:
            param = d[5]
            v = self.main.dsp_variation
            if param == 0x00 and len(d) >= 8:
                vals = [x for _, x in VARIATION_EFEITOS_LIST]
                if cap and not cap['insertion']:
                    v['p'] = [-1] * 16   # efeito novo: zera os params do anterior
                    v['ret'] = 64
                v['msb_val'] = d[6]
                v['msb_idx'] = vals.index(d[6]) if d[6] in vals else 0
                v['lsb_idx'] = d[7]
                v['active'] = True
                v.setdefault('chs', {})
                if ch not in v['chs']:
                    v['chs'][ch] = 127
                if cap:
                    cap['insertion'] = True
            elif param in _INS_ADDR_IDX and len(d) >= 7:
                v.setdefault('p', [-1] * 16)
                v['p'][_INS_ADDR_IDX[param]] = d[6]
                v['active'] = True
                v.setdefault('chs', {})
                if ch not in v['chs']:
                    v['chs'][ch] = 127
                if cap:
                    cap['insertion'] = True
            return

        # Multi Part 43 10 4C 08 00 XX YY -> Grave/Agudo/Pan/Rev/Cho ou Voice Creator.
        if high == 0x08 and len(d) >= 7:
            addr, val = d[5], d[6]
            c = self.main.canais[ch]
            if addr == 0x72:
                c["Grave"] = val
            elif addr == 0x73:
                c["Agudo"] = val
            elif addr == 0x0E:
                c["Pan"] = val
            elif addr == 0x12:
                c["Chorus"] = val
            elif addr == 0x13:
                c["Reverb"] = val
            elif addr in (0x09, 0x0A):
                # Detune: 2 bytes separados no fio (cada um só um nibble), 1
                # valor combinado só no modelo - ver detune_combinar em
                # MHS_Utils.py.
                if not hasattr(self, '_detune_nibbles'):
                    self._detune_nibbles = {i: [0x08, 0x00] for i in range(TOTAL_CANAIS)}
                par = self._detune_nibbles.setdefault(ch, [0x08, 0x00])
                if addr == 0x09: par[0] = val & 0x0F
                else: par[1] = val & 0x0F
                c.setdefault("VoiceCreator", {})[0x09] = detune_combinar(par[0], par[1])
                if cap:
                    cap['visto_vc'].add(0x09)
            elif addr not in _MP_RESERVADOS:
                c.setdefault("VoiceCreator", {})[addr] = val
                if cap:
                    cap['visto_vc'].add(addr)
            return

        # Portamento (Mono Priority/Modo/Modo do Tempo) - bloco SEPARADO
        # 0x0A (43 10 4C 0A pp aa vv), não o 0x08 de sempre. Endereços
        # 0x01-0x03 - mesmo valor de byte que Bank Select MSB/LSB/Program
        # Number do bloco 0x08, mas SEM relação nenhuma (bloco diferente) -
        # e sem ambiguidade real na chave VoiceCreator porque esses 3
        # endereços já são reservados (nunca capturados) no bloco 0x08.
        if high == 0x0A and len(d) >= 7:
            addr, val = d[5], d[6]
            if addr in (0x01, 0x02, 0x03):
                c = self.main.canais[ch]
                c.setdefault("VoiceCreator", {})[addr] = val
                if cap:
                    cap['visto_vc'].add(addr)
            return

    def _cap_dsp_cc(self, msg):
        cap = self._captura_dsp
        ch = self.main.canal_atual
        if not (0 <= ch < TOTAL_CANAIS):
            return
        c = self.main.canais[ch]
        cc, val = msg.control, msg.value
        if cc in (CC_PAN, CC_REVERB, CC_CHORUS):
            c[{CC_PAN: "Pan", CC_REVERB: "Reverb", CC_CHORUS: "Chorus"}[cc]] = val
            return
        if cc == 5:
            # Portamento Time - o mecanismo que funciona de verdade (CC 5 +
            # CC 65 derivado), não os endereços SysEx 0x67/0x68 do Data
            # List (testados e sem efeito no som real).
            c.setdefault("VoiceCreator", {})["porta_time"] = val
            if cap:
                cap['visto_vc'].add("porta_time")
            return
        if cc in _CC_SOUND_MP:
            addr = _CC_SOUND_MP[cc]
            c.setdefault("VoiceCreator", {})[addr] = val
            if cap:
                cap['visto_vc'].add(addr)
            return
        if cc in (99, 98, 6, 38):
            if not hasattr(self, '_nrpn_in'):
                self._nrpn_in = {'msb': None, 'lsb': None}
            st = self._nrpn_in
            if cc == 99:
                st['msb'] = val
            elif cc == 98:
                st['lsb'] = val
            elif cc == 6 and st['msb'] is not None and st['lsb'] is not None:
                addr = _NRPN_SOUND_MP.get((st['msb'], st['lsb']))
                if addr is not None:
                    c.setdefault("VoiceCreator", {})[addr] = val
                    if cap:
                        cap['visto_vc'].add(addr)
            return

    def _agendar_reafirmar_vol_expr(self, alvos):
        # ~0,45s depois da troca de timbre, reafirma Volume (CC7) e Expression
        # (CC11) da COLUNA pro sintetizador - o timbre novo trouxe os valores
        # dele, mas quem manda é a mixagem da tela.
        def _reaf():
            if not self.midi_out:
                return
            for ch in alvos:
                if not (0 <= ch < TOTAL_CANAIS):
                    continue
                c = self.main.canais[ch]
                try:
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_VOLUME, value=int(c.get("Volume", 100))))
                    self.midi_out.send(mido.Message('control_change', channel=ch, control=CC_EXPRESSION, value=int(c.get("Expression", 127))))
                except Exception:
                    pass
        threading.Timer(0.45, _reaf).start()

    def start_worker(self):
        self._play_generation += 1
        self.worker_thread = threading.Thread(target=self.midi_worker, args=(self._play_generation,), daemon=True)
        self.worker_thread.start()

    def midi_worker(self, minha_geracao):
        import time
        import threading
        import mido
        import wx

        # None = reforça os 16 canais (1ª passagem, ou logo após trocar de
        # seção - conteúdo totalmente diferente, não dá pra aproveitar
        # nada da passagem anterior). Depois de uma passagem NATURAL pela
        # MESMA seção, vira o conjunto de canais que essa passagem de fato
        # automatizou via CC - só esses precisam de reforço (ver o
        # comentário em resetar_ccs_padrao_secao).
        canais_para_reforcar = None
        try:
            while self.playing and self._play_generation == minha_geracao:
                # Toda vez que uma passagem NOVA pela seção começa (loop
                # repetindo, ou trocando de seção) - igual ao SX600 de
                # verdade reexecutando o SInt a cada entrada de seção.
                self.resetar_ccs_padrao_secao(canais_para_reforcar)
                # Mesma distinção usada acima (None = seção nova/trocou,
                # conjunto = repetição natural da MESMA seção) - reaproveitada
                # mais abaixo pra decidir se o sysex de cabeça de seção pode
                # deixar de ser reenviado nesta passagem (ver comentário no
                # ramo 'sysex' e em prepare_section_cache/section_has_mid_sysex).
                is_repeat_pass = canais_para_reforcar is not None
                tpq = self.main.current_midi_data.ticks_per_beat if self.main.current_midi_data else 480
                ticks_per_measure = tpq * self.main.beats_per_measure

                idx = getattr(self.main, '_active_section_idx', 0)
                
                section_start = 0
                section_end = float('inf')
                secs = getattr(self.main, 'sections_info', [])
                # Blindagem (índice fora do alcance): mesmo já não devendo
                # mais acontecer (ver comentário em build_full_section_list/
                # rebuild_sections_from_cache, MHS_MainFrame.py) - essa
                # combinação exata (idx de uma numeração, sections_info de
                # outra, ou vazia num instante de troca de aba/arquivo) foi
                # o "IndexError: list index out of range" real que derrubava
                # esta thread inteira (self.playing virava False) - cair no
                # fallback de "sem seção" é infinitamente melhor que travar
                # o Play todo por causa de 1 passagem.
                if idx != wx.NOT_FOUND and secs and 0 <= idx < len(secs):
                    sec = secs[idx]
                    section_start = sec.get('start', 0)
                    if section_start is None: section_start = 0
                    section_end = sec.get('end', float('inf'))
                    if section_end is None or section_end == float('inf'):
                        section_end = sum(m.time for m in self.main.merged_track_cache)
                        if section_end <= section_start: section_end = section_start + (tpq * self.main.beats_per_measure)
                else: section_end = tpq * self.main.beats_per_measure

                total_section_ticks = section_end - section_start
                if total_section_ticks <= 0: total_section_ticks = tpq * self.main.beats_per_measure
                msgs = getattr(self.main, 'current_section_msgs', [])
                temp_accumulated = 0
                
                if self.anchor_tick % tpq == 0:
                    next_beat_tick = self.anchor_tick
                else:
                    next_beat_tick = ((self.anchor_tick // tpq) + 1) * tpq
                    
                beat_count = int(next_beat_tick / tpq) % self.main.beats_per_measure
                
                msg_idx = 0
                msg_metro_down_on = mido.Message('note_on', channel=9, note=22, velocity=100)
                msg_metro_down_off = mido.Message('note_off', channel=9, note=22, velocity=0)
                msg_metro_beat_on = mido.Message('note_on', channel=9, note=21, velocity=100)
                msg_metro_beat_off = mido.Message('note_off', channel=9, note=21, velocity=0)
                
                last_gui_sync = 0
                current_bpm_tempo = self.main.current_tempo
                scan_accum = 0
                for m in msgs:
                    scan_accum += m.time
                    if scan_accum <= self.anchor_tick:
                        if m.type == 'set_tempo': current_bpm_tempo = m.tempo
                    else: break

                float_tick = float(self.anchor_tick)
                last_time = time.perf_counter()

                while True:
                    if not self.playing or self.force_reload_loop or self._play_generation != minha_geracao: break
                    
                    current_idx_check = getattr(self.main, '_active_section_idx', 0)
                    if getattr(self.main, 'last_idx', -1) != current_idx_check:
                        self.main.last_idx = current_idx_check
                        self.force_reload_loop = True
                        self.anchor_tick = 0
                        break
                    
                    now = time.perf_counter()
                    delta_sec = now - last_time
                    last_time = now
                    delta_ticks = (delta_sec * tpq * 1000000.0) / current_bpm_tempo
                    float_tick += delta_ticks
                    current_tick = int(float_tick)
                    
                    is_end_of_loop = False
                    if current_tick >= total_section_ticks:
                        current_tick = total_section_ticks
                        is_end_of_loop = True

                    self.current_accumulated_ticks = current_tick

                    if now - last_gui_sync > 0.05:
                        last_gui_sync = now
                        dialog = getattr(self.main, 'active_midi_dialog', None)
                        if dialog and type(dialog).__name__ == "EventListDialog" and hasattr(dialog, 'update_realtime_playhead'):
                            wx.CallAfter(dialog.update_realtime_playhead, current_tick)

                    if self.use_metronome and current_tick >= next_beat_tick and not is_end_of_loop:
                        # Quando o próximo clique cai EXATAMENTE na virada do
                        # loop (o caso comum: seção com um número inteiro de
                        # compassos), esse clique e o clique do início da
                        # PRÓXIMA passagem (tick 0 de novo, mesmo beat_count 0)
                        # são o MESMO tempo forte - sem o `not is_end_of_loop`,
                        # os dois disparavam, uma batida "a mais" ouvida bem
                        # na virada (fim do compasso + reinício do loop). O
                        # clique real acontece só uma vez, já no início da
                        # passagem seguinte.
                        #
                        # Teste pedido pelo Michel: se tiver uma porta MIDI
                        # separada configurada pro metrônomo, o clique vai
                        # pra ELA (dispositivo à parte); senão, continua
                        # exatamente como sempre foi, pela porta principal.
                        porta_metro = self.midi_out_metronomo or self.midi_out
                        if porta_metro:
                            try:
                                if beat_count == 0:
                                    porta_metro.send(msg_metro_down_on)
                                    threading.Timer(0.05, lambda p=porta_metro: p.send(msg_metro_down_off)).start()
                                else:
                                    porta_metro.send(msg_metro_beat_on)
                                    threading.Timer(0.05, lambda p=porta_metro: p.send(msg_metro_beat_off)).start()
                            except Exception: pass
                        next_beat_tick += tpq
                        beat_count = (beat_count + 1) % self.main.beats_per_measure

                    while msg_idx < len(msgs):
                        msg = msgs[msg_idx]
                        if temp_accumulated + msg.time <= current_tick:
                            temp_accumulated += msg.time
                            msg_idx += 1
                            if temp_accumulated < self.anchor_tick: continue 
                            if msg.type == 'set_tempo': current_bpm_tempo = msg.tempo
                            ch = getattr(msg, 'channel', None)
                            if ch is not None:
                                any_solo = any(c['Solo'] for c in self.main.canais)
                                can_play = self.main.canais[ch]['Solo'] if any_solo else not self.main.canais[ch]['Mute']
                                if can_play and not getattr(msg, 'is_meta', False):
                                    out_msg = msg.copy()
                                    try: self.midi_out.send(out_msg)
                                    except Exception: pass
                            elif msg.type == 'sysex':
                                # SysEx (Drum Setup, DSP, etc) não tem canal - sem
                                # este ramo, "ch is not None" acima nunca era
                                # verdadeiro pra ele e o Play nunca reenviava
                                # nenhum SysEx embutido no meio de uma seção,
                                # em nenhuma seção, desde sempre. Não faz
                                # sentido barrar por Mute/Solo aqui (não é
                                # conteúdo de canal), então manda sempre.
                                #
                                # EXCETO numa repetição NATURAL da mesma seção
                                # quando ela não tem sysex de verdade no meio
                                # (section_has_mid_sysex == False, calculado em
                                # prepare_section_cache): nesse caso, todo sysex
                                # da seção está agrupado na cabeça, já foi
                                # mandado na passagem anterior e o teclado não
                                # tem como ter "esquecido" - reenviar de novo só
                                # soma atraso na virada do loop sem mudar nada
                                # no som (confirmado analisando os .sty do
                                # Michel: cabeça sempre igual, e nos raros casos
                                # com sysex real no meio - ex. Balada MHS.sty,
                                # "Main D" - a flag fica True e este atalho não
                                # entra, mantendo o reenvio de sempre).
                                # Drum Setup (endereço 0x30/0x31, Montagem de Kit
                                # E Parâmetros) NUNCA entra nesse atalho, mesmo
                                # com section_has_mid_sysex == False - achado com
                                # o Michel (Regional MHS 02.sty, canal Rhythm 1
                                # "se desfazendo" a cada volta do loop): o Program
                                # Change do canal (que RESSELECIONA o kit e RESETA
                                # a afinação por nota no teclado real) é uma
                                # mensagem "com canal", nunca passa por este
                                # atalho - sempre reenvia, toda passagem. Se o
                                # SysEx de Drum Setup que deveria vir logo depois
                                # dele for pulado (por estar "agrupado na cabeça",
                                # o caso comum - Program Change e SysEx de Drum
                                # Setup normalmente ficam no MESMO tick), o reset
                                # do Program Change nunca é desfeito de volta -
                                # exatamente o "kit se desfaz na virada do loop"
                                # relatado, e só no(s) canal(is) cuja seção
                                # resseleciona Bank/Patch de verdade.
                                d = bytes(msg.data)
                                eh_drum_setup = len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] in (0x30, 0x31)
                                if is_repeat_pass and not eh_drum_setup and not getattr(self.main, 'section_has_mid_sysex', True):
                                    pass
                                else:
                                    try: self.midi_out.send(msg.copy())
                                    except Exception: pass
                        else: break 
                    
                    if is_end_of_loop:
                        break

                    time.sleep(0.001)

                if self.force_reload_loop:
                    self.force_reload_loop = False
                    self.panic_reset()
                    # Troca de seção/recarga forçada: a passagem seguinte é
                    # de conteúdo DIFERENTE - não dá pra reaproveitar "quem
                    # automatizou o quê" desta aqui. Reforço completo (os
                    # 16 canais) da próxima vez, por segurança.
                    canais_para_reforcar = None
                    continue

                # Passagem terminou NATURALMENTE (mesma seção vai repetir
                # o loop) - só os canais que ela de fato automatizou via
                # CC 7/10/11/91/93 (Volume/Pan/Expression/Reverb/Chorus) OU
                # Pitch Bend podem ter saído do padrão no teclado; os outros
                # continuam com o valor certo desde a última vez, não
                # precisam de reforço nenhum na volta. Pitch Bend entrou
                # aqui depois (achado com o Michel, "Os Barões da
                # Pisadinha.sty", Fill In BB): igual ao Fade Out de CC, um
                # Pitch Bend no meio da seção (o baixo descendo 1 oitava,
                # por exemplo) é ESTADO, não evento isolado - sem reforço,
                # ficava "grudado" curvado ao voltar o loop.
                canais_para_reforcar = {
                    m.channel for m in msgs
                    if (m.type == 'control_change' and m.control in (7, 10, 11, 91, 93)) or m.type == 'pitchwheel'
                }

                if self.playing: self.anchor_tick = 0
                if self.gravando and self.recorded_events:
                    # `aplicar_gravacao` agora é thread-safe (mesma técnica
                    # já usada em `prepare_section_cache`: checa `wx.
                    # IsMainThread()` e evita widget de verdade fora dela,
                    # fixando o índice de seção capturado em vez de deixar o
                    # refresh adiado reler a lista mais tarde) - chamada
                    # direta, sem `wx.CallAfter`, sem espera nenhuma. A parte
                    # que a PRÓXIMA passagem do loop precisa (sections_info/
                    # current_section_msgs) já fica pronta antes desta
                    # chamada retornar; só o que toca widget de verdade
                    # (título, listas, falar) é adiado por dentro dela mesma,
                    # sem bloquear esta thread.
                    self.main.aplicar_gravacao()

                current_idx = getattr(self.main, '_active_section_idx', 0)
                if getattr(self.main, 'last_idx', -1) != current_idx:
                    wx.CallAfter(self.main.prepare_section_cache, current_idx)
                    self.main.last_idx = current_idx
                    
        except Exception as e: 
            self.playing = False
            import traceback
            with open(self.main.log_file, "a", encoding="utf-8") as log:
                log.write(f"Erro Fatal no midi_worker:\n{traceback.format_exc()}\n")