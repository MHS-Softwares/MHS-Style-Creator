import math

# --- DESCOBRIR O ANDAMENTO PELA DURAÇÃO DOS ÁUDIOS ---
# Um loop de Audio Style é cortado em compassos inteiros: dura  compassos * tempos * 60 / BPM  segundos.
# Sabendo o compasso (4/4, por exemplo) e quantos compassos cada seção costuma ter, dá para fazer a conta
# ao contrário. Uma duração sozinha tem mais de uma resposta (4 compassos em 114 BPM dura o mesmo que
# 2 compassos em 57 BPM), mas vários áudios do mesmo estilo só concordam em um andamento - e as viradas
# (Fill In), que o Audio Phraser limita a 1 compasso, resolvem quase sempre.

BPM_MINIMO = 40.0
BPM_MAXIMO = 240.0
# Quanto uma duração pode fugir de um número inteiro de compassos (em compassos) e ainda contar.
TOLERANCIA = 0.03
# Faixa em que a maioria dos estilos está: fora dela, a candidata perde um pouco de força.
FAIXA_COMUM = (70.0, 190.0)


def compassos_provaveis(nome):
    # {número de compassos: peso} que uma seção com esse nome costuma ter num Audio Style.
    n = nome.strip().lower()
    if n.startswith("fill"):
        return {1: 1.0, 2: 0.3}
    if n.startswith("main"):
        return {4: 1.0, 2: 0.8, 8: 0.7, 1: 0.2, 3: 0.15, 6: 0.15, 16: 0.15}
    if n.startswith("intro"):
        return {2: 1.0, 4: 1.0, 1: 0.7, 8: 0.7, 3: 0.5, 6: 0.3}
    return {2: 1.0, 4: 1.0, 1: 0.7, 3: 0.6, 8: 0.6, 6: 0.3}


def _eh_ending(nome):
    return nome.strip().lower().startswith("ending")


def _tempos_por_compasso(numerador, denominador):
    # semínimas por compasso: 4/4 = 4, 3/4 = 3, 6/8 = 3
    return numerador * 4.0 / denominador


def _avaliar(bpm, duracoes, seminimas):
    # (pontuação, {seção: compassos}, quantas seções não-Ending não encaixaram)
    pontos, atribuicao, falhas = 0.0, {}, 0
    for nome, segundos in duracoes.items():
        compassos = segundos * bpm / (60.0 * seminimas)
        k = int(round(compassos))
        pesos = compassos_provaveis(nome)
        fim = _eh_ending(nome)
        # Ending costuma ter um rabo de som depois do último compasso: aceita sobra de até um compasso.
        if fim:
            k = int(math.floor(compassos + TOLERANCIA))
            ok = k in pesos and (compassos - k) < 1.0 - TOLERANCIA
        else:
            ok = k in pesos and abs(compassos - k) <= TOLERANCIA
        if ok:
            pontos += pesos[k] * (0.4 if fim else 1.0)
            atribuicao[nome] = k
        elif not fim:
            falhas += 1
    return pontos, atribuicao, falhas


def estimar_andamento(duracoes, numerador=4, denominador=4, maximo=4):
    """duracoes: {nome da seção: segundos}. Devolve até `maximo` candidatas, da mais para a menos provável:
    [{'bpm', 'pontos', 'compassos': {seção: n}, 'encaixam_todas': bool}]."""
    duracoes = {n: s for n, s in duracoes.items() if s and s > 0.2}
    if not duracoes:
        return []
    seminimas = _tempos_por_compasso(numerador, denominador)
    candidatas = []
    for nome, segundos in duracoes.items():
        for k in compassos_provaveis(nome):
            if _eh_ending(nome) and len(duracoes) > 1:
                continue  # o rabo do Ending faz a conta dele ser menos exata: só ajuda a conferir
            bpm = 60.0 * seminimas * k / segundos
            if BPM_MINIMO <= bpm <= BPM_MAXIMO:
                candidatas.append(bpm)
    resultados = []
    for bpm in sorted(set(round(c, 3) for c in candidatas)):
        pontos, atribuicao, falhas = _avaliar(bpm, duracoes, seminimas)
        if not atribuicao:
            continue
        # refina: o andamento que melhor casa as durações com os compassos escolhidos
        casadas = [n for n in atribuicao if not _eh_ending(n)] or list(atribuicao)
        total_seminimas = sum(atribuicao[n] * seminimas for n in casadas)
        total_segundos = sum(duracoes[n] for n in casadas)
        refinado = 60.0 * total_seminimas / total_segundos if total_segundos else bpm
        pontos, atribuicao, falhas = _avaliar(refinado, duracoes, seminimas)
        if not FAIXA_COMUM[0] <= refinado <= FAIXA_COMUM[1]:
            pontos *= 0.8
        resultados.append({'bpm': refinado, 'pontos': pontos, 'compassos': atribuicao, 'encaixam_todas': falhas == 0})
    # junta candidatas praticamente iguais, fica a de mais pontos
    resultados.sort(key=lambda r: (-r['pontos'], r['bpm']))
    finais = []
    for r in resultados:
        if all(abs(r['bpm'] - f['bpm']) / f['bpm'] > 0.004 for f in finais):
            finais.append(r)
    return finais[:maximo]


def arredondar_bpm(bpm):
    # 113,98 -> 114; 113,6 fica 113,6. Estilos quase sempre têm andamento inteiro.
    inteiro = round(bpm)
    return float(inteiro) if abs(bpm - inteiro) <= 0.08 else round(bpm, 1)


def texto_bpm(bpm):
    bpm = arredondar_bpm(bpm)
    return (f"{int(bpm)}" if bpm == int(bpm) else f"{bpm:.1f}".replace(".", ","))


def descrever(resultado):
    partes = [f"{nome} {n} {'compasso' if n == 1 else 'compassos'}" for nome, n in resultado['compassos'].items()]
    return ", ".join(partes)


def confianca(candidatas, n_audios):
    # 'alta' quando a melhor encaixa todas as seções e com folga sobre a segunda; senão 'baixa'.
    if not candidatas:
        return 'nenhuma'
    melhor = candidatas[0]
    if not melhor['encaixam_todas']:
        return 'baixa'
    tem_virada = any(n.strip().lower().startswith("fill") for n in melhor['compassos'])
    segunda = candidatas[1]['pontos'] if len(candidatas) > 1 else 0.0
    if (tem_virada or n_audios >= 3) and melhor['pontos'] >= segunda * 1.25:
        return 'alta'
    return 'baixa'
