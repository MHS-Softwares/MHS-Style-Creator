# -*- coding: utf-8 -*-
"""Leitura e gravação de arquivos de VOZ do teclado Yamaha.

Extensões conhecidas (todas com a mesma "casca"): .vce (voz comum), .drm
(kit de bateria), .liv (Live!), .mgv (MegaVoice), .sar (Super Articulation),
mais .org/.swv/.clv (lidas se tiverem a mesma estrutura).

Cada arquivo é um MIDI padrão (formato 0, 96 ticks, uma trilha só) com a
configuração de UMA voz no canal 1: seleção de timbre (Bank/Patch),
controladores (Expression, Reverb, Chorus, Portamento, Sound Controllers),
NRPN de vibrato/EG, SysEx XG de Multi Part (43 10 4C 08 ...), Portamento e
Offsets (43 10 4C 0A ...), efeito de Inserção (43 10 4C 03 ...) e mensagens
proprietárias (43 73 01 50/51 ...) que o Data List não documenta - essas
usam bytes de dado com 8 bits (até FF), por isso este módulo lê e grava o
MIDI "na mão" (o mido recusa bytes acima de 127). O que o programa não
entende fica em "Extras" e volta intacto ao exportar.

Dois modelos de arquivo (gerados de arquivos reais do teclado): 'A' (.vce,
.drm - modelo METALEIRA.vce) e 'B' (.mgv, .sar, .liv - modelo
CAVAAO.T331.mgv, com o efeito de Inserção completo).

Este módulo é IDÊNTICO nos dois programas (MHS Style Creator e MHS MIDI
Sequencer) e não depende de wx nem de mido.
"""
import os
import struct

CC_SOUND_MP = {74: 0x18, 71: 0x19, 73: 0x1A, 75: 0x1B, 72: 0x1C, 76: 0x15, 77: 0x16, 78: 0x17}
NRPN_SOUND_MP = {0x08: 0x15, 0x09: 0x16, 0x0A: 0x17, 0x20: 0x18, 0x21: 0x19, 0x63: 0x1A, 0x64: 0x1B, 0x66: 0x1C}
# Endereços do bloco Multi Part (0x08) guardados no dicionário VoiceCreator
VC08 = {0x08, 0x09, 0x0C, 0x0D, 0x0F, 0x10, 0x11, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
        0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52, 0x5A, 0x5B, 0x5C,
        0x5D, 0x5E, 0x5F, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x76, 0x77}
# Endereços do bloco Portamento (0x0A) guardados no mesmo dicionário
VC0A = {0x01, 0x02, 0x03}

# Extensões de voz e o rótulo de cada uma (ordem = ordem dos filtros de arquivo)
TIPOS_VOZ = [
    (".vce", "Voz (.vce)"),
    (".drm", "Kit de bateria (.drm)"),
    (".mgv", "MegaVoice (.mgv)"),
    (".sar", "Super Articulation (.sar)"),
    (".liv", "Live! (.liv)"),
]
WILDCARD_ABRIR = ("Vozes Yamaha|*.vce;*.drm;*.mgv;*.sar;*.liv;*.org;*.swv;*.clv|Todos os arquivos|*.*")
WILDCARD_SALVAR = "|".join(f"{r}|*{e}" for e, r in TIPOS_VOZ)

