# -*- coding: utf-8 -*-
"""Pedal de sustain SIMULADO ao tocar e gravar (v2.3).

O teclado Yamaha ignora o Sustain (CC64) dentro de um ritmo: um acorde de piano ou de violão gravado com o pedal
não sustenta. Aqui o pedal é traduzido em notas de verdade, com o note off no lugar certo, e o CC64 não é gravado.

Com o pedal pisado:
  - soltar a tecla NÃO manda o note off: a nota continua soando;
  - apertar de novo uma nota que ainda soa:
        violão/guitarra -> manda o note off dela e em seguida o note on (a corda é tocada outra vez; com um acorde
                           de 5 notas o NTR GTR, ou o Fixed com NTT Chord, forma o arrasto de dedos);
        piano           -> só o note on: as notas se acumulam, como nas cordas de um piano;
  - soltar o pedal manda o note off de todas as notas que já tinham a tecla solta (as que ainda estão com a tecla
    apertada continuam até você soltar).
Cada note on tem o seu note off (a conta é feita por nota), então o que fica gravado é sempre equilibrado.
"""
import mido

MODO_PIANO = 'piano'
MODO_VIOLAO = 'violao'
LIMITE_PEDAL = 64          # CC64 com valor 64 ou mais = pedal pisado


def _off(canal, nota):
    return mido.Message('note_off', channel=canal, note=nota, velocity=0)


class PedalSimulado(object):
    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.baixo = False
        self.soando = {}           # (canal, nota) -> note on mandados e ainda sem o note off
        self.solta_no_pedal = set()  # teclas soltas enquanto o pedal estava pisado (a nota segue soando)

    # ---------------------------------------------------------------------------------------------------------
    def pedal(self, valor):
        """Chegou um CC64. Devolve os note off que precisam sair agora (só ao SOLTAR o pedal)."""
        pisado = valor >= LIMITE_PEDAL
        if pisado == self.baixo:
            return []
        self.baixo = pisado
        if pisado:
            return []
        saida = []
        for (canal, nota) in sorted(self.solta_no_pedal):
            for _ in range(self.soando.pop((canal, nota), 0)):
                saida.append(_off(canal, nota))
        self.solta_no_pedal.clear()
        return saida

    def processar(self, msg, modo):
        """Uma nota tocada. 'modo' é MODO_PIANO ou MODO_VIOLAO. Devolve a lista de mensagens que realmente saem
        (gravação e eco para o teclado). Mensagens que não são notas passam como estão."""
        if msg.type not in ('note_on', 'note_off'):
            return [msg]
        chave = (msg.channel, msg.note)
        if msg.type == 'note_on' and msg.velocity > 0:
            saida = []
            ainda_soa = self.soando.get(chave, 0) > 0
            if ainda_soa and self.baixo and modo == MODO_VIOLAO:
                # a corda é tocada de novo: o note off da anterior sai antes do note on
                for _ in range(self.soando.pop(chave)):
                    saida.append(_off(*chave))
            self.solta_no_pedal.discard(chave)       # a tecla voltou a estar apertada
            self.soando[chave] = self.soando.get(chave, 0) + 1
            saida.append(msg)
            return saida
        # note off (ou note on com velocity 0)
        if self.soando.get(chave, 0) > 0:
            if self.baixo:
                self.solta_no_pedal.add(chave)       # segura: só sai quando soltar o pedal
                return []
            saida = [_off(*chave) for _ in range(self.soando.pop(chave))]
            return saida
        return [msg]

    def soltar_tudo(self):
        """Todos os note off pendentes de uma vez (parar, mudar o modo, pânico). Zera o estado."""
        saida = []
        for (canal, nota), n in sorted(self.soando.items()):
            for _ in range(n):
                saida.append(_off(canal, nota))
        self.reiniciar()
        return saida
