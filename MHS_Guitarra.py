# -*- coding: utf-8 -*-
"""NTR "Guitar" do CASM (v2.0).

Com NTR = Guitar o ritmo não guarda as notas que soam: cada nota-fonte escolhe uma CORDA do violão (Wierzba/Bedesem,
Style Files v2.1, item 5.2.5.1) e a oitava da nota-fonte escolhe a POSIÇÃO no braço:

    B -> 1ª corda (mi agudo)   A -> 2ª corda (si)   G -> 3ª corda (sol)   F -> 4ª corda (ré)
    E -> 5ª corda (lá)         D -> 6ª corda (mi grave)   C -> a nota raiz   C# -> uma quinta
    a oitava da nota-fonte escolhe a posição no braço: notas 48-59 = 1ª posição, 60-71 = 2ª, 72-83 = 3ª, 84-95 = 4ª
    (números MIDI; C3 = 48 no nome usado pelo programa)

Quem toca (o teclado) transforma isso nas notas do acorde tocado. Este programa não tem a base de acordes do teclado,
então, para ouvir e para escrever, usa uma tabela fixa por posição: nota-fonte <-> nota que soa, para o acorde de origem.

Posição 1 (notas-fonte 48-59, as de Dó2 a Si2 no nome Yamaha): confirmada no teclado com o acorde de Dó maior
(Dó, Fá, Sol, Lá, Si -> C3, E3, G3, C4, E4, no nome do programa). As outras posições ainda não têm tabela: as notas
delas ficam como estão (nem convertidas, nem tocadas com tradução).
"""

# Posição -> (primeira nota-fonte da posição, {classe de altura da nota-fonte: nota que soa no acorde de Dó}).
# Mantenha o dicionário simples para completar as outras posições quando houver a captura do teclado.
POSICOES = {
    1: (48, {0: 48,      # C  -> raiz (5ª corda, casa 3)
             4: 48,      # E  -> 5ª corda (a raiz do acorde de Dó cai nela)
             5: 52,      # F  -> 4ª corda (casa 2)
             7: 55,      # G  -> 3ª corda (solta)
             9: 60,      # A  -> 2ª corda (casa 1)
             11: 64}),   # B  -> 1ª corda (solta)
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
    """Nota-fonte da guitarra -> nota que soa. Devolve a própria nota se ela está numa posição ainda sem tabela,
    e None se é uma corda que o acorde não usa ou um gatilho de ruído (96 ou mais): essas ficam mudas."""
    if nota >= LIMITE_RUIDOS:
        return None             # notas acima da 4ª posição: gatilhos de ruído de dedo/palheta, sem altura
    base, tabela = _posicao_da_fonte(nota)
    if base is None:
        return nota
    som = tabela.get(nota - base)
    return None if som is None else som + deslocamento


def som_para_fonte(nota, deslocamento=0):
    """Nota que soa -> nota-fonte da guitarra, ou None se não bate com nenhuma corda da tabela."""
    n = nota - deslocamento
    for pos, (base, tabela) in POSICOES.items():
        escolhida = None
        for classe, som in tabela.items():
            if som == n and (escolhida is None or classe == 0):
                escolhida = classe          # onde duas cordas dão a mesma nota (C e E), vale a raiz (C)
        if escolhida is not None:
            return base + escolhida
    return None
