# -*- coding: utf-8 -*-
"""
Motor do "violão / harpa" dos Efeitos Midi (aba Harpa / Strum), sem janela.

Transforma acordes (notas tocadas juntas) em palhetadas de violão:
- TUDO em milissegundos: a velocidade da palhetada é a mesma em qualquer arquivo, seja qual for o tempo da música e a
  resolução (ticks por tempo) do MIDI. (Antes a palhetada era em ticks: num arquivo de 120 ticks por tempo ela ficava
  4 vezes mais lenta do que num de 480.)
- a direção varia de verdade: para baixo (grave para agudo) e para cima (agudo para grave, só nas cordas de cima),
  alternando pelo tempo da batida ou a cada acorde;
- cada corda tem sua velocidade (a 1ª corda da palhetada é a mais forte, as outras vão diminuindo; palhetada para cima é
  mais leve), a mão acelera um pouco durante a palhetada e há pequenas variações humanas (sempre as MESMAS para os mesmos
  acordes, para o preview e o resultado final soarem iguais);
- desenhos prontos: espalhar os acordes que já existem (mantém o ritmo), rasgueados que refazem o ritmo de um acorde longo
  e dedilhados.
"""
import bisect
import random

import mido

MS_ACORDE = 40.0                # notas que começam até 40 ms uma da outra são "o mesmo acorde"

CAT_PERSONALIZADO = "Personalizado"
CAT_ESPALHAR = "Espalhar os acordes (mantém o ritmo)"
CAT_RASGUEADO = "Rasgueado (refaz o ritmo dos acordes longos)"
CAT_DEDILHADO = "Dedilhado (cordas separadas)"
CAT_HARPA = "Harpa (cascata)"

DIRECOES = ["Do desenho", "Automática pelo tempo da batida", "Sempre para baixo (grave para agudo)",
            "Sempre para cima (agudo para grave)", "Alternar a cada acorde (baixo, cima, baixo...)"]
_DIRECAO_NOME = {1: "auto", 2: "baixo", 3: "cima", 4: "alterna"}

VELOCIDADES = [("Do desenho", None), ("Hiper rápida (5 ms por corda)", 5.0), ("Rápida (9 ms por corda)", 9.0),
               ("Média (16 ms por corda)", 16.0), ("Lenta (30 ms por corda)", 30.0), ("Harpa (60 ms por corda)", 60.0),
               ("Sincronizada na resolução do grid abaixo", "grade")]


# ------------------------------------------------------------------------------------------------------ tempo
class MapaTempo:
    """converte milissegundos em ticks usando o tempo (BPM) que vale em cada ponto da música"""

    def __init__(self, tpb, tempos=None):
        self.tpb = max(1, int(tpb))
        lim = []
        for tick, us in sorted(tempos or []):
            if lim and lim[-1][0] == tick:
                lim[-1] = (tick, us)
            else:
                lim.append((tick, us))
        if not lim or lim[0][0] > 0:
            lim.insert(0, (0, 500000))
        self.ticks = [x[0] for x in lim]
        self.us = [max(1, x[1]) for x in lim]

    @classmethod
    def de_midi(cls, midi):
        tempos = []
        for tr in midi.tracks:
            t = 0
            for m in tr:
                t += m.time
                if m.type == "set_tempo":
                    tempos.append((t, m.tempo))
        return cls(getattr(midi, "ticks_per_beat", 480), tempos)

    def tempo_em(self, tick):
        return self.us[max(0, bisect.bisect_right(self.ticks, tick) - 1)]

    def ms_para_ticks(self, tick, ms):
        return ms * 1000.0 * self.tpb / self.tempo_em(tick)

    def ticks_para_ms(self, tick, ticks):
        return ticks * self.tempo_em(tick) / (self.tpb * 1000.0)