# (tipo, dados..., espaço). Espaços: 'vc:N' (dicionário VoiceCreator),
# 'grave'/'agudo'/'expression'/'reverb'/'chorus'/'porta_time'/'porta_sw'/
# 'bank_msb'/'bank_lsb'/'patch', None (constante) ou 'raw' (Extras).
TEMPLATE_A = [
    ('cc', 0, 63, 'bank_msb'),
    ('cc', 32, 0, 'bank_lsb'),
    ('pc', 0, 31, 'patch'),
    ('cc', 72, 100, 'vc:28'),
    ('cc', 99, 1, None),
    ('cc', 98, 102, None),
    ('cc', 6, 64, 'vc:28'),
    ('cc', 38, 0, None),
    ('cc', 73, 64, 'vc:26'),
    ('cc', 99, 1, None),
    ('cc', 98, 100, None),
    ('cc', 6, 64, 'vc:27'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 8, None),
    ('cc', 6, 64, 'vc:21'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 9, None),
    ('cc', 6, 64, 'vc:22'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 10, None),
    ('cc', 6, 64, 'vc:23'),
    ('cc', 38, 0, None),
    ('sx', '43104c08001e40', 'vc:30'),
    ('sx', '43104c0a004040', 'raw'),
    ('sx', '43104c08002000', 'vc:32'),
    ('sx', '43104c08002100', 'vc:33'),
    ('sx', '43104c08002200', 'vc:34'),
    ('sx', '43104c08004e40', 'vc:78'),
    ('sx', '43104c0a004240', 'raw'),
    ('sx', '43104c08005000', 'vc:80'),
    ('sx', '43104c08005100', 'vc:81'),
    ('sx', '43104c08005200', 'vc:82'),
    ('sx', '43104c08005b40', 'vc:91'),
    ('sx', '43104c0a004440', 'raw'),
    ('sx', '43104c08005d00', 'vc:93'),
    ('sx', '43104c08005e00', 'vc:94'),
    ('sx', '43104c08005f00', 'vc:95'),
    ('sx', '43104c08000501', 'raw'),
    ('cc', 11, 100, 'expression'),
    ('cc', 71, 64, 'vc:25'),
    ('cc', 74, 64, 'vc:24'),
    ('cc', 5, 0, 'porta_time'),
    ('cc', 65, 0, 'porta_sw'),
    ('sx', '43104c08000c40', 'vc:12'),
    ('sx', '43104c08000d40', 'vc:13'),
    ('sx', '4373015008000540', 'raw'),
    ('sx', '4373015008030641', 'raw'),
    ('sx', '43104c0a000200', 'vc:2'),
    ('sx', '43104c0a000300', 'vc:3'),
    ('sx', '43104c0a000440', 'raw'),
    ('sx', '43104c0a000540', 'raw'),
    ('sx', '43104c0a000600', 'raw'),
    ('sx', '43104c0a000700', 'raw'),
    ('sx', '43104c0a000801', 'raw'),
    ('sx', '43104c0a00097f', 'raw'),
    ('sx', '43104c0a005000', 'raw'),
    ('sx', '43104c0a005100', 'raw'),
    ('sx', '43104c0800760c', 'vc:118'),
    ('sx', '43104c08007240', 'grave'),
    ('sx', '43104c08007736', 'vc:119'),
    ('sx', '43104c08007340', 'agudo'),
    ('sx', '43730151040000020000', 'raw'),
    ('sx', '4373015004000564', 'raw'),
    ('sx', '4373015004000210', 'raw'),
    ('sx', '4373015004000300', 'raw'),
    ('sx', '4373015004000400', 'raw'),
    ('cc', 91, 20, 'reverb'),
    ('cc', 93, 0, 'chorus'),
    ('sx', '4373015008000800', 'raw'),
    ('sx', '4373015008000100', 'raw'),
    ('sx', '43104c0300000110', 'raw'),
    ('sx', '43104c03000b14', 'raw'),
    ('sx', '43730151080011020000', 'raw'),
]

