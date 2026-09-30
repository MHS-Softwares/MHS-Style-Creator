# MHS Style Creator

Editor acessível de estilos/ritmos (`.sty`, `.prs`, `.cte`) para teclados
Yamaha, feito para funcionar **100% por teclado**, com retorno falado em
praticamente toda ação. Pensado desde o início para músicos cegos e com
baixa visão: nenhuma função depende de enxergar a tela, de mouse, ou de
cores.

Diferente de um sequenciador comum, um "estilo" da Yamaha não é uma
música com início e fim fixos - é um conjunto de **seções** curtas em
loop (Intro, Main A/B/C/D, Fill, Ending) que o teclado encadeia ao vivo,
transpondo automaticamente conforme o acorde tocado na mão esquerda. É
essa transposição automática - as regras de **CASM** - que faz um estilo
soar "certo" em qualquer tom. O MHS Style Creator edita tanto o conteúdo
musical de cada seção quanto essas regras.

## O que dá pra fazer

- Criar e editar seções, gravar e editar notas por canal.
- Montar e editar efeitos de DSP (Reverb, Chorus, Variation/Insertion).
- Afinar peças de bateria nota a nota (Drum Setup, inclusive via NRPN).
- Criar timbres próprios (Voice Creator).
- Editar as regras de transposição por acorde (CASM) com controle fino
  por faixa de nota.
- Quantizar, humanizar, aplicar arpejador/delay/harpa/presets de bateria.
- Copiar conteúdo entre seções e entre canais - inclusive entre arquivos
  diferentes, com conversão automática de resolução (ticks por beat).
- Converter estilos SFF1 para SFF2, alterar LSB (Bank Select) de ritmos
  individualmente ou em massa, e mais ferramentas de manutenção de
  arquivo.

O manual completo (`Manual do MHS Style Creator.txt`) documenta cada tela
e atalho de teclado em detalhe.

## Instalação

Requer Python 3 e as dependências em `requirements.txt`:

```bash
pip install -r requirements.txt
python main.py
```

Um `.sty`/`.prs`/`.cte` pode ser passado como argumento (ou associado à
extensão no Windows) para abrir direto.

## Sobre este projeto

Este programa é feito e mantido por um músico cego, para músicos com
deficiência visual que trabalham com teclados arranjadores Yamaha. Se ele
ajudar no seu trabalho e você quiser reconhecer/incentivar o
desenvolvimento, uma contribuição via Pix ou PayPal é sempre bem-vinda:

- **Chave Pix (e-mail):** michel.teclado@gmail.com
- **PayPal (e-mail):** michel.teclado@gmail.com
- **Destinatário:** Michel Henrique da Silva

## Licença

Nenhuma licença de código aberto foi concedida sobre este repositório -
todos os direitos são reservados ao autor. O código é público para
consulta e uso pessoal, mas redistribuir, revender ou publicar versões
modificadas não é permitido sem autorização.

## Aviso importante

O autor só dá suporte e se responsabiliza pelo instalador **oficial**,
disponibilizado na aba [Releases](https://github.com/MHS-Softwares/MHS-Style-Creator/releases)
deste repositório. Cópias obtidas por qualquer outro meio - sites de
terceiros, redes sociais, pendrive, e-mail, ou qualquer versão
recompilada/modificada por outra pessoa - não têm garantia nenhuma de
segurança ou de funcionamento correto, e o autor não tem como saber o
que foi alterado nelas.