# ------------------------------------------------------------------------------------------------------ desenhos
# padrão: (posição em 16avos de tempo, tipo, força). Tipos: D palhetada para baixo, U para cima (só as cordas de cima),
# X abafada (chuck), B nota grave, A segundo baixo, T três cordas de cima juntas, n<i> uma corda (0 = a mais grave, -1 = a mais aguda)
def _p(nome, cat, tipo, desc="", **kw):
    d = dict(nome=nome, cat=cat, tipo=tipo, desc=desc, ms=14.0, dir="auto", up_cordas=4, acento=1.0, humanizar=3.0,
             vel_var=4.0, fade=0.10, curta_ms=None, padrao=None, compasso=4, minimo=1.5, soar=False, vel_fiel=False)
    d.update(kw)
    return d


PRESETS = [
    # vel_fiel: a velocity de cada nota fica EXATAMENTE a que foi gravada (sem acento por direção, sem queda entre as cordas,
    # sem variação humana de força): só o tempo da palhetada muda, a dinâmica é a do Michel.
    _p("Personalizado (só os ajustes abaixo)", CAT_PERSONALIZADO, "espalhar", ms=14.0, dir="auto", vel_fiel=True),

    # --- espalhar os acordes que já existem
    _p("Palhetada natural (violão base)", CAT_ESPALHAR, "espalhar", ms=14.0, dir="auto"),
    _p("Palhetada rápida (pop, sertanejo)", CAT_ESPALHAR, "espalhar", ms=8.0, dir="auto"),
    _p("Palhetada lenta e aberta (balada)", CAT_ESPALHAR, "espalhar", ms=26.0, dir="baixo", acento=0.92, fade=0.14),
    _p("Só para baixo, firme (rock)", CAT_ESPALHAR, "espalhar", ms=11.0, dir="baixo", acento=1.08),
    _p("Só para cima, leve (contratempo)", CAT_ESPALHAR, "espalhar", ms=10.0, dir="cima", acento=0.95, up_cordas=4),
    _p("Baixo e cima alternando a cada acorde", CAT_ESPALHAR, "espalhar", ms=12.0, dir="alterna"),
    _p("Abafada (palm mute)", CAT_ESPALHAR, "espalhar", ms=7.0, dir="auto", curta_ms=70.0, acento=0.9),
    _p("Flamenco (rasgueado hiper rápido)", CAT_ESPALHAR, "espalhar", ms=4.0, dir="alterna", acento=1.05, humanizar=2.0),
    _p("Mão solta (bem humana, com variações)", CAT_ESPALHAR, "espalhar", ms=16.0, dir="auto", humanizar=9.0, vel_var=9.0),

    # --- rasgueados: refazem o ritmo de um acorde longo (acordes curtos só são espalhados)
    _p("Folk clássico (baixo, baixo-cima, cima-baixo-cima)", CAT_RASGUEADO, "rasgueado", ms=12.0,
       padrao=[(0, "D", 1.0), (4, "D", 0.85), (6, "U", 0.75), (10, "U", 0.75), (12, "D", 0.88), (14, "U", 0.75)]),
    _p("Pop em colcheias (baixo-cima o compasso todo)", CAT_RASGUEADO, "rasgueado", ms=10.0,
       padrao=[(0, "D", 1.0), (2, "U", 0.72), (4, "D", 0.88), (6, "U", 0.72), (8, "D", 0.95), (10, "U", 0.72),
               (12, "D", 0.88), (14, "U", 0.72)]),
    _p("Rock firme (colcheias para baixo, acento no 2 e 4)", CAT_RASGUEADO, "rasgueado", ms=9.0, acento=1.05,
       padrao=[(0, "D", 0.95), (2, "D", 0.8), (4, "D", 1.0), (6, "D", 0.8), (8, "D", 0.95), (10, "D", 0.8),
               (12, "D", 1.0), (14, "D", 0.8)]),
    _p("Balada suave (poucas batidas, soltas)", CAT_RASGUEADO, "rasgueado", ms=22.0, acento=0.92,
       padrao=[(0, "D", 1.0), (6, "U", 0.65), (8, "D", 0.85), (10, "U", 0.6), (14, "U", 0.65)]),
    _p("Baixo e batida abafada (pagode simples)", CAT_RASGUEADO, "rasgueado", ms=8.0,
       padrao=[(0, "B", 1.0), (2, "X", 0.7), (4, "D", 0.9), (6, "X", 0.7), (8, "B", 0.95), (10, "X", 0.7),
               (12, "D", 0.9), (14, "X", 0.7)]),
    _p("Reggae / ska (contratempo abafado)", CAT_RASGUEADO, "rasgueado", ms=6.0,
       padrao=[(0, "B", 1.0), (2, "X", 0.9), (6, "X", 0.9), (8, "B", 0.9), (10, "X", 0.9), (14, "X", 0.9)]),
    _p("Country: baixo alternado e batida (boom-chick)", CAT_RASGUEADO, "rasgueado", ms=8.0,
       padrao=[(0, "B", 1.0), (4, "T", 0.85), (8, "A", 0.95), (12, "T", 0.85)]),
    _p("Valsa (3 tempos): baixo e duas batidas", CAT_RASGUEADO, "rasgueado", ms=8.0, compasso=3, minimo=1.5,
       padrao=[(0, "B", 1.0), (4, "T", 0.8), (8, "T", 0.8)]),
    _p("Bossa-nova simplificada", CAT_RASGUEADO, "rasgueado", ms=6.0,
       padrao=[(0, "B", 1.0), (3, "T", 0.7), (6, "T", 0.7), (8, "A", 0.9), (11, "T", 0.7), (14, "T", 0.7)]),
    _p("Flamenco (rasgueado em 16avos, baixo e cima)", CAT_RASGUEADO, "rasgueado", ms=4.0, acento=1.05,
       padrao=[(i, "D" if i % 2 == 0 else "U", 1.0 if i % 4 == 0 else (0.88 if i % 2 == 0 else 0.7)) for i in range(16)]),

    # --- dedilhados: as notas ficam soando até o acorde acabar
    _p("Dedilhado básico (baixo e três cordas agudas)", CAT_DEDILHADO, "dedilhado", soar=True, humanizar=4.0,
       padrao=[(0, "n0", 1.0), (2, "n-3", 0.7), (4, "n-2", 0.75), (6, "n-1", 0.8), (8, "n-2", 0.75), (10, "n-3", 0.7),
               (12, "n-2", 0.75), (14, "n-1", 0.8)]),
    _p("Dedilhado subindo e descendo pelas cordas", CAT_DEDILHADO, "dedilhado", soar=True, humanizar=4.0,
       padrao=[(0, "n0", 1.0), (2, "n1", 0.75), (4, "n2", 0.75), (6, "n3", 0.8), (8, "n2", 0.75), (10, "n1", 0.75),
               (12, "n2", 0.75), (14, "n1", 0.75)]),
    _p("Dedilhado valsa (3 tempos)", CAT_DEDILHADO, "dedilhado", soar=True, compasso=3, humanizar=4.0,
       padrao=[(0, "n0", 1.0), (4, "T", 0.7), (8, "T", 0.7)]),
    _p("Travis picking simplificado (baixo alternado)", CAT_DEDILHADO, "dedilhado", soar=True, humanizar=4.0,
       padrao=[(0, "n0", 1.0), (2, "n-1", 0.7), (4, "n-2", 0.7), (6, "n-1", 0.7), (8, "A", 0.95), (10, "n-1", 0.7),
               (12, "n-2", 0.7), (14, "n-1", 0.7)]),
    _p("Dedilhado rápido em 16avos", CAT_DEDILHADO, "dedilhado", soar=True, humanizar=3.0,
       padrao=[(i, k, a) for g in range(4) for i, k, a in
               ((g * 4, "n0", 0.95), (g * 4 + 1, "n-3", 0.65), (g * 4 + 2, "n-2", 0.7), (g * 4 + 3, "n-1", 0.75))]),

    # --- harpa
    _p("Harpa média (cascata de baixo para cima)", CAT_HARPA, "espalhar", ms=30.0, dir="baixo", acento=0.95, up_cordas=None,
       fade=0.0, humanizar=2.0),
    _p("Harpa lenta (cascata mágica)", CAT_HARPA, "espalhar", ms=60.0, dir="baixo", acento=0.95, up_cordas=None,
       fade=0.0, humanizar=2.0),
    _p("Harpa que sobe e desce a cada acorde", CAT_HARPA, "espalhar", ms=40.0, dir="alterna", acento=0.95, up_cordas=None,
       fade=0.0, humanizar=2.0),
]