TEMPLATE_B = [
    ('cc', 0, 8, 'bank_msb'),
    ('cc', 32, 0, 'bank_lsb'),
    ('pc', 0, 88, 'patch'),
    ('cc', 72, 104, 'vc:28'),
    ('cc', 99, 1, None),
    ('cc', 98, 102, None),
    ('cc', 6, 64, 'vc:28'),
    ('cc', 38, 0, None),
    ('cc', 73, 64, 'vc:26'),
    ('cc', 99, 1, None),
    ('cc', 98, 100, None),
    ('cc', 6, 64, 'vc:27'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 8, None),
    ('cc', 6, 61, 'vc:21'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 9, None),
    ('cc', 6, 64, 'vc:22'),
    ('cc', 38, 0, None),
    ('cc', 99, 1, None),
    ('cc', 98, 10, None),
    ('cc', 6, 64, 'vc:23'),
    ('cc', 38, 0, None),
    ('sx', '43104c08001e40', 'vc:30'),
    ('sx', '43104c0a004040', 'raw'),
    ('sx', '43104c08002004', 'vc:32'),
    ('sx', '43104c08002100', 'vc:33'),
    ('sx', '43104c08002200', 'vc:34'),
    ('sx', '43104c08000501', 'raw'),
    ('sx', '4373015008000446', 'raw'),
    ('cc', 71, 64, 'vc:25'),
    ('cc', 74, 64, 'vc:24'),
    ('cc', 5, 0, 'porta_time'),
    ('sx', '43104c08000c40', 'vc:12'),
    ('sx', '43104c08000d40', 'vc:13'),
    ('sx', '4373015008000540', 'raw'),
    ('sx', '4373015008030641', 'raw'),
    ('sx', '43104c0a000200', 'vc:2'),
    ('sx', '43104c0a000300', 'vc:3'),
    ('sx', '43104c08007616', 'vc:118'),
    ('sx', '43104c08007240', 'grave'),
    ('sx', '43104c0800772a', 'vc:119'),
    ('sx', '43104c08007340', 'agudo'),
    ('sx', '43730151040000021402', 'raw'),
    ('sx', '4373015004000550', 'raw'),
    ('sx', '4373015004000210', 'raw'),
    ('sx', '43730150040003ff', 'raw'),
    ('sx', '4373015004000400', 'raw'),
    ('cc', 91, 22, 'reverb'),
    ('cc', 93, 0, 'chorus'),
    ('sx', '4373015008000800', 'raw'),
    ('sx', '4373015008000100', 'raw'),
    ('sx', '43104c0300001508', 'raw'),
    ('sx', '43104c03000b28', 'raw'),
    ('sx', '43730151080011020800', 'raw'),
    ('sx', '43104c03000208', 'raw'),
    ('sx', '43104c0300035c', 'raw'),
    ('sx', '43104c0300040a', 'raw'),
    ('sx', '43104c0300054e', 'raw'),
    ('sx', '43104c03000640', 'raw'),
    ('sx', '43104c03000700', 'raw'),
    ('sx', '43104c03000800', 'raw'),
    ('sx', '43104c03000900', 'raw'),
    ('sx', '43104c03000a00', 'raw'),
    ('sx', '43104c03002000', 'raw'),
    ('sx', '43104c03002100', 'raw'),
    ('sx', '43104c0300221c', 'raw'),
    ('sx', '43104c03002340', 'raw'),
    ('sx', '43104c0300242e', 'raw'),
    ('sx', '43104c03002540', 'raw'),
    ('sx', '4373015108001203000008', 'raw'),
]


def extensao_sugerida(bank, patch=0):
    """Extensão que o teclado usaria pra voz com esse Bank (MSB*128+LSB)."""
    msb, lsb = int(bank) // 128, int(bank) % 128
    if msb == 62:
        return ".drm"
    if msb == 8:
        return ".sar" if lsb == 32 else ".mgv"
    if msb == 0 and lsb == 115:
        return ".liv"
    return ".vce"


