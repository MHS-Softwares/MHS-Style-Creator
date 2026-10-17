# -*- coding: utf-8 -*-
"""NTR "Guitar" do CASM (v2.0).

Com NTR = Guitar o ritmo não guarda as notas que soam: cada nota-fonte escolhe uma CORDA do violão (Wierzba/Bedesem,
Style Files v2.1, item 5.2.5.1) e a oitava da nota-fonte escolhe a POSIÇÃO no braço:

    B -> 1ª corda (mi agudo)   A -> 2ª corda (si)   G -> 3ª corda (sol)   F -> 4ª corda (ré)
    C -> a nota raiz           C# -> uma quinta (abaixo ou acima, conforme a posição)
    (E e D, as cordas graves, e as notas com sustenido/bemol fora o C#, não soam no acorde de Dó)
    notas 48-59 = 1ª posição, 60-71 = 2ª, 72-83 = 3ª, 84-95 = 4ª (números MIDI; C3 = 48 no nome usado pelo programa)
    notas de 96 em diante: gatilhos de ruído de dedo/palheta, sem altura

Quem toca (o teclado) transforma isso nas notas do acorde tocado. Este programa não tem a base de acordes do teclado,
então usa uma tabela fixa por posição (nota-fonte <-> nota que soa) para o acorde de origem.

A tabela vem de uma captura REAL do teclado: um ritmo com a escala cromática nas 4 posições (uma por compasso) no canal
Chord 1, tocado com o acorde de Dó e gravado em MIDI (H:\\Modo GTR.sty e H:\\GTR.mid). As cordas aparecem como
inversões do acorde subindo: posição 1 = E G C E, posição 2 = G C E G, posição 3 = C E G C, posição 4 = E G C E (oitava
acima), sempre com a raiz C3 no grave.
"""

# Posição -> (primeira nota-fonte da posição, {classe de altura da nota-fonte: nota que soa no acorde de Dó}).
POSICOES = {
    1: (48, {0: 48, 1: 43, 5: 52, 7: 55, 9: 60, 11: 64}),
    2: (60, {0: 48, 1: 43, 5: 55, 7: 60, 9: 64, 11: 67}),
    3: (72, {0: 48, 1: 55, 5: 60, 7: 64, 9: 67, 11: 72}),
    4: (84, {0: 48, 1: 55, 5: 64, 7: 67, 9: 72, 11: 76}),
}

# Os ritmos de guitarra usam notas acima da 4ª posição (C7 = 96 em diante: C7, D7, E7, F#7, A#7, C#8 nos ritmos
# conferidos) como gatilhos de ruído de dedo/palheta. Não têm altura de acorde: o programa não as toca.
LIMITE_RUIDOS = 96

NOMES_RAIZ = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']


def deslocamento_da_raiz(nome_ou_indice):
    """Semitons da raiz do acorde de origem em relação a Dó (0 = Dó)."""
    if isinstance(nome_ou_indice, int):
        return nome_ou_indice % 12
    try:
        return NOMES_RAIZ.index(nome_ou_indice)
    except ValueError:
        return 0


def _posicao_da_fonte(nota):
    for pos, (base, tabela) in POSICOES.items():
        if base <= nota < base + 12:
            return base, tabela
    return None, None


def fonte_para_som(nota, deslocamento=0):
    """Nota-fonte da guitarra -> nota que soa. Devolve a própria nota se ela está abaixo da 1ª posição, e None se é
    uma corda que o acorde não usa ou um gatilho de ruído (96 ou mais): essas ficam mudas."""
    if nota >= LIMITE_RUIDOS:
        return None
    base, tabela = _posicao_da_fonte(nota)
    if base is None:
        return nota
    som = tabela.get(nota - base)
    return None if som is None else som + deslocamento


def escolher_posicao(notas_que_soam, deslocamento=0):
    """A posição (1 a 4) cuja tabela reproduz o maior número das notas dadas (as notas que soam do canal, numa
    seção). Empate: a posição mais baixa."""
    melhor, pontos = 1, -1
    for pos, (_base, tabela) in POSICOES.items():
        sons = {s + deslocamento for s in tabela.values()}
        marcou = sum(1 for n in notas_que_soam if n in sons)
        if marcou > pontos:
            melhor, pontos = pos, marcou
    return melhor


def som_para_fonte(nota, deslocamento=0, posicao=None):
    """Nota que soa -> nota-fonte da guitarra, usando preferencialmente a 'posicao' (1 a 4). Devolve None se a nota
    não bate com nenhuma corda da tabela. Onde duas cordas dão a mesma nota, vale a raiz (C)."""
    n = nota - deslocamento
    ordem = list(POSICOES)
    if posicao in POSICOES:
        ordem.sort(key=lambda p: (p != posicao, abs(p - posicao)))
    for pos in ordem:
        base, tabela = POSICOES[pos]
        classes = [c for c, som in tabela.items() if som == n]
        if classes:
            return base + (0 if 0 in classes else classes[0])
    return None