CATEGORIAS = ["Todos"] + [c for c in (CAT_PERSONALIZADO, CAT_ESPALHAR, CAT_RASGUEADO, CAT_DEDILHADO, CAT_HARPA)]


def rotulo_do_desenho(i):
    return PRESETS[i]["nome"]


def indices_da_categoria(cat):
    return [i for i, p in enumerate(PRESETS) if cat in (None, "", "Todos") or p["cat"] == cat]


# ------------------------------------------------------------------------------------------------------ acordes
def _agrupar_acordes(notas, mapa):
    """notas: dicts com start/end/msg_on/ch -> lista de acordes (lista de dicts), separados por canal"""
    por_canal = {}
    for ev in sorted(notas, key=lambda e: (e["start"], e["msg_on"].note)):
        por_canal.setdefault(ev["ch"], []).append(ev)
    saida = []
    for lista in por_canal.values():
        atual = []
        for ev in lista:
            if atual and ev["start"] - atual[0]["start"] <= max(1, int(round(mapa.ms_para_ticks(atual[0]["start"], MS_ACORDE)))):
                atual.append(ev)
            else:
                if atual:
                    saida.append(atual)
                atual = [ev]
        if atual:
            saida.append(atual)
    saida.sort(key=lambda a: a[0]["start"])
    return saida