def _modelo_da_extensao(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    return 'B' if ext in ('.mgv', '.sar', '.liv') else 'A'


# ---------- MIDI cru (aceita bytes de dado até 0xFF) ----------
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


def _eventos_crus(caminho):
    """Lista de eventos: ('pc', prog) | ('cc', ctrl, valor) | ('sx', bytes)."""
    b = open(caminho, 'rb').read()
    if b[:4] != b'MThd':
        raise ValueError("não é um arquivo MIDI")
    i = 14
    out = []
    while i + 8 <= len(b) and b[i:i + 4] == b'MTrk':
        ln = struct.unpack('>I', b[i + 4:i + 8])[0]
        j = i + 8
        fim = min(j + ln, len(b))
        run = None
        while j < fim:
            _, j = _vlq_ler(b, j)
            s = b[j]
            if s == 0xFF:
                l, k = _vlq_ler(b, j + 2)
                j = k + l
            elif s in (0xF0, 0xF7):
                l, k = _vlq_ler(b, j + 1)
                dados = b[k:k + l]
                if dados and dados[-1] == 0xF7:
                    dados = dados[:-1]
                out.append(('sx', bytes(dados)))
                j = k + l
            else:
                if s & 0x80:
                    run = s
                    j += 1
                n = 1 if (run & 0xF0) in (0xC0, 0xD0) else 2
                dados = b[j:j + n]
                j += n
                if (run & 0xF0) == 0xB0:
                    out.append(('cc', dados[0], dados[1]))
                elif (run & 0xF0) == 0xC0:
                    out.append(('pc', dados[0]))
        i = fim
    return out


def _escrever_midi(eventos, caminho):
    """eventos: lista de bytes já codificados (sem o delta)."""
    corpo = bytearray()
    corpo += b'\x05\xFF\x58\x04\x04\x02\x18\x08'
    corpo += b'\x05\xFF\x51\x03\x07\xA1\x20'
    for e in eventos:
        corpo += b'\x05' + e
    corpo += b'\x05\xFF\x2F\x00'
    with open(caminho, 'wb') as f:
        f.write(b'MThd' + struct.pack('>IHHH', 6, 0, 1, 96))
        f.write(b'MTrk' + struct.pack('>I', len(corpo)) + bytes(corpo))


def _ev_cc(c, v):
    return bytes([0xB0, c & 0x7F, max(0, min(127, int(v)))])


def _ev_pc(p):
    return bytes([0xC0, int(p) & 0x7F])


def _ev_sx(dados):
    d = bytes(dados) + b'\xF7'
    return b'\xF0' + _vlq_escrever(len(d)) + d


def _chave_extra(d):
    """Chave (hex) de uma mensagem "raw": tudo menos o(s) valor(es)."""
    d = bytes(d)
    if d[:3] == bytes([0x43, 0x73, 0x01]):
        return d[:7].hex()
    b = bytearray(d[:6])
    if len(b) > 4:
        b[4] = 0  # número da parte/canal - sempre normalizado pra 0
    return bytes(b).hex()


def _valor_extra(d):
    d = bytes(d)
    return (d[7:] if d[:3] == bytes([0x43, 0x73, 0x01]) else d[6:]).hex()


def vce_exportar(campos, caminho, modelo=None):
    """Grava um arquivo de voz com a configuração 'campos' (dict) no canal 1.

    O modelo ('A' ou 'B') sai da extensão de 'caminho' (.mgv/.sar/.liv = B, o
    resto = A), a menos que 'modelo' seja passado.

    campos aceita: Bank, Patch, Expression, Reverb, Chorus, Grave, Agudo,
    PortaTime, PortaSwitch, VoiceCreator (dict endereço -> valor) e Extras
    (dict hex -> hex, o que vce_ler devolveu). O que faltar fica com o valor
    do modelo (o mesmo dos arquivos do teclado)."""
    modelo = modelo or _modelo_da_extensao(caminho)
    template = TEMPLATE_B if modelo == 'B' else TEMPLATE_A
    vc = dict(campos.get('VoiceCreator') or {})
    extras = dict(campos.get('Extras') or {})
    mesmo_modelo = extras.get('__modelo__') == modelo
    extras = {k: v for k, v in extras.items() if not k.startswith('__')}
    porta = campos.get('PortaTime', vc.get('porta_time'))
    eventos = []
    usados_vc = set()
    usados_raw = set()
    bank = campos.get('Bank')
    for item in template:
        if item[0] == 'pc':
            eventos.append(_ev_pc(campos.get('Patch', item[2])))
        elif item[0] == 'cc':
            _, c, padrao, slot = item
            v = padrao
            if slot == 'bank_msb' and bank is not None: v = int(bank) // 128
            elif slot == 'bank_lsb' and bank is not None: v = int(bank) % 128
            elif slot in ('expression', 'reverb', 'chorus'):
                v = campos.get({'expression': 'Expression', 'reverb': 'Reverb', 'chorus': 'Chorus'}[slot], padrao)
            elif slot == 'porta_time' and porta is not None: v = porta
            elif slot == 'porta_sw' and 'PortaSwitch' in campos: v = 127 if campos['PortaSwitch'] else 0
            elif slot == 'porta_sw' and porta is not None: v = 127 if int(porta) > 0 else 0
            elif slot and slot.startswith('vc:'):
                a = int(slot[3:])
                v = vc.get(a, padrao)
                usados_vc.add(('08', a))
            eventos.append(_ev_cc(c, v))
        else:
            _, hx, slot = item
            d = bytearray.fromhex(hx)
            if slot and slot.startswith('vc:'):
                a = int(slot[3:])
                bloco = '0a' if d[3] == 0x0A else '08'
                d[6] = max(0, min(127, int(vc.get(a, d[6]))))
                usados_vc.add((bloco, a))
            elif slot == 'grave':
                d[6] = int(campos.get('Grave', d[6]))
            elif slot == 'agudo':
                d[6] = int(campos.get('Agudo', d[6]))
            elif slot == 'raw':
                k = _chave_extra(d)
                usados_raw.add(k)
                if mesmo_modelo and extras and k not in extras:
                    continue  # veio de um arquivo deste modelo que não tinha esta mensagem
                if k in extras:
                    val = bytes.fromhex(extras[k])
                    d = d[:(7 if d[:3] == bytes([0x43, 0x73, 0x01]) else 6)] + bytearray(val)
            eventos.append(_ev_sx(d))
    # Parâmetros que o modelo não trazia mas o canal tem (ex.: Note Shift)
    for a in sorted(k for k in vc if isinstance(k, int)):
        if a in VC08 and ('08', a) not in usados_vc:
            if a == 0x09:
                v = int(vc[a])
                if v != 128:
                    eventos.append(_ev_sx([0x43, 0x10, 0x4C, 0x08, 0x00, 0x09, (v >> 4) & 0x0F]))
                    eventos.append(_ev_sx([0x43, 0x10, 0x4C, 0x08, 0x00, 0x0A, v & 0x0F]))
            else:
                eventos.append(_ev_sx([0x43, 0x10, 0x4C, 0x08, 0x00, a, max(0, min(127, int(vc[a])))]))
        elif a in VC0A and ('0a', a) not in usados_vc:
            eventos.append(_ev_sx([0x43, 0x10, 0x4C, 0x0A, 0x00, a, max(0, min(127, int(vc[a])))]))
    # Extras que o modelo não conhecia (preserva tudo que veio de um arquivo)
    for k, val in extras.items():
        if k not in usados_raw:
            eventos.append(_ev_sx(bytes.fromhex(k) + bytes.fromhex(val)))
    _escrever_midi(eventos, caminho)


def vce_ler(caminho):
    """Lê um arquivo de voz e devolve um dict com as chaves que ele trouxe:
    Bank, Patch, Expression, Reverb, Chorus, Volume, Pan, Grave, Agudo,
    PortaTime, PortaSwitch, VoiceCreator (dict) e Extras (dict hex -> hex,
    mais '__modelo__': 'A'/'B')."""
    res = {'VoiceCreator': {}, 'Extras': {'__modelo__': _modelo_da_extensao(caminho)}}
    vc = res['VoiceCreator']
    bank = {'msb': None, 'lsb': None}
    nrpn = {'msb': None, 'lsb': None}
    detune = {}
    for x in _eventos_crus(caminho):
        if x[0] == 'pc':
            res['Patch'] = x[1]
        elif x[0] == 'cc':
            c, v = x[1], x[2]
            if c == 0: bank['msb'] = v
            elif c == 32: bank['lsb'] = v
            elif c == 7: res['Volume'] = v
            elif c == 10: res['Pan'] = v
            elif c == 11: res['Expression'] = v
            elif c == 91: res['Reverb'] = v
            elif c == 93: res['Chorus'] = v
            elif c == 65: res['PortaSwitch'] = 1 if v >= 64 else 0
            elif c == 5:
                res['PortaTime'] = v
                vc['porta_time'] = v
            elif c in CC_SOUND_MP: vc[CC_SOUND_MP[c]] = v
            elif c == 99: nrpn['msb'] = v
            elif c == 98: nrpn['lsb'] = v
            elif c == 6 and nrpn['msb'] == 1 and nrpn['lsb'] in NRPN_SOUND_MP:
                vc[NRPN_SOUND_MP[nrpn['lsb']]] = v
        else:
            d = x[1]
            if d[:4] == bytes([0x43, 0x10, 0x4C, 0x08]) and len(d) >= 7:
                a, v = d[5], d[6]
                if a == 0x72: res['Grave'] = v
                elif a == 0x73: res['Agudo'] = v
                elif a in (0x09, 0x0A): detune[a] = v
                elif a in VC08: vc[a] = v
                else: res['Extras'][_chave_extra(d)] = _valor_extra(d)
            elif d[:4] == bytes([0x43, 0x10, 0x4C, 0x0A]) and len(d) >= 7:
                if d[5] in VC0A: vc[d[5]] = d[6]
                else: res['Extras'][_chave_extra(d)] = _valor_extra(d)
            elif d[:3] in (bytes([0x43, 0x73, 0x01]), bytes([0x43, 0x10, 0x4C])) and len(d) >= 7:
                res['Extras'][_chave_extra(d)] = _valor_extra(d)
    if 0x09 in detune and 0x0A in detune:
        vc[0x09] = ((detune[0x09] & 0x0F) << 4) | (detune[0x0A] & 0x0F)
    if bank['msb'] is not None or bank['lsb'] is not None:
        res['Bank'] = (bank['msb'] or 0) * 128 + (bank['lsb'] or 0)
    return res