def _direcoes(inicios, tpb, modo):
    """direção de cada palhetada: 'D' para baixo (grave -> agudo), 'U' para cima (agudo -> grave). -> (direções, posição no tempo em 16avos)"""
    n = len(inicios)
    subs = [int(round(((t % tpb) / float(tpb)) * 4)) % 4 for t in inicios]
    if modo == "baixo":
        return ["D"] * n, subs
    if modo == "cima":
        return ["U"] * n, subs
    alterna = ["D" if i % 2 == 0 else "U" for i in range(n)]
    if modo == "alterna":
        return alterna, subs
    conj = set(subs)
    if len(conj) <= 1:
        return (["D"] * n if (not conj or 0 in conj) else alterna), subs       # todos no tempo: para baixo; todos no contratempo: alterna
    if any(s % 2 for s in conj):                                               # 16avos: baixo no tempo e no "e", cima nos outros
        return ["D" if s % 2 == 0 else "U" for s in subs], subs
    return ["D" if s == 0 else "U" for s in subs], subs                        # colcheias: baixo no tempo, cima no contratempo


def _arrastar(cordas, direcao, t0, ctx, acc, fim_fixo=None, ms=None, curta_ms=None, fade=None):
    """uma palhetada: cordas = [{'nota','vel','fim','ch'}], começa em t0. -> lista de notas {'ch','nota','vel','ini','fim'}"""
    p, mapa, rng, nat = ctx["preset"], ctx["mapa"], ctx["rng"], ctx["nat"]
    ms = ctx["ms"] if ms is None else ms
    fade = p["fade"] if fade is None else fade
    ordem = sorted(cordas, key=lambda c: c["nota"], reverse=(direcao == "U"))
    fracas = set()
    if direcao == "U" and p["up_cordas"] and len(ordem) > p["up_cordas"]:
        # a palhetada para cima pega pouco as cordas graves: elas continuam tocando (NUNCA se tira uma nota que foi gravada),
        # só mais fracas. Antes essas notas eram descartadas e o Dó mais grave de um acorde de 5 notas sumia do Event List.
        fracas = {id(c) for c in ordem[p["up_cordas"]:]}
    n = len(ordem)
    saida = []
    acum = 0.0
    for k, c in enumerate(ordem):
        if k > 0:
            acum += ms * (1.0 - 0.15 * (k - 1) / max(1, n - 2))                 # a mão acelera um pouco durante a palhetada
        if ctx["grade"]:
            deslocamento = k * ctx["grade"]
        else:
            jit = rng.uniform(-1, 1) * min(ctx["hum_ms"], 0.35 * ms) if k > 0 else 0.0
            deslocamento = int(round(mapa.ms_para_ticks(t0, max(0.0, acum + jit))))
        ini = t0 + deslocamento
        vel = c["vel"] * acc * (1.0 - fade * k / max(1, n - 1)) * (0.6 if id(c) in fracas else 1.0) + rng.uniform(-1, 1) * ctx["vel_var"] * nat
        fim = c["fim"] if fim_fixo is None else fim_fixo
        if curta_ms:
            fim = min(fim, ini + max(1, int(round(mapa.ms_para_ticks(ini, curta_ms)))))
        fim = max(fim, ini + max(1, int(round(mapa.ms_para_ticks(ini, 30.0)))))
        if p["vel_fiel"]:
            vel = c["vel"]
        saida.append({"ch": c["ch"], "nota": c["nota"], "vel": max(1, min(127, int(round(vel)))), "ini": ini, "fim": fim})
    return saida


def _um_acorde_espalhado(cordas, t0, direcao, sub, ctx):
    p = ctx["preset"]
    if direcao == "D":
        acc = (1.0 if sub == 0 else 0.93) * p["acento"]
    else:
        acc = 0.8 * p["acento"]
    return _arrastar(cordas, direcao, t0, ctx, acc, curta_ms=p["curta_ms"])


def _padrao_no_acorde(cordas, ini, fim, ctx):
    """refaz o ritmo de um acorde longo com o desenho do preset (repete o desenho até o acorde acabar)"""
    p, tpb, mapa, rng = ctx["preset"], ctx["tpb"], ctx["mapa"], ctx["rng"]
    barra = max(1, int(round(p["compasso"] * tpb)))
    eventos = []
    k = 0
    while ini + k * barra < fim:
        for pos, tipo, forca in p["padrao"]:
            t = ini + k * barra + int(round(pos * tpb / 4.0))
            if pos == 0 and k == 0:
                pass
            else:
                t += int(round(mapa.ms_para_ticks(t, rng.uniform(-1, 1) * ctx["hum_ms"])))
            t = max(ini, t)
            if t < fim:
                eventos.append((t, tipo, forca))
        k += 1
    eventos.sort(key=lambda e: e[0])
    folga = max(1, int(round(mapa.ms_para_ticks(ini, 8.0))))
    saida = []
    ordenadas = sorted(cordas, key=lambda c: c["nota"])
    for i, (t, tipo, forca) in enumerate(eventos):
        limite = fim if (p["soar"] or i + 1 >= len(eventos)) else max(t + 1, eventos[i + 1][0] - folga)
        limite = min(limite, fim)
        acc = forca * p["acento"]
        if tipo in ("D", "U"):
            saida += _arrastar(cordas, tipo, t, ctx, acc, fim_fixo=limite)
        elif tipo == "X":
            saida += _arrastar(cordas, "D", t, ctx, acc * 0.55, fim_fixo=t + max(1, int(round(mapa.ms_para_ticks(t, 55.0)))),
                               ms=2.0, fade=0.0)
        elif tipo == "T":
            topo = ordenadas[-3:]
            saida += _arrastar(topo, "D", t, ctx, acc, fim_fixo=limite, ms=max(3.0, ctx["ms"] * 0.6))
        else:
            if tipo == "B":
                alvo = ordenadas[0]
            elif tipo == "A":
                alvo = ordenadas[1] if len(ordenadas) >= 3 else ordenadas[0]
            else:                                                               # n<i>: uma corda (negativo conta de cima)
                i_corda = int(tipo[1:])
                alvo = ordenadas[max(-len(ordenadas), min(len(ordenadas) - 1, i_corda))]
            saida += _arrastar([alvo], "D", t, ctx, acc, fim_fixo=limite)
    return saida


def _fechar_repeticoes(notas):
    """uma nota que volta a ser tocada antes de acabar é cortada um instante antes (senão o teclado soma duas vezes a mesma nota)"""
    por = {}
    for n in sorted(notas, key=lambda x: x["ini"]):
        por.setdefault((n["ch"], n["nota"]), []).append(n)
    for lista in por.values():
        for a, b in zip(lista, lista[1:]):
            if a["fim"] >= b["ini"]:
                a["fim"] = max(a["ini"] + 1, b["ini"] - 1)


def processar(notas, params, tpb, mapa, ed_tick=float("inf"), prender=False):
    """aplica o desenho aos acordes do trecho.
    notas: dicts {'start','end','msg_on','ch'} (as notas do trecho, nos canais escolhidos)
    params: preset_idx, direcao (0 = do desenho ... 4), ms_corda (None = do desenho), grade_ticks (palhetada sincronizada), naturalidade (0-100),
            octaves (1-4)
    prender: True = nenhuma nota nasce depois do fim do trecho (ed_tick); o Style Creator usa, porque o que passa do fim de uma seção
             vazaria para a seção seguinte. O Sequencer deixa a palhetada passar do fim marcado.
    -> (lista de (tick, 1 se liga / 0 se desliga, mensagem), quantidade de notas geradas)"""
    idx = params.get("preset_idx")
    preset = PRESETS[idx] if isinstance(idx, int) and 0 <= idx < len(PRESETS) else PRESETS[0]
    nat = max(0.0, min(100.0, float(params.get("naturalidade", 50)))) / 50.0
    ms = params.get("ms_corda")
    grade = int(round(float(params.get("grade_ticks") or 0) * tpb / 480.0))      # o grid da janela é em ticks de 480 por tempo
    ms_corda = float(ms) if ms else preset["ms"]
    ctx = {"preset": preset, "mapa": mapa, "tpb": tpb, "nat": nat, "ms": ms_corda, "grade": grade,
           "hum_ms": preset["humanizar"] * nat, "vel_var": preset["vel_var"], "rng": None}
    oitavas = max(1, int(params.get("octaves", 1)))
    modo = _DIRECAO_NOME.get(int(params.get("direcao", 0)), preset["dir"])       # 0 = a direção do próprio desenho

    acordes = _agrupar_acordes(notas, mapa)
    gerar, sozinhas = [], []
    for ac in acordes:
        cordas, vistas = [], set()
        for o in range(oitavas):
            for ev in ac:
                nota = ev["msg_on"].note + 12 * o
                if 0 <= nota <= 127 and nota not in vistas:
                    vistas.add(nota)
                    cordas.append({"nota": nota, "vel": ev["msg_on"].velocity, "fim": max(ev["end"], ev["start"] + 1), "ch": ev["ch"]})
        ini = min(ev["start"] for ev in ac)
        fim = max(c["fim"] for c in cordas)
        if len(cordas) >= 2 or oitavas > 1:
            gerar.append((ini, fim, cordas))
        else:
            sozinhas.append({"ch": ac[0]["ch"], "nota": cordas[0]["nota"], "vel": cordas[0]["vel"], "ini": ini, "fim": fim})

    usa_padrao = preset["tipo"] in ("rasgueado", "dedilhado") and preset["padrao"]
    curtos = [g for g in gerar if not (usa_padrao and g[1] - g[0] >= preset["minimo"] * tpb)]
    direcoes, subs = _direcoes([g[0] for g in curtos], tpb, modo)
    por_curto = {id(g): (d, s) for g, d, s in zip(curtos, direcoes, subs)}

    geradas = []
    for g in gerar:
        ini, fim, cordas = g
        ctx["rng"] = random.Random((ini * 2654435761 + len(cordas) * 97 + cordas[0]["nota"]) & 0xFFFFFFFF)
        if id(g) in por_curto:
            d, s = por_curto[id(g)]
            geradas += _um_acorde_espalhado(cordas, ini, d, s, ctx)
        else:
            fim_ef = min(fim, ed_tick) if ed_tick != float("inf") else fim
            geradas += _padrao_no_acorde(cordas, ini, fim_ef, ctx)

    todas = sozinhas + geradas
    if prender and ed_tick != float("inf"):
        for n in todas:
            n["ini"] = min(n["ini"], int(ed_tick) - 1)
            n["fim"] = max(n["fim"], n["ini"] + 1)
    _fechar_repeticoes(todas)
    eventos = []
    for n in todas:
        eventos.append((n["ini"], 1, mido.Message("note_on", channel=n["ch"], note=n["nota"], velocity=n["vel"])))
        eventos.append((n["fim"], 0, mido.Message("note_off", channel=n["ch"], note=n["nota"], velocity=0)))
    return eventos, len(geradas)
