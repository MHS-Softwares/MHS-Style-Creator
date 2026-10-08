import wx
import mido
import threading
import time
import json
import os
import re
import copy
from MHS_Utils import (
    falar, YAMAHA_SECTION_ORDER,
    TOTAL_CANAIS, CANAL_BATERIA_1, CANAL_BATERIA_2,
    CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION,
    CC_SUSTAIN, CC_REVERB, CC_CHORUS, CC_ALL_NOTES_OFF,
    NOTA_METRONOMO_FORTE, NOTA_METRONOMO_FRACA, CANAL_METRONOMO,
    VALOR_MAX_MIDI, VALOR_MIN_MIDI, rotulo_canal,
    REV_MSB_LIST, CHO_MSB_LIST, VARIATION_EFEITOS_LIST,
    OFFSETS_VAR_2BYTES, OFFSETS_VAR_1BYTE,
    OFFSETS_REV_PARAMS, OFFSETS_CHO_PARAMS, REV_PARAM_INDEX, CHO_PARAM_INDEX,
    DRUM_NRPN_MSBS, verificar_nova_versao, verificar_nova_versao_detalhado,
    mesclar_tracks_rapido, nomes_portas_midi, limpar_cache_portas_midi,
    ativar_cache_portas_midi
)
from MHS_Dialogs import (SectionLengthDialog, StyleSettingsDialog,
                         QuantizacaoRealTimeDialog, QuantizarOfflineDialog, VelocityControlDialog,
                         MidiRouterDialog, SettingsDialog, GlobalDSPDialog,
                         SelecionarEfeitoVariationDialog, EditorParametrosVariationDialog,
                         ExportarCanalDialog, CopiarCanalEntreSecoesDialog, ClonarConfigCanalDialog, FadeDialog,
                         VoiceCreatorDialog, VOICE_CREATOR_ADDRS, VOICE_CREATOR_ADDRS_0A, MidiEffectsDialog, BATERIA_PRESETS,
                         ChangelogDialog, AlterarLSBDialog, oferecer_atualizacao)
from MHS_EventList import EventListDialog
from MHS_CasmEdit import SectionCasmDialog
from MHS_MidiEngine import MidiEngine
from MHS_DrumSetup import DrumSetupDialog

# Número da versão do app - um lugar só pra atualizar a cada release (título
# da janela, fala de abertura, e a tela de Changelog que aparece sozinha na
# primeira vez que essa versão é aberta, ver mostrar_changelog_se_necessario).
VERSAO_APP = "1.9.1"

# Nome do repositório no GitHub (github.com/MHS-Softwares/<REPO_GITHUB>) -
# usado por verificar_atualizacoes_ao_iniciar / SettingsDialog pra consultar
# a Release mais recente e comparar com VERSAO_APP.
REPO_GITHUB = "MHS-Style-Creator"

# Texto da tela de Changelog (ver mostrar_changelog_se_necessario) - embutido
# no código em vez de lido do Manual (um .txt separado) de propósito: essa
# tela é a PRIMEIRA coisa que o usuário vê depois de atualizar, e não pode
# depender de um arquivo externo que talvez não tenha sido empacotado junto
# no instalador. A cada nova versão, acrescente uma entrada nova aqui (mais
# curta/direta que a do Manual, pensada pra ser OUVIDA, não só lida) - o
# convite pra contribuir (MENSAGEM_APOIO) é comum a todas as versões.
MENSAGEM_APOIO = (
    "\n\n---\n\n"
    "Se este programa está ajudando você no seu trabalho, considere uma coisa:\n\n"
    "Ele é feito, do zero, por um músico cego - pensado pra funcionar 100% por "
    "teclado e leitor de tela, sem depender de enxergar nada na tela. Cada "
    "correção e cada recurso novo sai de muitas horas de trabalho voluntário, "
    "pensando em você e em outros músicos com deficiência visual que também "
    "precisam de uma ferramenta assim.\n\n"
    "Se puder, considere fazer uma contribuição via Pix, de qualquer valor - é "
    "um jeito simples de reconhecer esse trabalho e ajudar a mantê-lo vivo, "
    "sempre recebendo correções e novidades.\n\n"
    "Chave Pix (e-mail): michel.teclado@gmail.com\n"
    "Destinatário: Michel Henrique da Silva\n\n"
    "Qualquer valor já faz muita diferença. Muito obrigado por usar o MHS "
    "Style Creator!"
)

CHANGELOG_TEXTS = {
    "1.9.1": (
        "- Corrigido: depois de baixar a atualização pela janela de "
        "atualização, ao responder Sim em \"Deseja instalar agora?\" o "
        "programa fechava mas o instalador não abria (o arquivo ficava "
        "só na pasta Downloads). Agora o instalador abre de verdade. "
        "Se você recusar fechar o programa (por exemplo no \"salvar "
        "antes de sair\"), nada é instalado, como antes."
        "\n\n- Correção sugerida por Gabriel Schuck (@gabrielschuck), "
        "obrigado!"
    ),
    "1.9": (
        "- Corrigido: o instalador baixado pela janela de atualização "
        "agora é salvo na pasta Downloads que o Windows informa, e não "
        "numa pasta Downloads presumida dentro da pasta do usuário. Se "
        "você mudou o local da pasta Downloads (OneDrive, outra "
        "partição, outro disco), o arquivo antes ia parar num lugar onde "
        "você não procurava e a instalação não abria; agora vai para a "
        "sua pasta Downloads de verdade."
    ),
    "1.8": (
        "- Corrigido: o CASM de uma seção que existe no arquivo mas nunca "
        "teve bloco CASM próprio (ex.: uma Intro A criada por você num "
        "ritmo de outro programador que só tinha Intro B e C) não era "
        "gravado. A tela de Editar Seção reabria certinha (o valor ficava "
        "na memória), mas ao salvar o arquivo e reabrir, nada tinha sido "
        "gravado - nem exportando o CASM de outra seção pra ela. Agora o "
        "programa cria o bloco CASM da seção na hora de salvar, com os "
        "canais que você mexeu ou que têm nota, no mesmo formato que o "
        "arquivo já usa (Ctab em ritmo SFF1, Ctb2 nos outros).\n\n"
        "- Corrigido: criar uma seção nova num ritmo SFF1 plantava por "
        "cima dele uma identidade SFF2 completa (marcador SFF2 mais os "
        "SysEx de abertura repetidos), deixando o arquivo com os dois "
        "marcadores e tudo duplicado no começo. Isso não acontece mais, "
        "e ao abrir um ritmo SFF1 que já ficou assim, o programa remove "
        "sozinho a duplicata e avisa (é só salvar para gravar).\n\n"
        "- Corrigido: em ritmo SFF1, um canal que ganhava registro CASM "
        "novo dentro de um bloco já existente nascia no formato SFF2 "
        "(Ctb2), misturando os dois formatos no mesmo arquivo.\n\n"
        "- Novo: a janela de atualização agora baixa o instalador da "
        "nova versão direto por ela, sem abrir página nenhuma. O botão "
        "\"Baixar e instalar\" avisa o progresso por voz, confere a "
        "integridade do arquivo e, ao terminar, pergunta se você quer "
        "instalar agora (o programa fecha e abre o instalador). Se "
        "preferir não instalar na hora, o arquivo fica na sua pasta "
        "Downloads.\n\n"
        "- Mais rápido: abrir um ritmo (.sty) ficou cerca de 2,5 vezes mais "
        "rápido (de 100-240 ms para 40-90 ms num ritmo típico) - o programa "
        "gastava a maior parte do tempo reorganizando uma trilha única que "
        "já vinha pronta. A abertura do programa também ficou um pouco mais "
        "leve, listando os dispositivos MIDI uma vez só em vez de três."
    ),
    "1.6": (
        "- Novo: botão \"Baixar da Internet...\" na aba Instrumentos de "
        "Configurações Gerais (Ctrl+P). O programa procura no site "
        "jososoft.dk a lista de teclados Yamaha que têm arquivo .ins "
        "disponível e mostra pra você escolher o seu (dá pra digitar o nome "
        "pra ir direto). É só apertar Enter, ou dar Tab até o botão Baixar: "
        "o programa baixa, avisa tudo por voz, salva numa pasta chamada "
        "\"Ins files\" ao lado do programa e já deixa o arquivo escolhido "
        "como instrumento - só falta clicar em OK."
    ),
    "1.5": (
        "- Corrigido um bug grave no Drum Setup: o kit de bateria montado "
        "na \"Montagem de Kit\" (e às vezes os ajustes da \"Edição e "
        "Filtros SysEx\") podia se desfazer sozinho assim que o loop de "
        "uma seção dava a volta - em qualquer canal de bateria cuja seção "
        "resselecione o próprio Banco/Patch. Causa: o Program Change que "
        "resseleciona o kit sempre era reenviado a cada repetição do "
        "loop (resetando a afinação por nota no teclado real), mas o "
        "SysEx que deveria desfazer esse reset logo em seguida podia "
        "ficar de fora de uma otimização que evita reenviar sysex "
        "repetido - agora o SysEx de Drum Setup nunca entra nessa "
        "otimização, sempre acompanhando o Program Change em toda "
        "passagem. Reabrir o Drum Setup, trocar de aba, ou dar Stop e "
        "Play de novo escondia o problema temporariamente (reaplicavam "
        "tudo do zero) - só a virada natural do loop expunha o bug.\n\n"
        "- Corrigido um segundo bug, também no Drum Setup: dentro da "
        "própria tela, na aba \"Montagem de Kit\", só de ajustar o Banco/"
        "Patch/Peça Doadora de UMA peça (mesmo sem clicar \"Aplicar "
        "Mapeamento\") já podia desfazer, no teclado real, a afinação de "
        "QUALQUER OUTRA peça já confirmada antes nesse mesmo canal "
        "(ex.: montar a Caixa, aplicar, e só de mexer nos controles do "
        "Bumbo em seguida, a Caixa \"voltava\" pro kit padrão). Causa: a "
        "pré-audição do kit doador reseleciona o Banco/Patch do canal "
        "duas vezes (pra tocar e pra voltar), e isso reseta a afinação "
        "por nota inteira no teclado real - sem reaplicar depois o que "
        "já tinha sido confirmado. Os dados nunca se perdiam (por isso "
        "reabrir a tela sempre mostrava tudo certo), só o SOM ao vivo "
        "ficava errado até fechar e reabrir a tela de novo."
    ),
    "1.4": (
        "- Novo: aba \"Atualizações\" em Configurações Gerais (Ctrl+P) - "
        "caixa de marcação \"Verificar atualizações automaticamente ao "
        "iniciar o programa\" (ligada por padrão) e um botão \"Procurar "
        "Atualizações Agora\", disponível sempre. Ao achar uma versão mais "
        "nova publicada no GitHub, pergunta se quer abrir a página de "
        "download.\n\n"
        "- Novo: aba \"Pastas de Trabalho\" em Configurações Gerais - agora "
        "dá pra fixar uma pasta padrão pra Abrir e outra pra Salvar (dois "
        "campos, com botão pra escolher cada uma). Deixando em branco, "
        "continua como sempre foi: o programa lembra sozinho a última "
        "pasta usada.\n\n"
        "- Novo: menu Ajuda, com \"Novidades desta Versão...\" (reabre esta "
        "mesma tela sob demanda) e \"Ir para a Página do Projeto\" (abre o "
        "repositório no GitHub no navegador).\n\n"
        "- Corrigido: abrir Configurações Gerais e confirmar com OK "
        "apagava, sem querer, qualquer outra informação guardada no "
        "arquivo de configuração que não fosse dessa própria tela - entre "
        "elas, a marca de \"já mostrei o Changelog desta versão\", fazendo "
        "esta tela reaparecer sozinha toda vez que o programa era reaberto "
        "depois de mexer em qualquer preferência."
    ),
    "1.3": (
        "- Novo: duas ferramentas de LSB (Bank Select), no menu "
        "Ferramentas - pensadas pra quem usa ritmos de vários programadores/"
        "pacotes de expansão diferentes e às vezes esbarra em dois pacotes "
        "usando o mesmo LSB.\n\n"
        "- \"Alterar LSB do Ritmo Atual\": mostra quais LSBs o estilo aberto "
        "está usando agora (e em quais canais) e deixa você trocar - só as "
        "ocorrências de um LSB de origem específico, ou todas de uma vez, "
        "você escolhe.\n\n"
        "- \"Alterar LSB de Ritmos em Massa\": escolha vários arquivos de "
        "uma vez (.sty/.prs/.cte) na caixa de diálogo padrão do Windows, o "
        "programa mostra quantos usam cada LSB encontrado, você escolhe pra "
        "qual LSB trocar (e se é só uma origem específica ou tudo), e ao "
        "final mostra quantos arquivos foram alterados. Cada arquivo ganha "
        "um backup automático antes de ser tocado.\n\n"
        "- Corrigido: Copiar/Colar entre arquivos diferentes (abas) com "
        "resoluções diferentes (ticks por beat) distorcia o andamento do "
        "trecho colado - colar um trecho copiado de um arquivo em 1920 "
        "ticks por beat dentro de outro em 480, por exemplo, fazia esse "
        "trecho tocar 4x mais devagar (como se o BPM tivesse caído de 84 "
        "pra 21). Agora o Colar converte a resolução automaticamente - o "
        "andamento musical do trecho colado se mantém correto, não importa "
        "a resolução de cada arquivo.\n\n"
        "- Corrigido: o mesmo problema de resolução (ticks por beat) "
        "diferente também acontecia em \"Copiar Canal Entre Seções...\" "
        "(Ctrl+Alt+E) - essa ferramenta tem seu próprio código, separado "
        "do Colar, então precisou do mesmo ajuste à parte. Também corrigia "
        "só o andamento, mas cortava o final do trecho copiado sem querer "
        "(a checagem de \"cabe na seção de destino?\" usava os ticks ainda "
        "não convertidos) - agora, além do andamento certo, nenhum pedaço "
        "do trecho copiado se perde.\n\n"
        "- Corrigido: a PRIMEIRA vez que uma seção (tipicamente a Main A) "
        "precisava de uma entrada própria de CASM - seja copiando um canal "
        "pra ela (Ctrl+Alt+E) ou confirmando uma edição em Editar Seção - "
        "o programa reiniciava os 16 canais pro padrão de fábrica antes de "
        "aplicar a edição de só 1 deles, jogando fora qualquer configuração "
        "real que os outros 15 canais já tivessem (achado com o Michel: o "
        "\"Toca Sem Acorde\" de Rhythm1/Rhythm2 voltando sozinho, sem ele "
        "ter mexido nesses 2 canais). Agora, quando a seção é a Main A, a "
        "configuração real já carregada é preservada - só o canal "
        "realmente editado muda; outras seções continuam nascendo limpas "
        "(sem herdar resíduo da Main A), como já era."
    ),
    "1.2": (
        "- Corrigido um bug grave: gravar com uma seção em loop, deixando o "
        "loop dar a volta inteira com a gravação armada, podia corromper "
        "outras seções sem nenhuma relação com a que estava sendo gravada. "
        "Resolvido na raiz - as duas gravações que podiam brigar entre si "
        "agora nunca mais rodam ao mesmo tempo.\n\n"
        "- Corrigido: Apagar, Copiar, Recortar e Colar falavam o dobro da "
        "quantidade real de notas.\n\n"
        "- Corrigido: Copiar, Recortar e Apagar podiam levar ou apagar, sem "
        "querer, a configuração de mixagem plantada no início da seção, ou "
        "arrancar o desligamento da última nota sustentada da seção "
        "anterior, deixando ela tocando pra sempre.\n\n"
        "- Novo: ferramenta \"Verificar e Corrigir Notas Cruzando Seções\", "
        "no menu Ferramentas.\n\n"
        "- Novo: a última seção do arquivo agora tem a duração travada "
        "automaticamente ao abrir o arquivo, sem precisar de nenhuma ação "
        "manual.\n\n"
        "- Corrigido um efeito colateral real no SX600: ir para o Ending 1 "
        "podia ficar loopando a virada em vez de seguir pro Ending.\n\n"
        "- Corrigido: reabrir um arquivo já certinho podia marcar "
        "\"modificado\" à toa, mesmo sem nada ter mudado de verdade.\n\n"
        "- Corrigido: Colar numa seção menor que o trecho copiado (ou numa "
        "seção que ainda nem existia no arquivo) simplesmente não colava "
        "nada. Agora cola o que couber - criando a seção com 1 compasso "
        "quando for preciso - sem nunca deixar nota presa na borda do "
        "corte.\n\n"
        "- Novo: pasta padrão de Abrir/Salvar - uma subpasta \"MHS Style "
        "Creator\" dentro da sua pasta Músicas do Windows, igual ao MHS MIDI "
        "Sequencer já fazia."
    ),
}

# Layout do registro Ctb2 (47 bytes) do CASM, confirmado pela documentação
# real do formato (Peter Wierzba / Michael P. Bedesem, "Style Files -
# Introduction and Details", v2.1) e batido byte a byte com o que já
# tínhamos descoberto na marra pelo SX. O bloco do Ctb2 (a partir do byte 20
# do registro) é dividido em até 3 "zonas" de nota - grave/média/aguda -,
# cada uma com sua própria sub-estrutura de 6 bytes (NTR, NTT, High Key,
# Limite Grave, Limite Agudo, RTR = Retrigger Rule):
#   byte 20 = fim da Zona Grave / início da Zona Média (0 = Zona Grave
#             desligada - é o caso normal quase sempre)
#   byte 21 = fim da Zona Média / início da Zona Aguda = "Zona Aguda Início"
#   bytes 22-27 = sub-estrutura da ZONA GRAVE (NTR, NTT, High Key, Low
#                 Limit, High Limit, RTR) - normalmente inerte (byte 20 = 0)
#   bytes 28-33 = sub-estrutura da ZONA MÉDIA (a mais usada) - NTR/NTT/High
#                 Key/Low Limit/High Limit/RTR
#   bytes 34-39 = sub-estrutura da ZONA AGUDA - NTR/NTT/High Key/Low
#                 Limit/High Limit/RTR
#   bytes 40-46 = únicos 7 bytes que a própria documentação admite não saber
#                 ao certo (relacionados a canais de bateria/efeito extra de
#                 break) - só o byte 45 sobrou sem tela dedicada aqui
#   byte 18 = "Source Chord" (nota fundamental) - documentado na própria
#             v2.1 (item 4.6.3.3, tabela 12): "Determines the original key
#             of the source channel together with the following byte (i.e.
#             the key used when recording the source channel)". Um antigo
#             comentário nesta função (linha ~925 à época) achava, com base
#             em só 3 arquivos comparados, que esse byte era sempre 0 - um
#             ritmo real do Alex Oliveira ("19. Ze Ramalho 1.STY") provou
#             essa conclusão errada: 3 seções dele (Intro A, Main A, Fill
#             In AA) têm esse byte = 05H (Fá) em vez de 00H (Dó, o padrão) -
#             é assim que o teclado sabe transpor essas 3 seções (compostas
#             em Fá) de volta pra Dó na hora de tocar.
#   byte 19 = "Source Chord Type" (tipo do acorde de origem) - o par do
#             byte 18, mesma tabela 12. Praticamente sempre 02H (Maj7) - é
#             o "CMaj7" citado como padrão de fábrica pela própria
#             documentação - mas tecnicamente qualquer um dos 35 tipos de
#             acorde documentados é válido aqui.
#
# O RTR (Retrigger Rule) é o campo que decide como uma nota SUSTENTADA se
# comporta quando o acorde do ACMP muda no meio dela - foi o byte 33 (RTR da
# Zona Média) que a gente isolou empiricamente antes de achar a
# documentação, como o responsável pelo "desliza suave (glide) ou é
# cortada". Valores documentados:
#   stop               = a nota é simplesmente parada (causa o "corte")
#   pitch shift        = desliza de altura SEM reataque, pro tipo do novo
#                        acorde - "comum na maioria das faixas"; o que o
#                        Michel confirmou preferir no Gtr+Chord
#   pitch shift to root = desliza sem reataque, pra FUNDAMENTAL do novo
#                        acorde - "comum na faixa de baixo"
#   retrigger          = a nota é REATACADA numa nova altura pro tipo do
#                        acorde - "só para uso especial"
#   retrigger to root  = reataca pra FUNDAMENTAL do novo acorde - valor do
#                        canal Bass no Balada/AcusticoBR4
#   note generator     = só existe se programado no arquivo original
RTR_OPCOES = ['stop', 'pitch shift', 'pitch shift to root', 'retrigger', 'retrigger to root', 'note generator']

# Byte 18 do Ctb2 ("Source Chord") - a nota fundamental, valores 00H..0BH.
SOURCE_CHORD_ROOT_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']

# Byte 19 do Ctb2 ("Source Chord Type") - o tipo do acorde, valores
# 00H..22H, na ordem EXATA da tabela 12 da documentação (índice = valor do
# byte).
SOURCE_CHORD_TYPE_NAMES = [
    'Maj', 'Maj6', 'Maj7', 'Maj7#11', 'Maj(9)', 'Maj7(9)', 'Maj6(9)', 'aug',              # 00-07
    'min', 'min6', 'min7', 'min7b5', 'min(9)', 'min7(9)', 'min7(11)', 'minMaj7',           # 08-0F
    'minMaj7(9)', 'dim', 'dim7', '7th', '7sus4', '7b5', '7(9)', '7#11',                    # 10-17
    '7(13)', '7(b9)', '7(b13)', '7(#9)', 'Maj7aug', '7aug', '1+8', '1+5',                  # 18-1F
    'sus4', '1+2+5', 'cancel',                                                             # 20-22
]

# Único byte do Ctb2 que continua sem tela dedicada - a própria documentação
# admite não saber ao certo o que ele faz (só que costuma ficar em 0, exceto
# em alguns canais de bateria). Exposto como "Byte 45" no fim da lista de
# CASM de Editar Seção, só pra o Michel poder testar no SX se quiser -
# só é escrito de volta se ele de fato mudar o valor.
BYTES_CASM_DESCONHECIDOS = (45,)


def nome_prop_byte(indice_byte):
    return f"Byte {indice_byte}"


class TempoEnvelopeDialog(wx.Dialog):
    def __init__(self, parent, current_bpm):
        super().__init__(parent, title="Envelope de Tempo / BPM", size=(400, 300))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        lbl1 = wx.StaticText(self, label="BPM Inicial (Alteração Brusca):")
        self.txt_bpm1 = wx.TextCtrl(self, value=str(current_bpm))
        self.cb_gradual = wx.CheckBox(self, label="Alteração de tempo gradual")
        lbl2 = wx.StaticText(self, label="BPM Final (Alvo da Ralentada/Acelerada):")
        self.txt_bpm2 = wx.TextCtrl(self, value=str(current_bpm))
        self.txt_bpm2.Disable()
        self.cb_gradual.Bind(wx.EVT_CHECKBOX, self.on_check_gradual)
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        self.sizer.Add(lbl1, 0, wx.ALL, 5)
        self.sizer.Add(self.txt_bpm1, 0, wx.EXPAND | wx.ALL, 5)
        self.sizer.Add(self.cb_gradual, 0, wx.ALL, 5)
        self.sizer.Add(lbl2, 0, wx.ALL, 5)
        self.sizer.Add(self.txt_bpm2, 0, wx.EXPAND | wx.ALL, 5)
        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(self.sizer)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)
    def on_init_dialog(self, event):
        event.Skip()
        self.txt_bpm1.SetFocus()
    def on_check_gradual(self, event):
        if self.cb_gradual.GetValue():
            self.txt_bpm2.Enable()
            self.txt_bpm2.SetFocus()
        else:
            self.txt_bpm2.Disable()
            self.txt_bpm1.SetFocus()
    def get_values(self):
        return int(self.txt_bpm1.GetValue()), self.cb_gradual.GetValue(), int(self.txt_bpm2.GetValue())

class HumanizeDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Humanizar (Variação Aleatória em Tempo Real)", size=(400, 250))
        self.parent = parent
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        sz_time = wx.BoxSizer(wx.HORIZONTAL)
        sz_time.Add(wx.StaticText(self, label="Variação de Tempo Máxima (ms):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sp_time = wx.SpinCtrl(self, value="10", min=0, max=500)
        sz_time.Add(self.sp_time, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Add(sz_time, 0, wx.EXPAND | wx.ALL, 5)

        sz_vel = wx.BoxSizer(wx.HORIZONTAL)
        sz_vel.Add(wx.StaticText(self, label="Variação de Velocity Máxima (+/-):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sp_vel = wx.SpinCtrl(self, value="10", min=0, max=127)
        sz_vel.Add(self.sp_vel, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Add(sz_vel, 0, wx.EXPAND | wx.ALL, 5)

        lbl_info = wx.StaticText(self, label="Barra de Espaço toca/para o preview, igual nas outras telas.\nOK confirma exatamente o que está tocando agora.")
        self.sizer.Add(lbl_info, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(self.sizer)

        self.original_cache = [m.copy() for m in self.parent.merged_track_cache]

        self.sp_time.Bind(wx.EVT_SPINCTRL, self.on_slider_change)
        self.sp_time.Bind(wx.EVT_TEXT, self.on_slider_change)
        self.sp_vel.Bind(wx.EVT_SPINCTRL, self.on_slider_change)
        self.sp_vel.Bind(wx.EVT_TEXT, self.on_slider_change)
        self.timer_debounce = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.executar_preview, self.timer_debounce)
        self.Bind(wx.EVT_CLOSE, self.on_cancelar)
        self.Bind(wx.EVT_BUTTON, self.on_cancelar, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_INIT_DIALOG, self.on_init_dialog)

    def on_init_dialog(self, event):
        event.Skip()
        self.sp_time.SetFocus()

    def on_slider_change(self, event):
        self.timer_debounce.Start(100, oneShot=True)
        event.Skip()

    def on_key(self, event):
        code = event.GetKeyCode()
        # Barra de espaço = Tocar/Parar, Ctrl+Espaço = Tocar/Pausar - o mesmo
        # esquema já usado no editor de DSP (MHS_Dialogs.py) e no Drum Setup
        # (MHS_DrumSetup.py), pra poder ouvir o preview sem fechar essa tela.
        if code == wx.WXK_SPACE:
            if event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePause(None)
                return
            if not event.ControlDown() and not event.AltDown() and not event.ShiftDown():
                self.parent.OnTogglePlay(None)
                return
        event.Skip()

    def on_cancelar(self, event):
        # Cancelar (botão ou X da janela) tem que cancelar de verdade -
        # desfaz qualquer preview que já tenha sido aplicado ao vivo, em vez
        # de deixar o último preview "vazar" como se tivesse sido confirmado.
        self.parent.merged_track_cache = [m.copy() for m in self.original_cache]
        self.parent.prepare_section_cache()
        if self.parent.playing:
            self.parent.anchor_tick = self.parent.current_accumulated_ticks
            self.parent.force_reload_loop = True
        event.Skip()

    def executar_preview(self, event):
        ms_val = self.sp_time.GetValue()
        vel_val = self.sp_vel.GetValue()
        if ms_val == 0 and vel_val == 0:
            self.parent.merged_track_cache = [m.copy() for m in self.original_cache]
        else:
            import random
            ch_alvos = self.parent.canais_selecionados
            idx = self.parent.sectionList.GetSelection()
            if idx == wx.NOT_FOUND: return
            sec = self.parent.sections_info[idx]
            section_start = sec.get('start', 0)
            section_end = sec.get('end', float('inf'))
            tpq = self.parent.current_midi_data.ticks_per_beat if getattr(self.parent, 'current_midi_data', None) else 480
            if section_end == float('inf'):
                section_end = sum(m.time for m in self.original_cache)
                if section_end <= section_start: section_end = section_start + (tpq * self.parent.beats_per_measure)
            us_per_tick = self.parent.current_tempo / tpq
            dev_tick = int((ms_val * 1000) / us_per_tick)
            abs_msgs = []
            curr_t = 0
            # Fila FIFO por (canal, nota) - lida corretamente com notas
            # repetidas/sobrepostas na mesma altura (flans), que o dicionário
            # simples de antes perdia (uma nota igual sobrescrevia a outra).
            active = {}
            for msg in self.original_cache:
                curr_t += msg.time
                is_target = getattr(msg, 'channel', -1) in ch_alvos
                if is_target and section_start <= curr_t < section_end and msg.type in ['note_on', 'note_off']:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        shift = random.randint(-dev_tick, dev_tick) if dev_tick > 0 else 0
                        new_tick = curr_t + shift
                        new_tick = max(section_start, min(section_end - 2, new_tick))
                        new_vel = max(1, min(127, msg.velocity + random.randint(-vel_val, vel_val))) if vel_val > 0 else msg.velocity
                        key = (msg.channel, msg.note)
                        if key not in active:
                            active[key] = []
                        # Guarda o deslocamento EFETIVO (já com o clamp de
                        # seção aplicado) e o tick final do note_on, para o
                        # note_off correspondente (o próximo da fila) seguir
                        # o mesmo deslocamento e nunca terminar antes de começar.
                        active[key].append((new_tick - curr_t, new_tick))
                        abs_msgs.append((new_tick, msg.copy(velocity=new_vel)))
                    else:
                        key = (msg.channel, msg.note)
                        if key in active and active[key]:
                            delta_efetivo, on_tick = active[key].pop(0)
                            shifted_tick = max(0, curr_t + delta_efetivo)
                            if shifted_tick >= section_end - 2: shifted_tick = section_end - 2
                            if shifted_tick <= on_tick: shifted_tick = on_tick + 1
                            abs_msgs.append((shifted_tick, msg.copy()))
                        else:
                            abs_msgs.append((curr_t, msg.copy()))
                else:
                    abs_msgs.append((curr_t, msg.copy()))
            # Notas que ficaram sem note_off dentro da seção - fecha no fim,
            # igual ao comportamento de antes.
            for key, fila in active.items():
                ch, note = key
                for delta_efetivo, on_tick in fila:
                    clamped_off = section_end - 2
                    if clamped_off <= on_tick: clamped_off = on_tick + 1
                    abs_msgs.append((clamped_off, mido.Message('note_off', channel=ch, note=note, velocity=0)))
            abs_msgs.sort(key=lambda x: x[0])
            novo_cache = []
            last_t = 0
            for t, msg in abs_msgs:
                msg.time = int(round(t - last_t))
                novo_cache.append(msg)
                last_t = t
            self.parent.merged_track_cache = novo_cache
        self.parent.prepare_section_cache()
        if self.parent.playing:
            self.parent.anchor_tick = self.parent.current_accumulated_ticks
            self.parent.force_reload_loop = True

    def get_values(self):
        return self.sp_time.GetValue(), self.sp_vel.GetValue()

# --- Voice Creator: Sound Controllers como o SX grava ---
# Salvando um estilo pelo próprio Style Creator do SX600 com uma voz editada
# (ADA.T228.liv), o teclado gravou Cutoff/Resonance/Attack/Release como CC
# 74/71/73/72 e o Decay como NRPN 01 64 (não como SysEx de Multi Part
# 0x18-0x1C) - e esse arquivo tocou certo. Vibrato (0x15-0x17) segue o padrão
# XG (NRPN 01 08/09/0A).
_VC_PARA_CC = {0x18: 74, 0x19: 71, 0x1A: 73, 0x1C: 72}
_VC_PARA_NRPN_LSB = {0x15: 0x08, 0x16: 0x09, 0x17: 0x0A, 0x1B: 0x64}
_NRPN_LSB_GERENCIADOS = frozenset({0x08, 0x09, 0x0A, 0x20, 0x21, 0x63, 0x64, 0x66})

# --- "Acordes Ativos" (CASM Chord Mute): 34 tipos de acorde, 1 bit cada ---
# Registro CASM bytes 13-17 (5 bytes). Tipo N (numeração Yamaha 0-33) mora no
# byte de índice (4 - N//8), bit (N % 8). Bit 1 = o canal toca, 0 = mudo.
# O bit 0x04 do 1º byte é o "Toca Sem Acorde" (tratado à parte) e o 0x08 é
# desconhecido - os dois são preservados ao remontar o valor.
CHORD_MUTE_NOMES = [
    "Maj", "Maj6", "Maj7", "Maj7#11", "Maj(9)", "Maj7(9)", "Maj6(9)", "aug",
    "min", "min6", "min7", "min7b5", "min(9)", "min7(9)", "min7(11)", "minMaj7",
    "minMaj7(9)", "dim", "dim7", "7th", "7sus4", "7b5", "7(9)", "7#11",
    "7(13)", "7(b9)", "7(b13)", "7(#9)", "Maj7aug", "7aug", "1+8", "1+5",
    "sus4", "1+2+5",
]
CHORD_MUTE_DESCRICOES = {
    0: "maior", 1: "maior com sexta", 2: "maior com sétima maior", 3: "maior sétima com décima primeira aumentada",
    4: "maior com nona", 5: "maior sétima com nona", 6: "maior sexta com nona", 7: "aumentado",
    8: "menor", 9: "menor com sexta", 10: "menor com sétima", 11: "menor sétima com quinta diminuta, meio-diminuto",
    12: "menor com nona", 13: "menor sétima com nona", 14: "menor sétima com décima primeira", 15: "menor com sétima maior",
    16: "menor com sétima maior e nona", 17: "diminuto", 18: "diminuto com sétima diminuta", 19: "dominante, sétima",
    20: "sétima suspensa de quarta", 21: "sétima com quinta bemol", 22: "sétima com nona", 23: "sétima com décima primeira aumentada",
    24: "sétima com décima terceira", 25: "sétima com nona bemol", 26: "sétima com décima terceira bemol", 27: "sétima com nona aumentada",
    28: "maior sétima aumentado", 29: "sétima aumentado", 30: "só fundamental e oitava", 31: "só fundamental e quinta",
    32: "suspenso de quarta", 33: "fundamental, segunda e quinta",
}
CHORD_MUTE_FAMILIAS = [
    ("Maiores", [0, 1, 2, 3, 4, 5, 6, 28]),
    ("Menores", [8, 9, 10, 11, 12, 13, 14, 15, 16]),
    ("Dominantes (sétima)", [19, 20, 21, 22, 23, 24, 25, 26, 27, 29]),
    ("Diminutos e aumentado", [17, 18, 7]),
    ("Suspensos e outros", [32, 33, 30, 31]),
]


PRESET_TODOS = bytes([0x03, 0xff, 0xff, 0xff, 0xff])


def chord_mute_tipos_ativos(b5):
    """Conjunto dos tipos de acorde (0-33) que tocam, a partir dos 5 bytes."""
    b5 = bytes(b5)
    if len(b5) != 5:
        return set(range(34))
    return {n for n in range(34) if b5[4 - n // 8] & (1 << (n % 8))}


def chord_mute_montar(tipos, base=None):
    """Monta os 5 bytes a partir do conjunto de tipos. Preserva, do 1º byte
    de 'base', os bits que não são tipo de acorde (0x04 e 0x08)."""
    base = bytearray(bytes(base)) if base is not None and len(bytes(base)) == 5 else bytearray(5)
    base[0] &= ~0x03 & 0xff
    for i in (1, 2, 3, 4):
        base[i] = 0
    for n in tipos:
        if 0 <= n < 34:
            base[4 - n // 8] |= 1 << (n % 8)
    return bytes(base)


def chord_mute_nome(b5):
    tipos = chord_mute_tipos_ativos(b5)
    if len(tipos) == 34:
        return "Todos"
    if not tipos:
        return "Nenhum"
    if tipos == chord_mute_tipos_ativos(bytes([0x03, 0xff, 0xf8, 0x00, 0xff])):
        return "Maiores"
    if tipos == chord_mute_tipos_ativos(bytes([0x00, 0x00, 0x07, 0xff, 0x00])):
        return "Menores"
    return f"Personalizado ({len(tipos)} de 34 tipos)"


class AcordesAtivosDialog(wx.Dialog):
    """Lista de caixas de marcação com os 34 tipos de acorde do CASM."""

    def __init__(self, parent, n_alvos, valor_atual):
        super().__init__(parent, title="Acordes Ativos", size=(520, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.rotulos_ordem = []
        for familia, tipos in CHORD_MUTE_FAMILIAS:
            for n in tipos:
                self.rotulos_ordem.append(n)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label=f"Estes {n_alvos} canal(is) tocam para quais tipos de acorde? "
                                           "Marque com Espaço:"), 0, wx.ALL, 8)
        rotulos = []
        fam_de = {}
        for familia, tipos in CHORD_MUTE_FAMILIAS:
            for n in tipos:
                fam_de[n] = familia
        for n in self.rotulos_ordem:
            rotulos.append(f"{fam_de[n]}: {CHORD_MUTE_NOMES[n]} ({CHORD_MUTE_DESCRICOES[n]})")
        self.lista = wx.CheckListBox(self, choices=rotulos, name="Tipos de acorde")
        ativos = chord_mute_tipos_ativos(valor_atual)
        for i, n in enumerate(self.rotulos_ordem):
            self.lista.Check(i, n in ativos)
        vbox.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        atalhos = wx.BoxSizer(wx.HORIZONTAL)
        for rotulo, tipos_fn in (
            ("&Todos", lambda: set(range(34))),
            ("&Nenhum", lambda: set()),
            ("&Maiores", lambda: chord_mute_tipos_ativos(bytes([0x03, 0xff, 0xf8, 0x00, 0xff]))),
            ("M&enores", lambda: chord_mute_tipos_ativos(bytes([0x00, 0x00, 0x07, 0xff, 0x00]))),
            ("&Sétimas", lambda: set(dict(CHORD_MUTE_FAMILIAS)["Dominantes (sétima)"])),
        ):
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=tipos_fn: self._marcar_so(f()))
            atalhos.Add(b, 0, wx.ALL, 4)
        vbox.Add(atalhos, 0, wx.LEFT | wx.RIGHT, 4)
        vbox.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(vbox)
        wx.CallLater(100, self.lista.SetFocus)

    def _marcar_so(self, tipos):
        for i, n in enumerate(self.rotulos_ordem):
            self.lista.Check(i, n in tipos)
        self.lista.SetFocus()

    def get_tipos(self):
        return {n for i, n in enumerate(self.rotulos_ordem) if self.lista.IsChecked(i)}


class EnvelopeCCDialog(wx.Dialog):
    # Igual ao "Envelope de Automação de CC" (Shift+E) do MHS MIDI
    # Sequencer, a pedido do Michel - substitui a versão anterior (número
    # do CC digitado na mão, sem nome, sem valor inicial "de verdade") por
    # uma lista com o nome de cada CC e valores pré-preenchidos com o
    # estado atual do canal, quando o programa já rastreia esse CC
    # (Volume/Pan/Expression/Reverb/Chorus - os 5 que self.canais guarda).
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title="Envelope de Automação de CC", size=(400, 260))
        self.parent = parent
        self.canal_idx = canal_idx

        from MHS_Utils import get_cc_name
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.cc_choices = []
        self.cc_map = {}
        for num in range(128):
            nome = get_cc_name(num)
            if nome == f"CC {num}":
                label = f"{num:03d} - Control Change {num}"
            else:
                label = f"{num:03d} - {nome}"
            self.cc_choices.append(label)
            self.cc_map[label] = num

        sizer.Add(wx.StaticText(self, label="Selecione o Control Change (CC):"), 0, wx.ALL, 5)
        self.combo_cc = wx.ComboBox(self, choices=self.cc_choices, style=wx.CB_READONLY)
        self.combo_cc.SetSelection(7)
        sizer.Add(self.combo_cc, 0, wx.EXPAND | wx.ALL, 5)
        self.combo_cc.Bind(wx.EVT_COMBOBOX, self.on_cc_change)

        sz_h = wx.BoxSizer(wx.HORIZONTAL)
        sz_start = wx.BoxSizer(wx.VERTICAL)
        sz_start.Add(wx.StaticText(self, label="Valor Inicial (Origem):"), 0, wx.BOTTOM, 5)
        val_inicial = self._valor_atual_canal(7)
        self.txt_start = wx.TextCtrl(self, value=str(val_inicial))
        sz_start.Add(self.txt_start, 0, wx.EXPAND)

        sz_end = wx.BoxSizer(wx.VERTICAL)
        sz_end.Add(wx.StaticText(self, label="Valor Final (Destino):"), 0, wx.BOTTOM, 5)
        self.txt_end = wx.TextCtrl(self, value=str(val_inicial))
        sz_end.Add(self.txt_end, 0, wx.EXPAND)

        sz_h.Add(sz_start, 1, wx.EXPAND | wx.RIGHT, 10)
        sz_h.Add(sz_end, 1, wx.EXPAND)
        sizer.Add(sz_h, 0, wx.EXPAND | wx.ALL, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        wx.CallLater(100, self.combo_cc.SetFocus)

    def _valor_atual_canal(self, cc_num):
        c = self.parent.canais[self.canal_idx] if 0 <= self.canal_idx < len(self.parent.canais) else {}
        if cc_num == 7: return c.get("Volume", 100)
        if cc_num == 10: return c.get("Pan", 64)
        if cc_num == 11: return c.get("Expression", 127)
        if cc_num == 91: return c.get("Reverb", 40)
        if cc_num == 93: return c.get("Chorus", 0)
        return 64

    def on_cc_change(self, event):
        from MHS_Utils import falar
        label = self.combo_cc.GetValue()
        cc_num = self.cc_map[label]
        val = self._valor_atual_canal(cc_num)
        self.txt_start.SetValue(str(val))
        self.txt_end.SetValue(str(val))
        falar(f"{label} selecionado", imediato=True)

    def get_values(self):
        cc_num = self.cc_map[self.combo_cc.GetValue()]
        try: st = int(self.txt_start.GetValue())
        except: st = 64
        try: en = int(self.txt_end.GetValue())
        except: en = 64
        return cc_num, max(0, min(127, st)), max(0, min(127, en))

class StyleCreatorFrame(wx.Frame):
    def __init__(self, arquivo_inicial=None):
        ativar_cache_portas_midi()
        super().__init__(parent=None, title=f'MHS Style Creator Acessível v{VERSAO_APP}', size=(850, 750))
        import sys
        import os
        from MHS_Utils import TOTAL_CANAIS, VALOR_MAX_MIDI
        
        # Inicia o motor MIDI (Ele segura as variaveis de transporte e áudio)
        from MHS_MidiEngine import MidiEngine
        self.midi_engine = MidiEngine(self)
        
        # BLINDAGEM NUITKA: Descobre o diretório real do .exe ou do script
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.config_file = os.path.join(self.base_dir, "config.json")
        self.log_file = os.path.join(self.base_dir, "erros.log")

        self.current_file_path = None
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False
        # Protege aplicar_gravacao contra chamada concorrente: o midi_worker
        # (thread de fundo) chama aplicar_gravacao() direto na virada do
        # loop enquanto gravando, e o usuário pode apertar R (parar a
        # gravação, também chama aplicar_gravacao) no MESMO instante, pela
        # thread principal - sem essa trava, as duas podiam interlevar a
        # reconstrução de merged_track_cache (uma lê/reescreve a lista
        # enquanto a outra ainda está no meio da própria reconstrução),
        # corrompendo seções inteiras do arquivo (achado com o Michel:
        # gravar com o loop dando a volta bagunçava seções sem relação
        # nenhuma com a que estava sendo gravada).
        self._grava_lock = threading.Lock()
        self.canais_selecionados = {0}
        self.non_continuous_sel = False
        self.in_point = None
        self.out_point = None
        self.clipboard_events = []
        self._log_midi_in = False
        # Captura automática do timbre/DSP quando você troca a voz pelo teclado
        # (ligável/desligável em Opções).
        self._captura_dsp_ligada = True
        self.config = {
            "midi_out": "", "midi_in": [], "ins_files": [], "selected_ins_idx": 0,
            "last_open_dir": "", "last_save_dir": "", "recentes": [],
            "rotas_midi": [{'active': False, 'src': '1', 'dst': '11'}, {'active': False, 'src': 'PB', 'dst': '10'}, {'active': False, 'src': '0', 'dst': '0'}, {'active': False, 'src': '0', 'dst': '0'}],
            # Teste pedido pelo Michel: metrônomo (canal 10) numa porta MIDI
            # separada do resto do estilo - "" (vazio) = comportamento de
            # sempre, tudo pela porta principal.
            "midi_out_metronomo": "", "metronomo_volume": 100,
        }
        # Guias: cada estilo aberto vira uma aba independente. self.abas guarda
        # um "instantâneo" completo por aba (ver ATRIBUTOS_DOCUMENTO); os
        # atributos ao vivo (self.canais, self.merged_track_cache etc.) são
        # sempre os da aba ATUAL - trocar de aba salva o que está ao vivo na
        # aba de saída e carrega o instantâneo da aba de entrada.
        self.abas = []
        self.aba_atual = -1
        self.ins_db = {}
        self.bank_names = {}
        self.current_midi_data = None
        self.merged_track_cache = []
        self.sections_info = []
        self.current_section_msgs = []
        self.section_has_mid_sysex = False
        self.midi_setup_msgs = []
        self.casm_rules = self.get_default_casm_rules()
        self.canais = []
        for ch in range(TOTAL_CANAIS):
            self.canais.append({"Nome": f"Canal {ch+1}", "Mute": False, "Solo": False, "Arm": False, "Volume": 100, "Pan": 64, "Expression": VALOR_MAX_MIDI, "Bank": 0, "Patch": 0, "Reverb": 0, "Chorus": 0, "Grave": 64, "Agudo": 64})
        
        self.canal_atual = 0
        self.propriedade_atual = 0
        self.propriedades = ["Nome", "Mute", "Solo", "Arm", "Volume", "Pan", "Grave", "Agudo", "Expression", "Bank", "Patch", "Reverb", "Chorus", "Transpose"]
        self.active_output_notes = {}
        self.pending_section = None 
        
        self.play_base_time = 0.0
        self.rt_quantize = False
        self.rt_quantize_res = 16.0
        self.in_vel_ctrl_on = False
        self.in_vel_min = 1
        self.in_vel_max = VALOR_MAX_MIDI
        self.rotas_midi = self.config["rotas_midi"]

        self.dsp_global = self._dsp_global_padrao()
        self.dsp_variation = self._dsp_variation_padrao()

        self.current_tempo = 500000
        self.last_idx = -1
        self.section_duration_seconds = 0
        self.current_main_prefix = "Main A"
        self.beats_per_measure = 4
        
        from MHS_Utils import falar
        falar(f"MHS Style Creator versão {VERSAO_APP.replace('.', ' ponto ')} iniciado.", imediato=True)
        self.load_config()
        # Ao abrir o programa, manda Local Control Off (mesmo que o F8) -
        # assim o teclado só toca o que o programa mandar, sem o som direto
        # das teclas físicas atrapalhando os testes. Some sozinho, sem
        # precisar lembrar de apertar F8 toda vez. F8 continua funcionando
        # normalmente pra ligar/desligar na mão durante o uso.
        self.midi_engine.set_local_control(False)
        self.InitUI()
        self.parse_selected_ins()
        self.setup_midi_in()
        # A abertura acabou: dali em diante toda listagem de portas (trocar
        # de dispositivo, Configurações) volta a ser sempre a lista fresca.
        limpar_cache_portas_midi()
        self.atualizar_titulo()

        # Duplo clique num .sty/.prs/.cte no Windows (ou "Abrir com") manda o
        # caminho do arquivo por linha de comando - InitUI() já mostrou a
        # janela vazia, então abre numa aba nova por cima, igual ao Ctrl+O.
        if arquivo_inicial and os.path.exists(arquivo_inicial):
            wx.CallAfter(self.abrir_caminho_em_nova_aba, arquivo_inicial)

        # NÃO agendado aqui dentro do __init__ de propósito: a suíte de
        # testes inteira constrói StyleCreatorFrame() direto (sem passar por
        # main.py), várias vezes por arquivo, sempre usando o config.json
        # REAL (self.config_file só é isolado quando o teste troca na mão) -
        # um wx.CallAfter automático aqui dispararia um ShowModal() de
        # verdade (bloqueante) em QUALQUER teste que desse um wx.Yield(),
        # travando a suíte inteira. Só main.py (o ponto de entrada real do
        # programa) agenda essa checagem, depois de construir o frame.

    def mostrar_changelog_se_necessario(self):
        # Pedido do Michel: toda vez que ele lançar uma atualização, o
        # usuário deve ver a tela de Changelog dessa versão - mas só na
        # PRIMEIRA vez que ele abrir essa versão nova, nunca de novo depois
        # (a não ser que reinstale/apague o config.json, que é quando essa
        # marca também some). Guarda no config.json qual foi a ÚLTIMA versão
        # cujo changelog já foi mostrado - se for diferente da versão atual
        # (VERSAO_APP), mostra e atualiza a marca. Silencioso se não houver
        # texto cadastrado pra essa versão (evita crash numa versão futura
        # que, por algum motivo, esqueça de entrar em CHANGELOG_TEXTS).
        if self.config.get("changelog_versao_mostrada") == VERSAO_APP:
            return
        texto = CHANGELOG_TEXTS.get(VERSAO_APP)
        if texto:
            dlg = ChangelogDialog(self, VERSAO_APP, texto + MENSAGEM_APOIO)
            dlg.ShowModal()
            dlg.Destroy()
        self.config["changelog_versao_mostrada"] = VERSAO_APP
        self.save_config()

    def OnMostrarNovidades(self, event):
        # Menu Ajuda > Novidades desta Versão - reexibe a MESMA tela de
        # Changelog que mostrar_changelog_se_necessario mostra sozinha na
        # primeira vez que uma versão nova é aberta, mas sob demanda, sem
        # mexer em "changelog_versao_mostrada" (não é a checagem automática).
        texto = CHANGELOG_TEXTS.get(VERSAO_APP)
        if texto:
            dlg = ChangelogDialog(self, VERSAO_APP, texto + MENSAGEM_APOIO)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            falar("Nenhuma novidade cadastrada para esta versão.", imediato=True)

    def OnAbrirPaginaProjeto(self, event):
        import webbrowser
        webbrowser.open(f"https://github.com/MHS-Softwares/{REPO_GITHUB}")

    def verificar_atualizacoes_ao_iniciar(self):
        # Chamado só por main.py (via wx.CallAfter), nunca no __init__ - mesmo
        # motivo do mostrar_changelog_se_necessario: testes automatizados
        # constroem StyleCreatorFrame() direto, e isso não pode disparar
        # tráfego de rede nenhum. Roda em thread separada (não pode travar a
        # abertura do programa esperando resposta de rede) e só incomoda o
        # usuário se REALMENTE houver uma versão nova - silencioso em caso de
        # falha de rede ou já estar atualizado (a checagem manual, pelo botão
        # em Configurações, é que dá feedback nos dois casos).
        if not self.config.get('verificar_atualizacoes', True):
            return
        threading.Thread(target=self._verificar_atualizacao_silenciosa_thread, daemon=True).start()

    def _verificar_atualizacao_silenciosa_thread(self):
        info = verificar_nova_versao_detalhado(REPO_GITHUB, VERSAO_APP)
        if info and info['tem']:
            wx.CallAfter(self._avisar_atualizacao_disponivel, info)

    def _avisar_atualizacao_disponivel(self, info):
        # Janela de atualização: baixa o instalador direto daqui e, ao fim,
        # oferece instalar na hora (fecha o programa e abre o instalador).
        oferecer_atualizacao(self, self, "MHS Style Creator", info['versao'], VERSAO_APP, info['url_pagina'], info['instalador'])

    def __getattr__(self, name):
        # A MÁGICA: Se o código pedir alguma destas variáveis, busca no Motor MIDI
        props_motor = [
            'midi_out', 'midi_ins', 'midi_out_metronomo', 'playing', 'paused', 'gravando',
            'force_reload_loop', 'anchor_tick', 'current_accumulated_ticks',
            'recorded_events', 'active_keys', 'live_physical_keys',
            'use_metronome'
        ]
        if name in props_motor:
            return getattr(self.midi_engine, name)
        raise AttributeError(f"'{self.__class__.__name__}' não possui o atributo '{name}'")

    def __setattr__(self, name, value):
        # A MÁGICA: Se o código tentar alterar estas variáveis, altera lá no Motor MIDI
        props_motor = [
            'midi_out', 'midi_ins', 'midi_out_metronomo', 'playing', 'paused', 'gravando',
            'force_reload_loop', 'anchor_tick', 'current_accumulated_ticks',
            'recorded_events', 'active_keys', 'live_physical_keys',
            'use_metronome'
        ]
        if name in props_motor:
            try:
                engine = super().__getattribute__('midi_engine')
                setattr(engine, name, value)
                return
            except AttributeError:
                pass
        super().__setattr__(name, value)
    def abrir_porta_metronomo(self):
        # Teste pedido pelo Michel: (re)abre a porta MIDI separada do
        # metrônomo, se ele tiver configurado uma, e já manda a
        # configuração fixa (Bank 16256, Patch 0, Reverb 0, Chorus 0,
        # Volume do Metrônomo) pra ela. Se "midi_out_metronomo" estiver
        # vazio (opção "mesma porta principal"), fecha qualquer porta que
        # estivesse aberta e volta ao comportamento de sempre - metrônomo
        # pela porta principal, sem precisar mexer em mais nada.
        if self.midi_out_metronomo:
            try: self.midi_out_metronomo.close()
            except Exception: pass
            self.midi_out_metronomo = None
        nome_porta = self.config.get("midi_out_metronomo")
        if nome_porta:
            from MHS_Utils import achar_porta_certa
            porta_certa = achar_porta_certa(nome_porta, nomes_portas_midi('saida'))
            if porta_certa:
                try:
                    self.midi_out_metronomo = mido.open_output(porta_certa)
                    self.midi_engine.enviar_setup_metronomo()
                except Exception:
                    pass

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
                self.rotas_midi = self.config.get("rotas_midi", self.rotas_midi)
                if self.config.get("midi_out"):
                    from MHS_Utils import achar_porta_certa
                    porta_certa = achar_porta_certa(self.config["midi_out"], nomes_portas_midi('saida'))
                    if porta_certa:
                        self.midi_out = mido.open_output(porta_certa)
                self.abrir_porta_metronomo()
            except Exception as e:
                with open(self.log_file, "a", encoding="utf-8") as log:
                    log.write(f"Erro ao ler config.json: {e}\n")
                from MHS_Utils import falar
                falar("Erro ao carregar configurações. O arquivo pode estar corrompido.", imediato=True)
        else:
            self.save_config()

        # Pasta padrão "MHS Style Creator" (subpasta dentro da pasta Músicas
        # do usuário do Windows) - mesma convenção já usada no MHS MIDI
        # Sequencer (ver load_config em MHS.py, pasta "MHS MIDI Sequencer"),
        # pedida pelo Michel pra evitar cair sempre em Documentos/Downloads
        # nas telas de Abrir/Salvar Como. Só entra em ação se AINDA não tiver
        # nenhuma pasta configurada - nunca sobrescreve uma pasta que o
        # usuário já escolheu manualmente numa sessão anterior.
        if not self.config.get("last_open_dir") or not self.config.get("last_save_dir"):
            try:
                import ctypes
                import ctypes.wintypes
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                ctypes.windll.shell32.SHGetFolderPathW(None, 13, None, 0, buf)
                pasta_musicas = buf.value
            except Exception:
                pasta_musicas = os.path.join(os.path.expanduser('~'), 'Music')
            pasta_mhs = os.path.join(pasta_musicas, "MHS Style Creator")
            try:
                if not os.path.exists(pasta_mhs):
                    os.makedirs(pasta_mhs)
            except Exception:
                pasta_mhs = pasta_musicas
            if not self.config.get("last_open_dir"):
                self.config["last_open_dir"] = pasta_mhs
            if not self.config.get("last_save_dir"):
                self.config["last_save_dir"] = pasta_mhs
            self.save_config()

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e: print(f"Erro ao salvar config.json: {e}")

    def get_default_casm_rules(self):
        # Padrão pedido pelo Michel: idêntico, canal por canal e zona por
        # zona, ao CASM real da Main A de "ARROCHA 01.STY" (P:\02 - Ritmos\
        # 01 - Ritmos Michel) - um ritmo dele mesmo que já considera "bem
        # padrão". Extraído com o próprio extract_casm/decodificador deste
        # programa (não à mão), pra garantir que bate byte a byte com o que
        # o SX realmente lê desse arquivo. Usado sempre que uma seção ganha
        # um CASM novo (obter_casm_da_secao com criar_se_ausente=True) -
        # inclusive ao criar um Novo Estilo do zero.
        rules = {}
        for ch in range(TOTAL_CANAIS):
            rules[ch] = {
                'play_type': 'trans',
                'ntt_type': 'bypass',
                'ntt_bass': False,
                'high_key': 6,
                'note_limit_low': VALOR_MIN_MIDI,
                'note_limit_high': VALOR_MAX_MIDI,
                'dst': ch,
                'active_chords': bytes([0x03, 0xff, 0xff, 0xff, 0xff]),
                'note_split_high': VALOR_MAX_MIDI,
                'ntr_hi': 'trans',
                'ntt_hi': 'bypass',
                'ntt_hi_bass': False,
                'high_key_hi': 6,
                'editable': True,
                'rtr': 'pitch shift',
                'note_limit_low_hi': VALOR_MIN_MIDI,
                'note_limit_high_hi': VALOR_MAX_MIDI,
                'rtr_hi': 'pitch shift',
                'note_split_low': 0,
                'ntr_lo': 'trans',
                'ntt_lo': 'bypass',
                'ntt_lo_bass': False,
                'high_key_lo': 6,
                'note_limit_low_lo': VALOR_MIN_MIDI,
                'note_limit_high_lo': VALOR_MAX_MIDI,
                'rtr_lo': 'pitch shift',
                # Padrão de fábrica da própria Yamaha (doc v2.1, item
                # 4.6.3.3): "CMaj7" - Dó como fundamental, Maj7 como tipo.
                'source_chord_root': 'C',
                'source_chord_type': 'Maj7',
            }

        # Rhythm1 e Rhythm2 (bateria): não editável, "Toca Sem Acorde"
        # ligado (bit 0x04 em "Acordes Ativos" - é isso que deixa a bateria
        # livre do ACMP, confirmado comparando vários arquivos genuínos),
        # NTR/NTT Zona Aguda espelhando a Zona Média (fixed/bypass).
        for ch in (CANAL_BATERIA_1, CANAL_BATERIA_2):
            rules[ch].update(
                play_type='fixed', ntt_type='bypass', high_key=6,
                ntr_hi='fixed', ntt_hi='bypass', high_key_hi=6,
                ntr_lo='fixed', ntt_lo='bypass', high_key_lo=6,
                editable=False,
                active_chords=bytes([0x07, 0xff, 0xff, 0xff, 0xff]),
            )

        # Bass: Trans+Melody com Bass ligado, High Key 3, Retrigger Rule
        # "retrigger to root" nas 3 zonas (reataca na fundamental do novo
        # acorde ao trocar - o que faz sentido pra uma linha de baixo).
        rules[10].update(
            play_type='trans', ntt_type='melody', ntt_bass=True, high_key=3,
            ntr_hi='trans', ntt_hi='melody', ntt_hi_bass=True, high_key_hi=3,
            ntr_lo='trans', ntt_lo='melody', ntt_lo_bass=True, high_key_lo=3,
            editable=False,
            rtr='retrigger to root', rtr_hi='retrigger to root', rtr_lo='retrigger to root',
        )

        # Chord1, Chord2 e Pad: Fixed+Chord, High Key 7, Zona Aguda
        # espelhando a Zona Média (fixed/chord/7) - os três com o mesmo
        # papel no ARROCHA.
        for ch in (11, 12, 13):
            rules[ch].update(
                play_type='fixed', ntt_type='chord', high_key=7,
                ntr_hi='fixed', ntt_hi='chord', high_key_hi=7,
                ntr_lo='fixed', ntt_lo='chord', high_key_lo=7,
                editable=False,
            )

        # Phrase1 e Phrase2: Fixed+Melody, High Key 7 - mas aqui a Zona
        # Aguda NÃO espelha a Média (fica em trans/bypass, igual ao
        # genérico) e continuam editáveis.
        for ch in (14, 15):
            rules[ch].update(
                play_type='fixed', ntt_type='melody', high_key=7,
                ntr_hi='trans', ntt_hi='bypass', high_key_hi=7,
            )

        return rules
    def obter_casm_da_secao(self, nome_secao, criar_se_ausente=False):
        biblioteca = getattr(self, 'casm_rules_by_section', None)
        if biblioteca is None:
            biblioteca = {}
            self.casm_rules_by_section = biblioteca
        chave_alvo = (nome_secao or "").strip().lower()
        for nome_guardado, regras in biblioteca.items():
            if nome_guardado.strip().lower() == chave_alvo:
                return regras
        if criar_se_ausente:
            # A CRIAÇÃO DE VERDADE: só agora essa seção passa a existir na
            # biblioteca oficial, com sua própria cópia independente das
            # regras - sem isso, a edição ficava só na tela, nunca chegando
            # no arquivo salvo. Uma seção que nunca foi tocada começa sempre
            # dos padrões limpos (get_default_casm_rules) - nunca copiando o
            # que sobrou de outra seção qualquer (self.casm_rules é só a
            # config "representante" pra exibição, geralmente da Main A, e
            # usar ela aqui fazia toda seção nova nascer com resquício dela
            # em vez dos padrões de canal pedidos) - EXCETO quando a seção
            # sendo criada agora é JUSTAMENTE a "Main A" que self.casm_rules
            # representa: aí não é "resquício de outra seção", É a própria
            # seção, com os valores REAIS já carregados do arquivo (ou já
            # editados nesta sessão) - usar defaults genéricos aqui jogava
            # fora, pros 15 canais que não estavam sendo mexidos no momento,
            # qualquer configuração real que já existisse (achado com o
            # Michel: "Toca Sem Acorde" do Rhythm1/Rhythm2, já testado e
            # funcionando no SX600, voltou a Desligado só porque ele copiou
            # o Chord 1 de outro ritmo - Ctrl+Alt+E - ou limpou o CASM dele
            # em Editar Seção, e essa foi a PRIMEIRA vez que a seção "Main A"
            # deste arquivo precisou de uma entrada própria na biblioteca).
            # Mesma convenção já usada em construir_casm_do_zero (seção
            # "Main A" tratada como sinônimo de self.casm_rules).
            if chave_alvo == "main a":
                nova_regra = copy.deepcopy(self.casm_rules)
            else:
                nova_regra = self.get_default_casm_rules()
            biblioteca[nome_secao] = nova_regra
            return nova_regra
        return self.casm_rules
    def extract_casm(self, raw_casm_data):
        import re
        rules_per_section = {}
        if not raw_casm_data:
            self.casm_rules_by_section = {}
            return self.get_default_casm_rules()

        try:
            for cseg_match in re.finditer(b'CSEG', raw_casm_data):
                start = cseg_match.start()
                size = int.from_bytes(raw_casm_data[start+4:start+8], byteorder='big')
                cseg_data = raw_casm_data[start+8 : start+8+size]
                
                sdec_idx = cseg_data.find(b'Sdec')
                nomes_secao = ["Unknown"]
                varredura_inicio = 0
                if sdec_idx != -1:
                    sdec_size = int.from_bytes(cseg_data[sdec_idx+4:sdec_idx+8], byteorder='big')
                    sdec_texto = cseg_data[sdec_idx+8 : sdec_idx+8+sdec_size].decode('latin-1', errors='ignore')
                    nomes_secao = [n.strip() for n in sdec_texto.split(',') if n.strip()]
                    if not nomes_secao:
                        nomes_secao = ["Unknown"]
                    varredura_inicio = sdec_idx + 8 + sdec_size

                sec_rules = self.get_default_casm_rules()
                canais_vistos = set()

                for m in re.finditer(b'Ctab|Ctb2', cseg_data[varredura_inicio:]):
                    tag = m.group()
                    bloco_start = varredura_inicio + m.start()
                    bloco_size = int.from_bytes(cseg_data[bloco_start+4:bloco_start+8], byteorder='big')
                    registro = cseg_data[bloco_start+8 : bloco_start+8+bloco_size]

                    src = registro[0]
                    dst = registro[9] if len(registro) > 9 else src
                    editable = registro[10] if len(registro) > 10 else None
                    chordmute = registro[13:18] if len(registro) >= 18 else None
                    # Bytes 18/19 ("Source Chord"/"Source Chord Type") - a
                    # mesma posição em Ctab E Ctb2 (a doc confirma: a
                    # "primeira parte" do registro é idêntica nos dois
                    # formatos). Índice fora da tabela (arquivo corrompido/
                    # valor nunca visto) cai no padrão Yamaha (C Maj7).
                    source_chord_root = registro[18] if len(registro) > 18 and registro[18] < len(SOURCE_CHORD_ROOT_NAMES) else 0
                    source_chord_type = registro[19] if len(registro) > 19 and registro[19] < len(SOURCE_CHORD_TYPE_NAMES) else 2

                    raw_bytes = None
                    rtr = note_split_low = ntr_lo = ntt_lo = hkey_lo = l_lim_lo = h_lim_lo = rtr_lo = None
                    l_lim_hi = h_lim_hi = rtr_hi = None
                    if tag == b'Ctb2' and len(registro) >= 34:
                        ntr = registro[28]
                        ntt = registro[29]
                        hkey = registro[30]
                        l_lim = registro[31]
                        h_lim = registro[32]
                        note_split_high = registro[21]
                        ntr_hi = registro[34] if len(registro) > 34 else None
                        ntt_hi = registro[35] if len(registro) > 35 else None
                        hkey_hi = registro[36] if len(registro) > 36 else None
                        # Zona Média - Retrigger Rule.
                        if len(registro) > 33:
                            rtr = registro[33]
                        # Zona Aguda - Low/High Limit e Retrigger Rule.
                        if len(registro) > 39:
                            l_lim_hi = registro[37]
                            h_lim_hi = registro[38]
                            rtr_hi = registro[39]
                        # Zona Grave - fronteira (byte 20) e sub-estrutura
                        # inteira (bytes 22-27).
                        if len(registro) > 27:
                            note_split_low = registro[20]
                            ntr_lo = registro[22]
                            ntt_lo = registro[23]
                            hkey_lo = registro[24]
                            l_lim_lo = registro[25]
                            h_lim_lo = registro[26]
                            rtr_lo = registro[27]
                        if len(registro) >= max(BYTES_CASM_DESCONHECIDOS) + 1:
                            raw_bytes = {i: registro[i] for i in BYTES_CASM_DESCONHECIDOS}
                    elif tag == b'Ctab' and len(registro) >= 26:
                        ntr = registro[20]
                        ntt = registro[21]
                        hkey = registro[22]
                        l_lim = registro[23]
                        h_lim = registro[24]
                        # Retrigger Rule - documentado na v2.1 (tabela 37,
                        # usando os offsets do Ctab regular como referência)
                        # como byte 25, a mesma "zona única" de NTR/NTT/High
                        # Key/Limites que Ctab já tinha - só não estava sendo
                        # lida. Achado investigando por que dois ritmos reais
                        # (LAIRTON 02.S837.sty vs ANJINHO DOS TECLADOS.sty, os
                        # dois com o canal Bass tocando a mesma composição)
                        # se comportavam diferente ao tocar um acorde "on
                        # bass"/sétima - o Bass do Lairton (Ctb2) tinha RTR
                        # real = "retrigger to root", o do Anjinho (Ctab)
                        # sempre caía no padrão da tela por essa leitura
                        # faltar.
                        if len(registro) > 25:
                            rtr = registro[25]
                        note_split_high = None
                        ntr_hi = None
                        ntt_hi = None
                        hkey_hi = None
                    else:
                        continue

                    self._apply_casm_rule(sec_rules, src, dst, ntr, ntt, hkey, l_lim, h_lim, canais_vistos, chordmute, note_split_high, ntr_hi, ntt_hi, hkey_hi, editable, raw_bytes,
                                           rtr=rtr, note_split_low=note_split_low, ntr_lo=ntr_lo, ntt_lo=ntt_lo, hkey_lo=hkey_lo, l_lim_lo=l_lim_lo, h_lim_lo=h_lim_lo, rtr_lo=rtr_lo,
                                           l_lim_hi=l_lim_hi, h_lim_hi=h_lim_hi, rtr_hi=rtr_hi,
                                           source_chord_root=source_chord_root, source_chord_type=source_chord_type)

                for nome in nomes_secao:
                    rules_per_section[nome] = sec_rules

        except Exception as e:
            with open(self.log_file, "a", encoding="utf-8") as log:
                log.write(f"Erro no Extrator de CSEG: {e}\n")

        self.casm_rules_by_section = rules_per_section

        if not rules_per_section:
            return self.get_default_casm_rules()

        secao_escolhida = None
        for nome_secao in rules_per_section:
            if nome_secao.strip().lower() == "main a":
                secao_escolhida = nome_secao
                break
        if secao_escolhida is None:
            secao_escolhida = next(iter(rules_per_section))

        return rules_per_section[secao_escolhida]
    def patch_casm_binary(self):
        dados_originais = getattr(self, 'raw_casm_data', b'')
        if not dados_originais:
            if getattr(self, 'casm_rules_by_section', None):
                import base64
                from MHS_CasmTemplate import CASM_TEMPLATE_B64
                dados_originais = base64.b64decode(CASM_TEMPLATE_B64)
                self.raw_casm_data = dados_originais
            else:
                return dados_originais

        biblioteca = getattr(self, 'casm_rules_by_section', {}) or {}
        if not biblioteca:
            return dados_originais

        dados = bytes(dados_originais)
        if dados[:4] != b'CASM':
            return dados_originais

        # Pra decidir se um canal que nunca teve registro físico PRECISA de
        # um agora - não basta olhar se a regra de NTR/NTT foi editada (dá
        # pra gravar uma nota nova num canal sem nunca abrir a tela de CASM
        # dele). Mapeia, uma vez só, em que ticks cada canal tem nota de
        # verdade, pra cruzar com o intervalo de cada seção mais abaixo.
        notas_por_canal = {}
        curr_t_notas = 0
        for msg in getattr(self, 'merged_track_cache', []):
            curr_t_notas += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                ch_nota = getattr(msg, 'channel', None)
                if ch_nota is not None:
                    notas_por_canal.setdefault(ch_nota, []).append(curr_t_notas)

        def canal_tem_notas_na_secao(ch, nomes_da_secao):
            ticks = notas_por_canal.get(ch)
            if not ticks:
                return False
            for nome in nomes_da_secao:
                for sec in getattr(self, 'sections_info', []):
                    if sec.get('name', '').strip().lower() != nome.strip().lower():
                        continue
                    st = sec.get('start')
                    ed = sec.get('end')
                    if st is None:
                        continue
                    if ed is None:
                        ed = float('inf')
                    if any(st <= t < ed for t in ticks):
                        return True
            return False

        ntr_map = {'trans': 0, 'fixed': 1, 'gtr': 2}
        ntt_map = {
            'bypass': 0, 'melody': 1, 'chord': 2, 'melodic minor': 3,
            'melodic minor 5th': 4, 'harmonic minor': 5, 'harmonic minor 5th': 6,
            'natural minor': 7, 'natural minor 5th': 8, 'dorian': 9,
            'dorian 5th': 10, 'all purpose': 11, 'any chord': 12,
            'vocal': 13, 'pitch shift': 14
        }
        rtr_map = {nome: i for i, nome in enumerate(RTR_OPCOES)}
        source_root_map = {nome: i for i, nome in enumerate(SOURCE_CHORD_ROOT_NAMES)}
        source_type_map = {nome: i for i, nome in enumerate(SOURCE_CHORD_TYPE_NAMES)}
        # As mesmas 9 vozes que o próprio molde genérico da Yamaha sempre
        # reserva por seção (ver MHS_CasmTemplate.py) - só nesses canais é
        # seguro criar um registro novo do zero.
        nomes_padrao = {
            0: "Track1  ", 8: "Rhythm1 ", 9: "Rhythm2 ", 10: "Bass    ",
            11: "Chord1  ", 12: "Chord2  ", 13: "Pad     ", 14: "Phrase1 ", 15: "Phrase2 "
        }

        def valores_de(regra):
            # Um valor por byte do Ctb2 (bytes 20-39), pras 3 zonas de nota -
            # devolvidos num dict (em vez de uma tupla gigante) porque agora
            # são as 3 zonas inteiras, não só a Zona Média + Zona Aguda de
            # antes.
            ntt_val = ntt_map.get(regra.get('ntt_type', 'bypass').lower(), 0)
            if regra.get('ntt_bass', False):
                ntt_val |= 0x80
            ntt_hi_val = ntt_map.get(regra.get('ntt_hi', 'bypass').lower(), 0)
            if regra.get('ntt_hi_bass', False):
                ntt_hi_val |= 0x80
            ntt_lo_val = ntt_map.get(regra.get('ntt_lo', 'bypass').lower(), 0)
            if regra.get('ntt_lo_bass', False):
                ntt_lo_val |= 0x80
            return dict(
                ntr=ntr_map.get(regra.get('play_type', 'trans').lower(), 0),
                ntt=ntt_val,
                hkey=regra.get('high_key', 6),
                llim=regra.get('note_limit_low', 0),
                hlim=regra.get('note_limit_high', 127),
                split=max(0, min(127, regra.get('note_split_high', 127))),
                rtr=rtr_map.get(regra.get('rtr', 'pitch shift').lower(), 1),
                ntr_hi=ntr_map.get(regra.get('ntr_hi', 'trans').lower(), 0),
                ntt_hi=ntt_hi_val,
                hkey_hi=max(0, min(127, regra.get('high_key_hi', 6))),
                llim_hi=regra.get('note_limit_low_hi', 0),
                hlim_hi=regra.get('note_limit_high_hi', 127),
                rtr_hi=rtr_map.get(regra.get('rtr_hi', 'pitch shift').lower(), 1),
                split_low=max(0, min(127, regra.get('note_split_low', 0))),
                ntr_lo=ntr_map.get(regra.get('ntr_lo', 'trans').lower(), 0),
                ntt_lo=ntt_lo_val,
                hkey_lo=regra.get('high_key_lo', 6),
                llim_lo=regra.get('note_limit_low_lo', 0),
                hlim_lo=regra.get('note_limit_high_lo', 127),
                rtr_lo=rtr_map.get(regra.get('rtr_lo', 'pitch shift').lower(), 1),
                source_root=source_root_map.get(regra.get('source_chord_root', 'C'), 0),
                source_type=source_type_map.get(regra.get('source_chord_type', 'Maj7'), 2),
            )

        def montar_registro_novo(ch, regra):
            # A peça que faltava: um canal com regra configurada mas que a
            # seção nunca teve fisicamente (ex: adicionar Guitar num canal
            # que só tinha Rhythm2+Baixo) precisa de um registro Ctb2 criado
            # do zero - editar um registro que não existe não tem efeito
            # nenhum, o teclado só reconhece o que está de verdade no arquivo.
            # Usa as mesmas constantes universais confirmadas em três
            # arquivos reais independentes (ver comentários no ramo que edita
            # um registro já existente, logo abaixo).
            v = valores_de(regra)
            dst_val = max(0, min(15, regra.get('dst', ch)))
            chordmute_val = regra.get('active_chords', None)
            if chordmute_val is None or len(chordmute_val) != 5:
                chordmute_val = bytes([0x03, 0xff, 0xff, 0xff, 0xff])
            nome_voz = nomes_padrao.get(ch, f"Track{ch+1}")[:8].ljust(8).encode('latin-1', errors='ignore')

            r = bytearray(47)
            r[0] = ch
            r[1:9] = nome_voz
            r[9] = dst_val
            r[10] = 0 if regra.get('editable', True) else 1
            r[11] = 0x0f
            r[12] = 0xff
            r[13:18] = bytes(chordmute_val)
            r[18] = v['source_root']
            r[19] = v['source_type']
            r[20] = v['split_low']
            r[21] = v['split']
            r[22] = v['ntr_lo']
            r[23] = v['ntt_lo']
            r[24] = v['hkey_lo']
            r[25] = v['llim_lo']
            r[26] = v['hlim_lo']
            r[27] = v['rtr_lo']
            r[28] = v['ntr']
            r[29] = v['ntt']
            r[30] = v['hkey']
            r[31] = v['llim']
            r[32] = v['hlim']
            r[33] = v['rtr']
            r[34] = v['ntr_hi']
            r[35] = v['ntt_hi']
            r[36] = v['hkey_hi']
            r[37] = v['llim_hi']
            r[38] = v['hlim_hi']
            r[39] = v['rtr_hi']

            # Único byte que continua sem tela dedicada (ver
            # BYTES_CASM_DESCONHECIDOS) - só entra por cima do padrão acima
            # se o Michel de fato mexeu nele na tela de teste; senão o
            # registro novo nasce com o padrão de sempre (0).
            raw_bytes_val = regra.get('raw_bytes')
            if raw_bytes_val:
                for i, valor in raw_bytes_val.items():
                    if 0 <= i < len(r):
                        r[i] = max(0, min(255, valor))

            return b'Ctb2' + (47).to_bytes(4, 'big') + bytes(r)

        def montar_registro_novo_ctab(ch, regra):
            # Mesmo que montar_registro_novo, mas no formato Ctab (SFF1, 27
            # bytes - uma zona de nota só: bytes 20-25 = NTR/NTT/High Key/
            # Low Limit/High Limit/RTR). Usado em arquivos que são SFF1 de
            # verdade (todos os registros Ctab): misturar um Ctb2 de 47
            # bytes ali dentro desalinharia o arquivo pro teclado.
            v = valores_de(regra)
            dst_val = max(0, min(15, regra.get('dst', ch)))
            chordmute_val = regra.get('active_chords', None)
            if chordmute_val is None or len(chordmute_val) != 5:
                chordmute_val = bytes([0x03, 0xff, 0xff, 0xff, 0xff])
            nome_voz = nomes_padrao.get(ch, f"Track{ch+1}")[:8].ljust(8).encode('latin-1', errors='ignore')
            r = bytearray(27)
            r[0] = ch
            r[1:9] = nome_voz
            r[9] = dst_val
            r[10] = 0 if regra.get('editable', True) else 1
            r[11] = 0x0f
            r[12] = 0xff
            r[13:18] = bytes(chordmute_val)
            r[18] = v['source_root']
            r[19] = v['source_type']
            r[20] = v['ntr']
            r[21] = v['ntt']
            r[22] = v['hkey']
            r[23] = v['llim']
            r[24] = v['hlim']
            r[25] = v['rtr']
            return b'Ctab' + (27).to_bytes(4, 'big') + bytes(r)

        # Descobre o formato dos registros que o arquivo já usa (e quais
        # seções já têm bloco CASM próprio) numa passada só de leitura,
        # ANTES de mexer em qualquer coisa.
        nomes_cobertos = set()
        viu_ctab = False
        viu_ctb2 = False
        q = 8
        while True:
            i2 = dados.find(b'CSEG', q)
            if i2 == -1:
                break
            sz2 = int.from_bytes(dados[i2+4:i2+8], 'big')
            pl2 = dados[i2+8:i2+8+sz2]
            q = i2 + 8 + sz2
            s2 = pl2.find(b'Sdec')
            if s2 == -1:
                continue
            tam_sdec2 = int.from_bytes(pl2[s2+4:s2+8], 'big')
            for n in pl2[s2+8:s2+8+tam_sdec2].decode('latin-1', errors='ignore').split(','):
                if n.strip():
                    nomes_cobertos.add(n.strip().lower())
            r2 = s2 + 8 + tam_sdec2
            while r2 < len(pl2):
                t2 = bytes(pl2[r2:r2+4])
                if t2 == b'Ctab':
                    viu_ctab = True
                elif t2 == b'Ctb2':
                    viu_ctb2 = True
                else:
                    break
                r2 += 8 + int.from_bytes(pl2[r2+4:r2+8], 'big')
        # Arquivo SFF1 de verdade (só Ctab) continua gerando Ctab; qualquer
        # outro caso (Ctb2, ou nenhum registro ainda) usa o Ctb2 de sempre.
        usar_ctab = viu_ctab and not viu_ctb2

        pos = 8
        saida_csegs = bytearray()
        while True:
            idx = dados.find(b'CSEG', pos)
            if idx == -1:
                break
            cseg_size = int.from_bytes(dados[idx+4:idx+8], 'big')
            cseg_payload = dados[idx+8:idx+8+cseg_size]
            pos = idx + 8 + cseg_size

            sdec_idx = cseg_payload.find(b'Sdec')
            if sdec_idx == -1:
                saida_csegs += b'CSEG' + cseg_size.to_bytes(4, 'big') + cseg_payload
                continue
            sdec_size = int.from_bytes(cseg_payload[sdec_idx+4:sdec_idx+8], 'big')
            sdec_bloco = cseg_payload[sdec_idx:sdec_idx+8+sdec_size]
            sdec_texto = cseg_payload[sdec_idx+8:sdec_idx+8+sdec_size].decode('latin-1', errors='ignore')
            nomes_secao = [n.strip() for n in sdec_texto.split(',') if n.strip()]
            varredura_inicio = sdec_idx + 8 + sdec_size

            regras_secao = None
            for nome in nomes_secao:
                for nome_guardado, regras in biblioteca.items():
                    if nome_guardado.strip().lower() == nome.strip().lower():
                        regras_secao = regras
                        break
                if regras_secao is not None:
                    break

            if regras_secao is None:
                saida_csegs += b'CSEG' + cseg_size.to_bytes(4, 'big') + cseg_payload
                continue

            canais_existentes = set()
            registros_novos = bytearray()
            p = varredura_inicio
            while p < len(cseg_payload):
                tag = bytes(cseg_payload[p:p+4])
                if tag not in (b'Ctab', b'Ctb2'):
                    break
                bloco_size = int.from_bytes(cseg_payload[p+4:p+8], 'big')
                registro = bytearray(cseg_payload[p+8:p+8+bloco_size])
                p += 8 + bloco_size

                if bloco_size < 18:
                    registros_novos += tag + bloco_size.to_bytes(4, 'big') + bytes(registro)
                    continue

                src = registro[0]
                canais_existentes.add(src)
                regra = regras_secao.get(src)
                if regra is None:
                    registros_novos += tag + bloco_size.to_bytes(4, 'big') + bytes(registro)
                    continue

                v = valores_de(regra)
                dst_val = max(0, min(15, regra.get('dst', src)))
                chordmute_val = regra.get('active_chords', None)
                editable_val = 0 if regra.get('editable', True) else 1

                registro[9] = dst_val
                registro[10] = editable_val
                if chordmute_val is not None and len(chordmute_val) == 5:
                    registro[13:18] = bytes(chordmute_val)

                if bloco_size >= 20:
                    # Bytes 18/19 ("Source Chord"/"Source Chord Type",
                    # documentados na v2.1 - ver comentário no topo do
                    # arquivo): a "primeira parte" do registro (bytes 0-19) é
                    # IDÊNTICA em Ctab e Ctb2 - a LEITURA (extract_casm) já
                    # tratava os dois formatos igual, incondicionalmente. Só
                    # a ESCRITA (aqui) tinha ficado presa atrás de "if tag ==
                    # b'Ctb2'" - um ritmo real do Michel ("ANJINHO DOS
                    # TECLADOS.sty", canal Bass da Intro A, que usa o formato
                    # Ctab de 27 bytes mais antigo) provou o bug: editar a
                    # Nota Fundamental de Origem salvava certinho NA TELA
                    # (Editar Seção reabria mostrando o valor novo), mas o
                    # ARQUIVO salvo continuava com o valor antigo - porque
                    # essa escrita nunca alcançava um registro Ctab. Escreve
                    # o valor de verdade da regra pra QUALQUER formato de
                    # registro que tenha espaço pros bytes 18/19 (Ctab de 27
                    # bytes já tem - só as zonas extras de nota, mais
                    # abaixo, são exclusivas do Ctb2).
                    registro[18] = v['source_root']
                    registro[19] = v['source_type']

                if tag == b'Ctab' and bloco_size >= 26:
                    # Ctab (formato mais antigo/curto) tem só UMA zona de
                    # nota - NTR/NTT/High Key/Low Limit/High Limit/Retrigger
                    # Rule nos bytes 20-25 (documentado na v2.1, tabela 37,
                    # usando os offsets do Ctab regular como referência) -
                    # mapeada pra "Zona Média" no nosso dicionário de regras
                    # (Ctab não tem Zona Aguda/Grave separadas). A leitura
                    # (extract_casm) já lia esses bytes (menos o 25, corrigido
                    # junto com este fix) - a ESCRITA nunca tocava um registro
                    # Ctab, ficando presa atrás de "if tag == b'Ctb2'" (mesma
                    # classe de bug do Source Chord, achada investigando por
                    # que o Retrigger Rule do canal Bass de um ritmo real
                    # (ANJINHO DOS TECLADOS.sty, formato Ctab) nunca sobrevivia
                    # a uma edição - editar RTR pra "retrigger to root" e
                    # salvar o arquivo simplesmente não tinha efeito nenhum.
                    registro[20] = v['ntr']
                    registro[21] = v['ntt']
                    registro[22] = v['hkey']
                    registro[23] = v['llim']
                    registro[24] = v['hlim']
                    registro[25] = v['rtr']

                if tag == b'Ctb2' and bloco_size >= 34:
                    # Bytes 11/12: confirmado comparando vários arquivos reais
                    # independentes - sempre os mesmos em TODO canal de TODO
                    # arquivo, sem exceção - não são configuráveis, uma
                    # constante do formato.
                    registro[11] = 0x0f
                    registro[12] = 0xff

                    # Zona Média (a mais usada) - NTR/NTT/High Key/Limites/RTR.
                    registro[28] = v['ntr']
                    registro[29] = v['ntt']
                    registro[30] = v['hkey']
                    registro[31] = v['llim']
                    registro[32] = v['hlim']
                    registro[33] = v['rtr']

                    # Zona Aguda - fronteira (byte 21), NTR/NTT/High
                    # Key/Limites/RTR (bytes 34-39). Formato inteiro
                    # decifrado com a documentação real do Ctb2 (Peter
                    # Wierzba / Michael P. Bedesem) - ver comentário no topo
                    # do arquivo, perto de RTR_OPCOES.
                    if bloco_size >= 40:
                        registro[21] = v['split']
                        registro[34] = v['ntr_hi']
                        registro[35] = v['ntt_hi']
                        registro[36] = v['hkey_hi']
                        registro[37] = v['llim_hi']
                        registro[38] = v['hlim_hi']
                        registro[39] = v['rtr_hi']

                    # Zona Grave - fronteira (byte 20) e sub-estrutura
                    # inteira (bytes 22-27). Quase sempre inerte na prática
                    # (byte 20 = 0 desliga a zona), mas agora totalmente
                    # decifrada e editável como as outras duas.
                    if bloco_size >= 28:
                        registro[20] = v['split_low']
                        registro[22] = v['ntr_lo']
                        registro[23] = v['ntt_lo']
                        registro[24] = v['hkey_lo']
                        registro[25] = v['llim_lo']
                        registro[26] = v['hlim_lo']
                        registro[27] = v['rtr_lo']

                    # Único byte que continua sem tela dedicada (ver
                    # BYTES_CASM_DESCONHECIDOS) - só é sobrescrito se o
                    # Michel de propósito mudou ele na tela "Byte N".
                    raw_bytes_val = regra.get('raw_bytes')
                    if raw_bytes_val:
                        for i, valor in raw_bytes_val.items():
                            if 0 <= i < bloco_size:
                                registro[i] = max(0, min(255, valor))
                elif tag == b'Ctab' and bloco_size >= 26:
                    registro[20] = v['ntr']
                    registro[21] = v['ntt']
                    registro[22] = v['hkey']
                    registro[23] = v['llim']
                    registro[24] = v['hlim']

                registros_novos += tag + bloco_size.to_bytes(4, 'big') + bytes(registro)

            # Canais com regra configurada nessa seção mas que nunca tiveram
            # registro físico - cria agora, do zero. Confirmado no
            # AcusticoBR4.sty genuíno: o arranjo "só em acorde menor" das
            # Intros/Endings B e C usa os canais 3 a 8 (índice 2-7) como
            # espelho dos canais 11-16 - qualquer um dos 16 canais é válido,
            # não só os 9 "padrão" (Track1/Rhythm/Bass/Chord/Pad/Phrase).
            for ch in range(16):
                if ch in canais_existentes:
                    continue
                regra = regras_secao.get(ch)
                if not isinstance(regra, dict):
                    continue
                regra_e_padrao = (regra == self.get_default_casm_rules()[ch])
                if regra_e_padrao and not canal_tem_notas_na_secao(ch, nomes_secao):
                    # Canal nunca teve registro físico nessa seção do arquivo
                    # original, a regra continua exatamente no padrão de
                    # fábrica E não tem nenhuma nota gravada nessa seção -
                    # ninguém mexeu nele de verdade. Sem essa checagem, TODO
                    # canal vazio ganhava um registro novo do zero em toda
                    # seção, só porque regras_secao sempre tem uma entrada
                    # padrão pros 16 canais - inflava o CASM inteiro (quase
                    # dobrava de tamanho) mesmo quando nada foi alterado.
                    #
                    # Mas se o canal TEM nota (mesmo sem nunca ter aberto a
                    # tela de CASM dele - gravar um acorde não mexe na
                    # regra), o registro precisa ser criado do mesmo jeito,
                    # senão o teclado real não sabe como tratar essa nota e
                    # ela fica muda.
                    continue
                registros_novos += (montar_registro_novo_ctab(ch, regra) if usar_ctab
                                    else montar_registro_novo(ch, regra))

            novo_payload = bytes(sdec_bloco) + bytes(registros_novos)
            saida_csegs += b'CSEG' + len(novo_payload).to_bytes(4, 'big') + novo_payload

        # SEÇÕES QUE EXISTEM NO ARQUIVO MAS NUNCA TIVERAM BLOCO CASM PRÓPRIO
        # (ex.: uma Intro A criada pelo Michel num ritmo de outro
        # programador que só tinha Intro B/C): o laço acima só reescreve
        # blocos CSEG que JÁ estão no arquivo, então tudo que era editado
        # pra essas seções (Editar Seção, Exportar CASM, Copiar Canal...)
        # ficava só na memória - a tela reabria certinha, mas o arquivo
        # salvo nunca levava nada. Cria o bloco agora, no mesmo formato de
        # registro que o arquivo já usa (Ctab em arquivo SFF1, Ctb2 nos
        # outros). Só entram os canais em que alguém mexeu (regra diferente
        # do padrão de fábrica, canais 9-16) ou que têm nota de verdade
        # nessa seção - mesmo critério dos registros novos acima, pra não
        # inflar o arquivo com canais vazios.
        padroes = self.get_default_casm_rules()
        for sec in getattr(self, 'sections_info', []):
            nome_sec = (sec.get('name') or '').strip()
            if not sec.get('present') or sec.get('start') is None or not nome_sec:
                continue
            if nome_sec.lower() in nomes_cobertos:
                continue
            regras_secao = None
            for nome_guardado, regras in biblioteca.items():
                if nome_guardado.strip().lower() == nome_sec.lower():
                    regras_secao = regras
                    break
            if regras_secao is None:
                continue
            registros_da_secao = bytearray()
            for ch in range(16):
                regra = regras_secao.get(ch)
                if not isinstance(regra, dict):
                    continue
                mexido = ch >= 8 and regra != padroes.get(ch)
                if not (mexido or canal_tem_notas_na_secao(ch, [nome_sec])):
                    continue
                registros_da_secao += (montar_registro_novo_ctab(ch, regra) if usar_ctab
                                       else montar_registro_novo(ch, regra))
            if not registros_da_secao:
                continue
            nome_bytes = nome_sec.encode('latin-1', errors='ignore')
            novo_payload = b'Sdec' + len(nome_bytes).to_bytes(4, 'big') + nome_bytes + bytes(registros_da_secao)
            saida_csegs += b'CSEG' + len(novo_payload).to_bytes(4, 'big') + novo_payload
            nomes_cobertos.add(nome_sec.lower())

        return b'CASM' + len(saida_csegs).to_bytes(4, 'big') + bytes(saida_csegs)

    def _upgrade_casm_ctab_para_ctb2(self, dados):
        # Expande cada registro Ctab (formato SFF1, 27 bytes) pro formato
        # Ctb2 (SFF2, 47 bytes) - documentado na v2.1 (Wierzba/Bedesem, item
        # 4.5.1): "The only difference [entre SFF1 e SFF2] is the new Ctb2
        # structure". Só troca a "casca" (tag Ctab->Ctb2, tamanho 27->47,
        # preservando os bytes 0-19 - canal/nome/destino/editável/
        # constantes/chord mute/Source Chord, idênticos nos dois formatos).
        # Os bytes 20-46 nascem zerados aqui DE PROPÓSITO - quem
        # `converter_sff1_para_sff2` chama logo depois (o Salvar Arquivo
        # normal, via `patch_casm_binary`) já reescreve TODOS eles de
        # verdade a partir de `casm_rules_by_section` (as 3 zonas de nota +
        # Source Chord), usando os valores que `converter_sff1_para_sff2`
        # clona da Zona Média pra Aguda/Grave antes de salvar - então não
        # tem sentido tentar acertar esses bytes aqui, só a "casca" importa.
        # Segue o MESMO padrão de varredura de CSEG/Sdec/Ctab/Ctb2 de
        # `patch_casm_binary` (envelope da saída regenerado do zero a
        # partir dos blocos CSEG encontrados - o formato CASM não guarda
        # nada de útil fora deles).
        dados = bytes(dados)
        pos = 8
        saida_csegs = bytearray()
        canais_convertidos = []
        while True:
            idx = dados.find(b'CSEG', pos)
            if idx == -1:
                break
            cseg_size = int.from_bytes(dados[idx+4:idx+8], 'big')
            cseg_payload = dados[idx+8:idx+8+cseg_size]
            pos = idx + 8 + cseg_size

            sdec_idx = cseg_payload.find(b'Sdec')
            if sdec_idx == -1:
                saida_csegs += b'CSEG' + cseg_size.to_bytes(4, 'big') + cseg_payload
                continue
            sdec_size = int.from_bytes(cseg_payload[sdec_idx+4:sdec_idx+8], 'big')
            sdec_bloco = cseg_payload[sdec_idx:sdec_idx+8+sdec_size]
            sdec_texto = cseg_payload[sdec_idx+8:sdec_idx+8+sdec_size].decode('latin-1', errors='ignore')
            nomes_secao = [n.strip() for n in sdec_texto.split(',') if n.strip()]
            varredura_inicio = sdec_idx + 8 + sdec_size

            nome_regras = None
            for nome in nomes_secao:
                if nome in self.casm_rules_by_section:
                    nome_regras = nome
                    break

            registros_novos = bytearray()
            p = varredura_inicio
            while p < len(cseg_payload):
                tag = bytes(cseg_payload[p:p+4])
                if tag not in (b'Ctab', b'Ctb2'):
                    break
                bloco_size = int.from_bytes(cseg_payload[p+4:p+8], 'big')
                registro = cseg_payload[p+8:p+8+bloco_size]
                p += 8 + bloco_size

                if tag == b'Ctab' and bloco_size >= 20:
                    novo = bytearray(47)
                    n = min(len(registro), 20)
                    novo[0:n] = registro[0:n]
                    registros_novos += b'Ctb2' + (47).to_bytes(4, 'big') + bytes(novo)
                    if nome_regras is not None and len(registro) > 0:
                        canais_convertidos.append((nome_regras, registro[0]))
                else:
                    registros_novos += tag + bloco_size.to_bytes(4, 'big') + bytes(registro)

            novo_payload = bytes(sdec_bloco) + bytes(registros_novos)
            saida_csegs += b'CSEG' + len(novo_payload).to_bytes(4, 'big') + novo_payload

        return b'CASM' + len(saida_csegs).to_bytes(4, 'big') + bytes(saida_csegs), canais_convertidos

    def converter_sff1_para_sff2(self, event=None):
        # Pedido do Michel: os ritmos SFF1 (o formato mais antigo, canais
        # CASM em Ctab de 27 bytes) dão conflito com o nosso programa (que
        # trabalha em cima de SFF2/Ctb2) - ex.: o bug do Retrigger Rule do
        # Bass do "ANJINHO DOS TECLADOS.sty" (ver plano). Um teclado que já
        # suporta SFF2 converte um SFF1 automaticamente ao carregar - mas só
        # na memória, nunca salva de volta no arquivo - então reabrir esses
        # arquivos no nosso programa sempre volta pras limitações do formato
        # antigo (só 1 zona de nota, sem Aguda/Grave configuráveis
        # separadamente). Esta ferramenta faz a conversão de verdade, no
        # arquivo.
        #
        # O Michel já tinha tentado à mão (só renomear o marcador SFF1 pra
        # SFF2 no Event List) e o Anjinho ficou TOTALMENTE MUDO no teclado -
        # a documentação explica por quê: "a única diferença é a nova
        # estrutura Ctb2" - trocar só o RÓTULO sem converter os registros
        # físicos faz o teclado tentar ler registros de 47 bytes onde só há
        # 27 (lixo/desalinhamento). Por isso esta função SEMPRE converte os
        # dois juntos (marcador + registros CASM), nunca um sem o outro.
        from MHS_Utils import falar
        if not self.current_file_path or not self.current_midi_data:
            falar("Abra um arquivo salvo em disco primeiro.", imediato=True)
            return

        tpq = self.current_midi_data.ticks_per_beat
        if tpq != 1920:
            wx.MessageBox(
                f"Este arquivo usa {tpq} ticks por semínima - o formato SFF2 exige "
                "exatamente 1920 (documentação oficial, v2.1). Converter os ticks "
                "envolveria reescalar o tempo de TODO o arquivo, uma operação bem "
                "mais arriscada que esta ferramenta não faz. Conversão cancelada.",
                "Não é possível converter", wx.OK | wx.ICON_WARNING)
            return

        tem_sff1 = any(m.type == 'marker' and getattr(m, 'text', '') == 'SFF1' for m in self.merged_track_cache)
        dados = bytes(getattr(self, 'raw_casm_data', b'') or b'')
        n_registros = dados.count(b'Ctab')

        if not tem_sff1 and n_registros == 0:
            falar("Este arquivo já parece ser SFF2 - nenhum marcador SFF1 nem registro "
                  "Ctab (formato antigo) encontrado.", imediato=True)
            return

        # O marcador pode já dizer "SFF2" mesmo com registros Ctab por
        # baixo - exatamente o estado que uma renomeação manual do
        # marcador (sem converter o CASM de verdade) deixa pra trás, como o
        # Michel já tinha feito uma vez no Anjinho. Nesse caso não sobra
        # marcador pra trocar - só o CASM mesmo precisa ser corrigido pra
        # bater com o que o marcador já afirma.
        linha_marcador = ("- Trocar o marcador SFF1 pelo SFF2.\n" if tem_sff1 else
                           "- O marcador já diz SFF2 (mas o CASM ainda está no formato "
                           "antigo por baixo - provavelmente de uma troca manual só do "
                           "rótulo antes; é exatamente essa mistura que deixa o arquivo "
                           "mudo) - não sobra nada pra trocar aqui, só o CASM mesmo.\n")
        resposta = wx.MessageBox(
            f"Este arquivo tem {n_registros} registro(s) CASM no formato antigo "
            "(Ctab/SFF1). A conversão vai:\n\n"
            "- Expandir cada um pro formato novo (Ctb2/SFF2), repetindo os mesmos "
            "valores de NTR/NTT/High Key/Limites/Retrigger Rule nas 3 zonas de nota "
            "(Grave/Média/Aguda) - o mesmo padrão que arquivos SFF2 genuínos da "
            "Yamaha usam quando não há separação de zona de verdade.\n"
            f"{linha_marcador}"
            "- Sobrescrever o arquivo aberto (um backup automático é criado antes, "
            "ao lado dele).\n\n"
            "IMPORTANTE: não há garantia de que isso bate 100% com o conversor "
            "interno da Yamaha (lógica fechada deles, não documentada) - teste no "
            "teclado depois de converter.\n\n"
            "Converter agora?",
            "Converter SFF1 para SFF2", wx.YES_NO | wx.ICON_QUESTION)
        if resposta != wx.YES:
            return

        import shutil
        import datetime
        base, ext = os.path.splitext(self.current_file_path)
        carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_backup = f"{base} (backup antes da conversão SFF2 - {carimbo}){ext}"
        shutil.copy2(self.current_file_path, caminho_backup)

        self.save_state("Converter SFF1 para SFF2")

        novo_raw_casm, canais_convertidos = self._upgrade_casm_ctab_para_ctb2(dados)
        self.raw_casm_data = novo_raw_casm

        # Clona a "Zona Média" (a única que o Ctab tinha) pras Zonas Aguda e
        # Grave, e marca a fronteira das zonas como "sem separação real"
        # (Grave termina em 0, Aguda começa em 127) - o padrão que arquivos
        # SFF2 genuínos (ex.: LAIRTON 02.S837.sty) mostram quando o canal
        # nunca teve zona separada de verdade. `patch_casm_binary` (chamado
        # por `salvar_arquivo_sty`, logo abaixo) usa esses valores pra
        # escrever os bytes 20-39 de cada registro Ctb2 recém-expandido.
        for nome_secao, ch in canais_convertidos:
            regras_secao = self.casm_rules_by_section.get(nome_secao)
            if regras_secao is None or ch not in regras_secao:
                continue
            r = regras_secao[ch]
            r['note_split_high'] = 127
            r['note_split_low'] = 0
            r['ntr_hi'] = r.get('play_type', 'trans')
            r['ntt_hi'] = r.get('ntt_type', 'bypass')
            r['ntt_hi_bass'] = r.get('ntt_bass', False)
            r['high_key_hi'] = r.get('high_key', 6)
            r['note_limit_low_hi'] = r.get('note_limit_low', 0)
            r['note_limit_high_hi'] = r.get('note_limit_high', 127)
            r['rtr_hi'] = r.get('rtr', 'pitch shift')
            r['ntr_lo'] = r.get('play_type', 'trans')
            r['ntt_lo'] = r.get('ntt_type', 'bypass')
            r['ntt_lo_bass'] = r.get('ntt_bass', False)
            r['high_key_lo'] = r.get('high_key', 6)
            r['note_limit_low_lo'] = r.get('note_limit_low', 0)
            r['note_limit_high_lo'] = r.get('note_limit_high', 127)
            r['rtr_lo'] = r.get('rtr', 'pitch shift')

        # Troca o marcador SFF1 pelo SFF2 - a única outra diferença
        # documentada (v2.1, item 4.5.1).
        for m in self.merged_track_cache:
            if m.type == 'marker' and getattr(m, 'text', '') == 'SFF1':
                m.text = 'SFF2'

        self.dirty = True
        self.salvar_arquivo_sty(self.current_file_path)
        self.atualizar_titulo()
        falar(f"Convertido: {len(canais_convertidos)} registro(s) CASM de SFF1 pra SFF2. "
              f"Arquivo salvo - backup do original guardado ao lado, com a data e hora no "
              f"nome. Teste no teclado antes de confiar cegamente.", imediato=True)

    def _aplicar_editavel_estilo_inteiro(self, tornar_editavel):
        # Aplica 'editable' (CASM byte 10 - já corrigido: True = de
        # verdade editável no teclado, False = protegido/força apagar e
        # regravar do zero) nos 16 canais de TODAS as seções presentes de
        # uma vez - usado por travar_estilo_inteiro/destravar_estilo_inteiro.
        nomes_secoes = [s['name'] for s in getattr(self, 'sections_info', []) if s.get('present')]
        for nome in nomes_secoes:
            regras = self.obter_casm_da_secao(nome, criar_se_ausente=True)
            for ch in range(TOTAL_CANAIS):
                if ch in regras:
                    regras[ch]['editable'] = tornar_editavel
        return len(nomes_secoes)

    def travar_estilo_inteiro(self, event=None):
        # Pedido do Michel depois de trazer o "stylekey.cs" (um utilitário
        # externo em C#, roda por linha de comando) que fazia exatamente
        # isso - varrer todos os registros CASM (Ctab/Ctb2) de um .sty e
        # forçar o byte "Editável" em TODOS os canais de uma vez. Em vez
        # de tentar rodar/portar o .cs (Windows-only, compilado, seria uma
        # dependência externa desnecessária - o programa já lê/escreve
        # esse exato byte), a mesma ação foi implementada nativamente,
        # reaproveitando o CASM já testado - e usando a semântica CERTA
        # do byte (confirmada pelo Michel testando no SX600: 'Editável:
        # Desligado' é o que realmente PROTEGE o canal no teclado real,
        # forçando apagar e regravar do zero em vez de deixar sobrepor -
        # ver o fix da inversão de 'Editável', logo acima neste arquivo).
        # Pedido do Michel depois de testar e confirmar que funciona: caixa
        # de confirmação bem mais curta (sem o parágrafo inteiro
        # explicando o mecanismo) e SEM backup automático - já validado,
        # não precisa mais dessa rede de segurança.
        from MHS_Utils import falar
        if not self.current_file_path or not self.current_midi_data:
            falar("Abra um arquivo salvo em disco primeiro.", imediato=True)
            return

        resposta = wx.MessageBox(
            "Isso bloqueará os canais de Bass em diante a serem editados no teclado. "
            "Tem certeza que deseja bloquear?",
            "Travar Estilo Inteiro (Editável)", wx.YES_NO | wx.ICON_QUESTION)
        if resposta != wx.YES:
            return

        self.save_state("Travar Estilo Inteiro (Editável)")
        n_secoes = self._aplicar_editavel_estilo_inteiro(False)

        self.dirty = True
        self.salvar_arquivo_sty(self.current_file_path)
        self.atualizar_titulo()
        falar(f"Estilo travado: {n_secoes} seção(ões), 16 canais cada, marcados como "
              f"'Editável: Desligado'. Arquivo salvo.", imediato=True)

    def destravar_estilo_inteiro(self, event=None):
        # Reverso de travar_estilo_inteiro - mesma ideia, mesma caixa de
        # confirmação curta, sem backup (pedido do Michel depois de
        # validar as duas ferramentas), marcando 'Editável: Ligado' (de
        # verdade editável/sobrepor no teclado real) em vez de desligado.
        from MHS_Utils import falar
        if not self.current_file_path or not self.current_midi_data:
            falar("Abra um arquivo salvo em disco primeiro.", imediato=True)
            return

        resposta = wx.MessageBox(
            "Isso desbloqueará os canais de Bass em diante a serem editados no "
            "teclado. Tem certeza que deseja desbloquear?",
            "Destravar Estilo Inteiro (Editável)", wx.YES_NO | wx.ICON_QUESTION)
        if resposta != wx.YES:
            return

        self.save_state("Destravar Estilo Inteiro (Editável)")
        n_secoes = self._aplicar_editavel_estilo_inteiro(True)

        self.dirty = True
        self.salvar_arquivo_sty(self.current_file_path)
        self.atualizar_titulo()
        falar(f"Estilo destravado: {n_secoes} seção(ões), 16 canais cada, marcados como "
              f"'Editável: Ligado'. Arquivo salvo.", imediato=True)

    def atualizar_titulo(self):
        nome = os.path.basename(self.current_file_path) if self.current_file_path else "Novo Estilo"
        marca = "*" if self.dirty else ""
        grav = " [GRAVANDO]" if self.gravando else ""
        self.SetTitle(f"{marca}{nome}{grav} - MHS Style Creator Acessível v{VERSAO_APP}")

    def check_save(self):
        if not self.dirty: return True
        nome = os.path.basename(self.current_file_path) if self.current_file_path else "Novo Estilo"
        dlg = wx.MessageDialog(self, f"O estilo '{nome}' tem alterações não salvas. Deseja salvar agora?", "MHS Style Creator", wx.YES_NO | wx.CANCEL | wx.ICON_WARNING)
        dlg.SetYesNoCancelLabels("&Sim", "&Não", "&Cancelar")
        res = dlg.ShowModal()
        dlg.Destroy()
        if res == wx.ID_YES:
            if self.current_file_path:
                self.salvar_arquivo_sty(self.current_file_path)
                return True
            else:
                self.OnSaveAs(None)
                return not self.dirty
        elif res == wx.ID_CANCEL: return False
        return True

    # Tudo que pertence a UM estilo aberto - trocar de aba salva isso tudo
    # na aba de saída e recarrega isso tudo da aba de entrada. midi_out/
    # midi_in/playing/gravando etc. NÃO entram aqui de propósito - são do
    # motor MIDI, compartilhados por todas as abas (só existe uma porta de
    # saída de verdade).
    ATRIBUTOS_DOCUMENTO = [
        'current_file_path', 'undo_stack', 'redo_stack', 'dirty',
        'canais_selecionados', 'in_point', 'out_point',
        'current_midi_data', 'merged_track_cache', 'sections_info',
        'current_section_msgs', 'midi_setup_msgs', 'raw_casm_data',
        'casm_rules', 'casm_rules_by_section', 'canais', 'canais_ao_carregar',
        'canal_atual', 'propriedade_atual',
        'pending_section', 'current_tempo', 'last_idx',
        'section_duration_seconds', 'current_main_prefix', 'beats_per_measure',
        'dsp_global', 'dsp_variation',
    ]

    def _dsp_global_padrao(self):
        # 'rev_p'/'cho_p': os 16 parâmetros de cada efeito (mesmo modelo do
        # 'p' da Variation) - todos começam em -1 (não usar) até o usuário
        # mexer neles.
        return {
            'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
            'rev_p': [-1] * 16, 'rev_ret': 64,
            'cho_msb_idx': 1, 'cho_lsb_idx': 0,
            'cho_p': [-1] * 16, 'cho_ret': 64,
        }

    def _dsp_variation_padrao(self):
        # 'chs': dicionário {canal (0-15): nível de envio (0-127)} - com
        # "Conexão" em SYSTEM (ver sincronizar_dsp_no_track), qualquer
        # quantidade de canais pode mandar sinal pro mesmo efeito ao mesmo
        # tempo, cada um com seu próprio nível (endereço 0x14 no bloco Multi
        # Part, confirmado no Data List oficial do PSR-SX600). Com só 1
        # canal, usa o modo antigo (INSERTION) em vez disso - ver
        # sincronizar_dsp_no_track.
        return {'active': False, 'chs': {}, 'msb_idx': 0, 'msb_val': 0, 'lsb_idx': 0, 'ret': 64, 'p': [-1] * 16}

    def capturar_estado_documento(self):
        # CÓPIA DE VERDADE, não referência - o resto do código (load_style_data
        # etc.) muda os itens DENTRO da mesma lista (self.canais[ch] = ...) em
        # vez de criar uma lista nova, então sem o deepcopy aqui, duas abas
        # acabavam enxergando a mesmíssima lista por baixo dos panos e uma
        # carregada "vazava" pra dentro da outra.
        return {nome: copy.deepcopy(getattr(self, nome, None)) for nome in self.ATRIBUTOS_DOCUMENTO}

    def aplicar_estado_documento(self, estado):
        for nome in self.ATRIBUTOS_DOCUMENTO:
            setattr(self, nome, estado.get(nome))

    def titulo_da_aba(self, estado):
        nome = os.path.basename(estado.get('current_file_path') or "") or "Novo Estilo"
        marca = "*" if estado.get('dirty') else ""
        return f"{marca}{nome}"

    def sincronizar_aba_atual(self):
        # Guarda o que está ao vivo agora de volta na aba atual - chamar
        # antes de trocar/fechar/criar outra aba, senão a edição se perde.
        if self.aba_atual == -1 or not self.abas:
            return
        estado = self.capturar_estado_documento()
        # Guarda também onde o cursor estava nas duas listas - senão, ao
        # voltar pra essa aba, ela sempre caía na primeira seção (Intro A) e
        # no canal 1, perdendo o lugar onde você realmente estava.
        estado['_secao_idx'] = self.sectionList.GetSelection()
        estado['_canal_idx'] = self.channelList.GetSelection()
        self.abas[self.aba_atual]['estado'] = estado
        self.abas[self.aba_atual]['titulo'] = self.titulo_da_aba(estado)

    def criar_aba(self):
        # Só reserva o lugar e faz dela a atual - quem chama ainda precisa
        # popular self.X (OnNewStyle/load_style_data já fazem isso) e depois
        # chamar sincronizar_aba_atual() pra guardar o resultado na aba.
        self.sincronizar_aba_atual()
        self.abas.append({'titulo': 'Novo Estilo', 'estado': None})
        self.aba_atual = len(self.abas) - 1

    def desfazer_criacao_de_aba(self):
        # Usado quando abrir um arquivo falha no meio do caminho - tira a
        # aba em branco que tinha acabado de ser criada pra ele.
        if self.aba_atual == -1 or not self.abas:
            return
        idx = self.aba_atual
        del self.abas[idx]
        if not self.abas:
            self.aba_atual = -1
        else:
            self.ir_para_aba(min(idx, len(self.abas) - 1), salvar_atual=False)

    def ir_para_aba(self, idx, salvar_atual=True):
        if idx < 0 or idx >= len(self.abas) or idx == self.aba_atual:
            return
        if self.playing:
            self.OnTogglePlay(None)
        if self.gravando:
            self.gravando = False
            self.recorded_events = []
        if salvar_atual:
            self.sincronizar_aba_atual()
        # Zera o teclado ANTES de trocar - sem isso, resquício de Bank/Patch/
        # CC do ritmo anterior podia vazar pro que está sendo carregado agora
        # (mesmo comportamento do MHS MIDI Sequencer ao trocar de guia).
        self.reset_fisico_teclado()
        self.aba_atual = idx
        estado = self.abas[idx]['estado']
        self.aplicar_estado_documento(estado)
        self.anchor_tick = 0
        self.current_accumulated_ticks = 0
        self.send_initial_setup()
        self.refresh_section_list(forcar_idx=estado.get('_secao_idx'))
        self.update_mixer_list()
        canal_idx = estado.get('_canal_idx')
        if canal_idx is not None and 0 <= canal_idx < self.channelList.GetCount():
            self.channelList.SetSelection(canal_idx)
        self.atualizar_titulo()
        falar(f"Aba {idx+1} de {len(self.abas)}: {self.abas[idx]['titulo']}", imediato=True)

    def proxima_aba(self, event):
        if len(self.abas) < 2:
            falar("Nenhuma aba aberta." if not self.abas else "Só tem uma aba aberta.", imediato=True)
            return
        self.ir_para_aba((self.aba_atual + 1) % len(self.abas))

    def aba_anterior(self, event):
        if len(self.abas) < 2:
            falar("Nenhuma aba aberta." if not self.abas else "Só tem uma aba aberta.", imediato=True)
            return
        self.ir_para_aba((self.aba_atual - 1) % len(self.abas))

    def fechar_aba_atual(self, event):
        if self.aba_atual == -1 or not self.abas:
            falar("Nenhuma aba aberta.", imediato=True)
            return
        if not self.check_save():
            falar("Cancelado.", imediato=True)
            return
        titulo_fechada = self.abas[self.aba_atual]['titulo']
        idx = self.aba_atual
        del self.abas[idx]
        if not self.abas:
            self.aba_atual = -1
            self._resetar_documento_vazio()
            falar(f"{titulo_fechada} fechada. Nenhuma aba aberta.", imediato=True)
        else:
            novo_idx = min(idx, len(self.abas) - 1)
            self.aba_atual = -1  # força ir_para_aba a aplicar mesmo se o índice coincidir
            self.ir_para_aba(novo_idx, salvar_atual=False)
            falar(f"{titulo_fechada} fechada.", imediato=True)

    def _resetar_documento_vazio(self):
        from MHS_Utils import TOTAL_CANAIS, VALOR_MAX_MIDI
        self.reset_fisico_teclado()
        self.current_file_path = None
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False
        self.canais_selecionados = {0}
        self.non_continuous_sel = False
        self.in_point = None
        self.out_point = None
        self.current_midi_data = None
        self.merged_track_cache = []
        self.sections_info = []
        self.current_section_msgs = []
        self.section_has_mid_sysex = False
        self.midi_setup_msgs = []
        self.raw_casm_data = b''
        self.casm_rules = self.get_default_casm_rules()
        self.casm_rules_by_section = {}
        self.canais = []
        for ch in range(TOTAL_CANAIS):
            self.canais.append({"Nome": f"Canal {ch+1}", "Mute": False, "Solo": False, "Arm": False, "Volume": 100, "Pan": 64, "Expression": VALOR_MAX_MIDI, "Bank": 0, "Patch": 0, "Reverb": 0, "Chorus": 0, "Grave": 64, "Agudo": 64})
        self.canais_ao_carregar = copy.deepcopy(self.canais)
        self.canal_atual = 0
        self.propriedade_atual = 0
        self.pending_section = None
        self.current_tempo = 500000
        self.last_idx = -1
        self.section_duration_seconds = 0
        self.current_main_prefix = "Main A"
        self.beats_per_measure = 4
        self.dsp_global = self._dsp_global_padrao()
        self.dsp_variation = self._dsp_variation_padrao()
        self.refresh_section_list()
        self.update_mixer_list()
        self.atualizar_titulo()

    def verificar_salvar_todas_abas(self):
        # Chamado ao sair do programa - confere TODAS as abas, não só a
        # atual (o check_save sozinho só enxerga a que está ao vivo agora).
        self.sincronizar_aba_atual()
        idx_original = self.aba_atual
        for i in range(len(self.abas)):
            if i != self.aba_atual:
                self.aba_atual = -1
                self.ir_para_aba(i, salvar_atual=False)
            if not self.check_save():
                return False
            self.sincronizar_aba_atual()
        if idx_original != -1 and 0 <= idx_original < len(self.abas):
            self.aba_atual = -1
            self.ir_para_aba(idx_original, salvar_atual=False)
        return True

    def registrar_recente(self, path):
        recentes = self.config.get('recentes', [])
        recentes = [p for p in recentes if p != path]
        recentes.insert(0, path)
        self.config['recentes'] = recentes[:10]
        self.save_config()
        self.atualizar_menu_recentes()

    def atualizar_menu_recentes(self):
        menu = getattr(self, 'recent_menu', None)
        if menu is None:
            return
        for item in list(menu.GetMenuItems()):
            menu.Delete(item.GetId())
        recentes = self.config.get('recentes', [])
        if not recentes:
            menu.Append(wx.ID_ANY, "(nenhum arquivo recente)").Enable(False)
            return
        for i, path in enumerate(recentes):
            item = menu.Append(300 + i, f"&{i+1} {os.path.basename(path)}")
            self.Bind(wx.EVT_MENU, lambda e, p=path: self.abrir_caminho_em_nova_aba(p), item)

    def abrir_caminho_em_nova_aba(self, path):
        if not os.path.exists(path):
            falar("Esse arquivo não existe mais nesse caminho.", imediato=True)
            return
        self.criar_aba()
        try:
            self.load_style_data(path)
        except Exception:
            self.desfazer_criacao_de_aba()
            falar("Erro ao abrir o arquivo.", imediato=True)
            return
        # Trava a duração da seção que for FISICAMENTE A ÚLTIMA do arquivo
        # (qualquer que seja - não é sempre "a última do Ending"; pode ser
        # um Fill In, ou até uma Intro sozinha, dependendo de como cada
        # ritmo foi montado) assim que o arquivo é carregado, sem precisar
        # de nenhuma ação manual - pedido do Michel depois de repetidas
        # vezes vendo a duração da última seção "vazar" só de editar
        # OUTRO lugar do arquivo (a causa: sem seção seguinte, ela usa
        # "onde o arquivo termina" como fim, sem âncora nenhuma). Não mexe
        # em nenhuma nota (isso é feito só sob confirmação, pela ferramenta
        # manual Verificar Notas Cruzando Seções) - só planta um marcador
        # inerte, então é seguro rodar sempre, sem perguntar nada.
        # Mesma ideia: corrige silenciosamente a ordem de mensagens
        # empatadas no mesmo tick que ficaram erradas em alguma edição
        # anterior (achado com o Michel: o marcador "SInt" do cabeçalho
        # ficando antes do SysEx de configuração, em vez de depois - o
        # Style Creator do teclado sempre mantém depois) - ANTES de
        # travar a última seção, já que ambos mexem no mesmo cache.
        # Mesma ideia, mas pra remover um "SInt" que sobrou por engano
        # bem em cima de um marcador de seção DE VERDADE (redundante -
        # a seção já tem o marcador dela ali) - rodada ANTES das duas
        # acima, pra não sobrar nenhum SInt fora de lugar antes de
        # normalizar/travar o resto.
        if self._remover_identidade_sff2_duplicada_se_precisar():
            self.dirty = True
            falar("Este ritmo é SFF1 e tinha uma identidade SFF2 duplicada, deixada por uma versão antiga ao criar seção. Já corrigi - salve o arquivo para gravar.", imediato=True)
        if self._remover_sint_redundante_se_precisar():
            self.dirty = True
        if self._normalizar_ordem_mensagens_se_precisar():
            self.dirty = True
        if self._travar_secao_final_se_precisar():
            self.dirty = True
        self.sincronizar_aba_atual()
        self.registrar_recente(path)
        self.refresh_section_list()
        self.update_mixer_list()

    def _snapshot_state(self, action_name):
        # `current_midi_data` guardava um deepcopy do mido.MidiFile INTEIRO
        # (com as tracks originais do arquivo) - achado com o Michel que
        # isso nunca é lido de volta em lugar nenhum: `.ticks_per_beat` é o
        # único atributo que qualquer parte do programa usa dele (a
        # gravação de verdade sempre reconstrói as tracks do zero a partir
        # de merged_track_cache, ver salvar_arquivo_sty). Guardar só o
        # ticks_per_beat (um inteiro) em vez do objeto inteiro - e usar
        # msg.copy() em vez de deepcopy pra cada mensagem da lista, que o
        # mido já faz de um jeito bem mais rápido que o deepcopy genérico -
        # foi o que descobrimos ser o motivo real do atraso ao começar a
        # gravar (medido: ~65ms por chamada no Pop MHS 02.sty, virando ~3ms).
        return {
            "action": action_name,
            "tpb": self.current_midi_data.ticks_per_beat if self.current_midi_data else 480,
            "merged_cache": [m.copy() for m in self.merged_track_cache],
            "canais": copy.deepcopy(self.canais),
            "beats": self.beats_per_measure,
            "tempo": self.current_tempo,
            "dsp_variation": copy.deepcopy(getattr(self, 'dsp_variation', None)),
            "dsp_global": copy.deepcopy(getattr(self, 'dsp_global', None)),
        }

    def save_state(self, action_name="Ação"):
        if len(self.undo_stack) >= 30: self.undo_stack.pop(0)
        self.undo_stack.append(self._snapshot_state(action_name))
        self.redo_stack.clear()

    def redo(self, event):
        if self.playing: self.OnTogglePlay(None)
        if not self.redo_stack: falar("Nada para refazer.", imediato=True); return
        self.undo_stack.append(self._snapshot_state("Refazer"))
        state = self.redo_stack.pop()
        self._restore_state(state)
        falar(f"Refeito: {state['action']}", imediato=True)

    def _restore_state(self, state):
        self.current_midi_data = mido.MidiFile(ticks_per_beat=state["tpb"])
        self.merged_track_cache = [m.copy() for m in state["merged_cache"]]
        self.canais = copy.deepcopy(state["canais"])
        self.beats_per_measure = state["beats"]
        self.current_tempo = state["tempo"]
        if state.get("dsp_variation") is not None:
            self.dsp_variation = copy.deepcopy(state["dsp_variation"])
        if state.get("dsp_global") is not None:
            self.dsp_global = copy.deepcopy(state["dsp_global"])
        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_sections_from_cache()
        self.send_initial_setup()

    def _agendar_restaurar_foco(self, foco_anterior, atraso=100):
        # Devolve o foco pro MESMO controle que estava em foco antes de
        # abrir o diálogo (Seções, Canais, ou qualquer outro) em vez de
        # sempre forçar pra um lugar fixo - pedido do Michel pra QUALQUER
        # tela acessível pela janela principal se comportar assim, não só
        # Event List/Copiar Canal/Efeitos MIDI (que já tinham esse ajuste).
        def _restaurar():
            try:
                if foco_anterior:
                    foco_anterior.SetFocus()
                    return
            except RuntimeError:
                pass
            self.channelList.SetFocus()
        wx.CallLater(atraso, _restaurar)

    def abrir_quantizacao_realtime(self, event):
        foco_antes = wx.Window.FindFocus()
        dlg = QuantizacaoRealTimeDialog(self, self.rt_quantize, self.rt_quantize_res)
        if dlg.ShowModal() == wx.ID_OK:
            self.rt_quantize, self.rt_quantize_res = dlg.get_valores()
            falar("Opções de quantização aplicadas.", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()

    def aplicar_quantizacao_offline(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]
        dlg = QuantizarOfflineDialog(self, getattr(self, 'rt_quantize_res', 16))
        if dlg.ShowModal() == wx.ID_OK:
            res = dlg.get_valores()
            tpq = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
            grid = (tpq * 4.0) / res
            self.save_state("Quantizar")
            abs_msgs = []
            curr_t = 0
            for msg in self.merged_track_cache:
                curr_t += msg.time
                if getattr(msg, 'channel', -1) in self.canais_selecionados and sec['start'] <= curr_t < sec['end']:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        rel = curr_t - sec['start']
                        new_t = sec['start'] + int(round(rel / grid) * grid)
                        abs_msgs.append((new_t, msg.copy()))
                        continue
                abs_msgs.append((curr_t, msg.copy()))
            self.rebuild_from_abs_list(abs_msgs)
            falar(f"{len(self.canais_selecionados)} canais quantizados.", imediato=True)
        dlg.Destroy()

    def aplicar_envelope_cc(self, event):
        # Trazido do MHS MIDI Sequencer (Shift+E), a pedido do Michel -
        # mesma tela (EnvelopeCCDialog, lista com nome de cada CC e valor
        # pré-preenchido do canal atual), mesmo motor de rampa já testado
        # do Fade In/Fade Out (_aplicar_rampa_cc), só que com o CC/valores
        # escolhidos na tela em vez de fixos em CC 11.
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de aplicar um Envelope de CC.", imediato=True)
            return
        if self.in_point is None or self.out_point is None:
            falar("Marque um trecho com Entrada (I) e Saída (O) antes de aplicar o Envelope de CC.", imediato=True)
            return
        foco_antes = wx.Window.FindFocus()
        dlg = EnvelopeCCDialog(self, self.canal_atual)
        if dlg.ShowModal() == wx.ID_OK:
            cc, v1, v2 = dlg.get_values()
            self._aplicar_rampa_cc(cc, v1, v2)
        dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def alterar_bpm_incremental(self, delta):
        if not self.current_midi_data: return
        self.save_state("Alterar BPM Geral")
        current_bpm = int(round(mido.tempo2bpm(self.current_tempo)))
        novo_bpm = max(20, min(300, current_bpm + delta))
        self.current_tempo = mido.bpm2tempo(novo_bpm)
        tempo_encontrado = False
        abs_t = 0
        for msg in self.merged_track_cache:
            abs_t += msg.time
            if msg.type == 'set_tempo' and abs_t == 0:
                msg.tempo = self.current_tempo
                tempo_encontrado = True
        if not tempo_encontrado:
            self.merged_track_cache.insert(0, mido.MetaMessage('set_tempo', tempo=self.current_tempo, time=0))
        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_sections_from_cache()
        falar(f"BPM {novo_bpm}", imediato=True)

    def aplicar_envelope_tempo(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]
        target_tick = self.get_current_absolute_tick()
        has_io = (self.in_point is not None and self.out_point is not None)
        if has_io:
            start_tick = min(self.in_point, self.out_point)
            end_tick = max(self.in_point, self.out_point)
        else:
            start_tick = target_tick
            end_tick = target_tick
        tpq = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
        current_bpm_tempo = self.current_tempo
        scan_accum = 0
        for m in self.merged_track_cache:
            scan_accum += m.time
            if scan_accum <= start_tick:
                if m.type == 'set_tempo':
                    current_bpm_tempo = m.tempo
            else: break
        current_bpm = int(round(mido.tempo2bpm(current_bpm_tempo)))
        dlg = TempoEnvelopeDialog(self, current_bpm)
        if dlg.ShowModal() == wx.ID_OK:
            bpm1, gradual, bpm2 = dlg.get_values()
            self.save_state("Envelope de Tempo")
            if gradual and not has_io:
                end_tick = sec.get('end', float('inf'))
                if end_tick == float('inf'):
                    end_tick = sec.get('start', 0) + (tpq * self.beats_per_measure)
            abs_msgs = []
            curr_t = 0
            for msg in self.merged_track_cache:
                curr_t += msg.time
                if msg.type == 'set_tempo' and start_tick <= curr_t <= end_tick: continue 
                abs_msgs.append((curr_t, msg))
            if not gradual:
                abs_msgs.append((start_tick, mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm1))))
            else:
                ticks_diff = end_tick - start_tick
                if ticks_diff <= 0: ticks_diff = 1
                step_ticks = tpq / 8
                steps = max(2, int(ticks_diff / step_ticks)) 
                for i in range(steps):
                    t = start_tick + int(i * ticks_diff / (steps - 1))
                    if t > end_tick: t = end_tick
                    current_step_bpm = bpm1 + (bpm2 - bpm1) * (i / (steps - 1))
                    abs_msgs.append((t, mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(int(current_step_bpm)))))
            abs_msgs.sort(key=lambda x: x[0])
            self.merged_track_cache = []
            last_t = 0
            for t, msg in abs_msgs:
                msg.time = int(round(t - last_t))
                self.merged_track_cache.append(msg)
                last_t = t
            self.in_point = None
            self.out_point = None
            self.dirty = True
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            falar("Envelope de Tempo aplicado.", imediato=True)
        dlg.Destroy()

    def aplicar_humanizacao(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        self.save_state("Humanização") 
        dlg = HumanizeDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirty = True
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            falar("Humanização aplicada.", imediato=True)
        else:
            self.undo_stack.pop() 
            falar("Cancelado.", imediato=True)
        dlg.Destroy()

    def abrir_velocity_control(self, event):
        foco_antes = wx.Window.FindFocus()
        dlg = VelocityControlDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            estado = "ativado" if self.in_vel_ctrl_on else "desativado"
            falar(f"Configurações de Velocity Control aplicadas ({estado}).", imediato=True)
        else:
            dlg.restaurar()
            falar("Cancelado.", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()

    def abrir_dsp_global(self, event):
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de mexer nos efeitos.", imediato=True)
            return
        foco_antes = wx.Window.FindFocus()
        dlg = GlobalDSPDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.save_state("Efeitos DSP Globais")
            self.sincronizar_dsp_no_track()
            falar("Efeitos DSP Globais aplicados e salvos no estilo.", imediato=True)
        else:
            dlg.restaurar()
            falar("Cancelado.", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()

    def abrir_dsp_variation(self, event):
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de mexer nos efeitos.", imediato=True)
            return
        foco_antes = wx.Window.FindFocus()
        dlg1 = SelecionarEfeitoVariationDialog(self, self.canal_atual)
        if dlg1.ShowModal() != wx.ID_OK:
            removido = dlg1.efeito_removido
            dlg1.Destroy()
            if not removido:
                falar("Cancelado.", imediato=True)
            self._agendar_restaurar_foco(foco_antes)
            return
        canais_idx, msb_idx, msb_val, lsb_idx = dlg1.get_valores()
        dlg1.Destroy()

        dlg2 = EditorParametrosVariationDialog(self, canais_idx, msb_val, msb_idx, lsb_idx)
        # Não depende do valor que ShowModal() devolve - esse editor não tem
        # um "cancelar" de verdade (Enter, Esc, X e o botão fecham todos
        # mantendo os valores), e em um teste real ShowModal() voltou algo
        # diferente de ID_OK mesmo com o diálogo fechando do jeito certo -
        # então sincroniza sempre, incondicionalmente.
        dlg2.ShowModal()
        self.save_state("Efeito DSP de Inserção")
        self.sincronizar_dsp_no_track()
        nomes_canais = ", ".join(str(c + 1) for c in canais_idx) if canais_idx else "nenhum"
        falar(f"Efeito salvo. Canais: {nomes_canais}.", imediato=True)
        dlg2.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def abrir_conversor_midi(self, event):
        foco_antes = wx.Window.FindFocus()
        dlg = MidiRouterDialog(self, self.rotas_midi)
        if dlg.ShowModal() == wx.ID_OK:
            self.rotas_midi = dlg.get_valores()
            self.config['rotas_midi'] = self.rotas_midi
            self.save_config()
            falar("Rotas MIDI atualizadas.", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()

    def abrir_event_list(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []):
            falar("Selecione uma seção primeiro.", imediato=True)
            return
        section = self.sections_info[idx]
        if not section.get('present', False) or section.get('start') is None:
            falar("Esta seção está vazia.", imediato=True)
            return
        tpq = getattr(self.current_midi_data, 'ticks_per_beat', 480)
        self.save_state("Edições no Event List")
        start_tick = self.current_accumulated_ticks if self.playing else self.anchor_tick
        # Guarda quem tinha foco ANTES de abrir (sectionList ou channelList,
        # o que o Michel estava usando) pra devolver o foco pro mesmo lugar
        # ao fechar - sem isso, o código sempre mandava pro channelList,
        # mesmo se ele tivesse saído da sectionList.
        foco_antes_do_event_list = wx.Window.FindFocus()
        dlg = EventListDialog(self, self.canal_atual, section, self.current_tempo, tpq)
        
        # Injeta o Dialog na memória da thread segura
        self.active_midi_dialog = dlg
        
        if hasattr(dlg, 'set_playhead_tick'):
            wx.CallAfter(dlg.set_playhead_tick, start_tick)
        dlg.ShowModal()
        
        # Limpa ao fechar
        self.active_midi_dialog = None
        
        if getattr(dlg, 'modified', False):
            self.dirty = True
            self.atualizar_titulo()
        else:
            self.undo_stack.pop()
        dlg.Destroy()
        def _restaurar_foco():
            if foco_antes_do_event_list:
                foco_antes_do_event_list.SetFocus()
            else:
                self.channelList.SetFocus()
        wx.CallLater(100, _restaurar_foco)

    def editar_secao(self, event):
        import wx
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]

        nome_do_preset_acordes = chord_mute_nome

        NTR_OPCOES = ["trans", "fixed", "gtr"]
        NTT_OPCOES = ['bypass', 'melody', 'chord', 'melodic minor', 'melodic minor 5th', 'harmonic minor',
                      'harmonic minor 5th', 'natural minor', 'natural minor 5th', 'dorian', 'dorian 5th',
                      'all purpose', 'any chord', 'vocal', 'pitch shift']

        # Nomes de propriedade agrupados por "tipo de edição" - a tela de
        # CASM agora tem as 3 zonas de nota (grave/média/aguda) inteiras,
        # cada uma com seu próprio NTR/NTT/NTT Bass/High Key/Limites/RTR;
        # sem agrupar assim, cada handler de tecla abaixo viraria uma cópia
        # quase idêntica pra cada zona.
        PROPS_NTR = ("NTR (Play Type)", "Zona Aguda NTR", "Zona Grave NTR")
        PROPS_NTT = ("NTT Type", "Zona Aguda NTT", "Zona Grave NTT")
        PROPS_NTT_BASS = ("NTT Bass", "Zona Aguda NTT Bass", "Zona Grave NTT Bass")
        PROPS_RTR = ("Retrigger Rule (RTR)", "Zona Aguda Retrigger Rule (RTR)", "Zona Grave Retrigger Rule (RTR)")
        PROPS_BOOL_LIGADO = PROPS_NTT_BASS + ("Toca Sem Acorde", "Editável")
        PROPS_NUMERICAS_CASM = ("High Key", "Low Limit", "High Limit", "Zona Aguda Início", "Zona Aguda High Key",
                                 "Zona Aguda Low Limit", "Zona Aguda High Limit",
                                 "Zona Grave Fim", "Zona Grave High Key", "Zona Grave Low Limit", "Zona Grave High Limit")
        PROPS_PREVIEW_NOTA = ("Low Limit", "High Limit", "Zona Aguda Início", "Zona Aguda High Key",
                               "Zona Aguda Low Limit", "Zona Aguda High Limit",
                               "Zona Grave Fim", "Zona Grave Low Limit", "Zona Grave High Limit")
        # Byte 18/19 do Ctb2 ("Source Chord"/"Source Chord Type" - ver
        # comentário no topo do arquivo, perto de SOURCE_CHORD_ROOT_NAMES) -
        # a raiz/tipo do acorde que o canal foi COMPOSTO assumindo (o padrão
        # de fábrica é C/Maj7). Pedido do Michel depois de descobrir que um
        # ritmo real (zerado em "0"/"C" achando que era constante do
        # formato) usava esse par pra transpor 3 seções compostas em Fá de
        # volta pra Dó na hora de tocar.
        PROPS_SOURCE_ROOT = ("Nota Fundamental de Origem",)
        PROPS_SOURCE_TYPE = ("Tipo do Acorde de Origem",)
        PROPS_SO_ENTER = (PROPS_NTR + PROPS_NTT + PROPS_BOOL_LIGADO + PROPS_RTR
                           + PROPS_SOURCE_ROOT + PROPS_SOURCE_TYPE
                           + ("Redirecionar Para", "Acordes Ativos"))

        def regra_do_canal(canal_data, modificados_canal=()):
            # Converte um canal da tela ("Editar Seção") pro formato interno
            # do CASM - usado tanto ao salvar a própria seção quanto ao
            # exportar o CASM dela pra outras. Devolve SEMPRE as 3 zonas
            # inteiras (não só as tocadas) - agora que tudo é decifrado e
            # transparente, reescrever o mesmo valor que já estava lá é
            # inofensivo (round-trip perfeito quando nada muda).
            acordes_base = bytes(canal_data["Acordes Ativos"])
            if len(acordes_base) != 5:
                acordes_base = bytes([0x03, 0xff, 0xff, 0xff, 0xff])
            primeiro_byte = acordes_base[0] & ~0x04 & 0xff
            if canal_data["Toca Sem Acorde"]:
                primeiro_byte |= 0x04
            resultado = {
                'play_type': canal_data["NTR (Play Type)"],
                'ntt_type': canal_data["NTT Type"],
                'ntt_bass': canal_data["NTT Bass"],
                'high_key': canal_data["High Key"],
                'note_limit_low': canal_data["Low Limit"],
                'note_limit_high': canal_data["High Limit"],
                'rtr': canal_data["Retrigger Rule (RTR)"],

                'note_split_high': canal_data["Zona Aguda Início"],
                'ntr_hi': canal_data["Zona Aguda NTR"],
                'ntt_hi': canal_data["Zona Aguda NTT"],
                'ntt_hi_bass': canal_data["Zona Aguda NTT Bass"],
                'high_key_hi': canal_data["Zona Aguda High Key"],
                'note_limit_low_hi': canal_data["Zona Aguda Low Limit"],
                'note_limit_high_hi': canal_data["Zona Aguda High Limit"],
                'rtr_hi': canal_data["Zona Aguda Retrigger Rule (RTR)"],

                'note_split_low': canal_data["Zona Grave Fim"],
                'ntr_lo': canal_data["Zona Grave NTR"],
                'ntt_lo': canal_data["Zona Grave NTT"],
                'ntt_lo_bass': canal_data["Zona Grave NTT Bass"],
                'high_key_lo': canal_data["Zona Grave High Key"],
                'note_limit_low_lo': canal_data["Zona Grave Low Limit"],
                'note_limit_high_lo': canal_data["Zona Grave High Limit"],
                'rtr_lo': canal_data["Zona Grave Retrigger Rule (RTR)"],

                'dst': canal_data["Redirecionar Para"],
                'active_chords': bytes([primeiro_byte]) + acordes_base[1:],
                'editable': canal_data["Editável"],
                'source_chord_root': canal_data["Nota Fundamental de Origem"],
                'source_chord_type': canal_data["Tipo do Acorde de Origem"],
            }
            # Único byte que continua sem tela dedicada (ver
            # BYTES_CASM_DESCONHECIDOS) - só entra no resultado se o Michel
            # de fato mexeu nele nesta tela, pra não disparar a criação de
            # um registro físico novo (via patch_casm_binary/regra_e_padrao)
            # só por causa de um ajuste em outra propriedade qualquer.
            algum_byte_tocado = any(nome_prop_byte(i) in modificados_canal for i in BYTES_CASM_DESCONHECIDOS)
            if algum_byte_tocado:
                resultado['raw_bytes'] = {i: canal_data[nome_prop_byte(i)] for i in BYTES_CASM_DESCONHECIDOS}
            return resultado

        class SectionEditDialog(wx.Dialog):
            def __init__(self, parent_frame, sec_info):
                super().__init__(parent_frame, title=f"Editar Seção - {sec_info['display_name']}", size=(650, 650), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
                self.parent_frame = parent_frame
                self.sec_info = sec_info
                
                # Lista 1 - propriedades gerais do canal (as mesmas de
                # sempre, MENOS o CASM, que agora mora na Lista 2).
                self.propriedades = ["Volume", "Pan", "Grave", "Agudo", "Expression", "Bank", "Patch", "Reverb",
                                      "Chorus", "Transpose", "Pitch Bend", "Editável", "Toca Sem Acorde",
                                      "Redirecionar Para", "Acordes Ativos"]
                self.prop_atual = 0
                # Lista 2 - dados de CASM do canal, agrupados por zona de
                # nota na ordem pedida: Zona Média (a mais usada) primeiro,
                # depois Zona Aguda, por fim Zona Grave.
                self.propriedades_casm = [
                    "NTR (Play Type)", "NTT Type", "NTT Bass", "High Key", "Low Limit", "High Limit", "Retrigger Rule (RTR)",
                    "Zona Aguda Início", "Zona Aguda NTR", "Zona Aguda NTT", "Zona Aguda NTT Bass", "Zona Aguda High Key",
                    "Zona Aguda Low Limit", "Zona Aguda High Limit", "Zona Aguda Retrigger Rule (RTR)",
                    "Zona Grave Fim", "Zona Grave NTR", "Zona Grave NTT", "Zona Grave NTT Bass", "Zona Grave High Key",
                    "Zona Grave Low Limit", "Zona Grave High Limit", "Zona Grave Retrigger Rule (RTR)",
                    "Nota Fundamental de Origem", "Tipo do Acorde de Origem",
                ] + [nome_prop_byte(i) for i in BYTES_CASM_DESCONHECIDOS]
                self.prop_atual_casm = 0
                self.playing_local = False

                self.canais_data = []
                for ch in range(16):
                    # O valor real DESSA seção, não o instantâneo global -
                    # um ritmo genuíno pode ter Patch/Banco/Volume
                    # diferente só numa seção (ex.: canal 16 do Ballada 2).
                    c = self.parent_frame.ler_propriedades_locais_secao(self.parent_frame.merged_track_cache, ch, sec_info.get('start'), sec_info.get('end'))
                    c["Transpose"] = 0
                    # "Pitch Bend" NÃO é reiniciado pra 0 aqui - ele já vem
                    # de ler_propriedades_locais_secao com o valor REAL da
                    # Sensibilidade da Roda de Pitch Bend (RPN 0) desta
                    # seção (ou o padrão de fábrica, 2 semitons). Diferente
                    # do Transpose (uma AÇÃO - some das notas do arquivo),
                    # Pitch Bend aqui é uma CONFIGURAÇÃO persistente do
                    # canal, igual a Volume/Pan/Bank.

                    casm = self.parent_frame.obter_casm_da_secao(sec_info['name']).get(ch, {})
                    c["NTR (Play Type)"] = casm.get('play_type', 'trans')
                    c["NTT Type"] = casm.get('ntt_type', 'bypass')
                    c["NTT Bass"] = casm.get('ntt_bass', False)
                    c["High Key"] = casm.get('high_key', 6)
                    c["Low Limit"] = casm.get('note_limit_low', 0)
                    c["High Limit"] = casm.get('note_limit_high', 127)
                    c["Retrigger Rule (RTR)"] = casm.get('rtr', 'pitch shift')
                    c["Nota Fundamental de Origem"] = casm.get('source_chord_root', 'C')
                    c["Tipo do Acorde de Origem"] = casm.get('source_chord_type', 'Maj7')

                    c["Zona Aguda Início"] = casm.get('note_split_high', 127)
                    c["Zona Aguda NTR"] = casm.get('ntr_hi', 'trans')
                    c["Zona Aguda NTT"] = casm.get('ntt_hi', 'bypass')
                    c["Zona Aguda NTT Bass"] = casm.get('ntt_hi_bass', False)
                    c["Zona Aguda High Key"] = casm.get('high_key_hi', 6)
                    c["Zona Aguda Low Limit"] = casm.get('note_limit_low_hi', 0)
                    c["Zona Aguda High Limit"] = casm.get('note_limit_high_hi', 127)
                    c["Zona Aguda Retrigger Rule (RTR)"] = casm.get('rtr_hi', 'pitch shift')

                    # A Zona Grave, decifrada junto com a Zona Aguda: quase
                    # sempre inerte na prática ("Zona Grave Fim" = 0), mas
                    # totalmente editável igual as outras duas agora.
                    c["Zona Grave Fim"] = casm.get('note_split_low', 0)
                    c["Zona Grave NTR"] = casm.get('ntr_lo', 'trans')
                    c["Zona Grave NTT"] = casm.get('ntt_lo', 'bypass')
                    c["Zona Grave NTT Bass"] = casm.get('ntt_lo_bass', False)
                    c["Zona Grave High Key"] = casm.get('high_key_lo', 6)
                    c["Zona Grave Low Limit"] = casm.get('note_limit_low_lo', 0)
                    c["Zona Grave High Limit"] = casm.get('note_limit_high_lo', 127)
                    c["Zona Grave Retrigger Rule (RTR)"] = casm.get('rtr_lo', 'pitch shift')

                    c["Redirecionar Para"] = casm.get('dst', ch)
                    acordes_brutos = bytes(casm.get('active_chords', PRESET_TODOS))
                    if len(acordes_brutos) != 5:
                        acordes_brutos = PRESET_TODOS
                    # O bit 0x04 do primeiro byte é o que faz o canal tocar mesmo
                    # sem nenhum acorde no ACMP (confirmado comparando com arquivos
                    # genuínos da Yamaha - é assim que a bateria de verdade fica
                    # livre do ACMP). Ele é mantido separado do preset de acordes
                    # pra não se perder quando o usuário trocar entre Maiores/
                    # Menores/Todos.
                    c["Toca Sem Acorde"] = bool(acordes_brutos[0] & 0x04)
                    c["Acordes Ativos"] = bytes([acordes_brutos[0] & ~0x04 & 0xff]) + acordes_brutos[1:]

                    # "Editável" (byte 10) - achávamos que não tinha função
                    # nenhuma e não dava tela pra ele; descoberta do byte 33
                    # (RTR da Zona Média, que faltava pro sustain do Chord1
                    # funcionar) mostrou que um bit "sem função aparente"
                    # pode ter função sim - então ele fica editável.
                    c["Editável"] = bool(casm.get('editable', True))

                    # Único byte do Ctb2 que continua sem tela dedicada (ver
                    # BYTES_CASM_DESCONHECIDOS) - entra com o valor REAL que
                    # está no arquivo agora (0 se o canal nunca teve
                    # registro físico), pronto pro Michel testar no SX.
                    raw_bytes = casm.get('raw_bytes', {}) or {}
                    for idx in BYTES_CASM_DESCONHECIDOS:
                        c[nome_prop_byte(idx)] = raw_bytes.get(idx, 0)

                    self.canais_data.append(c)

                self.modificados = {ch: set() for ch in range(16)}
                # Seleção múltipla de canais - igualzinho à janela principal
                # (canais_selecionados/non_continuous_sel, ver
                # OnChannelListKeyDown/toggle_selecao_canal): Shift+Espaço
                # entra no modo não contínuo e alterna o canal atual,
                # Shift+Cima/Baixo estende um bloco contínuo, Ctrl+A marca
                # todos, Shift+Esc limpa. Editar uma propriedade com o canal
                # em foco fazendo parte da seleção afeta TODOS os
                # selecionados de uma vez (ver _alvos_edicao).
                self.canais_selecionados = {0}
                self.non_continuous_sel = False
                self.sizer = wx.BoxSizer(wx.VERTICAL)
                self.list_box = wx.ListBox(self, style=wx.LB_SINGLE)
                self.list_box.SetName("Propriedades Gerais do Canal")
                self.sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 10)
                self.list_box_casm = wx.ListBox(self, style=wx.LB_SINGLE)
                self.list_box_casm.SetName("Dados de CASM do Canal (Zona Média, Zona Aguda e Zona Grave)")
                self.sizer.Add(self.list_box_casm, 1, wx.EXPAND | wx.ALL, 10)

                btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
                self.btn_ok = wx.Button(self, wx.ID_OK, "&Salvar Alterações")
                self.btn_exportar = wx.Button(self, wx.ID_ANY, "E&xportar CASM")
                self.btn_exportar_canal = wx.Button(self, wx.ID_ANY, "&Exportar CASM do Canal Selecionado")
                self.btn_limpar_casm = wx.Button(self, wx.ID_ANY, "&Limpar CASM do Canal")
                self.btn_cancel = wx.Button(self, wx.ID_CANCEL, "Ca&ncelar")
                btn_sizer.Add(self.btn_ok, 0, wx.ALL, 10)
                btn_sizer.Add(self.btn_exportar, 0, wx.ALL, 10)
                btn_sizer.Add(self.btn_exportar_canal, 0, wx.ALL, 10)
                btn_sizer.Add(self.btn_limpar_casm, 0, wx.ALL, 10)
                btn_sizer.Add(self.btn_cancel, 0, wx.ALL, 10)
                self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER)
                self.btn_exportar.Bind(wx.EVT_BUTTON, self.exportar_casm)
                self.btn_exportar_canal.Bind(wx.EVT_BUTTON, self.exportar_casm_do_canal)
                self.btn_limpar_casm.Bind(wx.EVT_BUTTON, self.limpar_casm_canal)

                self.SetSizer(self.sizer)
                self.atualizar_lista()
                self.atualizar_lista_casm()
                self.list_box.SetSelection(0)
                self.list_box_casm.SetSelection(0)

                self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
                self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: wx.CallAfter(self.acao_enter))
                self.list_box_casm.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: wx.CallAfter(self.acao_enter))
                # As duas listas mostram os MESMOS 16 canais (só que com
                # colunas diferentes) - mudar de canal numa acompanha a
                # outra automaticamente, pedido do Michel ("se eu selecionar
                # o canal 12 na primeira lista, ao dar Tab já estarei em
                # cima do canal 12 na segunda").
                self.list_box.Bind(wx.EVT_LISTBOX, self.on_selecao_lista_geral)
                self.list_box_casm.Bind(wx.EVT_LISTBOX, self.on_selecao_lista_casm)
                self.Bind(wx.EVT_CLOSE, self.parar_e_fechar)

            def _colapsar_selecao_se_solta(self, ch):
                # Igual a OnChannelSelect da janela principal: mover o foco
                # de canal SEM Shift/Ctrl (seta solta, clique do mouse,
                # Home/End) colapsa a seleção múltipla de volta pra só o
                # canal recém-focado - sai do modo não contínuo também.
                if ch == wx.NOT_FOUND:
                    return
                if not wx.GetKeyState(wx.WXK_SHIFT) and not wx.GetKeyState(wx.WXK_CONTROL):
                    # Nada a colapsar se já não havia seleção múltipla nenhuma
                    # (o caso comum - só navegando linha a linha): NÃO chamar
                    # _atualizar_visual_selecao aqui, que reescreve as 16
                    # linhas das duas listas a cada tecla - é exatamente a
                    # reescrita cara que _atualizar_uma_linha (usada pelo
                    # Cima/Baixo/Home/End normal) foi criada pra evitar
                    # (bagunçava a rolagem/foco do NVDA perto do fim da
                    # lista - bug relatado de novo pelo Michel depois desta
                    # função ter sido adicionada).
                    if not self.non_continuous_sel and len(self.canais_selecionados) <= 1:
                        # Não havia seleção múltipla nenhuma pra colapsar -
                        # só troca o canal "corrente" (barato) e sai, sem
                        # reescrever as 16 linhas à toa.
                        self.canais_selecionados = {ch}
                        return
                    self.canais_selecionados = {ch}
                    self.non_continuous_sel = False
                    self._atualizar_visual_selecao(skip_idx=ch)

            def on_selecao_lista_geral(self, event):
                event.Skip()
                ch = self.list_box.GetSelection()
                if ch != wx.NOT_FOUND and self.list_box_casm.GetSelection() != ch:
                    self.list_box_casm.SetSelection(ch)
                self._colapsar_selecao_se_solta(ch)

            def on_selecao_lista_casm(self, event):
                event.Skip()
                ch = self.list_box_casm.GetSelection()
                if ch != wx.NOT_FOUND and self.list_box.GetSelection() != ch:
                    self.list_box.SetSelection(ch)
                self._colapsar_selecao_se_solta(ch)

            def _lista_ativa(self):
                # Devolve (listbox, lista_de_propriedades, prop_atual, kind)
                # da lista que está com foco agora - 'geral' ou 'casm'. Usado
                # por todo handler de tecla abaixo, pra não duplicar a lógica
                # de navegação/edição pra cada uma das duas listas.
                if self.FindFocus() == self.list_box_casm:
                    return self.list_box_casm, self.propriedades_casm, self.prop_atual_casm, 'casm'
                return self.list_box, self.propriedades, self.prop_atual, 'geral'

            def _alvos_edicao(self):
                # Igual a _alvos_edicao_canal da janela principal: se o canal
                # em foco faz parte de uma seleção múltipla, editar uma
                # propriedade afeta TODOS os canais selecionados de uma vez -
                # senão, afeta só o canal focado.
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                if ch == wx.NOT_FOUND:
                    return set()
                if ch in self.canais_selecionados:
                    return set(self.canais_selecionados)
                return {ch}

            def _atualizar_visual_selecao(self, skip_idx=None):
                # Reescreve as 16 linhas das DUAS listas (o "[Selecionado]"
                # já sai embutido em _texto_linha) - usado só em ações raras
                # de seleção (Shift+Espaço, Ctrl+A, Shift+Esc), nunca no
                # caminho quente de navegação.
                for ch in range(16):
                    if ch == skip_idx:
                        continue
                    self._atualizar_uma_linha(self.list_box, self.propriedades, self.prop_atual, ch)
                    self._atualizar_uma_linha(self.list_box_casm, self.propriedades_casm, self.prop_atual_casm, ch)

            def toggle_selecao_canal(self):
                # Shift+Espaço - igual à janela principal (toggle_selecao_canal).
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                if ch == wx.NOT_FOUND:
                    return
                from MHS_Utils import falar
                if not self.non_continuous_sel:
                    self.non_continuous_sel = True
                    self.canais_selecionados.add(ch)
                    self._atualizar_visual_selecao()
                    falar(f"Seleção não contínua ativada. Canal {ch+1} selecionado", imediato=True)
                elif ch in self.canais_selecionados:
                    self.canais_selecionados.discard(ch)
                    self._atualizar_visual_selecao()
                    falar(f"Canal {ch+1} não selecionado", imediato=True)
                else:
                    self.canais_selecionados.add(ch)
                    self._atualizar_visual_selecao()
                    falar(f"Canal {ch+1} selecionado", imediato=True)

            def selecionar_todos_canais(self):
                # Ctrl+A - igual à janela principal.
                self.canais_selecionados = set(range(16))
                self._atualizar_visual_selecao()
                from MHS_Utils import falar
                falar("Todos selecionados", imediato=True)

            def limpar_selecao_canais(self):
                # Shift+Esc - igual à janela principal (limpar_tudo_mestre),
                # sem a parte de Entrada/Saída (não existe aqui).
                self.non_continuous_sel = False
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                self.canais_selecionados = {ch if ch != wx.NOT_FOUND else 0}
                self._atualizar_visual_selecao()
                from MHS_Utils import falar
                falar("Seleção de canais desfeita.", imediato=True)

            def relatar_selecoes_canais(self):
                # Ctrl+Shift+Espaço - igual à janela principal (relatar_selecoes_canais).
                from MHS_Utils import falar
                qtd_canais = len(self.canais_selecionados)
                if qtd_canais <= 1 and not self.non_continuous_sel:
                    falar("Nenhuma seleção de canais ativa no momento.", imediato=True)
                    return
                canais_numeros = sorted(c + 1 for c in self.canais_selecionados)
                grupos = []
                if canais_numeros:
                    inicio = canais_numeros[0]
                    fim = canais_numeros[0]
                    for n in canais_numeros[1:]:
                        if n == fim + 1:
                            fim = n
                        else:
                            grupos.append(str(inicio) if inicio == fim else f"{inicio} ao {fim}")
                            inicio = n
                            fim = n
                    grupos.append(str(inicio) if inicio == fim else f"{inicio} ao {fim}")
                canais_str = ", ".join(grupos)
                falar(f"{qtd_canais} canais selecionados: {canais_str}", imediato=True)

            def handle_midi_in(self, msg):
                ch = self.list_box.GetSelection()
                if ch == wx.NOT_FOUND: return
                if msg.type in ('note_on', 'note_off', 'polytouch'):
                    # self.parent_frame.active_midi_dialog desvia TODA a MIDI
                    # IN pra cá enquanto esta tela está aberta (ver
                    # midi_in_handler) - sem isso, o timbre trocado aqui
                    # (Bank/Patch, via program_change/CC abaixo) nunca soa ao
                    # tocar no teclado físico, só ao dar Play na seção (mesmo
                    # fix já aplicado no Voice Creator - ver handle_midi_in
                    # em MHS_Dialogs.py).
                    porta = getattr(self.parent_frame, 'midi_out', None)
                    if porta:
                        try: porta.send(msg.copy(channel=ch))
                        except Exception: pass
                    return
                if msg.type == 'pitchwheel' or (msg.type == 'control_change' and msg.control == 1):
                    # As DUAS RODAS físicas do teclado (Pitch Bend e
                    # Modulação) - mesmo motivo das notas acima: sem ecoar
                    # pro sintetizador, girar qualquer uma delas com esta
                    # tela aberta não faz nenhum som (o Michel reportou
                    # justamente testando a Sensibilidade da Roda de Pitch
                    # Bend recém-corrigida).
                    porta = getattr(self.parent_frame, 'midi_out', None)
                    if porta:
                        try: porta.send(msg.copy(channel=ch))
                        except Exception: pass
                    return
                mudou = False
                if msg.type == 'program_change':
                    self.canais_data[ch]["Patch"] = msg.program
                    self.modificados[ch].add("Patch")
                    mudou = True
                elif msg.type == 'control_change':
                    if msg.control == 0:
                        self.canais_data[ch]["Bank"] = (msg.value * 128) + (self.canais_data[ch]["Bank"] % 128)
                        self.modificados[ch].add("Bank"); mudou = True
                    elif msg.control == 32:
                        self.canais_data[ch]["Bank"] = ((self.canais_data[ch]["Bank"] // 128) * 128) + msg.value
                        self.modificados[ch].add("Bank"); mudou = True
                if mudou:
                    self.parent_frame.enviar_midi_param("Bank", self.canais_data[ch]["Bank"], ch)
                    self.parent_frame.enviar_midi_param("Patch", self.canais_data[ch]["Patch"], ch)
                    self.atualizar_lista()
                    if msg.type == 'program_change':
                        nome = self.parent_frame.ins_db.get(self.canais_data[ch]["Bank"], {}).get(msg.program, f"Patch {msg.program}")
                        from MHS_Utils import falar
                        falar(nome.replace('PSR-SX600 ', ''), imediato=True)

            def _texto_valor(self, ch, p):
                # Formatação de valor compartilhada pelas duas listas -
                # cada propriedade só cai numa das duas, então não há
                # ambiguidade em checar os nomes das duas de uma vez só.
                c = self.canais_data[ch]
                val = c[p]
                if p == "Patch":
                    return self.parent_frame.ins_db.get(c["Bank"], {}).get(val, f"Patch {val}").replace('PSR-SX600 ', '')
                if p == "Bank":
                    nome_b = self.parent_frame.bank_names.get(val, "")
                    return f"{val} ({nome_b.replace('PSR-SX600 ', '')})" if nome_b else str(val)
                if p in PROPS_BOOL_LIGADO:
                    return "Ligado" if val else "Desligado"
                if p == "Redirecionar Para":
                    return "Nenhum (toca no próprio canal)" if val == ch else f"Canal {val + 1}"
                if p == "Acordes Ativos":
                    return nome_do_preset_acordes(val)
                return str(val)

            def _texto_linha(self, propriedades, prop_idx, ch):
                from MHS_Utils import rotulo_canal
                p = propriedades[prop_idx]
                val_str = self._texto_valor(ch, p)
                mod = "*" if p in self.modificados[ch] else ""
                sel_tag = " [Selecionado]" if ch in self.canais_selecionados else ""
                return f"{rotulo_canal(ch)}  |  {p}{mod} {val_str}{sel_tag}"

            def _atualizar_uma_linha(self, listbox, propriedades, prop_idx, ch):
                # Reescreve o texto de UMA SÓ linha (sem Freeze - desnecessário
                # pra uma linha só). É a peça central da navegação "limpa": em
                # vez de reescrever as 16 linhas toda vez que a propriedade
                # muda (o que bagunçava a rolagem da lista justo no ÚLTIMO
                # canal, fazendo o NVDA "pular" pra uma linha de cima - ver
                # AO2 no MHS MIDI Sequencer, que nunca deixa o próprio WX
                # anunciar nada, só a fala manual), só atualizamos a linha de
                # DESTINO, e só um pouquinho antes do foco nativo chegar nela
                # (ver on_key). A linha de onde saímos fica "desatualizada" -
                # sem problema, porque ninguém mais vai lê-la até voltarmos,
                # e quando voltarmos ela será atualizada de novo antes de
                # chegarmos.
                listbox.SetString(ch, self._texto_linha(propriedades, prop_idx, ch))

            def _atualizar_qualquer_lista(self, listbox, propriedades, prop_idx, skip_idx=None):
                # Só usado pra atualizações RARAS que precisam repovoar a
                # lista inteira de uma vez (abrir a tela, Limpar CASM do
                # Canal, MIDI chegando no meio da edição) - NUNCA no caminho
                # quente de navegação (setas), que usa _atualizar_uma_linha.
                listbox.Freeze()
                if listbox.GetCount() == 0:
                    for _ in range(16): listbox.Append("")
                for ch in range(16):
                    if ch == skip_idx:
                        continue
                    listbox.SetString(ch, self._texto_linha(propriedades, prop_idx, ch))
                listbox.Thaw()

            def atualizar_lista(self, skip_idx=None):
                self._atualizar_qualquer_lista(self.list_box, self.propriedades, self.prop_atual, skip_idx)

            def atualizar_lista_casm(self, skip_idx=None):
                self._atualizar_qualquer_lista(self.list_box_casm, self.propriedades_casm, self.prop_atual_casm, skip_idx)

            def falar_propriedade_atual(self):
                # NÃO mexe em NENHUMA linha da lista (nem a própria, nem as
                # outras) - só fala a propriedade/valor atuais. Quem garante
                # que a linha do canal em foco mostre o valor certo quando
                # ele for lido de novo é a atualização "de passagem" feita
                # em on_key logo antes de qualquer navegação de canal (setas
                # Cima/Baixo/Home/End/PageUp/PageDown).
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                if ch == wx.NOT_FOUND:
                    return
                p = propriedades[prop_idx]
                val_str = self._texto_valor(ch, p)
                from MHS_Utils import falar
                falar(f"{p} {val_str}", imediato=True)

            def tocar_secao_loop(self):
                if self.playing_local:
                    self.parar_tudo()
                    from MHS_Utils import falar
                    falar("Parou", imediato=True)
                    return
                self.playing_local = True
                from MHS_Utils import falar
                falar("Ouvindo Seção", imediato=True)
                
                def worker():
                    import time, mido
                    while self.playing_local:
                        self.parent_frame.prepare_section_cache()
                        msgs = getattr(self.parent_frame, 'current_section_msgs', [])
                        
                        for ch in range(16):
                            for p in ["Bank", "Patch", "Volume", "Pan", "Expression", "Reverb", "Chorus"]:
                                self.parent_frame.enviar_midi_param(p, self.canais_data[ch][p], ch)
                                
                        start_t = time.perf_counter()
                        accum = 0
                        for msg in msgs:
                            if not self.playing_local: break
                            delay = mido.tick2second(msg.time, self.parent_frame.current_midi_data.ticks_per_beat, self.parent_frame.current_tempo)
                            accum += delay
                            while (time.perf_counter() - start_t) < accum:
                                if not self.playing_local: break
                                time.sleep(0.001)
                                
                            if not msg.is_meta and self.parent_frame.midi_out:
                                m = msg.copy()
                                ch = getattr(m, 'channel', -1)
                                if ch != -1:
                                    # F5/F6 (Mute/Solo) mudam self.parent_frame.canais[ch],
                                    # mas esse laço de "Ouvir Seção" tinha vida própria e
                                    # nunca checava isso - só o motor principal (Play da
                                    # tela cheia) respeitava Mute/Solo. Sem este gate, o
                                    # canal continuava tocando normalmente aqui dentro,
                                    # mesmo depois de mutado/solado.
                                    any_solo = any(c['Solo'] for c in self.parent_frame.canais)
                                    pode_tocar = self.parent_frame.canais[ch]['Solo'] if any_solo else not self.parent_frame.canais[ch]['Mute']
                                    if not pode_tocar: continue
                                    if m.type == 'program_change': continue
                                    if m.type == 'control_change' and m.control in [0, 32, 7, 10, 11, 91, 93]: continue

                                    if m.type in ['note_on', 'note_off'] and self.canais_data[ch]["Transpose"] != 0:
                                        m.note = max(0, min(127, m.note + self.canais_data[ch]["Transpose"]))

                                    try: self.parent_frame.midi_out.send(m)
                                    except Exception: pass
                        if not self.playing_local: break
                        time.sleep(0.5)
                import threading
                self.thread_local = threading.Thread(target=worker, daemon=True)
                self.thread_local.start()

            def parar_tudo(self):
                self.playing_local = False
                if self.parent_frame.midi_out:
                    import mido
                    for ch in range(16):
                        try:
                            self.parent_frame.midi_out.send(mido.Message('control_change', channel=ch, control=123, value=0))
                            self.parent_frame.midi_out.send(mido.Message('control_change', channel=ch, control=64, value=0))
                            self.parent_frame.midi_out.send(mido.Message('control_change', channel=ch, control=1, value=0))
                            self.parent_frame.midi_out.send(mido.Message('pitchwheel', channel=ch, pitch=0))
                        except Exception: pass

            def parar_e_fechar(self, event=None):
                self.parar_tudo()
                if event: event.Skip()

            def tocar_nota_preview(self, ch, nota):
                porta = getattr(self.parent_frame, 'midi_out', None)
                if not porta: return
                import mido
                import threading
                if getattr(self, 'preview_limite_timer', None):
                    self.preview_limite_timer.cancel()
                # Antes cancelava só o timer, sem apagar a nota anterior - se
                # ela fosse diferente da nova (mudando rápido de valor), ficava
                # presa tocando pra sempre. Agora apaga a nota anterior de
                # verdade antes de tocar a nova, igual o Velocity Midi Control.
                ativo = getattr(self, 'preview_nota_ativa', None)
                if ativo:
                    ch_ant, nota_ant = ativo
                    try:
                        porta.send(mido.Message('note_off', channel=ch_ant, note=nota_ant, velocity=0))
                    except Exception:
                        pass
                try:
                    porta.send(mido.Message('note_on', channel=ch, note=nota, velocity=60))
                except Exception:
                    pass
                self.preview_nota_ativa = (ch, nota)
                def parar_nota():
                    try:
                        porta.send(mido.Message('note_off', channel=ch, note=nota, velocity=0))
                    except Exception:
                        pass
                    if getattr(self, 'preview_nota_ativa', None) == (ch, nota):
                        self.preview_nota_ativa = None
                self.preview_limite_timer = threading.Timer(0.4, parar_nota)
                self.preview_limite_timer.start()

            def enviar_pitch_bend(self, ch, semitons):
                # Manda a RPN 0 (Pitch Bend Sensitivity/Range) pro teclado -
                # quantos semitons a RODA de pitch bend sobe/desce no MÁXIMO
                # (o padrão da maioria dos teclados é 2). Isso só CONFIGURA
                # a roda - nunca dobra o som sozinho (bug antigo: mandava
                # sempre 24 fixo de sensibilidade e ainda por cima disparava
                # um evento de pitch bend de verdade, como se estivesse
                # girando a roda - o Michel reportou isso comparando com o
                # MIDI Sequencer, que já fazia certo).
                porta = getattr(self.parent_frame, 'midi_out', None)
                if not porta: return
                import mido
                try:
                    valor = max(0, min(24, int(semitons)))
                    porta.send(mido.Message('control_change', channel=ch, control=101, value=0))
                    porta.send(mido.Message('control_change', channel=ch, control=100, value=0))
                    porta.send(mido.Message('control_change', channel=ch, control=6, value=valor))
                    porta.send(mido.Message('control_change', channel=ch, control=101, value=127))
                    porta.send(mido.Message('control_change', channel=ch, control=100, value=127))
                except Exception:
                    pass

            def acao_enter(self):
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                if ch == wx.NOT_FOUND: return
                p = propriedades[prop_idx]
                val = self.canais_data[ch][p]
                # Todos os canais selecionados recebem o MESMO valor
                # escolhido/digitado - diferente do +/-, que preserva a
                # diferença entre eles (igual à janela principal,
                # acao_enter_canal/toggle_propriedade_direta).
                alvos = self._alvos_edicao()

                def _confirmar(msg):
                    for alvo in alvos:
                        self.modificados[alvo].add(p)
                    # Não reescreve o texto de NENHUMA linha aqui (nem a
                    # própria, nem as outras) - a linha do canal atual fica
                    # "desatualizada" até a próxima vez que sairmos dela
                    # (setas Cima/Baixo/Home/End já cuidam de atualizá-la de
                    # passagem, ver on_key) - mesma lógica de
                    # falar_propriedade_atual, evita qualquer notificação
                    # nativa de mudança de texto por cima desta fala manual.
                    from MHS_Utils import falar
                    falar(msg, imediato=True)

                if p in PROPS_NTR:
                    opcoes = list(NTR_OPCOES)
                    dlg = wx.SingleChoiceDialog(self, f"Escolha a Regra de Transposição ({p}) para {len(alvos)} canal(is):", "Editar NTR", opcoes)
                    if val in opcoes: dlg.SetSelection(opcoes.index(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        escolha = dlg.GetStringSelection()
                        for alvo in alvos: self.canais_data[alvo][p] = escolha
                        _confirmar(f"{p} alterado para {escolha}")
                    dlg.Destroy()

                elif p in PROPS_NTT:
                    opcoes = list(NTT_OPCOES)
                    dlg = wx.SingleChoiceDialog(self, f"Escolha a Tabela de Notas ({p}) para {len(alvos)} canal(is):", "Editar NTT", opcoes)
                    if val in opcoes: dlg.SetSelection(opcoes.index(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        escolha = dlg.GetStringSelection()
                        for alvo in alvos: self.canais_data[alvo][p] = escolha
                        _confirmar(f"{p} alterado para {escolha}")
                    dlg.Destroy()

                elif p in PROPS_RTR:
                    opcoes = list(RTR_OPCOES)
                    dlg = wx.SingleChoiceDialog(self, f"Escolha a regra de retrigger ({p}) para {len(alvos)} canal(is):", "Editar Retrigger Rule", opcoes)
                    if val in opcoes: dlg.SetSelection(opcoes.index(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        escolha = dlg.GetStringSelection()
                        for alvo in alvos: self.canais_data[alvo][p] = escolha
                        _confirmar(f"{p} alterado para {escolha}")
                    dlg.Destroy()

                elif p in PROPS_SOURCE_ROOT:
                    opcoes = list(SOURCE_CHORD_ROOT_NAMES)
                    dlg = wx.SingleChoiceDialog(self, f"Em que nota fundamental estes {len(alvos)} canal(is) foram COMPOSTOS "
                                                       "(a tecla que o teclado usa como referência pra "
                                                       "transpor de volta na hora de tocar)?",
                                                 "Editar Nota Fundamental de Origem", opcoes)
                    if val in opcoes: dlg.SetSelection(opcoes.index(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        escolha = dlg.GetStringSelection()
                        for alvo in alvos: self.canais_data[alvo][p] = escolha
                        _confirmar(f"{p} alterado para {escolha}")
                    dlg.Destroy()

                elif p in PROPS_SOURCE_TYPE:
                    opcoes = list(SOURCE_CHORD_TYPE_NAMES)
                    dlg = wx.SingleChoiceDialog(self, f"Que tipo de acorde estes {len(alvos)} canal(is) foram COMPOSTOS assumindo "
                                                       "(o padrão de fábrica da Yamaha é Maj7)?",
                                                 "Editar Tipo do Acorde de Origem", opcoes)
                    if val in opcoes: dlg.SetSelection(opcoes.index(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        escolha = dlg.GetStringSelection()
                        for alvo in alvos: self.canais_data[alvo][p] = escolha
                        _confirmar(f"{p} alterado para {escolha}")
                    dlg.Destroy()

                elif p in PROPS_BOOL_LIGADO:
                    # Todos vão pro estado OPOSTO ao que o canal em foco tinha
                    # (igual a toggle_propriedade_direta da janela principal).
                    novo_estado = not self.canais_data[ch][p]
                    for alvo in alvos: self.canais_data[alvo][p] = novo_estado
                    _confirmar(f"{p} {'Ligado' if novo_estado else 'Desligado'}")

                elif p == "Redirecionar Para":
                    dlg = wx.TextEntryDialog(self, f"Para qual canal (1 a 16) estes {len(alvos)} canal(is) devem redirecionar o som?", "Redirecionar Para", str(val + 1))
                    # Seleciona o valor atual inteiro assim que a tela abre -
                    # digitar um número novo já apaga o que estava lá, em vez
                    # de misturar os dois (ex: tinha "2", digitar "16" virava
                    # "216" em vez de "16").
                    def _selecionar_tudo_redirecionar(event, _dlg=dlg):
                        event.Skip()
                        for filho in _dlg.GetChildren():
                            if isinstance(filho, wx.TextCtrl):
                                filho.SetFocus()
                                filho.SelectAll()
                                break
                    dlg.Bind(wx.EVT_INIT_DIALOG, _selecionar_tudo_redirecionar)
                    if dlg.ShowModal() == wx.ID_OK:
                        try:
                            v = int(dlg.GetValue())
                            v = max(1, min(16, v))
                            for alvo in alvos: self.canais_data[alvo][p] = v - 1
                            _confirmar(f"Redireciona para o canal {v}")
                        except Exception: pass
                    dlg.Destroy()

                elif p == "Acordes Ativos":
                    dlg = AcordesAtivosDialog(self, len(alvos), val)
                    if dlg.ShowModal() == wx.ID_OK:
                        tipos = dlg.get_tipos()
                        for alvo in alvos:
                            self.canais_data[alvo][p] = chord_mute_montar(tipos, self.canais_data[alvo][p])
                        _confirmar(f"Acordes Ativos: {nome_do_preset_acordes(self.canais_data[ch][p])}")
                    dlg.Destroy()

                else:
                    eh_byte_desconhecido = p.startswith("Byte ")
                    dlg = wx.TextEntryDialog(self, f"Digite o valor para {p} ({len(alvos)} canal(is)):", "Edição Direta", str(val))
                    if dlg.ShowModal() == wx.ID_OK:
                        try:
                            v = int(dlg.GetValue())
                            if eh_byte_desconhecido:
                                limit, min_v = 255, 0
                            else:
                                limit = 16384 if p == "Bank" else (24 if p in ("Transpose", "Pitch Bend") else 127)
                                # Transpose é uma AÇÃO (-24 a +24 semitons de notas de verdade);
                                # Pitch Bend é a Sensibilidade da Roda (0 a 24 semitons, sem negativo).
                                min_v = -24 if p == "Transpose" else 0
                            v = max(min_v, min(limit, v))
                            for alvo in alvos:
                                self.canais_data[alvo][p] = v
                                if p == "Pitch Bend":
                                    self.enviar_pitch_bend(alvo, v)
                                elif p in PROPS_PREVIEW_NOTA:
                                    self.tocar_nota_preview(alvo, v)
                                elif not eh_byte_desconhecido and p not in PROPS_NUMERICAS_CASM and p != "Transpose":
                                    self.parent_frame.enviar_midi_param(p, v, alvo)
                            _confirmar(f"{p} em {v}")
                        except Exception: pass
                    dlg.Destroy()
                listbox.SetFocus()

            def on_key(self, event):
                k = event.GetKeyCode()
                if k == wx.WXK_TAB:
                    event.Skip()
                    return
                foco_atual = self.FindFocus()
                if foco_atual in (self.list_box, self.list_box_casm):
                    shift = event.ShiftDown()
                    ctrl = event.ControlDown()
                    alt = event.AltDown()
                    if k == wx.WXK_SPACE:
                        # Shift+Espaço/Ctrl+Shift+Espaço = seleção de canais
                        # (ver toggle_selecao_canal/relatar_selecoes_canais);
                        # Espaço puro continua sendo audicionar a seção.
                        if shift and ctrl and not alt:
                            self.relatar_selecoes_canais()
                            return
                        if shift and not ctrl and not alt:
                            self.toggle_selecao_canal()
                            return
                        self.tocar_secao_loop()
                        return
                    if ctrl and not shift and not alt and k == ord('A'):
                        self.selecionar_todos_canais()
                        return
                    if shift and not ctrl and not alt and k == wx.WXK_ESCAPE:
                        self.limpar_selecao_canais()
                        return
                    if k in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
                        self.acao_enter()
                        return
                    if k == wx.WXK_LEFT:
                        # Sempre consome a tecla, mesmo na primeira propriedade -
                        # sem isso (Skip cai pro list_box), segurar a seta virava
                        # descer de canal sozinho ao chegar no limite (faltava
                        # a "parede").
                        _, propriedades, prop_idx, kind = self._lista_ativa()
                        if prop_idx > 0:
                            if kind == 'casm': self.prop_atual_casm -= 1
                            else: self.prop_atual -= 1
                            self.falar_propriedade_atual()
                        return
                    elif k == wx.WXK_RIGHT:
                        _, propriedades, prop_idx, kind = self._lista_ativa()
                        if prop_idx < len(propriedades) - 1:
                            if kind == 'casm': self.prop_atual_casm += 1
                            else: self.prop_atual += 1
                            self.falar_propriedade_atual()
                        return
                    elif k in [wx.WXK_ADD, wx.WXK_NUMPAD_ADD, ord('=')]:
                        self.alterar_valor(1)
                        return
                    elif k in [wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT, ord('-')]:
                        self.alterar_valor(-1)
                        return
                    elif k == wx.WXK_F5:
                        self.toggle_mute_solo_local("Mute")
                        return
                    elif k == wx.WXK_F6:
                        self.toggle_mute_solo_local("Solo")
                        return
                    elif k in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME, wx.WXK_END):
                        listbox, propriedades, prop_idx, kind = self._lista_ativa()
                        ch = listbox.GetSelection()
                        if ch == wx.NOT_FOUND:
                            event.Skip()
                            return
                        if shift and not ctrl and not alt and k in (wx.WXK_UP, wx.WXK_DOWN):
                            # Shift+Cima/Baixo = estender um bloco contínuo de
                            # seleção de canais - igual à janela principal
                            # (OnChannelListKeyDown). Move as DUAS listas
                            # (mostram os mesmos 16 canais) na mão, sem Skip -
                            # senão o list_box nativo moveria só a que tem foco.
                            novo_ch = ch
                            if k == wx.WXK_UP and ch > 0: novo_ch = ch - 1
                            elif k == wx.WXK_DOWN and ch < 15: novo_ch = ch + 1
                            if novo_ch != ch:
                                self.list_box.SetSelection(novo_ch)
                                self.list_box_casm.SetSelection(novo_ch)
                                from MHS_Utils import falar, rotulo_canal
                                if self.non_continuous_sel:
                                    # Modo não contínuo (Shift+Espaço): só
                                    # passeia pela seleção espalhada, sem
                                    # alterá-la.
                                    texto = "Selecionado, " if novo_ch in self.canais_selecionados else ""
                                    falar(f"{texto}{rotulo_canal(novo_ch)}", imediato=True)
                                else:
                                    self.canais_selecionados.add(novo_ch)
                                    self._atualizar_visual_selecao(skip_idx=novo_ch)
                                    falar(f"{rotulo_canal(novo_ch)} Selecionado", imediato=True)
                            return
                        # Deixa o próprio list_box mover a seleção (Skip), mas
                        # ANTES disso atualiza só a linha de DESTINO com a
                        # propriedade atual - assim, quando o NVDA anunciar a
                        # linha recém-focada (comportamento nativo, sempre
                        # funcionou bem), ela já está com o texto certo, sem
                        # precisarmos reescrever as outras 15 linhas.
                        if k == wx.WXK_UP: alvo = max(0, ch - 1)
                        elif k == wx.WXK_DOWN: alvo = min(15, ch + 1)
                        elif k == wx.WXK_HOME: alvo = 0
                        else: alvo = 15  # wx.WXK_END
                        if alvo != ch:
                            self._atualizar_uma_linha(listbox, propriedades, prop_idx, alvo)
                        event.Skip()
                        return
                event.Skip()

            def toggle_mute_solo_local(self, prop):
                # F5/F6 - mesma ideia da janela principal (Mute/Solo ao vivo,
                # pra poder ouvir só o(s) canal(is) que interessa(m) enquanto
                # audiciona a seção com Espaço). Sem Arm (F7) aqui - essa
                # tela não grava eventos, então "armar pra gravação" não
                # faz sentido dentro dela.
                ch = self.list_box.GetSelection()
                if ch == wx.NOT_FOUND:
                    return
                c = self.parent_frame.canais[ch]
                c[prop] = not c[prop]
                if prop == "Mute" and c[prop]:
                    self.parent_frame.silence_channel(ch)
                elif prop == "Solo" and c[prop]:
                    for i in range(16):
                        if i != ch:
                            self.parent_frame.silence_channel(i)
                from MHS_Utils import falar, rotulo_canal
                estado_str = "Ligado" if c[prop] else "Desligado"
                falar(f"{rotulo_canal(ch)}: {prop} {estado_str}", imediato=True)

            def alterar_valor(self, delta):
                listbox, propriedades, prop_idx, kind = self._lista_ativa()
                ch = listbox.GetSelection()
                if ch == wx.NOT_FOUND: return
                p = propriedades[prop_idx]

                if p in PROPS_SO_ENTER:
                    from MHS_Utils import falar
                    falar("Pressione Enter para editar as opções", imediato=True)
                    return

                eh_byte_desconhecido = p.startswith("Byte ")
                if eh_byte_desconhecido:
                    limit, min_v = 255, 0
                else:
                    limit = 16384 if p == "Bank" else (24 if p in ("Transpose", "Pitch Bend") else 127)
                    # Transpose é uma AÇÃO (-24 a +24 semitons de notas de verdade);
                    # Pitch Bend é a Sensibilidade da Roda (0 a 24 semitons, sem negativo).
                    min_v = -24 if p == "Transpose" else 0

                # Cada canal selecionado recebe o MESMO delta em cima do SEU
                # PRÓPRIO valor (preserva a diferença relativa entre eles) -
                # igual à janela principal (alterar_valor_canal).
                for alvo in self._alvos_edicao():
                    self.canais_data[alvo][p] = max(min_v, min(limit, self.canais_data[alvo][p] + delta))
                    self.modificados[alvo].add(p)

                    if p == "Pitch Bend":
                        self.enviar_pitch_bend(alvo, self.canais_data[alvo][p])
                    elif p in PROPS_PREVIEW_NOTA:
                        self.tocar_nota_preview(alvo, self.canais_data[alvo][p])
                    elif not eh_byte_desconhecido and p not in PROPS_NUMERICAS_CASM and p != "Transpose":
                        self.parent_frame.enviar_midi_param(p, self.canais_data[alvo][p], alvo)

                # Não reescreve NENHUMA linha aqui (nem a própria) - +/- é
                # segurado/repetido com frequência, então é justamente onde
                # mais importa não ficar reescrevendo a lista a cada
                # toque. A linha se corrige sozinha na próxima vez que
                # sairmos dela (ver on_key, Cima/Baixo/Home/End). A fala é
                # sempre sobre o canal EM FOCO (mesmo quando vários mudaram).
                from MHS_Utils import falar
                falar(f"{p} {self.canais_data[ch][p]}", imediato=True)

            def limpar_casm_canal(self, event=None):
                # Volta TODAS as propriedades de CASM do canal selecionado
                # (as 3 zonas de nota inteiras, Toca Sem Acorde, Redirecionar
                # Para e Acordes Ativos) para o padrão de fábrica do papel
                # desse canal (Baixo/Acorde/Frase/Bateria/genérico) - os
                # mesmos padrões usados quando uma seção nova nasce
                # (get_default_casm_rules). NÃO mexe em Volume/Pan/Bank/
                # Patch/Reverb/Chorus/Transpose/Pitch Bend/Grave/Agudo/
                # Expression (não é CASM) nem em Editável ou no Byte 45
                # restante (o Michel decide esses por conta própria).
                ch = self.list_box.GetSelection()
                if ch == wx.NOT_FOUND:
                    ch = self.list_box_casm.GetSelection()
                if ch == wx.NOT_FOUND:
                    return
                padrao = self.parent_frame.get_default_casm_rules()[ch]
                c = self.canais_data[ch]
                c["NTR (Play Type)"] = padrao['play_type']
                c["NTT Type"] = padrao['ntt_type']
                c["NTT Bass"] = padrao['ntt_bass']
                c["High Key"] = padrao['high_key']
                c["Low Limit"] = padrao['note_limit_low']
                c["High Limit"] = padrao['note_limit_high']
                c["Retrigger Rule (RTR)"] = padrao['rtr']
                c["Nota Fundamental de Origem"] = padrao['source_chord_root']
                c["Tipo do Acorde de Origem"] = padrao['source_chord_type']

                c["Zona Aguda Início"] = padrao['note_split_high']
                c["Zona Aguda NTR"] = padrao['ntr_hi']
                c["Zona Aguda NTT"] = padrao['ntt_hi']
                c["Zona Aguda NTT Bass"] = padrao['ntt_hi_bass']
                c["Zona Aguda High Key"] = padrao['high_key_hi']
                c["Zona Aguda Low Limit"] = padrao['note_limit_low_hi']
                c["Zona Aguda High Limit"] = padrao['note_limit_high_hi']
                c["Zona Aguda Retrigger Rule (RTR)"] = padrao['rtr_hi']

                c["Zona Grave Fim"] = padrao['note_split_low']
                c["Zona Grave NTR"] = padrao['ntr_lo']
                c["Zona Grave NTT"] = padrao['ntt_lo']
                c["Zona Grave NTT Bass"] = padrao['ntt_lo_bass']
                c["Zona Grave High Key"] = padrao['high_key_lo']
                c["Zona Grave Low Limit"] = padrao['note_limit_low_lo']
                c["Zona Grave High Limit"] = padrao['note_limit_high_lo']
                c["Zona Grave Retrigger Rule (RTR)"] = padrao['rtr_lo']

                c["Redirecionar Para"] = padrao['dst']
                acordes_brutos = bytes(padrao['active_chords'])
                if len(acordes_brutos) != 5:
                    acordes_brutos = bytes([0x03, 0xff, 0xff, 0xff, 0xff])
                c["Toca Sem Acorde"] = bool(acordes_brutos[0] & 0x04)
                c["Acordes Ativos"] = bytes([acordes_brutos[0] & ~0x04 & 0xff]) + acordes_brutos[1:]

                for p in self.propriedades_casm:
                    if not p.startswith("Byte "):
                        self.modificados[ch].add(p)
                for p in ("Redirecionar Para", "Acordes Ativos", "Toca Sem Acorde"):
                    self.modificados[ch].add(p)

                self.atualizar_lista()
                self.atualizar_lista_casm()
                from MHS_Utils import falar, rotulo_canal
                falar(f"CASM de {rotulo_canal(ch)} limpo para o padrão", imediato=True)

            def exportar_casm_do_canal(self, event):
                # Mesma exportação de sempre, mas só do canal selecionado na
                # lista agora - o pedido do Michel foi "faz igual o Exportar
                # Canal lá da janela principal", que também não pede pra
                # escolher canal nenhum: o canal de origem já é o que está
                # selecionado, só as seções de destino é que se escolhe.
                ch = self.list_box.GetSelection()
                if ch == wx.NOT_FOUND:
                    from MHS_Utils import falar
                    falar("Selecione um canal primeiro.", imediato=True)
                    return
                self.exportar_casm(event, apenas_canal=ch)

            def exportar_casm(self, event, apenas_canal=None):
                import copy
                from MHS_Utils import YAMAHA_SECTION_ORDER, falar, rotulo_canal
                if apenas_canal is not None:
                    canais_alvo = [apenas_canal]
                    descricao_canal = f" do canal {rotulo_canal(apenas_canal)}"
                else:
                    canais_alvo = range(16)
                    descricao_canal = ""
                nome_atual = self.sec_info['name'].strip().lower()
                # Um grupo (com sua própria lista de marcação) por aba - a
                # atual primeiro, depois cada outra aba aberta. Antes era
                # uma lista só, gigante, com o nome da aba repetido na
                # frente de cada seção; o NVDA lia tudo isso item por item,
                # uma "listona" só. Agora cada grupo tem seu próprio título
                # (falado uma vez, ao entrar nele com Tab) e os itens
                # dentro dele são só o nome da seção + marcado/desmarcado
                # (que o NVDA já fala sozinho, nativo do CheckListBox).
                itens_aba_atual = [(None, n) for n in YAMAHA_SECTION_ORDER if n.strip().lower() != nome_atual]
                grupos = [("Aba atual", itens_aba_atual)]
                for i, aba in enumerate(getattr(self.parent_frame, 'abas', [])):
                    if i == self.parent_frame.aba_atual:
                        continue
                    grupos.append((aba['titulo'], [(i, n) for n in YAMAHA_SECTION_ORDER]))

                dlg_exp = wx.Dialog(self, title=f"Exportar CASM{descricao_canal}", size=(420, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
                sizer_exp = wx.BoxSizer(wx.VERTICAL)
                rotulo = wx.StaticText(dlg_exp, label=f"Marque as seções (de qualquer aba aberta) que devem receber o CASM{descricao_canal} da {self.sec_info['display_name']}:")
                sizer_exp.Add(rotulo, 0, wx.ALL, 10)

                def fabrica_handler_foco(titulo_grupo):
                    # Fábrica pra cada grupo já "amarrar" o próprio título -
                    # sem isso, todos os binds do for de baixo acabariam
                    # falando só o título do ÚLTIMO grupo (efeito colateral
                    # clássico de lambda dentro de laço em Python).
                    def handler(evt):
                        falar(f"Grupo: {titulo_grupo}", imediato=True)
                        evt.Skip()
                    return handler

                check_lists = []
                for titulo_grupo, itens_grupo in grupos:
                    sizer_exp.Add(wx.StaticText(dlg_exp, label=titulo_grupo), 0, wx.LEFT | wx.TOP, 10)
                    clb = wx.CheckListBox(dlg_exp, choices=[n for _, n in itens_grupo], size=(-1, 120))
                    clb.SetName(f"Grupo {titulo_grupo}")
                    clb.Bind(wx.EVT_SET_FOCUS, fabrica_handler_foco(titulo_grupo))
                    sizer_exp.Add(clb, 1, wx.EXPAND | wx.ALL, 10)
                    check_lists.append(clb)

                btn_sizer_exp = wx.BoxSizer(wx.HORIZONTAL)
                btn_ok_exp = wx.Button(dlg_exp, wx.ID_OK, "Exportar")
                btn_cancel_exp = wx.Button(dlg_exp, wx.ID_CANCEL, "Cancelar")
                btn_sizer_exp.Add(btn_ok_exp, 0, wx.ALL, 10)
                btn_sizer_exp.Add(btn_cancel_exp, 0, wx.ALL, 10)
                sizer_exp.Add(btn_sizer_exp, 0, wx.ALIGN_CENTER)
                dlg_exp.SetSizer(sizer_exp)
                check_lists[0].SetFocus()

                if dlg_exp.ShowModal() == wx.ID_OK:
                    marcados = []
                    for (_, itens_grupo), clb in zip(grupos, check_lists):
                        for idx in clb.GetCheckedItems():
                            marcados.append(itens_grupo[idx])
                    dlg_exp.Destroy()
                    if not marcados:
                        falar("Nenhuma seção marcada. Nada foi exportado.", imediato=True)
                        return
                    self.parent_frame.save_state(f"Exportar CASM{descricao_canal} de {self.sec_info['display_name']}")
                    # "Exportar CASM" é pra ser uma clonagem completa da seção
                    # de origem (ou só do canal escolhido, quando vem do botão
                    # "Exportar CASM do Canal Selecionado") - inclusive os
                    # bytes que o programa ainda não decifrou (ver
                    # BYTES_CASM_DESCONHECIDOS). Diferente do "Salvar
                    # Alterações" normal (que só regrava o byte que o Michel
                    # de fato tocou, pra não arriscar nada em edições
                    # pontuais), aqui a intenção é igualar a seção destino à
                    # de origem de verdade - inclusive nesses bytes -, então
                    # força todos os "Byte N" a entrar, com o valor atual da
                    # tela, mesmo que nenhum deles tenha sido tocado agora.
                    nomes_bytes = {nome_prop_byte(i) for i in BYTES_CASM_DESCONHECIDOS}
                    for destino, nome_alvo in marcados:
                        if destino is None:
                            casm_alvo = self.parent_frame.obter_casm_da_secao(nome_alvo, criar_se_ausente=True)
                            for ch in canais_alvo:
                                casm_alvo[ch].update(regra_do_canal(self.canais_data[ch], nomes_bytes))
                            continue
                        # Aba diferente: ela não está "ao vivo" agora, então
                        # mexe direto no instantâneo guardado dela.
                        estado_alvo = self.parent_frame.abas[destino]['estado']
                        biblioteca_alvo = estado_alvo.setdefault('casm_rules_by_section', {})
                        chave_alvo = nome_alvo.strip().lower()
                        casm_alvo = next((v for k, v in biblioteca_alvo.items() if k.strip().lower() == chave_alvo), None)
                        if casm_alvo is None:
                            base = estado_alvo.get('casm_rules') or self.parent_frame.get_default_casm_rules()
                            casm_alvo = copy.deepcopy(base)
                            biblioteca_alvo[nome_alvo] = casm_alvo
                        for ch in canais_alvo:
                            casm_alvo[ch].update(regra_do_canal(self.canais_data[ch], nomes_bytes))
                        estado_alvo['dirty'] = True
                        self.parent_frame.abas[destino]['titulo'] = self.parent_frame.titulo_da_aba(estado_alvo)
                    self.parent_frame.dirty = True
                    self.parent_frame.atualizar_titulo()
                    falar(f"CASM{descricao_canal} exportado da {self.sec_info['display_name']} para {len(marcados)} seção(ões).", imediato=True)
                else:
                    dlg_exp.Destroy()
                self.list_box.SetFocus()

        dlg = SectionEditDialog(self, sec)
        self.active_midi_dialog = dlg
        
        if dlg.ShowModal() == wx.ID_OK:
            dlg.parar_tudo()
            self.save_state(f"Mixagem Seção {sec['display_name']}")
            canais_data, modificados = dlg.canais_data, dlg.modificados
            casm_secao = self.obter_casm_da_secao(sec['name'], criar_se_ausente=True)
            
            propriedades_casm = list(dlg.propriedades_casm) + ["Toca Sem Acorde", "Redirecionar Para", "Acordes Ativos", "Editável"]
            for ch in range(16):
                if any(k in modificados[ch] for k in propriedades_casm):
                    casm_secao[ch].update(regra_do_canal(canais_data[ch], modificados[ch]))
                    self.dirty = True

            t_start = sec['start'] if sec['start'] is not None else 0
            t_end = sec['end']
            if t_end == float('inf'): t_end = sum(m.time for m in self.merged_track_cache)
            
            abs_msgs = []
            import mido
            from MHS_Utils import CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS

            # "Pitch Bend" aqui é a Sensibilidade da Roda (RPN 0: 101=0,
            # 100=0, 6=semitons, depois 101=127/100=127 pra fechar) - NUNCA
            # um evento de pitch bend de verdade tocado ao vivo. Acha, na
            # música INTEIRA e com estado (igual ao Drum Setup via NRPN,
            # ver aplicar_drum_setup), os índices exatos dessa sequência já
            # existente em cada canal - só ela, não qualquer 101/100/6/38
            # solto (Drum Setup via NRPN e o Voice Creator usam 99/98/6,
            # nunca 101/100, então não colidem). Assim dá pra trocar só a
            # sensibilidade, sem arriscar apagar uma dobra de pitch bend de
            # verdade que o Michel tenha tocado/gravado nessa seção.
            indices_pb_antigos = set()
            rpn_msb_scan = {c: None for c in range(16)}
            rpn_lsb_scan = {c: None for c in range(16)}
            dentro_pb0_scan = {c: False for c in range(16)}
            for idx_scan, msg_scan in enumerate(self.merged_track_cache):
                if msg_scan.type != 'control_change':
                    continue
                ch_scan = getattr(msg_scan, 'channel', None)
                if ch_scan is None:
                    continue
                if msg_scan.control == 101:
                    rpn_msb_scan[ch_scan] = msg_scan.value
                    if rpn_msb_scan[ch_scan] == 0 and rpn_lsb_scan[ch_scan] == 0:
                        dentro_pb0_scan[ch_scan] = True
                        indices_pb_antigos.add(idx_scan)
                    elif dentro_pb0_scan[ch_scan]:
                        indices_pb_antigos.add(idx_scan)
                        dentro_pb0_scan[ch_scan] = False
                elif msg_scan.control == 100:
                    rpn_lsb_scan[ch_scan] = msg_scan.value
                    if rpn_msb_scan[ch_scan] == 0 and rpn_lsb_scan[ch_scan] == 0:
                        dentro_pb0_scan[ch_scan] = True
                        indices_pb_antigos.add(idx_scan)
                    elif dentro_pb0_scan[ch_scan]:
                        indices_pb_antigos.add(idx_scan)
                        dentro_pb0_scan[ch_scan] = False
                elif msg_scan.control in (6, 38) and dentro_pb0_scan[ch_scan]:
                    indices_pb_antigos.add(idx_scan)

            curr_t = 0
            for idx, msg in enumerate(self.merged_track_cache):
                curr_t += msg.time
                m = msg.copy()
                if t_start <= curr_t < t_end:
                    if m.type == 'sysex':
                        # Grave/Agudo não têm .channel - o canal mora no
                        # próprio endereço (d[4]), então não caem no filtro
                        # de baixo (que usa getattr(m,'channel')).
                        d = bytes(m.data)
                        if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in (0x72, 0x73):
                            ch_eq = d[4]
                            mods_eq = modificados.get(ch_eq, set())
                            if (d[5] == 0x72 and "Grave" in mods_eq) or (d[5] == 0x73 and "Agudo" in mods_eq):
                                continue
                        abs_msgs.append((curr_t, m))
                        continue
                    ch = getattr(m, 'channel', -1)
                    if ch != -1 and ch in modificados:
                        mods = modificados[ch]
                        if m.type == 'program_change' and ("Patch" in mods or "Bank" in mods): continue
                        if m.type == 'control_change':
                            if m.control in [CC_BANK_MSB, CC_BANK_LSB] and ("Bank" in mods or "Patch" in mods): continue
                            if m.control == CC_VOLUME and "Volume" in mods: continue
                            if m.control == CC_PAN and "Pan" in mods: continue
                            if m.control == CC_EXPRESSION and "Expression" in mods: continue
                            if m.control == CC_REVERB and "Reverb" in mods: continue
                            if m.control == CC_CHORUS and "Chorus" in mods: continue
                            if m.control in (101, 100, 6, 38) and idx in indices_pb_antigos and "Pitch Bend" in mods: continue
                        # 'pitchwheel' NUNCA é removido daqui - é a roda de
                        # verdade tocada/gravada pelo Michel, não a
                        # configuração de sensibilidade (ver acima).

                        if m.type in ['note_on', 'note_off'] and "Transpose" in mods:
                            m.note = max(0, min(127, m.note + canais_data[ch]["Transpose"]))
                abs_msgs.append((curr_t, m))

            for ch in range(16):
                mods = modificados[ch]
                if not mods: continue
                c = canais_data[ch]
                if "Bank" in mods or "Patch" in mods:
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_BANK_MSB, value=c["Bank"] // 128)))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_BANK_LSB, value=c["Bank"] % 128)))
                    abs_msgs.append((t_start, mido.Message('program_change', channel=ch, program=c["Patch"])))
                if "Volume" in mods: abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_VOLUME, value=c["Volume"])))
                if "Pan" in mods: abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_PAN, value=c["Pan"])))
                if "Expression" in mods: abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_EXPRESSION, value=c["Expression"])))
                if "Reverb" in mods: abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_REVERB, value=c["Reverb"])))
                if "Chorus" in mods: abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=CC_CHORUS, value=c["Chorus"])))
                if "Grave" in mods: abs_msgs.append((t_start, mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x72, c["Grave"]))))
                if "Agudo" in mods: abs_msgs.append((t_start, mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x73, c["Agudo"]))))
                if "Pitch Bend" in mods:
                    # RPN 0 = Pitch Bend Sensitivity (o padrão da maioria dos
                    # teclados é 2 semitons) - só CONFIGURA a roda, nunca
                    # dobra o som sozinho.
                    valor_pb = max(0, min(24, int(c["Pitch Bend"])))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=101, value=0)))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=100, value=0)))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=6, value=valor_pb)))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=101, value=127)))
                    abs_msgs.append((t_start, mido.Message('control_change', channel=ch, control=100, value=127)))
            
            if hasattr(self, 'rebuild_from_abs_list'): self.rebuild_from_abs_list(abs_msgs)
            from MHS_Utils import falar
            falar(f"Seção {sec['display_name']} atualizada exclusivamente!", imediato=True)
        else:
            dlg.parar_tudo()
            
        self.active_midi_dialog = None
        dlg.Destroy()
    def OnSectionSelect(self, event):
        s = self.sectionList.GetStringSelection()
        if s:
            if "main" in s.lower() and "fill" not in s.lower():
                self.current_main_prefix = s.replace(" (vazio)", "")
            self.prepare_section_cache()
            self.anchor_tick = 0 
            self.current_accumulated_ticks = 0
        event.Skip()

    def OnSectionListCharHook(self, event):
        # Precisa ser EVT_CHAR_HOOK, não EVT_KEY_DOWN - um wx.ListBox nativo
        # engole o Enter puro antes dele virar um EVT_KEY_DOWN de verdade
        # (mesmo motivo do channelList já usar OnChannelListCharHook em vez
        # de tentar pegar isso no OnSectionListKeyDown/EVT_KEY_DOWN).
        if event.GetKeyCode() in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and not event.ControlDown() and not event.AltDown() and not event.ShiftDown():
            # Volta pro início da seção atual - navegar_tempo já sabe fazer
            # isso mesmo com o Play rodando (seta force_reload_loop, igual
            # o Ctrl+Home já fazia).
            self.navegar_tempo('inicio_secao')
        else:
            event.Skip()

    def OnSectionListKeyDown(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and not event.ShiftDown() and not event.AltDown():
            if key == wx.WXK_HOME:
                self.navegar_tempo('inicio_secao')
                return
            elif key == wx.WXK_END:
                self.navegar_tempo('fim_secao')
                return
        if key == wx.WXK_SPACE:
            if event.ControlDown(): self.OnTogglePause(None)
            else: self.OnTogglePlay(None)
        else: event.Skip()
    def OnChannelSelect(self, event):
        self.canal_atual = self.channelList.GetSelection()
        if not wx.GetKeyState(wx.WXK_SHIFT) and not wx.GetKeyState(wx.WXK_CONTROL):
            self.canais_selecionados = {self.canal_atual}
            self.non_continuous_sel = False
            # Pula a linha que acabou de virar a selecionada - reescrever o
            # texto dela bem na hora em que o WX já está anunciando a nova
            # seleção é o que causava a leitura dobrada ao subir/descer.
            self.atualizar_visual_selecao(skip_idx=self.canal_atual)
        event.Skip()

    def toggle_selecao_canal(self):
        # Shift+Espaço na lista de canais - igual ao MIDI Sequencer: a
        # primeira vez ativa o modo de seleção não contínua (marca o canal
        # atual sem mexer no que já estava selecionado); da segunda vez em
        # diante, alterna (liga/desliga) o canal atual dentro da seleção -
        # o jeito de marcar canais espalhados, não só um bloco contínuo.
        idx = self.channelList.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        self.canal_atual = idx
        if not getattr(self, 'non_continuous_sel', False):
            self.non_continuous_sel = True
            self.canais_selecionados.add(idx)
            self.atualizar_visual_selecao()
            falar(f"Seleção não contínua ativada. Canal {idx+1} selecionado", imediato=True)
        elif idx in self.canais_selecionados:
            self.canais_selecionados.discard(idx)
            self.atualizar_visual_selecao()
            falar(f"Canal {idx+1} não selecionado", imediato=True)
        else:
            self.canais_selecionados.add(idx)
            self.atualizar_visual_selecao()
            falar(f"Canal {idx+1} selecionado", imediato=True)

    def OnChannelListCharHook(self, event):
        if event.GetKeyCode() in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and not event.ControlDown() and not event.AltDown() and not event.ShiftDown():
            wx.CallAfter(self.acao_enter_canal)
        else:
            event.Skip()
    def OnChannelListKeyDown(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        alt = event.AltDown()
        shift = event.ShiftDown()
        if ctrl and not shift and not alt:
            if key == wx.WXK_HOME:
                self.navegar_tempo('inicio_secao')
                return
            elif key == wx.WXK_END:
                self.navegar_tempo('fim_secao')
                return
        if key == wx.WXK_SPACE:
            if shift and ctrl and not alt:
                self.relatar_selecoes_canais(None)
                return
            if shift and not ctrl and not alt:
                self.toggle_selecao_canal()
                return
            if ctrl: self.OnTogglePause(None)
            else: self.OnTogglePlay(None)
            return
        if not (ctrl or alt or shift):
            if key == wx.WXK_LEFT:
                if self.propriedade_atual > 0: 
                    self.propriedade_atual -= 1
                    self.atualizar_status_canal(falar_prop=True)
                return 
            elif key == wx.WXK_RIGHT:
                if self.propriedade_atual < len(self.propriedades) - 1: 
                    self.propriedade_atual += 1
                    self.atualizar_status_canal(falar_prop=True)
                return 
        if key in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and not ctrl:
            wx.CallAfter(self.acao_enter_canal)
            return
        elif key in [wx.WXK_ADD, wx.WXK_NUMPAD_ADD] or (key == ord('=')):
            self.alterar_valor_canal(1)
            return
        elif key in [wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT] or (key == ord('-')):
            self.alterar_valor_canal(-1)
            return
        if not (ctrl or alt or shift):
            if key == wx.WXK_F5: self.toggle_propriedade_direta("Mute"); return
            elif key == wx.WXK_F6: self.toggle_propriedade_direta("Solo"); return
            elif key == wx.WXK_F7: self.toggle_propriedade_direta("Arm"); return
        idx = self.channelList.GetSelection()
        if shift and key in [wx.WXK_UP, wx.WXK_DOWN]:
            old_idx = idx
            if key == wx.WXK_UP and idx > 0: idx -= 1
            elif key == wx.WXK_DOWN and idx < self.channelList.GetCount() - 1: idx += 1
            if idx != old_idx:
                self.canal_atual = idx
                self.channelList.SetSelection(idx)
                if getattr(self, 'non_continuous_sel', False):
                    # Modo não contínuo (ativado com Shift+Espaço): só
                    # passeia pela seleção espalhada, sem alterá-la - igual
                    # ao MIDI Sequencer, pra poder navegar sem perder o que
                    # já foi marcado.
                    texto = "Selecionado, " if idx in self.canais_selecionados else ""
                    falar(f"{texto}Canal {idx+1}", imediato=True)
                else:
                    self.canais_selecionados.add(idx)
                    self.atualizar_visual_selecao(skip_idx=idx)
                    falar(f"Canal {idx+1} Selecionado", imediato=True)
            return
        if ctrl and key == ord('A'):
            self.canais_selecionados = set(range(self.channelList.GetCount()))
            self.atualizar_visual_selecao()
            falar("Todos selecionados", imediato=True)
            return
        if not (ctrl or alt or shift) and key in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME, wx.WXK_END):
            # Deixa o próprio channelList mover a seleção (Skip), mas ANTES
            # disso atualiza só a linha de DESTINO com a propriedade atual -
            # assim, quando o NVDA anunciar a linha recém-focada
            # (comportamento nativo, sempre funcionou bem), ela já está com
            # o texto certo, sem precisarmos reescrever as outras 15 linhas.
            if idx != wx.NOT_FOUND:
                if key == wx.WXK_UP: alvo = max(0, idx - 1)
                elif key == wx.WXK_DOWN: alvo = min(self.channelList.GetCount() - 1, idx + 1)
                elif key == wx.WXK_HOME: alvo = 0
                else: alvo = self.channelList.GetCount() - 1  # wx.WXK_END
                if alvo != idx:
                    self._atualizar_uma_linha_canal(alvo)
        event.Skip()
    def atualizar_visual_selecao(self, skip_idx=None):
        for i in range(self.channelList.GetCount()):
            if i == skip_idx:
                continue
            texto_puro = self.channelList.GetString(i).replace(" [Selecionado]", "")
            nova_string = f"{texto_puro} [Selecionado]" if i in self.canais_selecionados else texto_puro
            if self.channelList.GetString(i) != nova_string:
                self.channelList.SetString(i, nova_string)

    def relatar_selecoes_canais(self, event):
        # Ctrl+Shift+Espaço - igual ao MIDI Sequencer: fala quantos canais
        # estão selecionados agora e quais (agrupando números seguidos em
        # faixas, ex: "3 canais selecionados: 1, 3 ao 5").
        qtd_canais = len(self.canais_selecionados)
        if qtd_canais <= 1 and not getattr(self, 'non_continuous_sel', False):
            falar("Nenhuma seleção de canais ativa no momento.", imediato=True)
            return
        canais_numeros = sorted(c + 1 for c in self.canais_selecionados)
        grupos = []
        if canais_numeros:
            inicio = canais_numeros[0]
            fim = canais_numeros[0]
            for n in canais_numeros[1:]:
                if n == fim + 1:
                    fim = n
                else:
                    grupos.append(str(inicio) if inicio == fim else f"{inicio} ao {fim}")
                    inicio = n
                    fim = n
            grupos.append(str(inicio) if inicio == fim else f"{inicio} ao {fim}")
        canais_str = ", ".join(grupos)
        falar(f"{qtd_canais} canais selecionados: {canais_str}", imediato=True)

    def limpar_tudo_mestre(self, event):
        # Shift+Esc - igual ao MIDI Sequencer: remove a seleção de tempo
        # (Entrada/Saída) e a de canais de uma vez, voltando pro canal atual
        # sozinho e saindo do modo de seleção não contínua.
        self.in_point = None
        self.out_point = None
        self.non_continuous_sel = False
        idx = self.channelList.GetSelection()
        self.canais_selecionados = {idx if idx != wx.NOT_FOUND else 0}
        self.atualizar_visual_selecao()
        falar("Limpeza total. Seleção de tempo e canais desfeita.", imediato=True)


    def ler_propriedades_locais_secao(self, track, canal, start, end):
        # Lê Volume/Pan/Expression/Bank/Patch/Reverb/Chorus/Grave/Agudo como
        # estão DE VERDADE dentro de UMA seção específica desse canal - ritmos
        # genuínos da Yamaha às vezes têm um Patch/Banco/Volume diferente
        # só numa seção (achado direto num arquivo real: "Ballada 2" do
        # Alex, canal 16). self.canais[canal] só guarda o instantâneo da
        # Área de Configuração (lido uma vez, no carregamento do arquivo) -
        # aqui a gente sobrepõe com o que essa seção específica reenvia,
        # preenchendo com o valor global só pro que ela não reenvia.
        from MHS_Utils import CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS
        props = dict(self.canais[canal])
        # "Pitch Bend" aqui é a Sensibilidade da Roda de Pitch Bend (RPN 0:
        # 101=0, 100=0, 6=semitons) - o padrão de fábrica da maioria dos
        # teclados é 2 semitons (igual ao MIDI Sequencer). NÃO é um "bend"
        # ao vivo - só é lido/gravado se o arquivo tiver essa sequência de
        # verdade nesta seção; senão fica no padrão.
        props.setdefault("Pitch Bend", 2)
        if start is None: start = 0
        if end is None: end = float('inf')
        msb, lsb = props["Bank"] // 128, props["Bank"] % 128
        rpn_msb, rpn_lsb, dentro_pb0 = None, None, False
        curr_t = 0
        for msg in track:
            curr_t += msg.time
            if curr_t < start: continue
            if curr_t >= end: break
            if msg.type == 'sysex':
                # SysEx não tem .channel (é `mido.Message('sysex', data=...)`
                # puro) - Grave/Agudo vêm daqui, com o canal codificado no
                # próprio endereço (d[4]), não no atributo .channel.
                d = bytes(msg.data)
                if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[4] == canal and d[5] in (0x72, 0x73):
                    props["Grave" if d[5] == 0x72 else "Agudo"] = d[6]
                continue
            if getattr(msg, 'channel', None) != canal: continue
            if msg.type == 'program_change':
                props["Patch"] = msg.program
            elif msg.type == 'control_change':
                if msg.control == CC_BANK_MSB:
                    msb = msg.value
                    props["Bank"] = msb * 128 + lsb
                elif msg.control == CC_BANK_LSB:
                    lsb = msg.value
                    props["Bank"] = msb * 128 + lsb
                elif msg.control == CC_VOLUME: props["Volume"] = msg.value
                elif msg.control == CC_PAN: props["Pan"] = msg.value
                elif msg.control == 101:
                    rpn_msb = msg.value
                    dentro_pb0 = (rpn_msb == 0 and rpn_lsb == 0)
                elif msg.control == 100:
                    rpn_lsb = msg.value
                    dentro_pb0 = (rpn_msb == 0 and rpn_lsb == 0)
                elif msg.control == 6 and dentro_pb0:
                    props["Pitch Bend"] = msg.value
                elif msg.control == CC_EXPRESSION: props["Expression"] = msg.value
                elif msg.control == CC_REVERB: props["Reverb"] = msg.value
                elif msg.control == CC_CHORUS: props["Chorus"] = msg.value
        return props

    def limpar_eventos_locais(self, ch, prop):
        if not getattr(self, 'merged_track_cache', None): return
        abs_msgs, modificado = self._normalizar_propriedade_generico(self.merged_track_cache, self.sections_info, self.canais, ch, prop)
        if modificado:
            abs_msgs = self.remover_duplicatas_estado(abs_msgs)
            self.rebuild_from_abs_list(abs_msgs)

    def _normalizar_propriedade_generico(self, merged_track_cache, sections_info, canais, ch, prop):
        # O mesmo algoritmo de limpar_eventos_locais, mas recebendo a
        # trilha/seções/canais como parâmetro em vez de sempre usar self.X -
        # assim dá pra reaproveitar tanto pra aba ao vivo quanto pro
        # instantâneo ('estado') de uma aba que não está na tela agora (ver
        # executar_copiar_canal_entre_secoes). Devolve (abs_msgs, modificado)
        # SEM commitar em lugar nenhum - quem chama decide como aplicar.
        if not merged_track_cache:
            return [], False

        starts = sorted({sec['start'] for sec in (sections_info or []) if sec.get('start') is not None})
        if not starts:
            return [], False

        from MHS_Utils import CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS
        import mido

        c = canais[ch]
        total_len = sum(m.time for m in merged_track_cache)
        
        inicio_janela = {}
        for i, start in enumerate(starts):
            inicio_janela[start] = 0 if i == 0 else start
        
        limite_secao = {}
        for i, start in enumerate(starts):
            fim_secao = starts[i + 1] if i + 1 < len(starts) else total_len
            busca_desde = inicio_janela[start]
            curr_t = 0
            limite = fim_secao
            for msg in merged_track_cache:
                curr_t += msg.time
                if curr_t < busca_desde: continue
                if curr_t >= fim_secao: break
                if msg.type == 'note_on' and getattr(msg, 'velocity', 0) > 0:
                    limite = curr_t
                    break
            limite_secao[start] = limite
        
        def bate_e_canal(msg):
            # Devolve True se essa msg é o prop pedido, NESTE canal - SysEx
            # (Grave/Agudo) não tem .channel, o canal mora no próprio
            # endereço (d[4]), então não dá pra usar getattr(msg,'channel')
            # igual as outras propriedades, que são todas CC/Program Change.
            if prop in ("Grave", "Agudo"):
                if msg.type != 'sysex': return False
                d = bytes(msg.data)
                addr = 0x72 if prop == "Grave" else 0x73
                return len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[4] == ch and d[5] == addr
            if getattr(msg, 'channel', -1) != ch: return False
            if prop == "Bank" and msg.type == 'control_change' and msg.control in [CC_BANK_MSB, CC_BANK_LSB]: return True
            if prop == "Patch" and msg.type == 'program_change': return True
            if prop == "Volume" and msg.type == 'control_change' and msg.control == CC_VOLUME: return True
            if prop == "Pan" and msg.type == 'control_change' and msg.control == CC_PAN: return True
            if prop == "Expression" and msg.type == 'control_change' and msg.control == CC_EXPRESSION: return True
            if prop == "Reverb" and msg.type == 'control_change' and msg.control == CC_REVERB: return True
            if prop == "Chorus" and msg.type == 'control_change' and msg.control == CC_CHORUS: return True
            return False
        
        abs_msgs = []
        curr_t = 0
        modificado = False
        secoes_com_bank_msb = set()
        secoes_com_bank_lsb = set()
        secoes_com_prop = set()
        
        for msg in merged_track_cache:
            curr_t += msg.time

            secao_atual = None
            for start in starts:
                # O AJUSTE: inclui o instante exato do limite na faixa local -
                # antes, uma reafirmação de Banco/Patch que caísse bem no mesmo
                # tick da primeira nota da seção (comum em arquivos reais, como
                # vimos agora) ficava de fora por 1 tick de diferença.
                if inicio_janela[start] <= curr_t <= limite_secao[start]:
                    secao_atual = start
                    break
            
            if secao_atual is not None and bate_e_canal(msg):
                modificado = True
                if prop == "Bank":
                    if msg.control == CC_BANK_MSB:
                        msg = msg.copy(value=c["Bank"] // 128)
                        secoes_com_bank_msb.add(secao_atual)
                    else:
                        msg = msg.copy(value=c["Bank"] % 128)
                        secoes_com_bank_lsb.add(secao_atual)
                elif prop == "Patch":
                    msg = msg.copy(program=c["Patch"])
                    secoes_com_prop.add(secao_atual)
                elif prop in ("Grave", "Agudo"):
                    addr = 0x72 if prop == "Grave" else 0x73
                    msg = msg.copy(data=(0x43, 0x10, 0x4C, 0x08, ch, addr, c[prop]))
                    secoes_com_prop.add(secao_atual)
                else:
                    msg = msg.copy(value=c[prop])
                    secoes_com_prop.add(secao_atual)
                    
            abs_msgs.append((curr_t, msg))
        
        cc_map = {"Volume": CC_VOLUME, "Pan": CC_PAN, "Expression": CC_EXPRESSION, "Reverb": CC_REVERB, "Chorus": CC_CHORUS}
        for start in starts:
            ponto_insercao = inicio_janela[start] if inicio_janela[start] > 0 else start
            if prop == "Bank":
                if start not in secoes_com_bank_msb:
                    abs_msgs.append((ponto_insercao, mido.Message('control_change', channel=ch, control=CC_BANK_MSB, value=c["Bank"] // 128)))
                    modificado = True
                if start not in secoes_com_bank_lsb:
                    abs_msgs.append((ponto_insercao, mido.Message('control_change', channel=ch, control=CC_BANK_LSB, value=c["Bank"] % 128)))
                    modificado = True
            elif prop == "Patch":
                if start not in secoes_com_prop:
                    abs_msgs.append((ponto_insercao, mido.Message('program_change', channel=ch, program=c["Patch"])))
                    modificado = True
            elif prop in ("Grave", "Agudo"):
                if start not in secoes_com_prop:
                    addr = 0x72 if prop == "Grave" else 0x73
                    abs_msgs.append((ponto_insercao, mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, addr, c[prop]))))
                    modificado = True
            elif prop in cc_map:
                if start not in secoes_com_prop:
                    abs_msgs.append((ponto_insercao, mido.Message('control_change', channel=ch, control=cc_map[prop], value=c[prop])))
                    modificado = True

        return abs_msgs, modificado

    def atualizar_status_canal(self, falar_prop=False):
        # NÃO mexe em NENHUMA linha da lista - só fala a propriedade/valor
        # atuais (quando falar_prop=True). Quem garante que a linha do
        # canal em foco mostre o valor certo quando ele for lido de novo é
        # a atualização "de passagem" feita em OnChannelListKeyDown logo
        # antes de qualquer navegação de canal (Cima/Baixo/Home/End) - ver
        # _atualizar_uma_linha_canal.
        if not getattr(self, 'canais', None): return
        idx = self.channelList.GetSelection()
        if idx == wx.NOT_FOUND: return
        if not falar_prop:
            return
        p = self.propriedades[self.propriedade_atual]
        c = self.canais[idx]
        val = c.get(p, 0 if p == "Transpose" else '')
        if p == "Patch":
            bank_id = c["Bank"]
            val_str = self.ins_db.get(bank_id, {}).get(val, f"Patch {val}").replace('PSR-SX600 ', '')
        elif p == "Bank":
            nome_banco = getattr(self, 'bank_names', {}).get(val, "")
            nome_limpo = nome_banco.replace('PSR-SX600 ', '') if nome_banco else ""
            val_str = f"{val} ({nome_limpo})" if nome_limpo else str(val)
        elif isinstance(val, bool): val_str = "Ligado" if val else "Desligado"
        else: val_str = str(val)
        falar(f"{p} {val_str}", imediato=True)

    def _alvos_edicao_canal(self):
        # Igual ao MHS MIDI Sequencer: se o canal em foco faz parte de uma
        # seleção múltipla (Shift+Cima/Baixo, Ctrl+A, Shift+Espaço), editar
        # uma propriedade afeta TODOS os canais selecionados de uma vez -
        # senão, afeta só o canal focado, como sempre.
        if self.canal_atual in self.canais_selecionados:
            return set(self.canais_selecionados)
        return {self.canal_atual}

    def _transpor_notas_canal(self, ch, semitons):
        """Soma 'semitons' a TODAS as notas do canal, em TODAS as seções do
        estilo (a trilha inteira). Devolve quantas notas mudaram."""
        if not semitons or not getattr(self, 'merged_track_cache', None):
            return 0
        trilha = self.merged_track_cache
        mudou = 0
        for i, m in enumerate(trilha):
            if m.type in ('note_on', 'note_off') and getattr(m, 'channel', -1) == ch:
                nova = max(0, min(127, m.note + semitons))
                if nova != m.note:
                    trilha[i] = m.copy(note=nova)
                    mudou += 1
        return mudou

    def _alterar_transpose_canais(self, alvos, incremento=None, absoluto=None):
        # A coluna "Transpose" da janela principal mexe nas notas do canal
        # em TODAS as seções (igual às outras colunas, que valem pro estilo
        # inteiro). O valor mostrado é o quanto o canal já foi transposto
        # desde que o arquivo foi aberto; a diferença entre o valor antigo e
        # o novo é aplicada de verdade nas notas (vale também pros canais
        # 9 e 10, a pedido do Michel).
        if not getattr(self, 'merged_track_cache', None):
            falar("Abra ou crie um estilo antes de transpor.", imediato=True)
            return
        self.save_state("Transpose do Canal")
        ch_foco = self.canal_atual
        novo_foco = self.canais[ch_foco].get("Transpose", 0)
        for ch in sorted(alvos):
            c = self.canais[ch]
            antigo = c.get("Transpose", 0)
            alvo_v = antigo + incremento if incremento is not None else absoluto
            alvo_v = max(-24, min(24, alvo_v))
            delta = alvo_v - antigo
            if delta:
                self._transpor_notas_canal(ch, delta)
                c["Transpose"] = alvo_v
            if ch == ch_foco:
                novo_foco = alvo_v
        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_from_abs_list(self._trilha_para_abs_list())
        falar(f"Transpose {novo_foco}", imediato=True)

    def _trilha_para_abs_list(self):
        abs_list = []
        t = 0
        for m in self.merged_track_cache:
            t += m.time
            abs_list.append((t, m.copy()))
        return abs_list

    def abrir_clonar_config_canal(self, event=None):
        if not getattr(self, 'canais', None) or not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de copiar configurações.", imediato=True)
            return
        origem = self.canal_atual
        foco_antes = wx.Window.FindFocus()
        dlg = ClonarConfigCanalDialog(self, origem)
        if dlg.ShowModal() == wx.ID_OK:
            alvos = dlg.get_alvos()
            dlg.Destroy()
            if not alvos:
                falar("Nenhum canal marcado. Nada foi copiado.", imediato=True)
            else:
                self.save_state(f"Copiar Configurações do Canal {origem + 1}")
                self.executar_clonar_config_canal(origem, alvos)
                nomes = ", ".join(rotulo_canal(c) for c in alvos)
                falar(f"Configurações do canal {rotulo_canal(origem)} copiadas para {nomes}.", imediato=True)
        else:
            dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    # ---- Vozes (.vce): importar/exportar a voz de um canal ----
    def _campos_voz_do_canal(self, ch):
        c = self.canais[ch]
        vc = dict(c.get("VoiceCreator", {}))
        campos = {
            "Bank": c.get("Bank", 0), "Patch": c.get("Patch", 0),
            "Expression": c.get("Expression", 127), "Reverb": c.get("Reverb", 0),
            "Chorus": c.get("Chorus", 0), "Grave": c.get("Grave", 64), "Agudo": c.get("Agudo", 64),
            "VoiceCreator": vc, "Extras": dict(c.get("VceExtras", {})),
        }
        if "porta_time" in vc:
            campos["PortaTime"] = vc["porta_time"]
        return campos

    def exportar_voz_canal(self, event=None):
        from mhs_vce import vce_exportar
        if not getattr(self, 'canais', None):
            falar("Nenhum canal disponível.", imediato=True)
            return
        ch = self.canal_atual
        c = self.canais[ch]
        nome = self.ins_db.get(c.get("Bank", 0), {}).get(c.get("Patch", 0), "") or "Voz"
        nome = re.sub(r'[\\/:*?"<>|]', "", nome.replace('PSR-SX600 ', '')).strip().replace(" ", "_")[:30] or "Voz"
        foco_antes = wx.Window.FindFocus()
        from mhs_vce import WILDCARD_SALVAR, TIPOS_VOZ, extensao_sugerida
        ext_sug = extensao_sugerida(c.get("Bank", 0))
        exts = [e for e, _ in TIPOS_VOZ]
        dlg = wx.FileDialog(self, f"Exportar voz do canal {rotulo_canal(ch)}", wildcard=WILDCARD_SALVAR,
                            defaultFile=nome + ext_sug, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        dlg.SetFilterIndex(exts.index(ext_sug))
        if dlg.ShowModal() == wx.ID_OK:
            caminho = dlg.GetPath()
            if os.path.splitext(caminho)[1].lower() not in exts:
                caminho += exts[max(0, dlg.GetFilterIndex())]
            try:
                vce_exportar(self._campos_voz_do_canal(ch), caminho)
                falar(f"Voz do canal {rotulo_canal(ch)} exportada para {os.path.basename(caminho)}.", imediato=True)
            except Exception as e:
                falar(f"Erro ao exportar a voz: {e}", imediato=True)
        dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def importar_voz_canal(self, event=None):
        if not getattr(self, 'canais', None) or not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de importar uma voz.", imediato=True)
            return
        foco_antes = wx.Window.FindFocus()
        dlg = wx.FileDialog(self, f"Importar voz para o canal {rotulo_canal(self.canal_atual)}",
                            wildcard=__import__("mhs_vce").WILDCARD_ABRIR, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            caminho = dlg.GetPath()
            dlg.Destroy()
            self.importar_voz_de_arquivo(self.canal_atual, caminho)
        else:
            dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def importar_voz_de_arquivo(self, ch, caminho):
        from mhs_vce import vce_ler
        try:
            d = vce_ler(caminho)
        except Exception as e:
            falar(f"Não consegui ler esse arquivo de voz: {e}", imediato=True)
            return False
        self.save_state(f"Importar Voz no Canal {ch + 1}")
        c = self.canais[ch]
        simples = ["Bank", "Patch", "Expression", "Reverb", "Chorus", "Grave", "Agudo"]
        for p in simples:
            if p in d:
                c[p] = d[p]
        c["VoiceCreator"] = dict(d.get("VoiceCreator", {}))
        c["VceExtras"] = dict(d.get("Extras", {}))
        # Ao vivo: timbre + mixagem + Voice Creator no teclado
        self.enviar_midi_param("Bank", c["Bank"], ch)
        self.enviar_midi_param("Patch", c["Patch"], ch)
        for p in ("Expression", "Reverb", "Chorus", "Grave", "Agudo"):
            self.enviar_midi_param(p, c[p], ch)
        self._enviar_voice_creator_ao_vivo(ch, c["VoiceCreator"])
        # No arquivo: as colunas e o Voice Creator ficam prontos pra salvar
        for p in simples:
            self.limpar_eventos_locais(ch, p)
        self.aplicar_voice_creator(ch, dict(c["VoiceCreator"]))
        self.dirty = True
        self.atualizar_titulo()
        self.update_mixer_list()
        nome = self.ins_db.get(c["Bank"], {}).get(c["Patch"], f"Patch {c['Patch']}").replace('PSR-SX600 ', '')
        falar(f"Voz {os.path.basename(caminho)} importada no canal {rotulo_canal(ch)}: {nome}.", imediato=True)
        return True

    def _enviar_voice_creator_ao_vivo(self, ch, vc):
        porta = getattr(self, 'midi_out', None)
        if not porta:
            return
        from MHS_Utils import detune_separar
        try:
            for a, v in vc.items():
                if a == "porta_time":
                    porta.send(mido.Message('control_change', channel=ch, control=5, value=v))
                    porta.send(mido.Message('control_change', channel=ch, control=65, value=127 if v > 0 else 0))
                elif a == 0x09:
                    alto, baixo = detune_separar(v)
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x09, alto)))
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x0A, baixo)))
                elif a in (0x01, 0x02, 0x03):
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x0A, ch, a, v)))
                elif isinstance(a, int):
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, a, v)))
        except Exception:
            pass

    def executar_clonar_config_canal(self, origem, alvos):
        import copy
        src = self.canais[origem]
        simples = ["Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo", "Bank", "Patch"]
        for alvo in alvos:
            if alvo == origem:
                continue
            dst = self.canais[alvo]
            for p in simples:
                if p in src:
                    dst[p] = src[p]
            self.enviar_midi_param("Bank", dst["Bank"], alvo)
            self.enviar_midi_param("Patch", dst["Patch"], alvo)
            for p in ("Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo"):
                self.enviar_midi_param(p, dst[p], alvo)
            # Tira dos trechos de cada seção qualquer valor "carimbado" que
            # ainda mandasse no lugar do que acabou de ser copiado.
            for p in simples:
                self.limpar_eventos_locais(alvo, p)
            # Bateria / Voice Creator: grava de verdade no arquivo
            for chave in ("DrumParams", "CustomDrumMap", "DrumParamsNRPN", "VoiceCreator"):
                if chave in src:
                    dst[chave] = copy.deepcopy(src[chave])
                else:
                    dst.pop(chave, None)
            if src.get("DrumParams") or src.get("CustomDrumMap") or src.get("DrumParamsNRPN"):
                self.aplicar_drum_setup(alvo, dict(dst.get("DrumParams", {})), dict(dst.get("CustomDrumMap", {})), dict(dst.get("DrumParamsNRPN", {})))
            if src.get("VoiceCreator"):
                self.aplicar_voice_creator(alvo, dict(dst["VoiceCreator"]))
        self.dirty = True
        self.atualizar_titulo()
        self.update_mixer_list()

    def alterar_valor_canal(self, incremento):
        p = self.propriedades[self.propriedade_atual]
        if p in ("Nome", "Mute", "Solo", "Arm"):
            from MHS_Utils import falar
            falar("Pressione Enter para editar", imediato=True)
            return

        if p == "Transpose":
            self._alterar_transpose_canais(self._alvos_edicao_canal(), incremento=incremento)
            return

        self.save_state("Edição de Propriedade do Canal")
        from MHS_Utils import VALOR_MIN_MIDI, VALOR_MAX_MIDI
        if p == "Bank": min_v, max_v = 0, 16384
        else: min_v, max_v = VALOR_MIN_MIDI, VALOR_MAX_MIDI

        # Cada canal alvo recebe o MESMO delta em cima do SEU PRÓPRIO valor
        # (preserva a diferença relativa entre eles - ex.: 100/101/102/103/104
        # todos +2 viram 102/103/104/105/106), não um valor único forçado.
        for ch in self._alvos_edicao_canal():
            c = self.canais[ch]
            c[p] = max(min_v, min(max_v, c[p] + incremento))
            # A EMPURRADA: Banco e Patch andam sempre juntos - mandar só um dos
            # dois sozinho, às vezes, não é suficiente pro teclado assentar a
            # troca de verdade (a mesma lição do baixo do Arrocha).
            if p in ("Bank", "Patch"):
                self.enviar_midi_param("Bank", c["Bank"], ch)
                self.enviar_midi_param("Patch", c["Patch"], ch)
            else:
                self.enviar_midi_param(p, c[p], ch)
            # A MÁGICA: Limpa o carimbo das seções locais!
            self.limpar_eventos_locais(ch, p)

        self.dirty = True
        self.atualizar_titulo()
        self.atualizar_status_canal(falar_prop=True)

    def acao_enter_canal(self):
        import wx
        p = self.propriedades[self.propriedade_atual]
        ch = self.canal_atual
        c = self.canais[ch]
        alvos = self._alvos_edicao_canal()
        if p in ["Mute", "Solo", "Arm"]:
            self.toggle_propriedade_direta(p)
            return
        if p == "Transpose":
            dlg = wx.TextEntryDialog(self, f"Transposição (-24 a 24 semitons) para {len(alvos)} canal(is):", "Transpose", str(c.get("Transpose", 0)))
            if dlg.ShowModal() == wx.ID_OK:
                try:
                    v = int(dlg.GetValue())
                    self._alterar_transpose_canais(alvos, absoluto=v)
                except ValueError:
                    falar("Valor inválido.", imediato=True)
            dlg.Destroy()
            wx.CallLater(100, lambda: self.channelList.SetFocus())
            return
        self.save_state("Edição de Propriedade do Canal")
        if p == "Nome":
            dlg = wx.TextEntryDialog(self, f"Nome para {len(alvos)} canal(is):", "Editar Nome", str(c[p]))
            if dlg.ShowModal() == wx.ID_OK:
                novo_nome = dlg.GetValue()
                for alvo in alvos:
                    self.canais[alvo][p] = novo_nome
                self.dirty = True
                self.atualizar_titulo()
                from MHS_Utils import falar
                falar(f"Nome alterado para {novo_nome}", imediato=True)
            else: self.undo_stack.pop()
            wx.CallLater(100, lambda: self.channelList.SetFocus())
            dlg.Destroy()
        else:
            # Todos os canais selecionados recebem o MESMO valor absoluto
            # digitado - diferente do +/-, que preserva a diferença entre
            # eles (igual ao MHS MIDI Sequencer).
            dlg = wx.TextEntryDialog(self, f"Valor de {p} para {len(alvos)} canal(is):", "Editar", str(c[p]))
            if dlg.ShowModal() == wx.ID_OK:
                try:
                    v = int(dlg.GetValue())
                    from MHS_Utils import VALOR_MIN_MIDI, VALOR_MAX_MIDI
                    if p == "Bank": min_v, max_v = 0, 16384
                    else: min_v, max_v = VALOR_MIN_MIDI, VALOR_MAX_MIDI
                    v = max(min_v, min(max_v, v))
                    for alvo in alvos:
                        cc = self.canais[alvo]
                        cc[p] = v
                        self.enviar_midi_param(p, v, alvo)
                        # A MÁGICA: Limpa o carimbo das seções locais!
                        self.limpar_eventos_locais(alvo, p)
                    self.dirty = True
                    self.atualizar_titulo()
                    from MHS_Utils import falar
                    falar(f"{p} alterado para {v}", imediato=True)
                except Exception: self.undo_stack.pop()
            else: self.undo_stack.pop()
            wx.CallLater(100, lambda: self.channelList.SetFocus())
            dlg.Destroy()
    def toggle_propriedade_direta(self, prop):
        if prop not in ["Mute", "Solo", "Arm"]: self.save_state("Toggle Propriedade")
        # Mesma regra dos outros dois métodos: canal em foco dentro de uma
        # seleção múltipla liga/desliga TODOS os selecionados de uma vez,
        # todos indo pro estado OPOSTO ao que o canal focado tinha.
        alvos = self._alvos_edicao_canal()
        novo_estado = not self.canais[self.canal_atual][prop]
        for ch in alvos:
            self.canais[ch][prop] = novo_estado
            if prop == "Mute" and novo_estado:
                self.silence_channel(ch)
        if prop == "Solo" and novo_estado:
            for i in range(16):
                if i not in alvos:
                    self.silence_channel(i)
        if prop not in ["Mute", "Solo", "Arm"]:
            self.dirty = True
            self.atualizar_titulo()
        estado_str = "Ligado" if novo_estado else "Desligado"
        falar(f"{prop} {estado_str}", imediato=True)
        # Não reescreve nenhuma linha aqui - a linha do canal atual se
        # corrige sozinha na próxima vez que sairmos dela (ver
        # OnChannelListKeyDown, Cima/Baixo/Home/End).

    def _texto_linha_canal(self, ch):
        c = self.canais[ch]
        status = ("[S] " if c['Solo'] else "") + ("[M] " if c['Mute'] else "") + ("[A] " if c['Arm'] else "")
        p = self.propriedades[self.propriedade_atual]
        val = c.get(p, 0 if p == "Transpose" else '')
        if p == "Patch":
            bank_id = c["Bank"]
            val_str = self.ins_db.get(bank_id, {}).get(val, f"Patch {val}").replace('PSR-SX600 ', '')
        elif p == "Bank":
            nome_banco = getattr(self, 'bank_names', {}).get(val, "")
            nome_limpo = nome_banco.replace('PSR-SX600 ', '') if nome_banco else ""
            val_str = f"{val} ({nome_limpo})" if nome_limpo else str(val)
        elif isinstance(val, bool): val_str = "Ligado" if val else "Desligado"
        else: val_str = str(val)
        sel_tag = " [Selecionado]" if ch in self.canais_selecionados else ""
        return f"{rotulo_canal(ch)}  |  {status}{p} {val_str}{sel_tag}"

    def _atualizar_uma_linha_canal(self, ch):
        # Reescreve o texto de UMA SÓ linha (sem Freeze - desnecessário pra
        # uma linha só). Peça central da "navegação limpa" (igual ao MHS
        # MIDI Sequencer, que nunca deixa o próprio WX anunciar nada - só a
        # fala manual via accessible_output2): em vez de reescrever as 16
        # linhas toda vez que a propriedade muda (o que bagunçava a rolagem
        # da lista justo no ÚLTIMO canal, fazendo o NVDA "pular" pra uma
        # linha de cima), só atualizamos a linha de DESTINO, um pouquinho
        # antes do foco nativo chegar nela (ver OnChannelListKeyDown). A
        # linha de onde saímos fica "desatualizada" sem problema - ninguém
        # mais vai lê-la até voltarmos, e ela será corrigida de novo antes
        # de chegarmos lá.
        nova_string = self._texto_linha_canal(ch)
        if self.channelList.GetString(ch) != nova_string:
            self.channelList.SetString(ch, nova_string)

    def update_mixer_list(self, skip_idx=None):
        # Só usado pra atualizações RARAS que precisam repovoar a lista
        # inteira de uma vez (abrir o programa, MIDI chegando no meio da
        # edição) - NUNCA no caminho quente de navegação (setas), que usa
        # _atualizar_uma_linha_canal.
        self.channelList.Freeze()
        if self.channelList.GetCount() == 0:
            for ch in range(TOTAL_CANAIS): self.channelList.Append("")
        for ch in range(TOTAL_CANAIS):
            if ch == skip_idx:
                continue
            self._atualizar_uma_linha_canal(ch)
        self.channelList.Thaw()
    def toggle_gravacao(self, event):
        if not self.gravando:
            if not any(c["Arm"] for c in self.canais):
                falar("Arme pelo menos um canal para gravar.", imediato=True)
                return
            idx = self.sectionList.GetSelection()
            secao_criada = False
            if idx != wx.NOT_FOUND and getattr(self, 'sections_info', []):
                section = self.sections_info[idx]
                # Não confia só em section['present'] (vem de self.sections_info,
                # que pode estar OBSOLETO num instante ruim - achado com o
                # Michel: gravar numa seção que JÁ EXISTIA de verdade, mas o
                # cache achava que não, chamava criar_secao_nova por engano e
                # plantava uma identidade SFF2/marcador NOVOS por cima da
                # seção real, bagunçando tudo depois dela). Antes de criar
                # qualquer coisa, confere de novo, direto no arquivo (marcador
                # de verdade em merged_track_cache), sem confiar em cache
                # nenhum - é barato e sempre correto.
                nome_alvo = section['name'].strip().lower()
                existe_de_verdade = any(
                    m.type in ('marker', 'cuepoint') and getattr(m, 'text', '').strip().lower() == nome_alvo
                    for m in getattr(self, 'merged_track_cache', [])
                )
                # Se a música JÁ ESTÁ TOCANDO, a seção obrigatoriamente já
                # existe de verdade - não tem como estar tocando uma seção
                # que não existe. Suspeita do Michel: armar a gravação (R)
                # com a seção já em reprodução (Espaço antes) é justamente o
                # instante em que section['present'] mentia "não existe" -
                # aqui a gente nem PRECISA confiar em nenhuma leitura desse
                # campo, o `self.playing` sozinho já garante que é real.
                if self.playing:
                    existe_de_verdade = True
                if existe_de_verdade and not section.get('present', False):
                    # O cache mentia "não existe" - conserta o cache na hora
                    # (sem recriar nada) e segue gravando na seção de verdade.
                    self.rebuild_sections_from_cache()
                    idx = self.sectionList.GetSelection()
                    if idx != wx.NOT_FOUND and idx < len(self.sections_info):
                        section = self.sections_info[idx]
                if not existe_de_verdade and (not section.get('present', False) or section.get('start') is None):
                    if not getattr(self, 'current_midi_data', None):
                        falar("Abra ou crie um estilo antes de gravar.", imediato=True)
                        return
                    tpq = self.current_midi_data.ticks_per_beat
                    tpm = tpq * self.beats_per_measure
                    self.criar_secao_nova(section['name'], 1, tpm)
                    secao_criada = True
                # O CASM de uma seção só existia se alguém tivesse aberto
                # "Editar Seção" e salvo nela pelo menos uma vez - gravar
                # direto (mesmo numa seção que já existia) nunca criava essa
                # entrada, e sem ela patch_casm_binary nunca toca os registros
                # dessa seção (ela fica com o molde genérico, nunca corrigido,
                # e a seção sai muda mesmo com notas de verdade gravadas).
                self.obter_casm_da_secao(section['name'], criar_se_ausente=True)
            self.gravando = True
            if self.playing:
                self.save_state("Gravação (Punch In)")
            self.atualizar_titulo()
            if secao_criada:
                falar("Seção criada com 1 compasso. Gravação Armada. Pressione Espaço para tocar ou toque uma tecla.", imediato=True)
            else:
                falar("Gravação Armada. Pressione Espaço para tocar ou toque uma tecla.", imediato=True)
        else:
            self.gravando = False
            self.atualizar_titulo()
            falar("Gravação Desativada.", imediato=True)
            self.aplicar_gravacao()

    def aplicar_gravacao(self):
        # Serializado (ver comentário em self._grava_lock, no __init__) -
        # nunca deixa a chamada do midi_worker (loop dando a volta) e a
        # chamada manual (usuário parando a gravação) reconstruírem
        # merged_track_cache ao mesmo tempo.
        with self._grava_lock:
            self._aplicar_gravacao_impl()

    def _aplicar_gravacao_impl(self):
        if not self.recorded_events: return
        tpq = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
        # Mesma checagem do prepare_section_cache: chamado de dentro do
        # midi_worker (virada do loop de gravação, fora da thread principal),
        # ler sectionList.GetSelection() (widget de verdade) não é seguro -
        # usa o índice da seção ativa (já mantido certinho por quem chamou).
        no_main_thread = not wx.IsMainThread()
        idx = self.sectionList.GetSelection() if not no_main_thread else getattr(self, '_active_section_idx', wx.NOT_FOUND)
        section_start = 0
        section_end = float('inf')
        if idx != wx.NOT_FOUND and getattr(self, 'sections_info', []):
            sec = self.sections_info[idx]
            section_start = sec.get('start', 0)
            if section_start is None: section_start = 0
            section_end = sec.get('end', float('inf'))
            if section_end is None or section_end == float('inf'):
                # Seção sem próxima (é a última coisa do arquivo, ex: Main A
                # sozinho num ritmo recém-começado) - o fim de verdade é o
                # fim do ARQUIVO inteiro (que a âncora plantada em
                # criar_secao_nova/apply_section_resize garante que cobre os
                # compassos declarados), não "sempre 1 compasso". Esse
                # fallback fixo em 1 compasso era o que fazia a gravação
                # cortar (sem quantização) ou dobrar de volta pro compasso 1
                # (com quantização) tudo que fosse tocado do compasso 2 em
                # diante, mesmo numa seção redimensionada pra 4 compassos.
                section_end = sum(m.time for m in self.merged_track_cache)
                if section_end <= section_start:
                    section_end = section_start + (tpq * self.beats_per_measure)
        else:
            section_end = tpq * self.beats_per_measure
            
        # Fila (FIFO) por nota, não um slot único - um slot único perde a
        # instância anterior se a MESMA nota for retocada antes do note_off
        # dela chegar (ex.: violão com técnica de "sustain": segura o
        # acorde a seção inteira E retoca as mesmas notas por cima) - a
        # nota antiga ficava SEM NENHUM note_off gerado (nem aqui, nem no
        # fechamento de fim-de-gravação logo abaixo, que só vê a instância
        # mais recente) - um desbalanceamento de verdade no arquivo salvo,
        # não só um jeito errado de mostrar. Achado com o Michel no violão
        # do Pop MHS 02.sty (mesma raiz do bug já corrigido em load_events,
        # dessa vez na gravação em si).
        from collections import defaultdict, deque
        active_rec_notes = defaultdict(deque)
        abs_rec_events = []
        note_shifts = defaultdict(deque)
        for tick, msg in self.recorded_events:
            if self.rt_quantize:
                if msg.type == 'note_on' and msg.velocity > 0:
                    grid_ticks = (tpq * 4.0) / self.rt_quantize_res
                    rel_tick = tick - section_start
                    snapped_rel = max(0, round(rel_tick / grid_ticks) * grid_ticks)
                    new_tick = section_start + int(snapped_rel)
                    if new_tick >= section_end: new_tick = section_start + (new_tick - section_end)
                    note_shifts[(msg.channel, msg.note)].append(new_tick - tick)
                    tick = new_tick
                elif msg.type in ['note_off', 'note_on']:
                    key = (msg.channel, msg.note)
                    fila_shift = note_shifts.get(key)
                    if fila_shift:
                        tick = max(0, tick + fila_shift.popleft())
            if msg.type == 'note_on' and msg.velocity > 0:
                if tick < section_end:
                    active_rec_notes[(msg.channel, msg.note)].append(tick)
                    abs_rec_events.append([tick, msg.copy()])
            elif msg.type in ['note_off', 'note_on']:
                key = (msg.channel, msg.note)
                fila = active_rec_notes.get(key)
                if fila:
                    on_tick = fila.popleft()
                    clamped_off = tick
                    if clamped_off >= section_end: clamped_off = section_end - 2
                    if clamped_off <= on_tick: clamped_off = on_tick + 1
                    abs_rec_events.append([clamped_off, msg.copy()])
            else:
                if msg.type not in ['note_off', 'note_on']:
                    if tick < section_end:
                        abs_rec_events.append([tick, msg.copy()])

        for key, fila in active_rec_notes.items():
            ch, note = key
            for on_tick in fila:
                clamped_off = section_end - 2
                if clamped_off <= on_tick: clamped_off = on_tick + 1
                abs_rec_events.append([clamped_off, mido.Message('note_off', channel=ch, note=note, velocity=0)])

        abs_events = []
        curr_t = 0
        for m in self.merged_track_cache:
            curr_t += m.time
            abs_events.append([curr_t, m.copy()])
            
        abs_events.extend(abs_rec_events)
        abs_events.sort(key=lambda x: x[0])
        self.merged_track_cache = []
        last_t = 0
        for tick, msg in abs_events:
            msg.time = int(round(tick - last_t))
            self.merged_track_cache.append(msg)
            last_t = tick
            
        self.recorded_events = []
        self.dirty = True
        if no_main_thread:
            # Igual ao prepare_section_cache: a parte que os PRÓXIMOS giros
            # do laço de gravação precisam (sections_info/current_section_msgs
            # atualizados) roda direto aqui, sem CallAfter nem espera - já
            # está seguro (dados puros). Só o que toca widget de verdade
            # (título, listas, falar) é adiado sem bloquear ninguém.
            #
            # `idx` foi capturado LOGO NO INÍCIO desta chamada (antes de
            # qualquer coisa assíncrona rodar) - é o índice que REALMENTE
            # estava ativo quando esta gravação foi processada. O refresh da
            # lista de seções (`refresh_section_list`) recebe esse MESMO
            # índice via `forcar_idx`, em vez de deixá-lo reler `sectionList.
            # GetSelection()`/adivinhar pelo nome quando finalmente rodar (um
            # instante indeterminado depois, no CallAfter).
            #
            # ACHADO (causa real do "pulou pra seção errada"): `_active_
            # section_idx` indexa a lista CANÔNICA (`build_full_section_
            # list`, ordem fixa Intro A/B/C, Main A/B/C/D, Fills, Ending -
            # a mesma ordem que populate `sectionList` de verdade e que
            # `refresh_section_list` sempre usa), NÃO a ordem física/por
            # tick do arquivo (`_secoes_de_track`, que só lista o que
            # existe, na ordem em que aparece na música - completamente
            # diferente da canônica). Setar `sections_info` só com `_secoes_
            # de_track` (como fazia antes) deixa esse atributo TEMPORARIAMENTE
            # na ordem errada - e como `prepare_section_cache(force_idx=idx)`
            # e o laço de tick do midi_worker leem `sections_info[idx]`
            # imediatamente em seguida (antes do CallAfter adiado que
            # devolveria a ordem canônica via refresh_section_list), o MESMO
            # índice passa a apontar pra outra seção completamente diferente
            # até o refresh adiado rodar - exatamente o "pulo" relatado.
            # Fix: já reordena pra canônica aqui mesmo (puro dado, sem
            # widget, seguro fora da thread principal) - o índice nunca
            # fica "errado" nem por um instante. Numa atribuição SÓ (não
            # em duas, como antes) - mesmo cuidado de rebuild_sections_
            # from_cache (ver comentário em build_full_section_list):
            # mesmo aqui rodando na própria thread do midi_worker (então
            # sem risco de UMA corrida com ELE especificamente), deixar
            # `self.sections_info` visível na ordem física por um instante
            # é uma pegadinha à toa - mais barato eliminar de vez.
            self.sections_info = self.build_full_section_list(self._secoes_de_track(self.merged_track_cache))
            self.prepare_section_cache(force_idx=idx)
            wx.CallAfter(self.atualizar_titulo)
            wx.CallAfter(self.refresh_section_list, False, idx)
            wx.CallAfter(self.update_mixer_list)
            wx.CallAfter(falar, "Gravação salva.", imediato=True)
        else:
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            falar("Gravação salva.", imediato=True)
    def ticks_por_compasso(self, tpq, numerador, denominador):
        # Um compasso numerador/denominador vale numerador notas de
        # 1/denominador - e uma nota de 1/denominador vale tpq*4/denominador
        # ticks (tpq é sempre ticks por SEMÍNIMA, 1/4, no MIDI). Pra 4/4
        # (denominador 4) isso bate exatamente com o tpq*numerador de sempre.
        return int(round(tpq * numerador * 4 / denominador))

    def obter_compasso_da_secao(self, track, start):
        # Lê a figura de compasso (numerador/denominador) que está de
        # verdade em vigor NAQUELE ponto do arquivo - procura o 'time_signature'
        # mais recente até ali (igual a lógica de "valor local" do Grave/
        # Agudo/Bank/Patch), caindo no padrão global do estilo (self.
        # beats_per_measure, sempre /4) se a seção nunca teve o próprio.
        numerador, denominador = self.beats_per_measure, 4
        if start is None:
            return numerador, denominador
        curr_t = 0
        for msg in track:
            curr_t += msg.time
            if curr_t > start:
                break
            if msg.type == 'time_signature':
                numerador, denominador = msg.numerator, msg.denominator
        return numerador, denominador

    def OnResizeSection(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not self.sections_info: return
        section = self.sections_info[idx]
        if not self.current_midi_data: return
        tpq = self.current_midi_data.ticks_per_beat
        foco_antes = wx.Window.FindFocus()

        if not section.get('present', False) or section.get('start') is None:
            # Seção nova ainda não existe em lugar nenhum do arquivo - não
            # tem "figura local" pra ler, usa o padrão global do estilo.
            num_atual, den_atual = self.beats_per_measure, 4
            dlg = SectionLengthDialog(self, section['display_name'], 1, num_atual, den_atual)
            if dlg.ShowModal() == wx.ID_OK:
                new_measures, novo_num, novo_den = dlg.GetValues()
                tpm = self.ticks_por_compasso(tpq, novo_num, novo_den)
                self.criar_secao_nova(section['name'], new_measures, tpm, novo_num, novo_den)
                falar(f"Seção {section['display_name']} criada com {new_measures} compassos de {novo_num}/{novo_den}.", imediato=True)
            self._agendar_restaurar_foco(foco_antes)
            dlg.Destroy()
            return

        start_tick = section['start']
        end_tick = section['end']
        if end_tick == float('inf'):
            end_tick = sum(m.time for m in self.merged_track_cache)
        num_atual, den_atual = self.obter_compasso_da_secao(self.merged_track_cache, start_tick)
        tpm_atual = self.ticks_por_compasso(tpq, num_atual, den_atual)
        current_ticks = end_tick - start_tick
        current_measures = int(round(current_ticks / tpm_atual))
        if current_measures <= 0: current_measures = 1
        # A seção pode estar com uma sobra torta (uma fração de compasso -
        # sobra de um bug antigo de redimensionamento, ou de uma gravação/
        # edição manual) - current_measures já vem ARREDONDADO, então só
        # comparar "new_measures != current_measures" não pega o caso onde
        # o usuário simplesmente confirma o número já mostrado (pensando
        # que já está certo) sem saber que os TICKS não batem exatamente.
        desalinhada = current_ticks != current_measures * tpm_atual

        dlg = SectionLengthDialog(self, section['display_name'], current_measures, num_atual, den_atual)
        if dlg.ShowModal() == wx.ID_OK:
            new_measures, novo_num, novo_den = dlg.GetValues()
            if new_measures != current_measures or (novo_num, novo_den) != (num_atual, den_atual) or desalinhada:
                tpm_novo = self.ticks_por_compasso(tpq, novo_num, novo_den)
                self.apply_section_resize(section, current_measures, new_measures, tpm_atual, tpm_novo, novo_num, novo_den)
                if desalinhada and new_measures == current_measures and (novo_num, novo_den) == (num_atual, den_atual):
                    falar(f"Seção realinhada para {new_measures} compassos exatos de {novo_num}/{novo_den} (tinha uma sobra torta).", imediato=True)
                else:
                    falar(f"Seção alterada para {new_measures} compassos de {novo_num}/{novo_den}.", imediato=True)
            else:
                falar("Nenhuma alteração feita.", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()

    def criar_secao_nova(self, nome_secao, num_measures, tpm, numerador=None, denominador=None):
        self.save_state(f"Criar Seção {nome_secao}")
        self._criar_secao_nova_sem_undo(nome_secao, num_measures, tpm, numerador, denominador)

    def _criar_secao_nova_sem_undo(self, nome_secao, num_measures, tpm, numerador=None, denominador=None):
        # Mesmo corpo de criar_secao_nova, só que sem o save_state próprio -
        # usado por quem já empilhou o PRÓPRIO undo de uma operação maior
        # (ex: Copiar Canal Entre Seções criando o destino que ainda não
        # existia) - sem isso, cada seção criada dentro de um laço maior
        # empilhava mais um Ctrl+Z separado pra uma ação que o usuário só
        # pediu uma vez.
        # A MESMA ORDEM FÍSICA REAL confirmada nos arquivos genuínos: Main A-D,
        # Fill Ins, Intros, Endings, Fill In BA por último. A seção nova entra
        # logo depois da seção presente mais próxima que vem antes dela nessa
        # ordem - nunca gruda em cima de nada que já existe.
        ordem_fisica_real = [
            "Main A", "Main B", "Main C", "Main D",
            "Fill In AA", "Fill In BB", "Fill In CC", "Fill In DD",
            "Intro A", "Intro B", "Intro C",
            "Ending A", "Ending B", "Ending C",
            "Fill In BA"
        ]
        idx_alvo = ordem_fisica_real.index(nome_secao) if nome_secao in ordem_fisica_real else len(ordem_fisica_real)
        
        ponto_insercao = None
        for nome_anterior in reversed(ordem_fisica_real[:idx_alvo]):
            for sec in self.sections_info:
                if sec['name'].strip().lower() == nome_anterior.strip().lower() and sec.get('present', False):
                    fim = sec['end']
                    if fim == float('inf'): fim = sum(m.time for m in self.merged_track_cache)
                    ponto_insercao = fim
                    break
            if ponto_insercao is not None:
                break
        
        import mido

        # Este arquivo já teve, alguma vez, a identidade "SFF2" que TODO
        # arquivo genuíno da Yamaha tem no começo (marcador SFF2 + os 4
        # SysEx desconhecidos + marcador SInt + reset GM/XG)? Um projeto
        # começado direto pela gravação (sem nunca passar por "Novo Estilo")
        # nasce sem nada disso - o SX600 recusa esse arquivo ("erro ao
        # carregar os dados") mesmo que todo o resto esteja certo, porque
        # ele nem reconhece o arquivo como um Estilo de verdade. Plantada
        # aqui, na primeiríssima seção que qualquer projeto cria, exatamente
        # como o "Novo Estilo" já faz.
        # "SFF1" também conta: um ritmo SFF1 de verdade (formato mais antigo,
        # CASM em Ctab) já TEM identidade e os próprios SysEx de abertura -
        # plantar um preâmbulo SFF2 por cima dele (bug achado no
        # FreiG-EuSegu.STY, de outro programador, quando o Michel criou uma
        # Intro A nele) deixava o arquivo com os dois marcadores, o
        # preâmbulo duplicado, e o marcador SFF2 afirmando um formato que os
        # registros Ctab não têm.
        tem_identidade_sff2 = any(m.type == 'marker' and getattr(m, 'text', '') in ('SFF1', 'SFF2') for m in self.merged_track_cache)

        if ponto_insercao is None:
            # Não existe nenhuma seção antes dela ainda - entra logo depois da
            # área de configuração inicial do arquivo.
            primeiro_marker_tick = None
            temp_abs = 0
            for m in self.merged_track_cache:
                temp_abs += m.time
                if m.type in ['marker', 'cuepoint'] and getattr(m, 'text', '') not in ['SFF1', 'SFF2', 'SInt']:
                    primeiro_marker_tick = temp_abs
                    break
            if primeiro_marker_tick is None:
                # De verdade a primeiríssima seção que este arquivo já teve -
                # sem isso, o marcador nascia bem no tick 0, sem espaço
                # nenhum sobrando ANTES dele pra Área de Configuração
                # (Banco/Patch de todo canal, Drum Setup, etc - tudo isso
                # tem que vir antes do primeiro marcador de seção). Com tudo
                # espremido no mesmo tick 0 do próprio marcador, a ordem
                # dentro desse instante único vira uma loteria (decidida só
                # pelo tipo de mensagem, não pela ordem real que faz
                # sentido) - também contribuía pro SX recusar o arquivo.
                # Reserva um compasso inteiro de respiro antes do primeiro
                # marcador, do mesmo jeito que todo arquivo genuíno da
                # Yamaha sempre tem.
                primeiro_marker_tick = tpm
            ponto_insercao = primeiro_marker_tick

        deslocamento = num_measures * tpm
        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            # Uma âncora "SInt" plantada por uma criação/redimensionamento
            # anterior (ver mais abaixo) não é conteúdo de verdade - carregar
            # ela pra frente só ia deixá-la sobrando no meio do arquivo,
            # inflando "fim do arquivo" pra além do que essa seção declara
            # de verdade. Uma âncora nova e correta entra no lugar certo,
            # abaixo.
            if curr_t >= ponto_insercao and msg.type in ('marker', 'cuepoint') and getattr(msg, 'text', '') == 'SInt':
                continue
            if curr_t >= ponto_insercao:
                abs_msgs.append((curr_t + deslocamento, msg))
            else:
                abs_msgs.append((curr_t, msg))

        abs_msgs.append((ponto_insercao, mido.MetaMessage('marker', text=nome_secao)))
        abs_msgs.append((ponto_insercao, mido.MetaMessage('text', text=f'fn:{nome_secao}\x00')))

        # Figura de compasso desta seção (numerador/denominador) - só grava
        # de verdade se for diferente do que já estaria em vigor ali (senão
        # fica um 'time_signature' redundante toda vez que alguém cria uma
        # seção nova sem nunca ter mexido nisso).
        if numerador is not None and denominador is not None:
            num_vigente, den_vigente = self.obter_compasso_da_secao(self.merged_track_cache, ponto_insercao)
            if (numerador, denominador) != (num_vigente, den_vigente):
                abs_msgs.append((ponto_insercao, mido.MetaMessage('time_signature', numerator=numerador, denominator=denominador, time=0)))

        # Âncora do fim de verdade da seção: se esta for a última coisa do
        # arquivo (nada depois dela ainda), a duração total do arquivo
        # (soma dos deltas) ia ficar do tamanho de onde está o último
        # evento real - se a seção nascer vazia ou com notas só no comecinho,
        # "fim do arquivo" ficava bem menor que os compassos declarados, e
        # o Play/Gravação loopava de volta antes do fim de verdade. Um
        # marcador inerte "SInt" (já ignorado como fronteira de seção em
        # todo o programa) garante que a duração nunca fique curta.
        abs_msgs.append((ponto_insercao + deslocamento, mido.MetaMessage('marker', text='SInt')))

        self.rebuild_from_abs_list(abs_msgs)

        if not tem_identidade_sff2:
            # Planta a identidade "SFF2" - marcador SFF2, os 4 SysEx
            # desconhecidos que aparecem em todo arquivo real de estilo já
            # analisado, marcador SInt, e o reset GM/XG - exatamente na
            # mesma ordem literal que "Novo Estilo" já usa (comparado com
            # arquivos genuínos da Yamaha). Feito à parte do resto acima
            # (não misturado no abs_msgs/sort) porque o sort por tipo de
            # mensagem embaralharia essa ordem específica - aqui é um
            # PREPEND literal na frente de tudo, tick 0, sem depender de
            # prioridade nenhuma. Sem essa identidade, o SX600 recusa o
            # arquivo ("erro ao carregar os dados") mesmo com tudo mais
            # certo, porque nem reconhece o arquivo como um Estilo.
            preambulo = [
                mido.MetaMessage('marker', text='SFF2', time=0),
                mido.Message('sysex', data=(0x43, 0x76, 0x1A, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01), time=0),
                mido.Message('sysex', data=(0x43, 0x73, 0x39, 0x11, 0x00, 0x46, 0x00), time=0),
                mido.Message('sysex', data=(0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00), time=0),
                mido.Message('sysex', data=(0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00), time=0),
                mido.MetaMessage('marker', text='SInt', time=0),
                mido.Message('sysex', data=(0x7E, 0x7F, 0x09, 0x01), time=0),
                mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00), time=0),
            ]
            self.merged_track_cache = preambulo + self.merged_track_cache
            self.rebuild_sections_from_cache()

    def apply_section_resize(self, section, orig_measures, new_measures, tpm_orig, tpm_novo=None, novo_num=None, novo_den=None):
        if tpm_novo is None: tpm_novo = tpm_orig
        self.save_state("Redimensionamento de Seção")
        start_tick = section['start']
        end_tick = section['end']
        if end_tick == float('inf'): end_tick = sum(m.time for m in self.merged_track_cache)
        abs_msgs = []
        curr_time = 0
        for msg in self.merged_track_cache:
            curr_time += msg.time
            abs_msgs.append((curr_time, msg))
        new_ticks = new_measures * tpm_novo
        tick_diff = new_ticks - (end_tick - start_tick)
        new_abs_msgs = []
        for t, msg in abs_msgs:
            if t == start_tick and msg.type == 'time_signature':
                # A figura antiga desta seção sai - a nova (se houver) entra
                # mais abaixo, sem duplicar.
                continue
            if t < start_tick:
                new_abs_msgs.append((t, msg))
            elif start_tick <= t < end_tick:
                if t < start_tick + new_ticks:
                    new_abs_msgs.append((t, msg))
            else:
                # Uma âncora "SInt" plantada por um redimensionamento
                # ANTERIOR DESTA MESMA SEÇÃO (só faz sentido existir bem
                # em cima do fim antigo dela, end_tick - é o único lugar
                # onde uma seção que termina nela mesma, sem nada depois,
                # planta a própria âncora) não é conteúdo de verdade -
                # carregar ela pra frente deixava sobra no meio do
                # arquivo. Uma âncora nova e correta entra no lugar certo,
                # depois deste laço. CUIDADO: checar só "é um SInt" (sem
                # exigir t == end_tick) descartava TAMBÉM a âncora de
                # fim de arquivo de uma seção POSTERIOR de verdade (ex.:
                # redimensionar Main C engolia a âncora do fim do Main D)
                # - o "fim do arquivo" encolhia até o próximo evento real,
                # e a seção seguinte podia ficar com 0 ticks de duração
                # (nem dava pra redimensioná-la de novo, ZeroDivisionError
                # em orig_measures) ou ganhar sobras de compasso que não
                # deveriam estar ali.
                if t == end_tick and msg.type in ('marker', 'cuepoint') and getattr(msg, 'text', '') == 'SInt':
                    continue
                new_abs_msgs.append((t + tick_diff, msg))
        # Só duplica compasso por compasso pra crescer quando a figura NÃO
        # mudou - se mudou (ex.: 4/4 -> 6/8), os compassos antigos não têm o
        # mesmo tamanho dos novos, repetir do jeito de sempre bagunçaria
        # tudo; o trecho novo entra em silêncio, pronto pra compor do zero.
        if new_measures > orig_measures and tpm_novo == tpm_orig:
            for m_idx in range(orig_measures, new_measures):
                src_m_idx = m_idx % orig_measures
                src_start = start_tick + src_m_idx * tpm_orig
                src_end = src_start + tpm_orig
                for t, msg in abs_msgs:
                    if src_start <= t < src_end and getattr(msg, 'type', '') not in ['marker', 'cuepoint']:
                        new_t = t + (m_idx - src_m_idx) * tpm_orig
                        new_abs_msgs.append((new_t, msg.copy()))
        if novo_num is not None and novo_den is not None:
            num_vigente, den_vigente = self.obter_compasso_da_secao(self.merged_track_cache, start_tick)
            if (novo_num, novo_den) != (num_vigente, den_vigente):
                import mido
                new_abs_msgs.append((start_tick, mido.MetaMessage('time_signature', numerator=novo_num, denominator=novo_den, time=0)))

        # Âncora do fim de verdade da seção redimensionada: se ela for a
        # última coisa do arquivo, a duração total (soma dos deltas) ia
        # ficar do tamanho de onde está o último evento real, não do
        # tamanho declarado nos compassos - se sobrar silêncio no fim
        # (compassos novos em branco, ou poucas notas gravadas), Play e
        # Gravação loopavam de volta ANTES do fim de verdade da seção
        # (é o que fazia "gravar só no primeiro compasso" mesmo depois de
        # redimensionar pra 4). Um marcador inerte "SInt" (já ignorado como
        # fronteira de seção em todo o programa) garante que a duração
        # nunca fique curta - inofensivo se já existir conteúdo depois.
        import mido
        new_abs_msgs.append((start_tick + new_ticks, mido.MetaMessage('marker', text='SInt')))

        # Empate no mesmo tick precisa da MESMA prioridade usada em todo
        # lugar (_msg_priority) - senão um "sort" só por tick (estável)
        # preserva a ordem de inserção da lista, e a âncora SInt nova
        # (sempre a ÚLTIMA coisa anexada, linha acima) ficava DEPOIS do
        # end_of_track pré-existente que atravessou o laço principal -
        # deixando o end_of_track fisicamente não-último na trilha, e
        # isso fazia _ultima_secao_ja_travada() achar "não travado" a
        # cada reabertura (não-idempotente).
        new_abs_msgs.sort(key=lambda x: (x[0], self._msg_priority(x[1])))
        self.merged_track_cache = []
        last_t = 0
        for t, msg in new_abs_msgs:
            msg.time = t - last_t
            self.merged_track_cache.append(msg)
            last_t = t
        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_sections_from_cache()

    def verificar_e_corrigir_alinhamento_compassos(self, event=None):
        # Pedido do Michel depois de achar (e corrigirmos manualmente) uma
        # seção com uma "sobra torta" (Main C do Country MHS.sty, com uma
        # fração de compasso a mais - sobra de um bug antigo de
        # redimensionamento já corrigido nesta sessão, ver apply_section_
        # resize) - "o programa não é capaz de fazer este auto ajuste
        # quando houvesse este desajuste?". Sim: esta ferramenta varre
        # TODAS as seções do arquivo, acha qualquer uma cuja duração não
        # seja um múltiplo EXATO do tamanho do compasso dela, e corrige
        # cada uma com a mesma técnica usada manualmente (redimensionar
        # pra compassos+1 e depois de volta - trunca a sobra exatamente na
        # cabeça do compasso certa, sem mexer no conteúdo de verdade).
        from MHS_Utils import falar
        if not self.current_midi_data:
            falar("Abra um estilo antes de verificar o alinhamento dos compassos.", imediato=True)
            return

        tpq = self.current_midi_data.ticks_per_beat
        fim_arquivo = sum(m.time for m in self.merged_track_cache)
        desalinhadas = []
        for s in self.sections_info:
            if not s.get('present', False) or s.get('start') is None:
                continue
            fim = fim_arquivo if s['end'] == float('inf') else s['end']
            num, den = self.obter_compasso_da_secao(self.merged_track_cache, s['start'])
            tpm = self.ticks_por_compasso(tpq, num, den)
            dur = fim - s['start']
            if tpm <= 0:
                continue
            resto = dur % tpm
            if resto != 0:
                compassos_exatos = dur / tpm
                desalinhadas.append((s['name'], dur, tpm, resto, compassos_exatos))

        if not desalinhadas:
            falar("Nenhuma seção fora de alinhamento encontrada - todas têm um número exato de compassos.", imediato=True)
            return

        linhas = "\n".join(
            f"- {nome}: {dur} ticks = {compassos:.4f} compassos (sobra de {resto} ticks)"
            for nome, dur, tpm, resto, compassos in desalinhadas
        )
        resposta = wx.MessageBox(
            f"{len(desalinhadas)} seção(ões) com uma sobra fora da cabeça do compasso:\n\n"
            f"{linhas}\n\n"
            "Cada uma será realinhada pro número de compassos mais próximo (a sobra é "
            "descartada, o conteúdo de verdade dentro dos compassos completos não muda). "
            "Um backup automático é criado antes, ao lado do arquivo.\n\n"
            "Corrigir agora?",
            "Corrigir Alinhamento de Compassos", wx.YES_NO | wx.ICON_QUESTION)
        if resposta != wx.YES:
            return

        if self.current_file_path:
            import shutil
            import datetime
            base, ext = os.path.splitext(self.current_file_path)
            carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_backup = f"{base} (backup antes do alinhamento de compassos - {carimbo}){ext}"
            shutil.copy2(self.current_file_path, caminho_backup)

        self.save_state("Corrigir Alinhamento de Compassos")

        for nome_secao, dur, tpm, resto, compassos_exatos in desalinhadas:
            secoes_por_nome = {s['name']: s for s in self.sections_info if s.get('present')}
            s = secoes_por_nome[nome_secao]
            start_tick = s['start']
            end_tick = s['end']
            if end_tick == float('inf'):
                end_tick = sum(m.time for m in self.merged_track_cache)
            num_atual, den_atual = self.obter_compasso_da_secao(self.merged_track_cache, start_tick)
            tpm_atual = self.ticks_por_compasso(tpq, num_atual, den_atual)
            current_measures = int(round((end_tick - start_tick) / tpm_atual))
            if current_measures <= 0:
                current_measures = 1
            # Redimensiona pra +1 (força o resize de verdade mesmo se
            # current_measures já for o valor "arredondado" mostrado) e
            # depois de volta - a 2ª chamada trunca exatamente na cabeça
            # do compasso certa, descartando a sobra.
            self.apply_section_resize(s, current_measures, current_measures + 1, tpm_atual, tpm_atual, num_atual, den_atual)
            secoes_por_nome2 = {sx['name']: sx for sx in self.sections_info if sx.get('present')}
            s2 = secoes_por_nome2[nome_secao]
            self.apply_section_resize(s2, current_measures + 1, current_measures, tpm_atual, tpm_atual, num_atual, den_atual)

        if self.current_file_path:
            self.salvar_arquivo_sty(self.current_file_path)
            fim_msg = "Arquivo salvo - backup do original guardado ao lado, com a data e hora no nome."
        else:
            self.dirty = True
            fim_msg = "Salve o arquivo (Ctrl+S) pra gravar a correção em disco."
        self.atualizar_titulo()
        falar(f"{len(desalinhadas)} seção(ões) realinhada(s): {', '.join(n for n, *_ in desalinhadas)}. "
              f"{fim_msg}",
              imediato=True)

    def _normalizar_ordem_mensagens_se_precisar(self):
        # A ordem de mensagens EMPATADAS no mesmo tick, pra quem já
        # existia no arquivo, é preservada tal como estava - salvar_
        # arquivo_sty nunca reordena o que já existia, só o que ELE
        # MESMO insere de novo (ver comentário "ORDEM ORIGINAL É
        # SAGRADA" dentro dela). Se em algum momento anterior (uma
        # edição, um resize) essa ordem ficou errada - por exemplo, o
        # marcador inerte "SInt" do cabeçalho ficando ANTES do bloco de
        # SysEx de configuração inicial, em vez de depois (ver
        # comentário em _msg_priority) - ela fica errada pra sempre,
        # silenciosamente, até algo forçar uma reordenação de verdade
        # (do_copy/do_delete/apply_section_resize, que já usam _msg_
        # priority corretamente). Roda uma vez, silenciosamente, ao
        # abrir QUALQUER arquivo - só reordena mensagens EMPATADAS no
        # mesmo tick (nunca muda tick nenhum, nunca adiciona/remove
        # nada), então é seguro fazer sempre, sem perguntar. Devolve
        # True só se a ordem de alguma coisa realmente mudou.
        if not self.merged_track_cache:
            return False
        ordem_antes = [id(m) for m in self.merged_track_cache]
        abs_list = []
        t = 0
        for msg in self.merged_track_cache:
            t += msg.time
            abs_list.append([t, msg])
        novo = self._abs_list_para_delta_track(abs_list)
        if [id(m) for m in novo] == ordem_antes:
            return False
        self.merged_track_cache = novo
        return True

    def _remover_identidade_sff2_duplicada_se_precisar(self):
        # Conserta um estrago de versões antigas: criar uma seção nova num
        # ritmo que já era SFF1 (formato mais antigo, CASM em Ctab) plantava
        # POR CIMA dele um preâmbulo "SFF2" completo (marcador SFF2 + os 6
        # SysEx de abertura + SInt) - o arquivo ficava com os dois marcadores
        # (SFF2 e SFF1), tudo duplicado no tick 0, e um marcador SFF2
        # afirmando um formato que os registros Ctab não têm. Só age quando o
        # arquivo tem os DOIS marcadores E o CASM é só Ctab (SFF1 de
        # verdade): tira o marcador SFF2 e as cópias repetidas do preâmbulo
        # no tick 0 (mantém uma de cada). Devolve True só se mudou algo.
        cache = self.merged_track_cache
        if not cache:
            return False
        textos = {getattr(m, 'text', '') for m in cache if m.type == 'marker'}
        if 'SFF1' not in textos or 'SFF2' not in textos:
            return False
        raw = getattr(self, 'raw_casm_data', b'') or b''
        if b'Ctab' not in raw or b'Ctb2' in raw:
            return False
        preambulo = {
            (0x43, 0x76, 0x1A, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01),
            (0x43, 0x73, 0x39, 0x11, 0x00, 0x46, 0x00),
            (0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
            (0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
            (0x7E, 0x7F, 0x09, 0x01),
            (0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00),
        }
        vistos = set()
        mudou = False
        abs_list = []
        t = 0
        for msg in cache:
            t += msg.time
            if msg.type == 'marker' and getattr(msg, 'text', '') == 'SFF2':
                mudou = True
                continue
            if t == 0:
                chave = None
                if msg.type == 'sysex' and tuple(msg.data) in preambulo:
                    chave = ('sysex', tuple(msg.data))
                elif msg.type == 'marker' and getattr(msg, 'text', '') == 'SInt':
                    chave = ('sint',)
                if chave is not None:
                    if chave in vistos:
                        mudou = True
                        continue
                    vistos.add(chave)
            abs_list.append([t, msg])
        if not mudou:
            return False
        self.merged_track_cache = self._abs_list_para_delta_track(abs_list)
        return True

    def _remover_sint_redundante_se_precisar(self):
        # Uma âncora "SInt" que caiu EXATAMENTE no mesmo tick de um
        # marcador de seção DE VERDADE (ex.: sobra de um redimensionamento
        # antigo de "Ending A", cujo fim é o mesmo tick que o início de
        # "Fill In BA") é 100% redundante - a seção já tem seu próprio
        # marcador real ali, não precisa de âncora nenhuma. Sobrando, ela
        # fica intercalada entre o marcador real e a rajada de reset
        # (Bank/Patch/CC) que toda seção nova manda logo em seguida -
        # mesma classe de "marcador solto bagunçando a ordem" que já
        # causou um efeito colateral real no SX600 (ver _msg_priority) -
        # então, por segurança, remove qualquer SInt assim que coincidir
        # com um marcador de seção de verdade. Não mexe no SInt do
        # cabeçalho (tick 0, antes de qualquer seção) nem no que trava a
        # duração da última seção (num tick que NÃO tem marcador de
        # verdade nenhum - esses continuam exatamente onde estão).
        if not self.merged_track_cache:
            return False
        t = 0
        ticks_com_marcador_real = set()
        for msg in self.merged_track_cache:
            t += msg.time
            if (msg.type in ('marker', 'cuepoint')
                    and getattr(msg, 'text', '') not in ('SFF1', 'SFF2', 'SInt')):
                ticks_com_marcador_real.add(t)
        if not ticks_com_marcador_real:
            return False

        abs_list = []
        t = 0
        mudou = False
        for msg in self.merged_track_cache:
            t += msg.time
            if (msg.type in ('marker', 'cuepoint') and getattr(msg, 'text', '') == 'SInt'
                    and t in ticks_com_marcador_real):
                mudou = True
                continue
            abs_list.append([t, msg])
        if not mudou:
            return False
        self.merged_track_cache = self._abs_list_para_delta_track(abs_list)
        return True

    def _ultima_secao_ja_travada(self):
        # A última seção FÍSICA do arquivo (nunca fixo num nome - Fill In
        # BA, Fill In DD, Intro A sozinha como um "solo" antes da música
        # começar, o que for - cada ritmo é montado numa ordem diferente)
        # está travada quando a ÚLTIMA mensagem do arquivo inteiro é um
        # marcador "SInt" - a mesma âncora inerte que criar_secao_nova/
        # apply_section_resize já plantam pra garantir que uma seção não
        # fique mais curta que o declarado. Sendo a ÚLTIMA mensagem de
        # todas, ela também define sozinha onde "sum(m.time for m in
        # merged_track_cache)" (usado em todo lugar como "fim do arquivo"
        # pra quem não tem seção seguinte) para - travando a duração pra
        # sempre, imune a qualquer edição em outro lugar do arquivo.
        # Ignora um "end_of_track" que eventualmente sobre logo depois da
        # âncora (mido sempre trata isso como um marcador de fim de
        # trilha, não conteúdo de verdade - pode acabar reordenado pro
        # mesmo tick da âncora num save/reload) - o que importa é que a
        # ÚLTIMA coisa "de verdade" seja o SInt.
        #
        # Checagem por TICK (não por posição na lista): se a última nota
        # da seção termina EXATAMENTE no mesmo tick onde a âncora foi
        # plantada (comum - o SInt marca o fim, e o note_off que fecha a
        # última nota sustentada também cai ali), _msg_priority ordena o
        # SInt (1.5) ANTES desse note_off (5) no mesmo tick - então o
        # SInt nunca é o ÚLTIMO item da lista, mesmo já estando plantado
        # corretamente. Por posição, isso fazia a checagem achar "não
        # travado" e plantar uma 2ª âncora a cada reabertura (não-
        # idempotente). Certo é achar o tick MÁXIMO entre todo o conteúdo
        # de verdade (ignorando end_of_track) e conferir se existe um
        # SInt ali - não importa a ordem relativa a outras mensagens do
        # mesmo tick.
        t = 0
        fim = -1
        tem_conteudo = False
        for msg in self.merged_track_cache:
            t += msg.time
            if msg.type == 'end_of_track':
                continue
            tem_conteudo = True
            if t > fim:
                fim = t
        if not tem_conteudo:
            return False
        t = 0
        for msg in self.merged_track_cache:
            t += msg.time
            if msg.type == 'end_of_track':
                continue
            if t == fim and msg.type in ('marker', 'cuepoint') and getattr(msg, 'text', '') == 'SInt':
                return True
        return False

    def _travar_secao_final_se_precisar(self):
        # Descobre qual seção é FISICAMENTE A ÚLTIMA no arquivo agora (por
        # ordem de tick, não por nome) e planta a âncora "SInt" logo
        # depois dela, se ainda não tiver uma - trava a duração dela pra
        # sempre. Chamado tanto pela ferramenta manual (Ferramentas ->
        # Verificar e Corrigir Notas Cruzando Seções) quanto AUTOMATICAMENTE
        # toda vez que um arquivo é aberto (ver abrir_caminho_em_nova_aba) -
        # pedido do Michel pra não depender de rodar a ferramenta na mão:
        # "o programa tem que ter a inteligência de deixar tudo cravadinho
        # certinho" assim que o ritmo é carregado, seja lá qual for a
        # seção que termina a linha do tempo dele. Devolve True se mexeu
        # em alguma coisa (pra quem chama decidir se marca dirty/avisa).
        if self._ultima_secao_ja_travada():
            return False
        secoes_fisicas = self._secoes_de_track(self.merged_track_cache)
        if not secoes_fisicas:
            return False
        ultima = secoes_fisicas[-1]
        tpq = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
        num_u, den_u = self.obter_compasso_da_secao(self.merged_track_cache, ultima['start'])
        tpm_u = self.ticks_por_compasso(tpq, num_u, den_u)
        if tpm_u <= 0:
            return False
        fim_arquivo = sum(m.time for m in self.merged_track_cache)
        dur_u = fim_arquivo - ultima['start']
        compassos_u = max(1, int(round(dur_u / tpm_u)))

        secoes_por_nome = {s['name']: s for s in self.sections_info if s.get('present')}
        s = secoes_por_nome.get(ultima['name'])
        if s is None:
            return False
        self.apply_section_resize(s, compassos_u, compassos_u + 1, tpm_u, tpm_u, num_u, den_u)
        secoes_por_nome2 = {sx['name']: sx for sx in self.sections_info if sx.get('present')}
        s2 = secoes_por_nome2.get(ultima['name'])
        if s2 is None:
            return False
        self.apply_section_resize(s2, compassos_u + 1, compassos_u, tpm_u, tpm_u, num_u, den_u)
        return True

    def verificar_e_corrigir_notas_cruzando_secoes(self, event=None):
        # Pedido do Michel, depois de achar (com a gente) que o Fill In BA
        # (a última seção do arquivo) ficava crescendo sozinho a cada
        # edição em QUALQUER outro lugar do arquivo - inclusive só de
        # apagar 2 notas na Intro B. Causa raiz, em duas partes:
        #
        # 1) A ÚLTIMA seção física do arquivo (não necessariamente "Fill
        # In BA" - cada ritmo é montado numa ordem diferente, pode ser
        # Fill In DD, Intro C, o que for) não tem uma seção seguinte pra
        # marcar onde ela termina - o programa calcula o fim dela como
        # "onde o arquivo inteiro termina", sem nenhuma âncora fixa.
        # Qualquer variação no tamanho total do arquivo (mesmo vindo de
        # uma edição em outro lugar) "vaza" pro cálculo da duração dela.
        #
        # 2) Uma nota cujo desligamento só acontece no "reset" de acorde
        # que pertence à seção SEGUINTE (mesmo tick = fim desta seção =
        # início da próxima) tecnicamente "pertence" à seção onde ela
        # começou a tocar, mas o desligamento mora fisicamente na seção
        # de depois - isso já exigiu proteções específicas em várias
        # funções (Copiar/Apagar). Em vez de continuar caçando função por
        # função, esta ferramenta corrige o DADO na raiz: acha toda nota
        # assim e move o desligamento pra dentro da própria seção a que
        # ela pertence - depois disso, a ambiguidade de fronteira some de
        # vez, sem precisar de tratamento especial em mais nenhum lugar.
        #
        # A ferramenta ataca os dois problemas de uma vez: acha e corrige
        # toda nota "cruzando" uma fronteira de seção, e trava a duração
        # da seção que for FISICAMENTE A ÚLTIMA do arquivo (descoberta
        # dinamicamente a cada vez, nunca fixa num nome).
        from MHS_Utils import falar, rotulo_canal
        from collections import defaultdict, deque
        if not self.current_midi_data:
            falar("Abra um estilo antes de verificar.", imediato=True)
            return

        secoes_fisicas = self._secoes_de_track(self.merged_track_cache)
        if not secoes_fisicas:
            falar("Nenhuma seção encontrada no arquivo.", imediato=True)
            return

        fim_arquivo = sum(m.time for m in self.merged_track_cache)
        for s in secoes_fisicas:
            if s['end'] == float('inf'):
                s['end'] = fim_arquivo

        def secao_de_tick(tick):
            for i, s in enumerate(secoes_fisicas):
                if s['start'] <= tick < s['end']:
                    return i
            if tick >= secoes_fisicas[-1]['start']:
                return len(secoes_fisicas) - 1
            return None

        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            abs_msgs.append([curr_t, msg])

        fila = defaultdict(deque)
        cruzando = []
        for idx_msg, (t, msg) in enumerate(abs_msgs):
            if msg.is_meta or msg.type not in ('note_on', 'note_off'):
                continue
            ch = getattr(msg, 'channel', -1)
            key = (ch, msg.note)
            if msg.type == 'note_on' and msg.velocity > 0:
                fila[key].append((t, secao_de_tick(t)))
            else:
                if fila[key]:
                    on_tick, idx_sec_on = fila[key].popleft()
                    idx_sec_off = secao_de_tick(t)
                    if idx_sec_on is not None and idx_sec_off is not None and idx_sec_off != idx_sec_on:
                        cruzando.append({
                            'channel': ch, 'note': msg.note,
                            'idx_sec_on': idx_sec_on, 'idx_msg_off': idx_msg,
                            'on_tick': on_tick, 'off_tick_atual': t,
                        })

        ultima = secoes_fisicas[-1]
        tpq = self.current_midi_data.ticks_per_beat
        num_u, den_u = self.obter_compasso_da_secao(self.merged_track_cache, ultima['start'])
        tpm_u = self.ticks_por_compasso(tpq, num_u, den_u)
        precisa_ancora = not self._ultima_secao_ja_travada()

        if not cruzando and not precisa_ancora:
            falar("Nenhum problema encontrado: nenhuma nota cruzando seções, e a "
                  "duração da última seção já está travada.", imediato=True)
            return

        linhas = []
        for c in cruzando[:30]:
            nome_canal = rotulo_canal(c['channel'])
            sec_dona = secoes_fisicas[c['idx_sec_on']]['name']
            idx_off_atual = secao_de_tick(c['off_tick_atual'])
            sec_off_atual = secoes_fisicas[idx_off_atual]['name'] if idx_off_atual is not None else "?"
            linhas.append(f"- {nome_canal}, nota {c['note']}: começa na {sec_dona}, "
                           f"mas o desligamento está na {sec_off_atual}")
        texto_cruzando = "\n".join(linhas)
        if len(cruzando) > 30:
            texto_cruzando += f"\n... e mais {len(cruzando) - 30}."

        partes_msg = []
        if cruzando:
            partes_msg.append(
                f"{len(cruzando)} nota(s) com o desligamento caindo numa seção diferente "
                f"de onde começam:\n\n{texto_cruzando}\n\nCada uma será movida pra terminar "
                f"dentro da própria seção a que pertence.")
        if precisa_ancora:
            compassos_estimados = max(1, round((ultima['end'] - ultima['start']) / tpm_u)) if tpm_u > 0 else 1
            partes_msg.append(
                f"A última seção do arquivo ('{ultima['name']}') não tem uma duração travada "
                f"- qualquer edição em outro lugar do arquivo pode fazer ela crescer ou "
                f"encolher sozinha. Será travada em {compassos_estimados} compasso(s).")

        resposta = wx.MessageBox(
            "\n\n".join(partes_msg) + "\n\nUm backup automático é criado antes. Corrigir agora?",
            "Verificar Notas Cruzando Seções", wx.YES_NO | wx.ICON_QUESTION)
        if resposta != wx.YES:
            return

        if self.current_file_path:
            import shutil
            import datetime
            base, ext = os.path.splitext(self.current_file_path)
            carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_backup = f"{base} (backup antes de corrigir notas cruzando secoes - {carimbo}){ext}"
            shutil.copy2(self.current_file_path, caminho_backup)

        self.save_state("Corrigir Notas Cruzando Seções")

        for c in cruzando:
            sec_dona = secoes_fisicas[c['idx_sec_on']]
            novo_off = max(c['on_tick'] + 1, sec_dona['end'] - 2)
            abs_msgs[c['idx_msg_off']][0] = novo_off

        self.merged_track_cache = self._abs_list_para_delta_track(abs_msgs)
        self.rebuild_sections_from_cache()

        if precisa_ancora:
            self._travar_secao_final_se_precisar()

        if self.current_file_path:
            self.salvar_arquivo_sty(self.current_file_path)
            fim_msg = "Arquivo salvo - backup do original guardado ao lado, com a data e hora no nome."
        else:
            self.dirty = True
            fim_msg = "Salve o arquivo (Ctrl+S) pra gravar a correção em disco."
        self.atualizar_titulo()
        resumo = []
        if cruzando: resumo.append(f"{len(cruzando)} nota(s) realinhada(s)")
        if precisa_ancora: resumo.append("duração da última seção travada")
        falar(f"{' e '.join(resumo)}. {fim_msg}", imediato=True)

    def _contar_lsb(self, mensagens):
        # Conta, pra uma lista de mensagens mido (uma trilha, várias, ou o
        # merged_track_cache), quantas vezes cada valor de Bank Select LSB
        # (CC 32) aparece, e em quais canais - usado tanto pelo ritmo atual
        # quanto pelo scaneamento em massa (ver alterar_lsb_*).
        from MHS_Utils import CC_BANK_LSB
        from collections import Counter, defaultdict
        contagem = Counter()
        canais_por_lsb = defaultdict(set)
        for msg in mensagens:
            if msg.type == 'control_change' and msg.control == CC_BANK_LSB:
                contagem[msg.value] += 1
                canais_por_lsb[msg.value].add(getattr(msg, 'channel', -1))
        return contagem, canais_por_lsb

    def alterar_lsb_ritmo_atual(self, event=None):
        # Pedido do Michel: ritmos de pacotes de expansão de programadores
        # diferentes às vezes usam o MESMO LSB (Bank Select) sem querer -
        # ele já teve que ABANDONAR um pacote inteiro por causa disso. Esta
        # ferramenta mostra os LSBs que o estilo ABERTO está usando agora
        # (e em quais canais) e deixa trocar - só um LSB de origem
        # específico, ou todas as ocorrências de uma vez (a escolha é do
        # usuário, ver AlterarLSBDialog - confirmado com ele que
        # programadores diferentes podem misturar LSBs no MESMO arquivo,
        # então trocar tudo cegamente seria arriscado como padrão único).
        from MHS_Utils import falar, rotulo_canal, CC_BANK_LSB
        if not self.current_midi_data:
            falar("Abra um estilo antes de alterar o LSB.", imediato=True)
            return
        contagem, canais_por_lsb = self._contar_lsb(self.merged_track_cache)
        if not contagem:
            falar("Este estilo não tem nenhum Bank Select LSB configurado.", imediato=True)
            return
        linhas = []
        for lsb, n in sorted(contagem.items(), key=lambda x: -x[1]):
            canais_nome = ", ".join(rotulo_canal(c) for c in sorted(canais_por_lsb[lsb]) if 0 <= c <= 15)
            linhas.append(f"LSB {lsb:03d}: {n} ocorrência(s) - canais: {canais_nome}")
        texto_relatorio = "\n".join(linhas)
        lsb_mais_comum = max(contagem.items(), key=lambda x: x[1])[0]

        dlg = AlterarLSBDialog(self, "Alterar LSB do Ritmo Atual", texto_relatorio, lsb_mais_comum)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        lsb_destino, lsb_origem = dlg.get_valores()
        dlg.Destroy()

        self.save_state("Alterar LSB")
        alterados = 0
        for msg in self.merged_track_cache:
            if msg.type == 'control_change' and msg.control == CC_BANK_LSB:
                if lsb_origem is None or msg.value == lsb_origem:
                    if msg.value != lsb_destino:
                        msg.value = lsb_destino
                        alterados += 1
                        ch = getattr(msg, 'channel', -1)
                        if 0 <= ch <= 15:
                            c = self.canais[ch]
                            c["Bank"] = (c["Bank"] // 128) * 128 + lsb_destino
        if alterados == 0:
            self.undo_stack.pop()
            falar("Nada foi alterado - nenhuma ocorrência do LSB escolhido.", imediato=True)
            return
        self.dirty = True
        self.atualizar_titulo()
        self.update_mixer_list()
        falar(f"{alterados} ocorrência(s) alterada(s) para o LSB {lsb_destino:03d}. "
              f"Salve o arquivo (Ctrl+S) pra gravar.", imediato=True)

    def _ler_casm_bruto_do_arquivo(self, path):
        with open(path, 'rb') as f:
            raw = f.read()
        idx = raw.find(b'CASM')
        return raw[idx:] if idx != -1 else b''

    def alterar_lsb_ritmos_em_massa(self, event=None):
        # Mesma ideia de alterar_lsb_ritmo_atual, só que pra vários arquivos
        # de uma vez, escolhidos direto na caixa de diálogo padrão do
        # Windows (multi-seleção - "escolho uma pasta... seleciono quantos
        # ritmos eu quiser", tudo na mesma tela nativa). Cada arquivo
        # alterado ganha um backup automático antes (mesma convenção usada
        # em qualquer ferramenta desta sessão que mexe em arquivo de verdade
        # fora da aba aberta) - e o CASM é preservado byte a byte (só o
        # valor do CC32 muda; nada de estrutura/CASM é tocado).
        from MHS_Utils import falar, CC_BANK_LSB
        import shutil
        import datetime

        dlg_arq = wx.FileDialog(
            self, "Escolha os ritmos para alterar o LSB", defaultDir=self.config.get("pasta_abrir") or self.config.get("last_open_dir", ""),
            wildcard="Estilos Yamaha (*.sty;*.prs;*.cte)|*.sty;*.prs;*.cte|Todos os arquivos (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_MULTIPLE)
        if dlg_arq.ShowModal() != wx.ID_OK:
            dlg_arq.Destroy()
            return
        caminhos = list(dlg_arq.GetPaths())
        dlg_arq.Destroy()
        if not caminhos:
            return

        falar(f"Escaneando {len(caminhos)} arquivo(s), aguarde...", imediato=True)
        wx.Yield()

        contagem_arquivos = {}  # lsb -> quantos ARQUIVOS têm pelo menos 1 ocorrência
        dados_por_arquivo = {}  # path -> mido.MidiFile já aberto (reaproveitado na aplicação)
        falhas = []
        for caminho in caminhos:
            try:
                mid = mido.MidiFile(caminho)
            except Exception:
                falhas.append(caminho)
                continue
            dados_por_arquivo[caminho] = mid
            lsbs_deste_arquivo = set()
            for track in mid.tracks:
                for msg in track:
                    if msg.type == 'control_change' and msg.control == CC_BANK_LSB:
                        lsbs_deste_arquivo.add(msg.value)
            for lsb in lsbs_deste_arquivo:
                contagem_arquivos[lsb] = contagem_arquivos.get(lsb, 0) + 1

        if not contagem_arquivos:
            falar("Nenhum dos arquivos escolhidos tem Bank Select LSB configurado.", imediato=True)
            return

        linhas = [f"LSB {lsb:03d}: {n} arquivo(s)" for lsb, n in sorted(contagem_arquivos.items(), key=lambda x: -x[1])]
        if falhas:
            linhas.append(f"\n{len(falhas)} arquivo(s) não puderam ser lidos e foram ignorados.")
        texto_relatorio = f"{len(caminhos)} arquivo(s) escolhidos.\n\n" + "\n".join(linhas)
        lsb_mais_comum = max(contagem_arquivos.items(), key=lambda x: x[1])[0]

        dlg = AlterarLSBDialog(self, "Alterar LSB de Ritmos em Massa", texto_relatorio, lsb_mais_comum)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        lsb_destino, lsb_origem = dlg.get_valores()
        dlg.Destroy()

        falar("Por favor, aguarde. Alterando os arquivos...", imediato=True)
        wx.Yield()

        arquivos_alterados = 0
        for caminho, mid in dados_por_arquivo.items():
            mudou = False
            for track in mid.tracks:
                for msg in track:
                    if msg.type == 'control_change' and msg.control == CC_BANK_LSB:
                        if (lsb_origem is None or msg.value == lsb_origem) and msg.value != lsb_destino:
                            msg.value = lsb_destino
                            mudou = True
            if not mudou:
                continue
            try:
                casm_bytes = self._ler_casm_bruto_do_arquivo(caminho)
                base, ext = os.path.splitext(caminho)
                carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                caminho_backup = f"{base} (backup antes de alterar LSB - {carimbo}){ext}"
                shutil.copy2(caminho, caminho_backup)
                mid.save(caminho)
                if casm_bytes:
                    with open(caminho, 'ab') as f:
                        f.write(casm_bytes)
                arquivos_alterados += 1
            except Exception:
                falhas.append(caminho)

        dlg_fim = wx.MessageDialog(
            self,
            f"{arquivos_alterados} arquivo(s) foram alterados para o LSB {lsb_destino:03d}."
            + (f"\n\n{len(falhas)} arquivo(s) não puderam ser processados." if falhas else ""),
            "Alteração de LSB em Massa Concluída", wx.OK | wx.ICON_INFORMATION)
        dlg_fim.SetOKLabel("&Concluir")
        dlg_fim.ShowModal()
        dlg_fim.Destroy()
        falar(f"{arquivos_alterados} arquivos alterados para o LSB {lsb_destino:03d}.", imediato=True)

    def mark_in(self, event):
        self.in_point = self.get_current_absolute_tick()
        falar("Entrada", imediato=True)

    def mark_out(self, event):
        self.out_point = self.get_current_absolute_tick()
        falar("Saída", imediato=True)
        
    def limpar_marcas(self, event):
        self.in_point = None
        self.out_point = None
        falar("Marcas limpas.", imediato=True)

    def abrir_fade(self, event):
        # Trazido do MHS MIDI Sequencer, a pedido do Michel - mesma tela,
        # mesma ideia: uma rampa de CC 11 (Expression) entre as marcas de
        # Entrada/Saída, nos canais selecionados (ou no canal atual, se
        # nenhum estiver marcado) - sem mexer no Volume principal (CC 7).
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de aplicar um Fade.", imediato=True)
            return
        if self.in_point is None or self.out_point is None:
            falar("Marque um trecho com Entrada (I) e Saída (O) antes de aplicar o Fade.", imediato=True)
            return
        foco_antes = wx.Window.FindFocus()
        dlg = FadeDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            tipo_fade, todos_canais = dlg.get_valores()
            # 0 = Fade In (0 ao máximo), 1 = Fade Out (máximo a 0)
            val_start = 0 if tipo_fade == 0 else 127
            val_end = 127 if tipo_fade == 0 else 0

            # Guarda a seleção de canais atual pra não bagunçar a tela -
            # "Master Fade" força os 16 canais só pra esta operação.
            selecao_backup = set(self.canais_selecionados)
            if todos_canais:
                self.canais_selecionados = set(range(16))

            self._aplicar_rampa_cc(11, val_start, val_end)

            self.canais_selecionados = selecao_backup
        dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def _aplicar_rampa_cc(self, cc_num, val_start, val_end):
        # Motor comum de rampa de CC - usado tanto pelo Fade In/Fade Out
        # (CC 11 fixo, ver abrir_fade) quanto pelo menu "Envelope de
        # Automação de CC" (aplicar_envelope_cc, id=151, Shift+E - CC e
        # valores escolhidos na tela EnvelopeCCDialog).
        # Mesmo algoritmo do MHS MIDI Sequencer (aplicar_envelope_cc lá),
        # adaptado pra trilha única mesclada do Style Creator - insere uma
        # rampa de eventos de Control Change entre as marcas de Entrada/
        # Saída (já em ticks absolutos aqui, sem precisar converter de/pra
        # segundos como no Sequencer), removendo primeiro qualquer evento
        # do MESMO CC/canal que já existisse dentro do trecho.
        from MHS_Utils import get_cc_name
        if self.in_point is None or self.out_point is None:
            falar("Marque um trecho com Entrada e Saída antes de aplicar a rampa.", imediato=True)
            return
        start_tick = min(self.in_point, self.out_point)
        end_tick = max(self.in_point, self.out_point)
        if end_tick <= start_tick:
            falar("Marcas de Entrada e Saída inválidas.", imediato=True)
            return

        alvos = self.canais_selecionados if getattr(self, 'canais_selecionados', None) else {self.canal_atual}

        self.save_state("Envelope de CC")
        tpq = getattr(self.current_midi_data, 'ticks_per_beat', 480)
        step_ticks = max(1, tpq // 8)

        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            if (msg.type == 'control_change' and msg.control == cc_num
                    and getattr(msg, 'channel', None) in alvos
                    and start_tick <= curr_t <= end_tick):
                continue
            abs_msgs.append((curr_t, msg))

        diff_val = val_end - val_start
        for ch in alvos:
            tick = start_tick
            while tick < end_tick:
                progresso = (tick - start_tick) / (end_tick - start_tick)
                valor = int(round(val_start + (diff_val * progresso)))
                abs_msgs.append((tick, mido.Message('control_change', channel=ch, control=cc_num, value=valor)))
                tick += step_ticks
            abs_msgs.append((end_tick, mido.Message('control_change', channel=ch, control=cc_num, value=val_end)))

        self.rebuild_from_abs_list(abs_msgs)
        falar(f"Rampa de {get_cc_name(cc_num)} criada de {val_start} para {val_end} em {len(alvos)} canal(is).", imediato=True)
        self.in_point = self.out_point = None

    def abrir_efeitos_midi(self, event):
        # Trazido do MHS MIDI Sequencer (lá é Ctrl+K): tela de Efeitos MIDI
        # Offline com as 3 abas - Arpejador, MIDI Delay e Harpa / Strum.
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de aplicar efeitos MIDI.", imediato=True)
            return
        if self.in_point is None or self.out_point is None:
            falar("Marque um trecho com Entrada (I) e Saída (O) antes de aplicar efeitos MIDI.", imediato=True)
            return
        self.save_state("Efeito MIDI")
        # Guarda quem tinha foco ANTES de abrir (Ctrl+K funciona de
        # qualquer lugar, não só com o channelList em foco) pra devolver o
        # foco pro mesmo lugar ao fechar - mesma lógica do Event List e do
        # Copiar Canal Entre Seções.
        foco_antes_efeitos_midi = wx.Window.FindFocus()
        dlg = MidiEffectsDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirty = True
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            falar("Efeito MIDI aplicado.", imediato=True)
        else:
            if self.undo_stack:
                self.undo_stack.pop()
            falar("Cancelado.", imediato=True)
        dlg.Destroy()
        def _restaurar_foco():
            if foco_antes_efeitos_midi:
                foco_antes_efeitos_midi.SetFocus()
            else:
                self.channelList.SetFocus()
        wx.CallLater(100, _restaurar_foco)

    def aplicar_efeito_midi(self, tipo_efeito, params, is_preview=False):
        # Motor dos Efeitos MIDI Offline - mesmo algoritmo do MHS MIDI
        # Sequencer, adaptado pra trilha única mesclada do Style Creator
        # (lá é uma varredura por trilha; aqui, uma varredura só). Opera no
        # trecho Entrada (I) / Saída (O), nos canais selecionados (ou no
        # canal atual). Arpejo e Harpa SUBSTITUEM as notas-alvo do trecho;
        # o Delay e o preset de Bateria MANTÊM as originais e SOBREPÕEM (o
        # Michel não queria que o desenho de bateria apagasse o que já
        # estava tocando por baixo - ele quer somar, não substituir).
        import random
        if self.in_point is None or self.out_point is None:
            return
        start_tick = min(self.in_point, self.out_point)
        end_tick = max(self.in_point, self.out_point)
        if end_tick <= start_tick:
            return

        alvos = self.canais_selecionados if getattr(self, 'canais_selecionados', None) else {self.canal_atual}
        if tipo_efeito == 'bateria_preset':
            # Preset de bateria é sempre um INSERT no canal em foco, nunca
            # nos outros canais que porventura estejam multi-selecionados -
            # diferente do Arpejo/Delay/Harpa, que respeitam a seleção.
            alvos = {self.canal_atual}
        tpb = max(1, getattr(self.current_midi_data, 'ticks_per_beat', 480))

        flat = []          # (tick, is_off, msg) - tudo que não é nota-alvo já consumida
        active_notes = {}
        notas_originais = []
        curr_t = 0
        ultimo_tick = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            ultimo_tick = curr_t
            ch = getattr(msg, 'channel', None)
            is_off = 0 if (msg.type == 'note_off' or (msg.type == 'note_on' and getattr(msg, 'velocity', 0) == 0)) else 1
            if ch in alvos and start_tick <= curr_t < end_tick and msg.type in ('note_on', 'note_off'):
                if msg.type == 'note_on' and msg.velocity > 0:
                    ev = {'start': curr_t, 'end': -1, 'ch': ch, 'msg_on': msg, 'msg_off': None}
                    active_notes[(ch, msg.note)] = ev
                    notas_originais.append(ev)
                    if tipo_efeito in ('delay', 'bateria_preset'):
                        flat.append((curr_t, is_off, msg))
                elif (ch, msg.note) in active_notes:
                    ev = active_notes.pop((ch, msg.note))
                    ev['end'] = curr_t
                    ev['msg_off'] = msg
                    if tipo_efeito in ('delay', 'bateria_preset'):
                        flat.append((curr_t, is_off, msg))
                else:
                    flat.append((curr_t, is_off, msg))
            else:
                flat.append((curr_t, is_off, msg))

        for ev in active_notes.values():
            if ev['end'] == -1:
                ev['end'] = min(end_tick, ultimo_tick + tpb)
                ev['msg_off'] = mido.Message('note_off', channel=ev['ch'], note=ev['msg_on'].note, velocity=0)

        notas_originais.sort(key=lambda x: x['start'])
        novos_eventos = []
        eventos_processados = 0

        if notas_originais and tipo_efeito == 'delay':
            grid = max(1, int(round(params['grid'] * (tpb / 480.0))))
            repeats = params['repeats']
            decay = params['decay'] / 100.0
            for ev in notas_originais:
                dur = max(1, ev['end'] - ev['start'])
                for rep in range(1, repeats + 1):
                    new_vel = int(round(ev['msg_on'].velocity * (decay ** rep)))
                    if new_vel < 1:
                        break
                    new_start = ev['start'] + rep * grid
                    new_end = new_start + dur
                    novos_eventos.append((new_start, 1, ev['msg_on'].copy(velocity=new_vel)))
                    novos_eventos.append((new_end, 0, ev['msg_off'].copy()))
                    eventos_processados += 1

        elif notas_originais and tipo_efeito == 'arpejo':
            grid = max(1, int(round(params['grid'] * (tpb / 480.0))))
            octaves = params['octaves']
            direction = params['direction']
            gate = params['gate'] / 100.0

            chords = []
            current_chord = []
            chord_start = -1
            for ev in notas_originais:
                if not current_chord:
                    current_chord = [ev]
                    chord_start = ev['start']
                elif abs(ev['start'] - chord_start) <= 60:
                    current_chord.append(ev)
                else:
                    chords.append(current_chord)
                    current_chord = [ev]
                    chord_start = ev['start']
            if current_chord:
                chords.append(current_chord)

            for chord in chords:
                c_start = min(x['start'] for x in chord)
                c_end = max(x['end'] for x in chord)
                if c_end > end_tick:
                    c_end = end_tick
                if c_start >= c_end:
                    continue

                base_as_played = []
                for x in sorted(chord, key=lambda ev: ev['start']):
                    if x['msg_on'].note not in base_as_played:
                        base_as_played.append(x['msg_on'].note)
                if not base_as_played:
                    continue

                raw_pattern = []
                for oct in range(octaves):
                    for p in base_as_played:
                        np = p + (oct * 12)
                        if np <= 127 and np not in raw_pattern:
                            raw_pattern.append(np)

                if direction == 0:
                    pattern = sorted(raw_pattern)
                elif direction == 1:
                    pattern = sorted(raw_pattern, reverse=True)
                elif direction == 2:
                    up = sorted(raw_pattern)
                    pattern = up + up[-2:0:-1] if len(up) > 1 else up
                elif direction == 3:
                    pattern = raw_pattern
                else:
                    pattern = raw_pattern
                if not pattern:
                    continue

                cur_tick = c_start
                p_idx = 0
                ref_vel = chord[0]['msg_on'].velocity
                ch_arp = chord[0]['ch']
                while cur_tick < c_end:
                    note_val = random.choice(pattern) if direction == 4 else pattern[p_idx % len(pattern)]
                    dur_real = int(round(grid * gate))
                    note_end = min(cur_tick + dur_real, c_end)
                    if note_end > cur_tick:
                        novos_eventos.append((cur_tick, 1, mido.Message('note_on', channel=ch_arp, note=note_val, velocity=ref_vel)))
                        novos_eventos.append((note_end, 0, mido.Message('note_off', channel=ch_arp, note=note_val, velocity=0)))
                        eventos_processados += 1
                    cur_tick += grid
                    p_idx += 1

        elif notas_originais and tipo_efeito == 'harpa':
            delay_ticks = max(1, params['delay_ticks'])
            direction = params['direction']
            octaves = params['octaves']
            chord_tolerance = 40

            i_nota = 0
            while i_nota < len(notas_originais):
                ev = notas_originais[i_nota]
                start_ref = ev['start']
                chord_notes = [ev]
                j = i_nota + 1
                while j < len(notas_originais) and notas_originais[j]['start'] - start_ref <= chord_tolerance:
                    chord_notes.append(notas_originais[j])
                    j += 1

                if len(chord_notes) >= 2 or octaves > 1:
                    expanded = []
                    for oct_idx in range(octaves):
                        for ce in chord_notes:
                            nota_real = ce['msg_on'].note + (oct_idx * 12)
                            if 0 <= nota_real <= 127:
                                expanded.append({
                                    'start': ce['start'], 'end': ce['end'],
                                    'msg_on': ce['msg_on'].copy(note=nota_real),
                                    'msg_off': ce['msg_off'].copy(note=nota_real),
                                })
                    expanded.sort(key=lambda x: x['msg_on'].note)
                    if direction == 1:
                        expanded.reverse()
                    elif direction == 2:
                        meio = len(expanded) // 2
                        subida = expanded[:meio]
                        descida = expanded[meio:]
                        descida.reverse()
                        expanded = subida + descida
                    for idx, ce in enumerate(expanded):
                        offset = idx * delay_ticks
                        novos_eventos.append((ce['start'] + offset, 1, ce['msg_on']))
                        novos_eventos.append((ce['end'] + offset, 0, ce['msg_off']))
                        eventos_processados += 1
                else:
                    novos_eventos.append((chord_notes[0]['start'], 1, chord_notes[0]['msg_on']))
                    novos_eventos.append((chord_notes[0]['end'], 0, chord_notes[0]['msg_off']))
                i_nota = j

        elif tipo_efeito == 'bateria_preset':
            # INSERE um desenho pronto de bateria no canal em foco, a
            # partir da Entrada (I) - diferente do Arpejo/Delay/Harpa, não
            # precisa de nota nenhuma já existente no trecho. SOBREPÕE (não
            # apaga) o que já está tocando no canal - o preamble acima
            # mantém as notas originais em `flat` pra este tipo (mesmo
            # tratamento do Delay), então o desenho só ACRESCENTA batidas
            # de bateria em cima do que já estava ali.
            preset_idx = params.get('preset_idx')
            if preset_idx is not None and 0 <= preset_idx < len(BATERIA_PRESETS):
                _, _, duracao_beats, eventos_preset = BATERIA_PRESETS[preset_idx]
                escala = tpb / 480.0
                dur_ticks = int(round(480 * duracao_beats * escala))
                fim_preset = min(start_tick + dur_ticks, end_tick)
                gate = max(1, int(round(30 * escala)))
                for offset480, nota, vel in eventos_preset:
                    t = start_tick + int(round(offset480 * escala))
                    if t >= fim_preset:
                        continue
                    # O note_off tem que ficar ESTRITAMENTE dentro de
                    # [start_tick, fim_preset) - se ele grudar exatamente em
                    # fim_preset (comum no último toque de um rufo, perto da
                    # borda), esse tick fica FORA da faixa que o motor usa
                    # pra tocar a seção isolada no loop (prepare_section_cache
                    # corta em ">= section_end"), e o "desligar" nunca chega
                    # dentro do próprio loop dessa seção - achado com o
                    # Michel testando o Pop MHS 02.sty (crash de prato ficava
                    # "vazando" note_off pro início da seção seguinte).
                    fim_nota = min(t + gate, max(t + 1, fim_preset - 1))
                    novos_eventos.append((t, 1, mido.Message('note_on', channel=self.canal_atual, note=nota, velocity=vel)))
                    novos_eventos.append((fim_nota, 0, mido.Message('note_off', channel=self.canal_atual, note=nota, velocity=0)))
                    eventos_processados += 1

        flat.extend(novos_eventos)
        flat.sort(key=lambda x: (x[0], x[1]))
        abs_msgs = [(t, m) for (t, _, m) in flat]

        self.merged_track_cache = self._abs_list_para_delta_track(abs_msgs)

        if is_preview:
            self.prepare_section_cache()
            if getattr(self, 'playing', False):
                self.anchor_tick = self.current_accumulated_ticks
                self.force_reload_loop = True
        else:
            self.dirty = True
            self.rebuild_sections_from_cache()
        return eventos_processados

    def _eh_evento_contavel(self, msg):
        # O "lado de desligar" de uma nota (note_off, ou note_on com
        # velocity=0 - a forma como o mido/o formato grava a maioria dos
        # note_off) não conta como um item À PARTE pro usuário - uma nota
        # tocada é 1 coisa só, mesmo sendo 2 mensagens cruas no arquivo
        # (liga + desliga). Sem isso, "Apagar"/"Copiar"/"Recortar"/"Colar"
        # sempre falavam o DOBRO do que a pessoa realmente gravou (achado
        # com o Michel: 8 notas gravadas, "16 itens apagados"; 13 notas +
        # 1 CC94, "27 apagados" em vez de 14) - confuso especialmente pra
        # quem não conhece o formato MIDI por dentro.
        if msg.type == 'note_off':
            return False
        if msg.type == 'note_on' and msg.velocity == 0:
            return False
        return True

    def do_copy(self, event, cut=False):
        if not getattr(self, 'canais_selecionados', set()):
            falar("Erro: Nenhum canal selecionado.", imediato=True)
            return
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND: return
        sec = self.sections_info[idx]
        if sec.get('start') is None:
            # Seção canônica ainda não criada de verdade no arquivo (start/
            # end continuam None) - sem isso, "start_t <= curr_t < end_t"
            # mais abaixo comparava None com int e derrubava com TypeError.
            falar("Esta seção ainda não tem conteúdo - nada para copiar.", imediato=True)
            return
        start_t = self.in_point if self.in_point is not None else sec.get('start', 0)
        end_t = self.out_point if self.out_point is not None else sec.get('end', float('inf'))
        tpq = getattr(self.current_midi_data, 'ticks_per_beat', 480)
        if end_t == float('inf'):
            end_t = sum(m.time for m in self.merged_track_cache)
            if end_t <= start_t: end_t = start_t + (tpq * self.beats_per_measure)
        self.save_state("Recortar" if cut else "Copiar")
        self.clipboard_events = []
        # Guarda a resolução (ticks por beat) DESTE arquivo junto com o
        # clipboard - Copiar/Colar funciona entre abas diferentes (arquivos
        # abertos ao mesmo tempo), e cada .sty pode ter uma resolução
        # diferente (ex.: 480 vs 1920 ticks por beat). Sem converter, colar
        # em outra aba com resolução diferente distorcia o andamento do
        # trecho colado (achado com o Michel: copiou o Bass de um Regional
        # em 1920 ticks/beat pra outro em 480 - o trecho colado tocava 4x
        # mais devagar, como se o BPM tivesse caído de 84 pra 21). Ver
        # conversão em do_paste.
        self.clipboard_tpq = tpq
        base_ch = min(self.canais_selecionados)
        sec_start = sec.get('start', 0)
        # Rastreia notas ainda "abertas" (note_on sem note_off) no fim do
        # trecho copiado - uma nota que só é fechada pelo "reset" de acorde
        # da PRÓXIMA seção (mesmo tick == end_t, excluído por curr_t < end_t
        # de propósito, ver comentário abaixo) fica sem seu note_off ao ser
        # copiada isoladamente - colada em outro lugar, vira uma nota presa
        # pra sempre. Achado com o Michel: copiou a Intro A inteira pra
        # dentro da Intro C, e 2 notas do Chord 1 (que só fecham no "reset"
        # que pertence à Intro B, não à Intro A em si) ficaram penduradas.
        from collections import defaultdict, deque
        notas_abertas = defaultdict(deque)
        keep_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            ch = getattr(msg, 'channel', -1)
            # curr_t < end_t (aberto no fim) - com <= end_t, um evento bem na
            # cabeça da PRÓXIMA seção (que cai exatamente no tick "end" desta,
            # já que "end" é o start dela) era recortado/copiado junto, como
            # se ainda fosse desta seção (achado com o Michel gravando no
            # canal errado e cortando: o corte levava a primeira nota da
            # seção seguinte também).
            if ch in self.canais_selecionados and start_t <= curr_t < end_t:
                # CC/PC exatamente no tick 0 DA SEÇÃO (não do trecho marcado -
                # da seção inteira) são a "configuração de base" plantada ali
                # (Volume/Pan/Reverb/Variation Send/etc, ou um Program Change
                # de troca de kit) - não conteúdo musical de verdade. Copiar
                # pra outro lugar (ex.: colar no meio de outra seção) injetaria
                # uma mudança de mixagem espúria no meio da execução. Achado
                # com o Michel (CC94 do Alex na Ending A, tick 0, "antes do
                # bumbo") - a forma correta de levar config de seção pra outro
                # lugar é Ctrl+Alt+E, não Copiar/Recortar genérico.
                eh_config_tick0 = (msg.type in ('control_change', 'program_change')
                                    and curr_t == sec_start)
                # Um note_off (ou note_on velocity=0) exatamente no tick de
                # INÍCIO da seção (não do trecho marcado com I/O - da seção
                # inteira) é o que fecha a ÚLTIMA nota sustentada da seção
                # ANTERIOR (o "início" de uma seção É o "fim" da anterior) -
                # não é conteúdo desta seção. Incluir ele no Copiar/Recortar
                # arranca o desligamento de uma nota que nem é desta seção,
                # deixando-a tocando pra sempre. Achado com o Michel: apagou
                # o conteúdo antigo da Intro C pra colar a Intro B em cima, e
                # isso levou junto o note_off que fechava a última nota da
                # Intro B (Chord 2, notas 57/59).
                eh_fechamento_anterior = (
                    (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0))
                    and curr_t == sec_start)
                if (msg.type not in ['marker', 'cuepoint', 'track_name', 'set_tempo', 'time_signature']
                        and not eh_config_tick0 and not eh_fechamento_anterior):
                    self.clipboard_events.append({
                        'msg': msg.copy(),
                        'abs_offset': curr_t - start_t,
                        'rel_channel': ch - base_ch
                    })
                    if msg.type == 'note_on' and msg.velocity > 0:
                        notas_abertas[(ch, msg.note)].append(True)
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        fila_nota = notas_abertas.get((ch, msg.note))
                        if fila_nota: fila_nota.popleft()
                    if cut: continue
            keep_msgs.append((curr_t, msg))
        # Fecha, sinteticamente, qualquer nota que sobrou "aberta" no fim do
        # trecho (ver comentário acima) - sem isso, colar em outro lugar
        # deixaria essa nota tocando pra sempre.
        fim_relativo = max(0, (end_t - start_t) - 2)
        for (ch, nota), fila_nota in notas_abertas.items():
            for _ in fila_nota:
                self.clipboard_events.append({
                    'msg': mido.Message('note_off', channel=ch, note=nota, velocity=0),
                    'abs_offset': fim_relativo,
                    'rel_channel': ch - base_ch
                })
        # Conta em ITENS (notas ligar+desligar = 1 só), não em mensagens
        # cruas - ver _eh_evento_contavel.
        n_itens = sum(1 for c in self.clipboard_events if self._eh_evento_contavel(c['msg']))
        if cut:
            self.rebuild_from_abs_list(keep_msgs)
            falar(f"{n_itens} eventos recortados.", imediato=True)
        else:
            if self.clipboard_events:
                falar(f"{n_itens} copiados de {len(self.canais_selecionados)} canais.", imediato=True)
            else: falar("Nada para copiar neste trecho.", imediato=True)
        self.in_point = self.out_point = None

    def do_paste(self, event):
        if not getattr(self, 'clipboard_events', []):
            falar("Nada para colar.", imediato=True)
            return
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND: return
        sec = self.sections_info[idx]
        tpq = getattr(self.current_midi_data, 'ticks_per_beat', 480)
        tpm = tpq * self.beats_per_measure
        self.save_state("Colar")
        secao_criada = False
        if sec.get('start') is None:
            # A seção-alvo (uma das 15 canônicas) ainda não existe FISICAMENTE
            # no arquivo (start/end continuam None) - "target_end <= target_
            # start" com os dois None derrubava com TypeError, e colar numa
            # seção ainda não criada (ex.: uma Fill In nova, antes de gravar
            # ou editar nela pela primeira vez) simplesmente não fazia nada -
            # achado com o Michel montando um ritmo do zero, tentando colar o
            # conteúdo do Rhythm1 direto numa Fill In que ainda não existia.
            # Mesma técnica já usada ao armar a gravação numa seção vazia:
            # cria com 1 compasso (sem undo próprio - já está dentro do
            # "Colar" empilhado acima) e prossegue colando nela.
            self._criar_secao_nova_sem_undo(sec['name'], 1, tpm)
            sec = self.sections_info[idx]
            secao_criada = True
        target_start = sec.get('start', 0)
        target_end = sec.get('end', float('inf'))
        if target_end == float('inf'):
            # Seção FISICAMENTE a última do arquivo agora (_secoes_de_track
            # sempre devolve 'end': inf pra ela) - o fim de verdade é onde o
            # arquivo termina de fato (a âncora SInt que _travar_secao_final_
            # se_precisar/criar_secao_nova já garantem existir ali), não um
            # chute genérico de 4 compassos - senão colar numa seção recém-
            # criada de 1 compasso (o caso mais comum aqui) deixava passar
            # conteúdo de vários compassos a mais do que a seção realmente tem.
            fim_real = sum(m.time for m in self.merged_track_cache)
            target_end = fim_real if fim_real > target_start else target_start + tpm
        elif target_end <= target_start:
            target_end = target_start + (tpm * 4)
        paste_start = self.get_current_absolute_tick()
        target_base_ch = self.canal_atual
        # Converte os offsets do clipboard pra resolução DESTE arquivo, se
        # foram copiados de uma aba com ticks_per_beat diferente (ver
        # comentário em do_copy) - sem isso, colar entre arquivos com
        # resoluções diferentes distorcia o andamento do trecho colado.
        tpq_origem = getattr(self, 'clipboard_tpq', tpq) or tpq
        fator_tpq = tpq / tpq_origem
        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            abs_msgs.append((curr_t, msg))
        colados = 0
        colados_itens = 0
        # Quando a seção de destino é MENOR que o trecho copiado, cola pelo
        # menos o que couber (até target_end) em vez de recusar tudo - mas
        # uma nota cujo note_on entrou e o note_off ficou de fora (cortado
        # pela borda) não pode ficar tocando pra sempre: rastreia as notas
        # ainda "abertas" no fim do que foi colado e fecha elas sinteticamente
        # bem na borda, mesma técnica já usada em do_copy pro mesmo problema.
        from collections import defaultdict, deque
        notas_abertas = defaultdict(deque)
        for clip in self.clipboard_events:
            msg = clip['msg']
            abs_t = paste_start + round(clip['abs_offset'] * fator_tpq)
            if abs_t < target_end:
                new_ch = target_base_ch + clip['rel_channel']
                if 0 <= new_ch <= 15:
                    abs_msgs.append((abs_t, msg.copy(channel=new_ch)))
                    colados += 1
                    if self._eh_evento_contavel(msg): colados_itens += 1
                    if msg.type == 'note_on' and msg.velocity > 0:
                        notas_abertas[(new_ch, msg.note)].append(True)
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        fila_nota = notas_abertas.get((new_ch, msg.note))
                        if fila_nota: fila_nota.popleft()
        fim_relativo = max(paste_start, target_end - 2)
        for (ch_nota, nota), fila_nota in notas_abertas.items():
            for _ in fila_nota:
                abs_msgs.append((fim_relativo, mido.Message('note_off', channel=ch_nota, note=nota, velocity=0)))
                colados += 1
        if colados > 0:
            self.rebuild_from_abs_list(abs_msgs)
            if secao_criada:
                falar(f"Seção criada com 1 compasso. Colados {colados_itens} eventos.", imediato=True)
            else:
                falar(f"Colados {colados_itens} eventos.", imediato=True)
        else:
            self.undo_stack.pop()
            falar("Erro: Sem espaço na seção ou posição inválida.", imediato=True)

    def do_delete(self, event):
        if not getattr(self, 'canais_selecionados', set()):
            falar("Selecione os canais primeiro.", imediato=True)
            return
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND: return
        sec = self.sections_info[idx]
        if sec.get('start') is None:
            # Mesmo motivo do do_copy: sem seção física ainda, "start_t <=
            # curr_t < end_t" mais abaixo compararia None com int.
            falar("Esta seção ainda não tem conteúdo - nada para apagar.", imediato=True)
            return
        start_t = self.in_point if self.in_point is not None else sec.get('start', 0)
        end_t = self.out_point if self.out_point is not None else sec.get('end', float('inf'))
        if end_t == float('inf'): end_t = sum(m.time for m in self.merged_track_cache)
        if start_t > end_t: start_t, end_t = end_t, start_t
        self.save_state("Apagar")
        sec_start = sec.get('start', 0)
        keep_msgs = []
        curr_t = 0
        apagados = 0
        apagados_itens = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            ch = getattr(msg, 'channel', -1)
            # Mesmo ajuste do do_copy logo acima (curr_t < end_t, aberto no
            # fim) - sem isso, apagar um canal numa seção também apagava a
            # primeira nota da seção SEGUINTE, que cai bem no tick "end"
            # desta (o "end" de uma seção É o "start" da próxima).
            if ch in self.canais_selecionados and start_t <= curr_t < end_t:
                # Mesma exclusão do do_copy: CC/PC exatamente no tick 0 DA
                # SEÇÃO é configuração de base (Volume/Pan/Variation Send/
                # troca de kit), não conteúdo musical - "Apagar" não deve
                # arrancar a mixagem só por apagar as notas de um canal.
                # Confirmado com o Michel: quem quiser apagar TUDO mesmo
                # (config incluída) usa o Event List ou limpa a seção
                # inteira - "Apagar" (canal numa seção) fica mais seguro.
                eh_config_tick0 = (msg.type in ('control_change', 'program_change')
                                    and curr_t == sec_start)
                # Mesma proteção do do_copy: um note_off (ou note_on
                # velocity=0) exatamente no tick de início DA SEÇÃO fecha a
                # última nota da seção ANTERIOR, não é conteúdo desta -
                # "Apagar" não deve arrancar isso, senão a nota da seção
                # anterior fica tocando pra sempre.
                eh_fechamento_anterior = (
                    (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0))
                    and curr_t == sec_start)
                if (msg.type not in ['marker', 'cuepoint', 'track_name', 'set_tempo', 'time_signature']
                        and not eh_config_tick0 and not eh_fechamento_anterior):
                    apagados += 1
                    if self._eh_evento_contavel(msg): apagados_itens += 1
                    continue
            keep_msgs.append((curr_t, msg))
        if apagados > 0:
            self.rebuild_from_abs_list(keep_msgs)
            falar(f"{apagados_itens} eventos apagados.", imediato=True)
        else:
            self.undo_stack.pop()
            falar("Nada para apagar aqui.", imediato=True)

    def _msg_priority(self, m):
        if m.type == 'end_of_track':
            # Tem que ficar SEMPRE por último, mesmo empatado no mesmo tick
            # com outro conteúdo (ex.: a âncora SInt plantada bem no fim do
            # arquivo por apply_section_resize) - com prioridade 0 (igual a
            # qualquer meta message) ele podia ser ordenado ANTES do note_off/
            # SInt finais, deixando de ser fisicamente a última mensagem da
            # trilha (inválido) - e essa posição incerta é o que fazia
            # reabrir/renormalizar o mesmo arquivo produzir ordens diferentes
            # a cada vez (não-idempotente).
            return 999
        if getattr(m, 'is_meta', False):
            # "SInt" é um marcador INERTE (nunca fronteira de seção de
            # verdade, ver _secoes_de_track) - o que fica plantado no
            # cabeçalho do arquivo (tick 0, junto com o bloco de SysEx de
            # configuração inicial) precisa continuar DEPOIS desse
            # bloco, não antes - senão o teclado real recebe o marcador
            # ANTES da configuração ter sido aplicada. Com prioridade 0
            # (a mesma de qualquer marcador de seção de verdade, que
            # PRECISA vir primeiro), esse SInt específico era empurrado
            # pra frente do SysEx toda vez que o arquivo passava por
            # qualquer reordenação (praticamente qualquer edição) -
            # achado com o Michel comparando o arquivo salvo pelo
            # programa com o mesmo arquivo resalvo pelo Style Creator do
            # teclado (que sempre mantém o SInt depois do SysEx) - a
            # diferença batia exatamente com um efeito colateral real no
            # SX600 ao ir pro Ending 1. Prioridade 1.5 (entre o SysEx=1 e
            # o Bank Select=2) garante que ele sempre vai reordenar pra
            # DEPOIS de qualquer SysEx no mesmo tick, mesmo partindo de
            # um arquivo onde ele já estava na posição errada (um "stable
            # sort" com a MESMA prioridade só preservaria a ordem antiga;
            # sendo estritamente maior, o sort de verdade sempre corrige).
            # "SFF1"/"SFF2" (o identificador de FORMATO do arquivo, a
            # própria especificação Yamaha os coloca logo no início, antes
            # até do bloco de SysEx) e qualquer marcador de seção de
            # verdade continuam com prioridade 0, sem mudança nenhuma.
            if m.type in ('marker', 'cuepoint') and getattr(m, 'text', '') == 'SInt':
                return 1.5
            return 0
        if m.type == 'sysex':
            # O SysEx de Drum Setup por peça (0x43 0x10 0x4C 0x30/0x31...,
            # que inclui tanto o mapeamento de peça 0x70 quanto os
            # parâmetros de afinação/filtro) precisa chegar DEPOIS do
            # Program Change deste canal (trocar de kit reseta a peça pro
            # padrão do kit) - mas também precisa chegar ANTES de qualquer
            # nota, mesmo quando ela cai bem no mesmo instante que o Program
            # Change (uma gravação que já começa tocando na cabeça da
            # seção). Como os dois nunca podem ficar no mesmo tick+prioridade
            # ao mesmo tempo que o Program Change E antes da nota, esse
            # SysEx específico ganha prioridade própria (entre Program
            # Change e nota) em vez da prioridade genérica de SysEx - sem
            # isso, a primeira nota bem na cabeça da seção tocava com a
            # peça antiga por um tick, só "acertando" a partir da segunda.
            d = bytes(m.data)
            if len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] in (0x30, 0x31):
                return 4
            # Voice Creator (Multi Part 0x08 / Portamento 0x0A, endereçados a
            # um canal): mesma regra do Drum Setup - precisa chegar DEPOIS do
            # Program Change do canal. Com prioridade 1 ele caía ANTES do
            # Program Change no mesmo tick, e o SX ao trocar de timbre
            # voltava aos parâmetros originais da voz (achado com a voz
            # ADA.liv importada no Chord 1: no programa soava editada, no
            # teclado real soava o piano original).
            if len(d) >= 7 and d[0] == 0x43 and d[1] == 0x10 and d[2] == 0x4C and d[3] in (0x08, 0x0A) and d[4] < 16:
                return 4
            return 1
        if m.type == 'control_change' and m.control in [0, 32]: return 2
        if m.type == 'program_change': return 3
        if m.type in ['note_on', 'note_off']: return 5
        return 4

    def _abs_list_para_delta_track(self, abs_list):
        # Mesma conversão abs->delta do rebuild_from_abs_list, mas devolvendo
        # a trilha em vez de commitar em self.merged_track_cache - usado
        # tanto por rebuild_from_abs_list quanto por qualquer edição que
        # mexa no instantâneo ('estado') de uma aba que não está na tela
        # agora (ver executar_copiar_canal_entre_secoes).
        abs_list.sort(key=lambda x: (x[0], self._msg_priority(x[1])))
        track = []
        last_t = 0
        for t, msg in abs_list:
            msg.time = int(round(t - last_t))
            track.append(msg)
            last_t = t
        return track

    def _secoes_de_track(self, track):
        # Mesmo escaneamento de marcadores do rebuild_sections_from_cache,
        # mas devolvendo a lista em vez de mexer em self.sections_info -
        # mesmo motivo do helper acima.
        markers = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type in ['marker', 'cuepoint']:
                m_name = getattr(msg, 'text', getattr(msg, 'name', 'Sem Nome'))
                if m_name not in ['SFF1', 'SFF2', 'SInt']:
                    markers.append({'name': m_name, 'start': abs_time})
        markers.sort(key=lambda x: x['start'])
        return [
            {
                'name': m['name'],
                'start': m['start'],
                'end': markers[i + 1]['start'] if i + 1 < len(markers) else float('inf'),
                'present': True,
                'display_name': m['name']
            } for i, m in enumerate(markers)
        ]

    def rebuild_from_abs_list(self, abs_list):
        self.merged_track_cache = self._abs_list_para_delta_track(abs_list)
        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_sections_from_cache()

    def rebuild_sections_from_cache(self):
        # Não atribui a lista em ORDEM FÍSICA direto em self.sections_info -
        # só a versão já reordenada pra CANÔNICA (a mesma numeração que
        # `_active_section_idx`/a tela sempre usam). Ver o comentário em
        # build_full_section_list pra o motivo (uma corrida real que
        # derrubava o midi_worker com IndexError).
        self.sections_info = self.build_full_section_list(self._secoes_de_track(self.merged_track_cache))
        self.refresh_section_list(select_first=False)
        self.update_mixer_list()
        if getattr(self, 'playing', False):
            self.prepare_section_cache()

    def abrir_exportar_canal(self, event):
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de exportar um canal.", imediato=True)
            return
        canal_origem = self.canal_atual
        foco_antes = wx.Window.FindFocus()
        dlg = ExportarCanalDialog(self, canal_origem)
        if dlg.ShowModal() == wx.ID_OK:
            alvos, semitons = dlg.get_valores()
            dlg.Destroy()
            if not alvos:
                falar("Nenhum canal marcado. Nada foi exportado.", imediato=True)
                self._agendar_restaurar_foco(foco_antes)
                return
            self.save_state(f"Exportar Canal {rotulo_canal(canal_origem)}")
            self.executar_exportar_canal(canal_origem, alvos, semitons)
            nomes_alvos = ", ".join(rotulo_canal(c) for c in alvos)
            falar(f"Canal {rotulo_canal(canal_origem)} exportado para {nomes_alvos}.", imediato=True)
        else:
            dlg.Destroy()
        self._agendar_restaurar_foco(foco_antes)

    def executar_exportar_canal(self, canal_origem, alvos, semitons):
        import copy
        # 1. Varre a trilha mesclada uma vez, guardando (tick absoluto, cópia
        # da mensagem) de tudo que pertence ao canal de origem, junto com a
        # lista de tudo mais (que vai ser mantida ou descartada logo abaixo).
        origem_eventos = []
        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            ch = getattr(msg, 'channel', None)
            if ch == canal_origem:
                origem_eventos.append((curr_t, msg.copy()))
            abs_msgs.append((curr_t, msg))

        alvos_set = set(alvos)
        # 2. Descarta TODO o conteúdo antigo dos canais de destino (a
        # exportação substitui o que já estava gravado neles, seção por
        # seção - não mistura com o que sobrou).
        abs_msgs = [(t, m) for (t, m) in abs_msgs if getattr(m, 'channel', None) not in alvos_set]

        # 3. Para cada canal de destino, clona cada evento do canal de
        # origem, redireciona o canal e transpõe só as notas (o resto -
        # Control Change, Program Change, Pitch Bend etc - vai igual).
        for alvo in alvos:
            for t, msg in origem_eventos:
                novo = msg.copy(channel=alvo)
                if novo.type in ('note_on', 'note_off') and semitons != 0:
                    novo.note = max(0, min(127, novo.note + semitons))
                abs_msgs.append((t, novo))

        self.rebuild_from_abs_list(abs_msgs)

        # 4. CASM: mesma regra em todas as seções que já têm CASM próprio -
        # copiado como está (sem transpor), só forçando "Redirecionar Para"
        # a apontar pro próprio canal de destino (senão o áudio saía
        # redirecionado de volta pro canal de origem).
        # Usa self.sections_info (as seções que EXISTEM de verdade no
        # arquivo) em vez de só casm_rules_by_section - uma seção que nunca
        # foi aberta em "Editar Seção" ainda não tem entrada lá, mas mesmo
        # assim precisa receber o CASM (com os padrões de fábrica, que é
        # exatamente o que ela já estaria usando de qualquer forma).
        for sec in getattr(self, 'sections_info', []):
            casm_secao = self.obter_casm_da_secao(sec['name'], criar_se_ausente=True)
            regra_origem = casm_secao.get(canal_origem)
            if regra_origem is None:
                continue
            for alvo in alvos:
                nova_regra = copy.deepcopy(regra_origem)
                nova_regra['dst'] = alvo
                casm_secao[alvo] = nova_regra

        # 5. Timbre e mixagem: Volume, Pan, Expression, Bank, Patch, Reverb
        # e Chorus - os mesmos 7 que "limpar_eventos_locais" já sabe
        # normalizar em todas as seções (é a função que roda toda vez que
        # você edita uma dessas propriedades na lista de canais). Não mexe
        # em Nome/Mute/Solo/Arm - isso é identidade/estado de audição do
        # canal de destino, não faz parte do "timbre" que veio junto.
        propriedades_timbre = ["Volume", "Pan", "Expression", "Bank", "Patch", "Reverb", "Chorus", "Grave", "Agudo"]
        origem_props = self.canais[canal_origem]
        for alvo in alvos:
            destino_props = self.canais[alvo]
            for p in propriedades_timbre:
                destino_props[p] = origem_props[p]
            for p in propriedades_timbre:
                # enviar_midi_param manda ao vivo pro teclado agora mesmo -
                # limpar_eventos_locais sozinho só arruma o arquivo/trilha,
                # sem isso o som ficava com o timbre antigo até a próxima
                # vez que alguém mexesse manualmente na propriedade.
                self.enviar_midi_param(p, destino_props[p], alvo)
                self.limpar_eventos_locais(alvo, p)
        self.update_mixer_list()

    def _obter_ou_criar_casm_em_biblioteca(self, biblioteca, nome_secao):
        # Mesma busca por nome (sem diferenciar maiúsculas) do
        # obter_casm_da_secao, mas recebendo a biblioteca como parâmetro em
        # vez de sempre usar self.casm_rules_by_section - pra poder mexer no
        # CASM de uma aba que não é a que está na tela agora (ver
        # executar_copiar_canal_entre_secoes), do mesmo jeito que
        # exportar_casm já faz manualmente pra abas cruzadas.
        chave_alvo = (nome_secao or "").strip().lower()
        for nome_guardado, regras in biblioteca.items():
            if nome_guardado.strip().lower() == chave_alvo:
                return regras
        nova_regra = self.get_default_casm_rules()
        biblioteca[nome_secao] = nova_regra
        return nova_regra

    def abrir_copiar_canal_entre_secoes(self, event):
        if not getattr(self, 'current_midi_data', None):
            falar("Abra ou crie um estilo antes de copiar um canal.", imediato=True)
            return
        idx_sec = self.sectionList.GetSelection()
        if idx_sec == wx.NOT_FOUND or idx_sec >= len(self.sections_info):
            falar("Selecione uma seção primeiro.", imediato=True)
            return
        sec_origem = self.sections_info[idx_sec]
        canal_origem = self.canal_atual
        # Guarda quem tinha foco ANTES de abrir (Ctrl+Alt+E funciona de
        # qualquer lugar, não só com o channelList em foco) pra devolver o
        # foco pro mesmo lugar ao fechar - mesma lógica do Event List.
        foco_antes_copiar_canal = wx.Window.FindFocus()
        def _restaurar_foco():
            if foco_antes_copiar_canal:
                foco_antes_copiar_canal.SetFocus()
            else:
                self.channelList.SetFocus()
        dlg = CopiarCanalEntreSecoesDialog(self, canal_origem, sec_origem['name'], self.abas, self.aba_atual)
        if dlg.ShowModal() == wx.ID_OK:
            alvos, canal_destino, semitons = dlg.get_valores()
            dlg.Destroy()
            if not alvos:
                falar("Nenhum destino marcado. Nada foi copiado.", imediato=True)
                wx.CallLater(100, _restaurar_foco)
                return
            self.save_state(f"Copiar Canal {rotulo_canal(canal_origem)} Entre Seções")
            feitos, pulados = self.executar_copiar_canal_entre_secoes(canal_origem, sec_origem, canal_destino, alvos, semitons)
            if feitos == 0:
                self.undo_stack.pop()
            msg = f"Canal {rotulo_canal(canal_origem)} ({sec_origem['display_name']}) copiado para {feitos} destino(s)."
            if pulados:
                msg += f" {pulados} pulado(s) por não existir essa seção lá."
            falar(msg, imediato=True)
        else:
            dlg.Destroy()
        wx.CallLater(100, _restaurar_foco)

    def executar_copiar_canal_entre_secoes(self, canal_origem, sec_origem, canal_destino, alvos, semitons):
        import copy
        from collections import defaultdict, deque
        # 1. Recorta, do canal de origem, só o trecho da seção escolhida -
        # guardado em tick RELATIVO ao início da seção, pra poder ser
        # reencaixado no início de qualquer seção de destino, mesmo que ela
        # comece em outro lugar (ou esteja em outra aba, com outra duração).
        origem_start = sec_origem['start']
        origem_end = sec_origem['end']
        origem_eventos = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            if curr_t < origem_start: continue
            if curr_t >= origem_end: break
            if getattr(msg, 'channel', None) == canal_origem:
                origem_eventos.append((curr_t - origem_start, msg.copy()))

        # As propriedades de timbre/mixagem vêm da seção de ORIGEM
        # especificamente, não do instantâneo global do canal - um ritmo
        # genuíno pode ter um Patch/Banco/Volume diferente só numa seção
        # (ex.: canal 16 do Ballada 2), e é isso que "Editar Seção" mostra
        # pra essa seção; a cópia precisa levar o mesmo valor, não o da
        # Área de Configuração.
        origem_props = self.ler_propriedades_locais_secao(self.merged_track_cache, canal_origem, origem_start, origem_end)
        casm_origem_secao = self.obter_casm_da_secao(sec_origem['name'], criar_se_ausente=True)
        regra_origem = casm_origem_secao.get(canal_origem)

        # Quantos compassos (e a figura) a seção de ORIGEM tem - usado pra
        # criar a seção de destino do MESMO tamanho quando ela ainda não
        # existir (ex: colar num Fill vazio). Sem isso, colar num destino
        # que nunca foi criado simplesmente não tinha onde encaixar o
        # conteúdo - não colava nada, ou só o que coubesse por acaso num
        # compasso default de 1.
        tpq_origem = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
        origem_num, origem_den = self.obter_compasso_da_secao(self.merged_track_cache, origem_start)
        tpm_origem = self.ticks_por_compasso(tpq_origem, origem_num, origem_den)
        origem_fim_real = origem_end
        if origem_fim_real == float('inf'):
            origem_fim_real = sum(m.time for m in self.merged_track_cache)
        origem_measures = max(1, int(round((origem_fim_real - origem_start) / tpm_origem)))

        # Os 5 Fills ainda são de 1 compasso só no SX600 real (testado no
        # teclado - reprovado com mais que isso). O programa continua
        # aceitando Fill com vários compassos pra quem já tem um teclado
        # mais novo que aceita (não é pra tirar essa capacidade) - só essa
        # criação automática, ao colar num Fill vazio, que fica presa em 1
        # compasso por padrão, em vez de copiar o tamanho inteiro da origem.
        nomes_fill = {"fill in aa", "fill in bb", "fill in cc", "fill in dd", "fill in ba"}

        feitos = 0
        pulados = 0
        for destino_aba_idx, nome_secao_destino in alvos:
            eh_aba_atual = destino_aba_idx is None
            if eh_aba_atual:
                track = self.merged_track_cache
                sections_info = self.sections_info
                canais = self.canais
            else:
                estado = self.abas[destino_aba_idx]['estado']
                track = estado.get('merged_track_cache') or []
                sections_info = estado.get('sections_info') or []
                canais = estado.get('canais') or []

            # Resolução (ticks por beat) do arquivo de DESTINO - pode ser
            # diferente da origem (cada aba/arquivo tem a sua). Sem converter,
            # o conteúdo copiado tocava rápido/devagar demais - achado com o
            # Michel copiando o Chord 1 de "19. Regional 1.STY" (1920 ticks
            # por beat) pro "Regional MHS 01.sty" (480) via Ctrl+Alt+E: o
            # trecho colado tocava 4x mais devagar (andamento parecendo cair
            # de 84 pra 21 BPM) - mesma classe de bug já corrigida em
            # Colar (Ctrl+V), só que este caminho (Copiar Canal Entre
            # Seções) tem a própria cópia de código e não passava por lá.
            if eh_aba_atual:
                midi_destino = self.current_midi_data
            else:
                midi_destino = estado.get('current_midi_data')
            tpq_destino = getattr(midi_destino, 'ticks_per_beat', tpq_origem) or tpq_origem
            tpm_destino = self.ticks_por_compasso(tpq_destino, origem_num, origem_den)
            fator_tpq = tpq_destino / tpq_origem

            sec_destino = next((s for s in sections_info if s['name'].strip().lower() == nome_secao_destino.strip().lower() and s.get('start') is not None), None)
            if sec_destino is None:
                if eh_aba_atual:
                    # A seção de destino ainda não existe nesse arquivo -
                    # cria ela agora, do mesmo tamanho (compassos e figura)
                    # da seção de origem, em vez de simplesmente recusar a
                    # cópia - EXCETO um Fill, que nasce sempre com 1
                    # compasso só (ver nomes_fill acima). Usa tpm_destino (a
                    # resolução DESTE arquivo), não tpm_origem - senão a
                    # seção nascia com o tamanho físico errado sempre que as
                    # duas resoluções divergem.
                    measures_destino = 1 if nome_secao_destino.strip().lower() in nomes_fill else origem_measures
                    self._criar_secao_nova_sem_undo(nome_secao_destino, measures_destino, tpm_destino, origem_num, origem_den)
                    track = self.merged_track_cache
                    sections_info = self.sections_info
                    sec_destino = next((s for s in sections_info if s['name'].strip().lower() == nome_secao_destino.strip().lower() and s.get('start') is not None), None)
                if sec_destino is None:
                    pulados += 1
                    continue

            destino_start = sec_destino['start']
            destino_end = sec_destino['end']
            if destino_end is None or destino_end == float('inf'):
                # Seção de destino sem próxima depois dela (é a última coisa
                # do track) - sem resolver isso pra um tick concreto, o corte
                # de "não coube" logo abaixo nunca acionava (nada é >= infinito),
                # e o conteúdo colado vazava pra além do tamanho declarado da
                # seção (é assim que um Fill de 1 compasso recém-criado
                # acabava recebendo os 4 compassos inteiros da origem).
                destino_end = sum(m.time for m in track)

            # 2. Descarta o conteúdo antigo do canal de destino SÓ dentro
            # dessa seção - o resto da música (outras seções) fica intacto.
            abs_msgs = []
            curr_t = 0
            for msg in track:
                curr_t += msg.time
                if destino_start <= curr_t < destino_end and getattr(msg, 'channel', None) == canal_destino:
                    continue
                abs_msgs.append((curr_t, msg))

            # 3. Reencaixa o conteúdo recortado no início da seção de
            # destino, redirecionando o canal e transpondo só as notas. O
            # que passar do fim da seção de destino fica de fora (mesmo
            # critério de "não coube" que colar (Ctrl+V) já usa) - EXCETO
            # note_off de uma nota que REALMENTE abriu dentro do destino,
            # que é cortado bem no fim da seção se precisar (pra não deixar
            # essa nota presa tocando pra sempre quando a seção de destino é
            # mais curta que a de origem).
            #
            # `abertos` rastreia isso - sem ele, um note_off que sobra da
            # origem (de uma nota cujo note_on nem chegou a caber no
            # destino, por estar mais adiante, fora do compasso único de um
            # Fill por exemplo) ainda era incluído "cortado no fim" - um
            # "desligar" solto, sem "ligar" nenhum, sem som nenhum, só
            # sujeira na lista de eventos. Achado com o Michel copiando o
            # Chord 2 do Main A (4 compassos) pro Fill In AA (1 compasso só)
            # do Pop MHS 02.sty.
            eh_note_on = lambda m: m.type == 'note_on' and getattr(m, 'velocity', 0) > 0
            eh_note_off = lambda m: m.type == 'note_off' or (m.type == 'note_on' and getattr(m, 'velocity', 1) == 0)
            abertos = defaultdict(int)
            for offset, msg in origem_eventos:
                novo_t = destino_start + round(offset * fator_tpq)
                if eh_note_off(msg):
                    if abertos.get(msg.note, 0) <= 0:
                        continue
                    abertos[msg.note] -= 1
                    if novo_t >= destino_end:
                        novo_t = max(destino_start, destino_end - 1)
                elif novo_t >= destino_end:
                    continue
                elif eh_note_on(msg):
                    abertos[msg.note] += 1
                novo = msg.copy(channel=canal_destino)
                if novo.type in ('note_on', 'note_off') and semitons != 0:
                    novo.note = max(0, min(127, novo.note + semitons))
                abs_msgs.append((novo_t, novo))

            # 3a. Rede de segurança: confere se alguma nota do canal de
            # destino ficou sem fechar dentro da própria seção de destino,
            # e fecha sozinha se precisar. O clamp do passo 3 acima só
            # cobre note_off que sobrou de compasso a mais da ORIGEM - se a
            # ORIGEM já estivesse com uma nota sem note_off nenhum (ex.: um
            # resquício do bug antigo de gravação, ou qualquer outra causa),
            # a cópia simplesmente repetia o problema sem detectar nada.
            # Pedido do Michel: copiar de uma seção de 4 compassos pra uma
            # de 1 só não devia deixar nenhuma nota "pendurada".
            fila_dest = defaultdict(deque)
            for t, msg in abs_msgs:
                if destino_start <= t < destino_end and getattr(msg, 'channel', None) == canal_destino:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        fila_dest[msg.note].append(t)
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        fila = fila_dest.get(msg.note)
                        if fila:
                            fila.popleft()
            for nota, fila in fila_dest.items():
                for _ in fila:
                    fim_seguro = max(destino_start, destino_end - 1)
                    abs_msgs.append((fim_seguro, mido.Message('note_off', channel=canal_destino, note=nota, velocity=0)))

            # 3b. Timbre/mixagem (Volume, Pan, Expression, Bank, Patch,
            # Reverb, Chorus, Grave, Agudo) - só na cabeça da seção de
            # DESTINO, junto com o resto do conteúdo colado acima, e SÓ pras
            # propriedades que realmente diferem do padrão atual do canal.
            # NUNCA usar limpar_eventos_locais/_normalizar_propriedade_
            # generico nem escrever em canais[ch] aqui - os dois normalizam
            # o timbre em TODAS as seções do arquivo, não só a de destino
            # (bug real 1: copiar o canal 10 do Main B pro Fill In BB do
            # "Pop MHS 02.sty" injetou Grave/Agudo=64 em Main A/B/C/D e Fill
            # In AA também).
            #
            # E reafirmar Bank/Patch/CC à toa (mesmo quando o valor já é
            # igual ao normal do canal) também é errado (bug real 2, achado
            # depois do 1º conserto): um Program Change, mesmo repetindo o
            # MESMO timbre, reresseta o kit de bateria num teclado XG de
            # verdade - apagando a customização ao vivo do Drum Setup só
            # por focar na seção. Uma seção gravada de verdade (ex.: Fill
            # In AA) nunca tem essa reafirmação à toa - só grava um evento
            # quando o Michel de fato mudou algo ali. `propriedades_
            # diferentes` reproduz esse mesmo comportamento.
            propriedades_timbre = ["Volume", "Pan", "Expression", "Bank", "Patch", "Reverb", "Chorus", "Grave", "Agudo"]
            cc_map_timbre = {"Volume": CC_VOLUME, "Pan": CC_PAN, "Expression": CC_EXPRESSION, "Reverb": CC_REVERB, "Chorus": CC_CHORUS}
            baseline_destino = canais[canal_destino] if canais else {}
            propriedades_diferentes = [p for p in propriedades_timbre if origem_props[p] != baseline_destino.get(p)]
            if "Bank" in propriedades_diferentes:
                abs_msgs.append((destino_start, mido.Message('control_change', channel=canal_destino, control=CC_BANK_MSB, value=origem_props["Bank"] // 128)))
                abs_msgs.append((destino_start, mido.Message('control_change', channel=canal_destino, control=CC_BANK_LSB, value=origem_props["Bank"] % 128)))
            if "Patch" in propriedades_diferentes:
                abs_msgs.append((destino_start, mido.Message('program_change', channel=canal_destino, program=origem_props["Patch"])))
            for p, cc in cc_map_timbre.items():
                if p in propriedades_diferentes:
                    abs_msgs.append((destino_start, mido.Message('control_change', channel=canal_destino, control=cc, value=origem_props[p])))
            for p, addr in (("Grave", 0x72), ("Agudo", 0x73)):
                if p in propriedades_diferentes:
                    abs_msgs.append((destino_start, mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, canal_destino, addr, origem_props[p]))))

            if eh_aba_atual:
                self.rebuild_from_abs_list(abs_msgs)
                for p in propriedades_diferentes:
                    self.enviar_midi_param(p, origem_props[p], canal_destino)
            else:
                estado['merged_track_cache'] = self._abs_list_para_delta_track(abs_msgs)
                estado['sections_info'] = self._secoes_de_track(estado['merged_track_cache'])
                sections_info = estado['sections_info']

            # 4. CASM da seção de destino - copiado como está (sem
            # transpor), só forçando "Redirecionar Para" a apontar pro
            # próprio canal de destino.
            if regra_origem is not None:
                if eh_aba_atual:
                    casm_destino_secao = self.obter_casm_da_secao(nome_secao_destino, criar_se_ausente=True)
                else:
                    biblioteca = estado.setdefault('casm_rules_by_section', {})
                    if biblioteca is None:
                        biblioteca = {}
                        estado['casm_rules_by_section'] = biblioteca
                    casm_destino_secao = self._obter_ou_criar_casm_em_biblioteca(biblioteca, nome_secao_destino)
                nova_regra = copy.deepcopy(regra_origem)
                nova_regra['dst'] = canal_destino
                casm_destino_secao[canal_destino] = nova_regra

            if not eh_aba_atual:
                estado['dirty'] = True
                self.abas[destino_aba_idx]['titulo'] = self.titulo_da_aba(estado)

            feitos += 1

        if feitos > 0:
            self.update_mixer_list()
        return feitos, pulados

    def build_full_section_list(self, fonte=None):
        # `fonte` (opcional): usa esta lista em vez de `self.sections_info`
        # como base - permite reordenar pra canônica SEM nunca deixar
        # `self.sections_info` visível no meio do caminho na ordem física
        # (ver rebuild_sections_from_cache: um `midi_worker` rodando numa
        # thread de fundo lê `self.main.sections_info[idx]` continuamente,
        # com `idx` na numeração CANÔNICA - se ele lesse bem no instante em
        # que `self.sections_info` só tivesse passado pela ordem física
        # (mais curta/diferente), `idx` apontaria pra fora da lista -
        # exatamente o "IndexError: list index out of range" real que
        # apareceu no erros.log do Michel).
        found = {s['name'].strip().lower(): s for s in (fonte if fonte is not None else self.sections_info)}
        full = []
        for name in YAMAHA_SECTION_ORDER:
            key = name.lower()
            if key in found:
                item = dict(found[key])
                item['present'] = True
                item['display_name'] = item['name']
            else:
                item = {'name': name, 'display_name': f"{name} (vazio)", 'start': None, 'end': None, 'present': False}
            full.append(item)
        return full

    def refresh_section_list(self, select_first=True, forcar_idx=None):
        old_sel = self.sectionList.GetSelection()
        old_str = self.sectionList.GetStringSelection() if old_sel != wx.NOT_FOUND else ""
        self.sections_info = self.build_full_section_list()
        self.sectionList.Clear()
        for s in self.sections_info: self.sectionList.Append(s['display_name'])
        if self.sections_info:
            if forcar_idx is not None and 0 <= forcar_idx < len(self.sections_info):
                self.sectionList.SetSelection(forcar_idx)
            elif select_first: self.sectionList.SetSelection(0)
            else:
                new_sel = self.sectionList.FindString(old_str)
                if new_sel != wx.NOT_FOUND: self.sectionList.SetSelection(new_sel)
                elif old_sel != wx.NOT_FOUND and old_sel < len(self.sections_info): self.sectionList.SetSelection(old_sel)
                else: self.sectionList.SetSelection(0)
            self.prepare_section_cache()

    def OnNewStyle(self, event):
        foco_antes = wx.Window.FindFocus()
        dlg = StyleSettingsDialog(self, self.beats_per_measure)
        if dlg.ShowModal() == wx.ID_OK:
            self.criar_aba()
            self.reset_fisico_teclado()
            self.beats_per_measure = dlg.GetValues()
            new_mid = mido.MidiFile(ticks_per_beat=480)
            new_mid.type = 0
            track = mido.MidiTrack()
            new_mid.tracks.append(track)
            tpq = new_mid.ticks_per_beat
            tpm = tpq * self.beats_per_measure
            
            track.append(mido.MetaMessage('time_signature', numerator=self.beats_per_measure, denominator=4, time=0))
            track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
            track.append(mido.MetaMessage('marker', text='SFF2', time=0))
            
            # Os mesmos 4 SysEx desconhecidos que aparecem em todo arquivo real
            # de estilo já analisado, na mesma posição (antes do SInt).
            track.append(mido.Message('sysex', data=(0x43, 0x76, 0x1A, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01), time=0))
            track.append(mido.Message('sysex', data=(0x43, 0x73, 0x39, 0x11, 0x00, 0x46, 0x00), time=0))
            track.append(mido.Message('sysex', data=(0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00), time=0))
            track.append(mido.Message('sysex', data=(0x43, 0x73, 0x01, 0x51, 0x05, 0x00, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00), time=0))
            
            track.append(mido.MetaMessage('marker', text='SInt', time=0))
            
            msg_gm_reset = mido.Message('sysex', data=(0x7E, 0x7F, 0x09, 0x01), time=0)
            msg_xg_reset = mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00), time=192)
            track.append(msg_gm_reset)
            track.append(msg_xg_reset)
            
            from MHS_Utils import CANAL_BATERIA_1, CANAL_BATERIA_2
            
            # A rajada é agrupada por TIPO de mensagem (todos os Bank MSB juntos,
            # depois todos os Bank LSB, depois todos os Patch) - exatamente como
            # o próprio SX600 grava, e não canal por canal como fazíamos antes.
            for ch in range(16):
                bank = 16256 if ch in (CANAL_BATERIA_1, CANAL_BATERIA_2) else 0
                t = 192 if ch == 0 else 0
                track.append(mido.Message('control_change', channel=ch, control=0, value=bank // 128, time=t))
            for ch in range(16):
                bank = 16256 if ch in (CANAL_BATERIA_1, CANAL_BATERIA_2) else 0
                t = 5 if ch == 0 else 0
                track.append(mido.Message('control_change', channel=ch, control=32, value=bank % 128, time=t))
            for ch in range(16):
                patch = 1 if ch in (CANAL_BATERIA_1, CANAL_BATERIA_2) else 0
                t = 5 if ch == 0 else 0
                track.append(mido.Message('program_change', channel=ch, program=patch, time=t))
                
            track.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_1, 0x07, 0x03), time=5))
            track.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_2, 0x07, 0x02), time=0))
            
            track.append(mido.MetaMessage('marker', text='Main A', time=tpm))
            track.append(mido.MetaMessage('text', text='fn:Main A\x00', time=0))
            track.append(mido.MetaMessage('end_of_track', time=tpm))
            
            self.current_midi_data = new_mid
            self.merged_track_cache = mesclar_tracks_rapido(new_mid.tracks)
            self.current_file_path = None
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.dirty = False
            
            # SEM CASM AINDA: um estilo vazio de verdade não tem esse bloco -
            # ele só passa a existir quando algo realmente precisar dele.
            self.raw_casm_data = b''
            self.casm_rules_by_section = {}
            self.casm_rules = self.get_default_casm_rules()
            
            for ch in range(16):
                bank = 16256 if ch in (CANAL_BATERIA_1, CANAL_BATERIA_2) else 0
                patch = 1 if ch in (CANAL_BATERIA_1, CANAL_BATERIA_2) else 0
                self.canais[ch] = {"Nome": f"Canal {ch+1}", "Mute": False, "Solo": False, "Arm": False, "Volume": 100, "Pan": 64, "Expression": 127, "Bank": bank, "Patch": patch, "Reverb": 0, "Chorus": 0, "Grave": 64, "Agudo": 64}
            import copy
            self.canais_ao_carregar = copy.deepcopy(self.canais)
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            self.send_initial_setup()
            falar(f"Novo Estilo Criado com Matriz Yamaha Oficial.", imediato=True)
            self.sincronizar_aba_atual()
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()
    def OnToggleMetronome(self, event):
        self.use_metronome = self.metro_item.IsChecked()
        falar("Metrônomo ligado" if self.use_metronome else "Metrônomo desligado", imediato=True)

    def salvar_arquivo_sty(self, path):
        if not self.current_midi_data: return
        import os
        from MHS_Utils import falar
        try:
            import mido
            new_mid = mido.MidiFile(ticks_per_beat=self.current_midi_data.ticks_per_beat)
            new_mid.type = 0
            track = mido.MidiTrack()
            new_mid.tracks.append(track)
            
            primeiro_marker_tick = float('inf')
            temp_abs = 0
            for m in self.merged_track_cache:
                temp_abs += m.time
                if m.type in ['marker', 'cuepoint'] and getattr(m, 'text', '') not in ['SFF1', 'SFF2', 'SInt']:
                    primeiro_marker_tick = temp_abs
                    break
            if primeiro_marker_tick == float('inf'):
                primeiro_marker_tick = 0
            
            from MHS_Utils import CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS, CANAL_BATERIA_1, CANAL_BATERIA_2
            
            viu_bank_msb = set()
            viu_bank_lsb = set()
            viu_patch = set()
            viu_volume = set()
            viu_pan = set()
            viu_expression = set()
            viu_reverb = set()
            viu_chorus = set()
            viu_grave = set()
            viu_agudo = set()
            viu_part_mode = set()
            
            base = getattr(self, 'canais_ao_carregar', None)
            
            # A ORDEM ORIGINAL É SAGRADA: cada evento que já existia no arquivo
            # carrega o seu índice original (i) - isso garante que, no mesmo
            # instante, a ordem em que as coisas já estavam nunca é embaralhada
            # (é assim que SFF2 -> SysEx -> SInt se mantém correto).
            abs_events = []
            curr_t = 0
            tick_final = 0
            for i, msg in enumerate(self.merged_track_cache):
                curr_t += msg.time
                tick_final = curr_t
                
                if curr_t <= primeiro_marker_tick and hasattr(msg, 'channel'):
                    ch = msg.channel
                    if 0 <= ch <= 15:
                        if msg.type == 'control_change':
                            if msg.control == CC_BANK_MSB: viu_bank_msb.add(ch)
                            elif msg.control == CC_BANK_LSB: viu_bank_lsb.add(ch)
                            elif msg.control == CC_VOLUME: viu_volume.add(ch)
                            elif msg.control == CC_PAN: viu_pan.add(ch)
                            elif msg.control == CC_EXPRESSION: viu_expression.add(ch)
                            elif msg.control == CC_REVERB: viu_reverb.add(ch)
                            elif msg.control == CC_CHORUS: viu_chorus.add(ch)
                        elif msg.type == 'program_change':
                            viu_patch.add(ch)
                            
                if curr_t <= primeiro_marker_tick and msg.type == 'sysex':
                    d = bytes(msg.data)
                    if len(d) >= 6 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] == 0x07:
                        viu_part_mode.add(d[4])
                    elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] == 0x72:
                        viu_grave.add(d[4])
                    elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] == 0x73:
                        viu_agudo.add(d[4])
                        
                if msg.type != 'end_of_track':
                    abs_events.append((curr_t, self._msg_priority(msg), 0, i, msg))

            # Usa a MESMA _msg_priority usada em qualquer outra reconstrução
            # do arquivo (Copiar/Apagar, redimensionar seção, o normalizador
            # automático ao abrir) - uma escala própria só pra cá (mais
            # grosseira: sysex sempre antes de CC/PC, sem o caso especial do
            # Voice Creator/Drum Setup) fazia o conteúdo recém-gerado aqui
            # (Bank/Volume/Grave/Agudo faltando) sair numa ordem DIFERENTE da
            # que o normalizador julga correta - toda reabertura desfazia e
            # refazia essa reordenação (não-idempotente).
            prioridade = self._msg_priority

            # Tudo que é criado agora (preenchendo o que faltava) entra numa
            # "gaveta" à parte, sempre depois de qualquer coisa original que já
            # estivesse no mesmo instante - só a ordem ENTRE essas novidades é
            # decidida pela prioridade por tipo.
            novos = []
            for ch in range(16):
                c = self.canais[ch]
                b = base[ch] if base else c
                if ch not in viu_bank_msb:
                    m = mido.Message('control_change', channel=ch, control=CC_BANK_MSB, value=c["Bank"] // 128)
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_bank_lsb:
                    m = mido.Message('control_change', channel=ch, control=CC_BANK_LSB, value=c["Bank"] % 128)
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_patch:
                    m = mido.Message('program_change', channel=ch, program=c["Patch"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_volume and c["Volume"] != b["Volume"]:
                    m = mido.Message('control_change', channel=ch, control=CC_VOLUME, value=c["Volume"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_pan and c["Pan"] != b["Pan"]:
                    m = mido.Message('control_change', channel=ch, control=CC_PAN, value=c["Pan"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_expression and c["Expression"] != b["Expression"]:
                    m = mido.Message('control_change', channel=ch, control=CC_EXPRESSION, value=c["Expression"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_reverb and c["Reverb"] != b["Reverb"]:
                    m = mido.Message('control_change', channel=ch, control=CC_REVERB, value=c["Reverb"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_chorus and c["Chorus"] != b["Chorus"]:
                    m = mido.Message('control_change', channel=ch, control=CC_CHORUS, value=c["Chorus"])
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_grave and c.get("Grave", 64) != b.get("Grave", 64):
                    m = mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x72, c.get("Grave", 64)))
                    novos.append((primeiro_marker_tick, prioridade(m), m))
                if ch not in viu_agudo and c.get("Agudo", 64) != b.get("Agudo", 64):
                    m = mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x73, c.get("Agudo", 64)))
                    novos.append((primeiro_marker_tick, prioridade(m), m))
            
            if CANAL_BATERIA_1 not in viu_part_mode:
                m = mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_1, 0x07, 0x03))
                novos.append((primeiro_marker_tick, prioridade(m), m))
            if CANAL_BATERIA_2 not in viu_part_mode:
                m = mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, CANAL_BATERIA_2, 0x07, 0x02))
                novos.append((primeiro_marker_tick, prioridade(m), m))
            
            # As novidades entram na lista principal na "gaveta" 1.
            for t, prio, m in novos:
                abs_events.append((t, prio, 1, 0, m))
                if t > tick_final: tick_final = t

            # Ordena: primeiro pelo instante, depois por _msg_priority (a
            # MESMA usada em qualquer reconstrução do arquivo) - garante que
            # conteúdo original (ex.: uma nota) que devesse vir DEPOIS de um
            # SysEx/CC recém-sintetizado no mesmo tick (a config do canal
            # nunca existiu no arquivo até este save) realmente vai pra lá,
            # em vez de manter a posição antiga só por já existir. SÓ dentro
            # da MESMA prioridade é que "original sempre antes de novo"
            # decide o empate (a gaveta), e dentro da mesma gaveta, o
            # critério de sempre (índice original, ou ordem de criação pras
            # novidades) - sem isso, o normalizador automático (que só usa
            # _msg_priority, sem conceito de gaveta) discordava do que este
            # save tinha acabado de escrever, e cada reabertura desfazia e
            # refazia a mesma reordenação (não-idempotente).
            abs_events.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
            
            last_t = 0
            for item in abs_events:
                t, msg = item[0], item[-1]
                msg.time = int(round(t - last_t))
                track.append(msg)
                last_t = t
            
            # O FIM DE FAIXA RESPEITA O INSTANTE MAIS DISTANTE que já existia no
            # arquivo original - nunca fica colado no último evento real só
            # porque não tinha mais nada depois dele.
            track.append(mido.MetaMessage('end_of_track', time=max(0, tick_final - last_t)))
            
            new_mid.save(path)
            
            dados_casm = self.patch_casm_binary()
            if dados_casm:
                if dados_casm[:4] == b'CASM':
                    tamanho_real = len(dados_casm) - 8
                    dados_casm = dados_casm[:4] + tamanho_real.to_bytes(4, 'big') + dados_casm[8:]
                with open(path, 'ab') as f_casm:
                    f_casm.write(dados_casm)
            
            self.dirty = False
            self.atualizar_titulo()
            from MHS_Utils import falar
            falar("Arquivo salvo.", imediato=True)
            
        except Exception as e: 
            from MHS_Utils import falar
            falar(f"Erro ao salvar: {str(e)}", imediato=True)
    def OnSave(self, event):
        if self.current_file_path: self.salvar_arquivo_sty(self.current_file_path)
        else: self.OnSaveAs(event)

    def OnSaveAs(self, event):
        # Mesma prioridade do OnOpen: pasta padrão fixa primeiro, senão a
        # última pasta usada.
        default_dir = self.config.get("pasta_salvar") or self.config.get("last_save_dir", "")
        foco_antes = wx.Window.FindFocus()
        dlg = wx.FileDialog(self, "Salvar Como", defaultDir=default_dir, wildcard="Estilo Yamaha (*.sty)|*.sty|Arquivo MIDI (*.mid)|*.mid", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            self.current_file_path = dlg.GetPath()
            self.config["last_save_dir"] = os.path.dirname(self.current_file_path)
            self.save_config()
            self.salvar_arquivo_sty(self.current_file_path)
            self.registrar_recente(self.current_file_path)
            falar(f"Salvo como {os.path.basename(self.current_file_path)}", imediato=True)
        self._agendar_restaurar_foco(foco_antes)
        dlg.Destroy()
    def setup_midi_in(self):
        self.midi_engine.setup_midi_in()

    def OnToggleCapturaDSP(self, event):
        self._captura_dsp_ligada = not getattr(self, '_captura_dsp_ligada', True)
        estado = "ligada" if self._captura_dsp_ligada else "desligada"
        falar(f"Captura de timbre e DSP do teclado {estado}.", imediato=True)

    def OnToggleMidiLog(self, event):
        # Liga/desliga um log de TUDO que chega pela MIDI IN (inclusive SysEx),
        # pra capturar a rajada de troca de timbre do teclado e ver o que ele
        # despeja. Grava em midi_in_log.txt ao lado do programa.
        self._log_midi_in = not getattr(self, '_log_midi_in', False)
        if self._log_midi_in:
            self._midi_log_path = os.path.join(self.base_dir, "midi_in_log.txt")
            try:
                with open(self._midi_log_path, "w", encoding="utf-8") as f:
                    f.write("# Log de MIDI de entrada - " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                falar("Registro de MIDI de entrada ligado. Mude o timbre no teclado e depois "
                      "desligue este item. O arquivo midi_in_log.txt fica na pasta do programa.",
                      imediato=True)
            except Exception:
                self._log_midi_in = False
                falar("Não consegui criar o arquivo de log.", imediato=True)
        else:
            falar("Registro de MIDI de entrada desligado.", imediato=True)

    def _aplicar_captura_dsp_teclado(self, dsp_var_antes, dsp_glob_antes, canal_antes, ch, dsp_mudou=True):
        # Roda na thread da GUI, ao fim da rajada de troca de timbre pelo
        # teclado. Sem fala nenhuma - quem já anuncia é atualizar_apos_midi_in
        # (o nome do timbre).
        if not getattr(self, 'current_midi_data', None):
            return

        # Ponto de Ctrl+Z com o estado ANTES da rajada.
        canais_antes = copy.deepcopy(self.canais)
        if 0 <= ch < len(canais_antes):
            canais_antes[ch] = canal_antes
        if len(self.undo_stack) >= 30:
            self.undo_stack.pop(0)
        self.undo_stack.append({
            "action": "Troca de Timbre (teclado)",
            "tpb": self.current_midi_data.ticks_per_beat,
            "merged_cache": [m.copy() for m in self.merged_track_cache],
            "canais": canais_antes,
            "beats": self.beats_per_measure,
            "tempo": self.current_tempo,
            "dsp_variation": dsp_var_antes,
            "dsp_global": dsp_glob_antes,
        })
        self.redo_stack.clear()

        # Banco/Peça do timbre novo têm que valer em TODAS as seções, igual
        # ao editar pelas colunas - senão a seção volta pro timbre original.
        if 0 <= ch < len(self.canais):
            self.limpar_eventos_locais(ch, "Bank")
            self.limpar_eventos_locais(ch, "Patch")

        if dsp_mudou:
            self.sincronizar_dsp_no_track()

        self.dirty = True
        self.atualizar_titulo()
        self.rebuild_sections_from_cache()
        if self.playing:
            self.force_reload_loop = True

    def enviar_midi_param(self, prop, val, canal):
        self.midi_engine.enviar_midi_param(prop, val, canal)

    def processar_roteamento(self, msg):
        return self.midi_engine.processar_roteamento(msg)
    def undo(self, event):
        if self.playing: self.OnTogglePlay(None)
        if not self.undo_stack: falar("Nada para desfazer.", imediato=True); return
        self.recorded_events = []
        for key in list(self.active_output_notes.keys()):
            ch, orig_note = key
            note_info = self.active_output_notes.pop(key)
            if self.midi_out:
                try: self.midi_out.send(mido.Message('note_off', channel=ch, note=note_info['note'], velocity=0))
                except Exception: pass
        self.redo_stack.append(self._snapshot_state("Desfazer"))
        state = self.undo_stack.pop()
        self._restore_state(state)
        falar(f"Desfeito: {state['action']}", imediato=True)
    def trigger_perf_section(self, section_name):
        found_idx = -1
        search_terms = [section_name.lower()]
        if section_name.lower() == "break": search_terms.append("fill in ba")
        for i, section in enumerate(self.sections_info):
            if any(term in section['display_name'].lower() or term in section['name'].lower() for term in search_terms):
                if "main" in section['name'].lower() and "fill" not in section['name'].lower(): self.current_main_prefix = section['name']
                found_idx = i
                break
        if found_idx != -1:
            self.sectionList.SetSelection(found_idx)
            self.prepare_section_cache()
            self.anchor_tick = 0
            falar(self.sectionList.GetString(found_idx), imediato=True)
            if not self.playing and "ending" not in section_name.lower(): self.OnTogglePlay(None)

    def OnEscPress(self, event):
        event.Skip()
    def silence_channel(self, channel):
        self.midi_engine.silence_channel(channel)
    def prepare_section_cache(self, force_idx=None):
        if wx.IsMainThread():
            idx = force_idx if force_idx is not None else self.sectionList.GetSelection()
            self._active_section_idx = idx
        else:
            idx = force_idx if force_idx is not None else getattr(self, '_active_section_idx', 0)
            
        secs = getattr(self, 'sections_info', [])
        if idx == wx.NOT_FOUND or not secs or not (0 <= idx < len(secs)):
            self.current_section_msgs = []
            self.section_has_mid_sysex = False
            self.section_duration_seconds = 0
            return

        section = secs[idx]
        tpq = self.current_midi_data.ticks_per_beat if self.current_midi_data else 480
        if not section.get('present', False) or section.get('start') is None:
            self.current_section_msgs = []
            self.section_has_mid_sysex = False
            total_ticks = tpq * self.beats_per_measure
            self.section_duration_seconds = mido.tick2second(total_ticks, tpq, self.current_tempo)
            return
            
        msgs = []
        abs_tick = 0
        section_start_tick = section['start']
        section_end_tick = section['end']
        if section_end_tick == float('inf'): section_end_tick = sum(m.time for m in self.merged_track_cache)
        
        for msg in self.merged_track_cache:
            if abs_tick >= section_end_tick: break
            if abs_tick >= section_start_tick:
                temp_msg = msg.copy()
                if not msgs: temp_msg.time = 0
                msgs.append(temp_msg)
            abs_tick += msg.time
            
        self.current_section_msgs = msgs
        total_ticks = max(0, section_end_tick - section_start_tick)
        self.section_duration_seconds = mido.tick2second(total_ticks, tpq, self.current_tempo)

        # Sysex de cabeça de seção (Bank/Patch/DSP/Drum Setup) não precisa
        # ser reenviado a cada repetição NATURAL do mesmo loop - o teclado já
        # recebeu esse valor na passagem anterior e nada no meio da seção o
        # altera. Mas ALGUMAS seções (ex.: Balada MHS.sty, "Main D") têm um
        # sysex de verdade deslocado bem depois da cabeça (>TOLERANCE ticks
        # de distância dos outros) - aí não dá pra pular, tem que continuar
        # reenviando tudo a cada passagem, como sempre foi. `midi_worker` usa
        # esta flag pra decidir, por seção, se pode aplicar o atalho.
        TOLERANCE = 4
        sysex_ticks = []
        run_tick = 0
        for m in msgs:
            run_tick += m.time
            if m.type == 'sysex':
                sysex_ticks.append(run_tick)
        self.section_has_mid_sysex = bool(sysex_ticks) and (max(sysex_ticks) - min(sysex_ticks) > TOLERANCE)

    def get_current_absolute_tick(self):
        if wx.IsMainThread():
            idx = self.sectionList.GetSelection()
            self._active_section_idx = idx
        else:
            idx = getattr(self, '_active_section_idx', 0)
            
        secs = getattr(self, 'sections_info', [])
        if idx == wx.NOT_FOUND or not secs or not (0 <= idx < len(secs)): return 0
        section = secs[idx]
        base = section.get('start', 0)
        if base is None: base = 0
        if not self.playing: return int(round(base + self.anchor_tick))
        return int(round(base + self.current_accumulated_ticks))
    def OnTogglePlay(self, event):
        if self.playing:
            self.playing = False
            self.paused = False
            self.current_accumulated_ticks = self.anchor_tick
            self.panic_reset()
            self.active_output_notes.clear()
            from MHS_Utils import falar
            falar("Parou", imediato=True)
            for win in wx.GetTopLevelWindows():
                if type(win).__name__ == "EventListDialog" and hasattr(win, 'set_playhead_tick'):
                    wx.CallAfter(win.set_playhead_tick, self.anchor_tick)
            if getattr(self, 'gravando', False) or getattr(self, 'recorded_events', []):
                self.gravando = False
                self.aplicar_gravacao()
        else:
            if not getattr(self, 'current_midi_data', None) or not getattr(self, 'midi_out', None): return
            self.prepare_section_cache()
            self.last_idx = self.sectionList.GetSelection()
            for win in wx.GetTopLevelWindows():
                if type(win).__name__ == "EventListDialog" and hasattr(win, 'get_playhead_tick'):
                    tick = win.get_playhead_tick()
                    if tick is not None: self.anchor_tick = tick
            self.current_accumulated_ticks = self.anchor_tick
            self.paused = False
            self.playing = True
            # A configuração completa (Banco/Patch/CC/Drum Setup de todos os
            # canais) já foi mandada uma vez no carregamento do arquivo, e
            # qualquer edição depois disso já se atualiza ao vivo sozinha - por
            # isso o Play não precisa mais reenviar tudo de novo, e sai na hora.
            if getattr(self, 'gravando', False): self.save_state("Gravação")
            from MHS_Utils import falar
            falar("Tocando", imediato=True)
            self.midi_engine.start_worker()
    def OnTogglePause(self, event):
        if self.playing:
            self.anchor_tick = self.current_accumulated_ticks
            self.playing = False
            self.paused = True
            self.panic_reset()
            self.active_output_notes.clear()
            falar("Pausado", imediato=True)
            for win in wx.GetTopLevelWindows():
                if type(win).__name__ == "EventListDialog" and hasattr(win, 'set_playhead_tick'):
                    wx.CallAfter(win.set_playhead_tick, self.anchor_tick)
            if getattr(self, 'gravando', False) or getattr(self, 'recorded_events', []):
                self.gravando = False
                self.aplicar_gravacao()
        else: self.OnTogglePlay(None)

    def OnOpenSettings(self, event):
        try:
            dlg = SettingsDialog(self, self.config, VERSAO_APP, REPO_GITHUB)
            if dlg.ShowModal() == wx.ID_OK:
                # Merge, NUNCA substituição do dict inteiro - GetValues() só
                # conhece os campos desta própria tela (MIDI/Instrumentos/
                # Pastas/Atualizações); um "self.config = ..." aqui apagaria
                # silenciosamente qualquer outra chave (changelog_versao_
                # mostrada, last_open_dir, recentes, etc.) - bug real achado
                # pelo Michel: mexer em Configurações fazia a tela de
                # Changelog voltar a aparecer sozinha a cada reabertura,
                # porque "changelog_versao_mostrada" sumia do config.json.
                self.config.update(dlg.GetValues())
                self.save_config()
                self.parse_selected_ins()
                if self.midi_out: self.midi_out.close()
                try: self.midi_out = mido.open_output(self.config["midi_out"])
                except: pass
                self.abrir_porta_metronomo()
                self.setup_midi_in()
                self.update_mixer_list()
            dlg.Destroy()
        except Exception as e:
            try:
                with open(self.log_file, "a", encoding="utf-8") as log:
                    import traceback
                    log.write(f"Erro ao abrir Configurações Gerais: {e}\n{traceback.format_exc()}\n")
            except Exception:
                pass
            falar("Erro ao abrir a tela de Configurações Gerais. Veja o arquivo erros.log.", imediato=True)

    def OnOpen(self, event):
        # Pasta padrão fixa (definida em Configurações Gerais > Pastas de
        # Trabalho) tem prioridade sobre a última pasta usada - se o Michel
        # não fixou nenhuma, cai no comportamento de sempre (lembra a última).
        default_dir = self.config.get("pasta_abrir") or self.config.get("last_open_dir", "")
        dlg = wx.FileDialog(self, "Abrir", defaultDir=default_dir, wildcard="Estilos e MIDI (*.sty;*.prs;*.mid)|*.sty;*.prs;*.mid", style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            caminho = dlg.GetPath()
            self.config["last_open_dir"] = os.path.dirname(caminho)
            self.save_config()
            self.criar_aba()
            self.load_style_data(caminho)
            self.sincronizar_aba_atual()
            self.registrar_recente(caminho)
        dlg.Destroy()

    def parse_selected_ins(self):
        self.ins_db = {}
        self.bank_names = {}
        self.ins_drum_kits = {} # Guarda os nomes das baterias
        self.ins_cc_names = {}  # Guarda os nomes dos controles (Volume, Pan, etc)
        self.patch_to_kit = {}  # Relaciona o banco/patch com o nome do kit

        idx = self.config.get("selected_ins_idx", 0)
        files = self.config.get("ins_files", [])
        if not files or idx >= len(files): return
        try:
            with open(files[idx], 'r', encoding='latin-1') as f:
                content = f.read()

            # 1. Separa o arquivo por seções
            sections = {}
            curr_sec = None
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith(';'): continue
                if line.startswith('[') and line.endswith(']'):
                    curr_sec = line[1:-1]
                    sections[curr_sec] = {}
                elif '=' in line and curr_sec:
                    k, v = line.split('=', 1)
                    sections[curr_sec][k.strip()] = v.strip()

            # 2. Pega os Bancos e Patches normais
            for b_id, m in re.findall(r'Patch\[(\d+)\]=(.+)', content):
                nome_banco = m.strip()
                b_int = int(b_id)
                self.bank_names[b_int] = nome_banco
                if nome_banco in sections:
                    self.ins_db[b_int] = {int(p): n for p, n in sections[nome_banco].items() if p.isdigit()}

            # 3. Escaneia os Controller Names (CCs)
            for sec_name, sec_data in sections.items():
                if 'Controller' in sec_name:
                    for k, v in sec_data.items():
                        if k.isdigit(): self.ins_cc_names[int(k)] = v

            # 4. Mapeia qual Banco e Patch aciona qual Bateria
            for sec_name, sec_data in sections.items():
                for k, v in sec_data.items():
                    match = re.match(r'Key\[(\d+),(\d+)\]', k)
                    if match:
                        bank, patch = int(match.group(1)), int(match.group(2))
                        self.patch_to_kit[(bank, patch)] = v

            # 5. Monta o quebra-cabeça das peças (Resolvendo o BasedOn)
            def build_kit(k_name, visited=None):
                if visited is None: visited = set()
                if k_name in visited or k_name not in sections: return {}
                visited.add(k_name)
                sec_data = sections[k_name]
                kit_map = {}
                # Yamaha escreve BasedOn e as vezes BaseOn. Pegamos os dois!
                base = sec_data.get('BasedOn') or sec_data.get('BaseOn')
                if base: kit_map.update(build_kit(base, visited))
                for k, v in sec_data.items():
                    if k.isdigit(): kit_map[int(k)] = v
                return kit_map

            for kit_name in set(self.patch_to_kit.values()):
                self.ins_drum_kits[kit_name] = build_kit(kit_name)

        except Exception as e:
            print("Erro no Scanner Supremo do INS:", e)

    def traduzir_evento_midi(self, msg, current_ch=None):
        if current_ch is None: current_ch = getattr(msg, 'channel', 0)
        
        banco = self.canais[current_ch]["Bank"] if current_ch < 16 else 0
        patch = self.canais[current_ch]["Patch"] if current_ch < 16 else 0

        from MHS_Utils import get_nome_nota, get_cc_name

        if msg.type in ['note_on', 'note_off', 'polytouch']:
            nota = msg.note
            # Pergunta pro Scanner se esse canal tá com um Kit de Bateria selecionado
            if (banco, patch) in getattr(self, 'patch_to_kit', {}):
                kit_name = self.patch_to_kit[(banco, patch)]
                if kit_name in getattr(self, 'ins_drum_kits', {}):
                    nome_peca = self.ins_drum_kits[kit_name].get(nota)
                    if nome_peca: return f"Nota {nota} ({nome_peca})"
                    
            # Se não for bateria, traz C3, D4, etc...
            return f"Nota {nota} ({get_nome_nota(nota)})"

        elif msg.type == 'control_change':
            cc = msg.control
            # Puxa do INS. Se o INS não tiver o nome, puxa o padrão do Utils.
            nome_cc = getattr(self, 'ins_cc_names', {}).get(cc)
            if not nome_cc: nome_cc = get_cc_name(cc)
            return f"CC {cc} ({nome_cc})"

        elif msg.type == 'program_change':
            prg = msg.program
            nome_patch = self.ins_db.get(banco, {}).get(prg, f"Patch {prg}")
            return f"PC {prg} ({nome_patch})"
            
        elif msg.type == 'pitchwheel':
            return "Pitch Bend"

        return str(msg.type).capitalize()
    def load_style_data(self, path):
        import os
        import mido
        import wx
        from MHS_Utils import falar, TOTAL_CANAIS, VALOR_MAX_MIDI, detune_combinar

        self.reset_fisico_teclado()
        try:
            self.raw_casm_data = b''
            with open(path, 'rb') as f:
                raw_data = f.read()
                casm_idx = raw_data.find(b'CASM')
                if casm_idx != -1: self.raw_casm_data = raw_data[casm_idx:]
                
            if not self.raw_casm_data and path.lower().endswith('.mid'):
                caminho_csm = os.path.splitext(path)[0] + '.csm'
                if os.path.exists(caminho_csm):
                    with open(caminho_csm, 'rb') as f:
                        csm_data = f.read()
                        c_idx = csm_data.find(b'CASM')
                        if c_idx != -1: self.raw_casm_data = csm_data[c_idx:]
                        else: self.raw_casm_data = csm_data
                    wx.CallAfter(falar, "Arquivo CASM associado encontrado e mesclado!", imediato=True)
                    
            mid = mido.MidiFile(path)
            self.current_midi_data = mid
            self.merged_track_cache = mesclar_tracks_rapido(mid.tracks)
            self.midi_setup_msgs = []
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.dirty = False
            self.current_file_path = path
            self.dsp_global = self._dsp_global_padrao()
            self.dsp_variation = self._dsp_variation_padrao()
            self.casm_rules = self.extract_casm(self.raw_casm_data)
            
            for ch in range(TOTAL_CANAIS):
                self.canais[ch] = {"Nome": f"Canal {ch+1}", "Mute": False, "Solo": False, "Arm": False, "Volume": 100, "Pan": 64, "Expression": VALOR_MAX_MIDI, "Bank": 0, "Patch": 0, "Reverb": 0, "Chorus": 0, "Grave": 64, "Agudo": 64}
            detune_nibbles = {ch: [0x08, 0x00] for ch in range(TOTAL_CANAIS)}  # ver detune_combinar/detune_separar

            # A MÁGICA: Varre o arquivo para descobrir em que Tick começa a música real!
            primeiro_marker_tick = float('inf')
            temp_abs = 0
            for m in self.merged_track_cache:
                temp_abs += m.time
                if m.type in ['marker', 'cuepoint'] and getattr(m, 'text', '') not in ['SFF1', 'SFF2', 'SInt']:
                    primeiro_marker_tick = temp_abs
                    break
            
            # Se não tiver markers, assume o primeiro compasso como Setup
            if primeiro_marker_tick == float('inf'):
                primeiro_marker_tick = mid.ticks_per_beat * 4

            temp_msb = {ch: 0 for ch in range(TOTAL_CANAIS)}
            temp_lsb = {ch: 0 for ch in range(TOTAL_CANAIS)}
            nrpn_msb = {ch: None for ch in range(TOTAL_CANAIS)}
            nrpn_lsb = {ch: None for ch in range(TOTAL_CANAIS)}
            abs_t = 0
            for msg in self.merged_track_cache:
                abs_t += msg.time
                if msg.type == 'set_tempo': self.current_tempo = msg.tempo
                elif msg.type == 'time_signature': self.beats_per_measure = msg.numerator
                
                # O LEITOR NÃO AFOBADO: Lê todos os timbres espalhados ANTES da primeira seção!
                if abs_t <= primeiro_marker_tick:
                    if msg.type == 'control_change':
                        if msg.control == 0: 
                            temp_msb[msg.channel] = msg.value
                            self.canais[msg.channel]["Bank"] = (temp_msb[msg.channel] * 128) + temp_lsb[msg.channel]
                        elif msg.control == 32: 
                            temp_lsb[msg.channel] = msg.value
                            self.canais[msg.channel]["Bank"] = (temp_msb[msg.channel] * 128) + temp_lsb[msg.channel]
                        elif msg.control == 7: self.canais[msg.channel]["Volume"] = msg.value
                        elif msg.control == 10: self.canais[msg.channel]["Pan"] = msg.value
                        elif msg.control == 11: self.canais[msg.channel]["Expression"] = msg.value
                        elif msg.control == 91: self.canais[msg.channel]["Reverb"] = msg.value
                        elif msg.control == 93: self.canais[msg.channel]["Chorus"] = msg.value
                        elif msg.control == 5:
                            # Portamento Time (CC5) - o mecanismo que REALMENTE
                            # funciona no teclado (confirmado testando pelo
                            # Michel; os endereços SysEx 0x67/0x68 do Data List
                            # não tinham efeito nenhum). CC65 (Portamento
                            # Switch) é só DERIVADO daqui (Ligado se > 0) -
                            # nunca precisa virar uma chave própria.
                            self.canais[msg.channel].setdefault("VoiceCreator", {})["porta_time"] = msg.value
                        elif msg.control == 94 and msg.value > 0:
                            # CC94 = "Variation Send Level" (mesma família do
                            # Reverb Send/CC91 e Chorus Send/CC93) - confirmado
                            # em dois arquivos genuínos (Teclado.sty, Rock.sty):
                            # é ASSIM que vários canais mandam sinal pro mesmo
                            # efeito de inserção, não pela SysEx de Multi Part
                            # que eu tinha tentado antes (essa nunca funcionou
                            # no teclado real).
                            self.dsp_variation['chs'][msg.channel] = msg.value
                        elif msg.control == 99: nrpn_msb[msg.channel] = msg.value
                        elif msg.control == 98: nrpn_lsb[msg.channel] = msg.value
                        elif msg.control == 6:
                            # Drum Setup via NRPN (Guia 3) - só os endereços de
                            # bateria conhecidos (14H-35H do Data List); outro
                            # uso de NRPN no mesmo canal não entra aqui.
                            n_msb, n_lsb = nrpn_msb[msg.channel], nrpn_lsb[msg.channel]
                            if n_msb in DRUM_NRPN_MSBS and n_lsb is not None:
                                self.canais[msg.channel].setdefault("DrumParamsNRPN", {})[(n_lsb, n_msb)] = msg.value
                        self.midi_setup_msgs.append(msg)
                    elif msg.type == 'program_change':
                        self.canais[msg.channel]["Patch"] = msg.program
                        self.midi_setup_msgs.append(msg)
                    elif msg.type in ['pitchwheel', 'sysex']:
                        self.midi_setup_msgs.append(msg)
                        if msg.type == 'sysex':
                            d = bytes(msg.data)
                            if len(d) >= 6 and d[0] == 0x43 and d[2] == 0x4C and d[3] in (0x30, 0x31):
                                canal_bateria = 9 if d[3] == 0x30 else 8
                                nota = d[4]
                                if len(d) >= 10 and d[5] == 0x70:
                                    self.canais[canal_bateria].setdefault("CustomDrumMap", {})
                                    self.canais[canal_bateria]["CustomDrumMap"][nota] = {
                                        'bank': d[6] * 128 + d[7],
                                        'patch': d[8],
                                        'dest_note': d[9]
                                    }
                                elif len(d) >= 7:
                                    param_id = d[5]
                                    valor = d[6]
                                    self.canais[canal_bateria].setdefault("DrumParams", {})
                                    self.canais[canal_bateria]["DrumParams"][(nota, param_id)] = valor
                            elif len(d) >= 6 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x02 and d[4] == 0x01:
                                self._ler_sysex_dsp(d)
                            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] == 0x14:
                                # Multi Part, endereço 0x14 = "Variation Send Level" do
                                # canal d[4] - confirmado no Data List oficial do
                                # PSR-SX600. É assim que vários canais mandam sinal pro
                                # MESMO efeito de inserção ao mesmo tempo (com a
                                # Conexão em SYSTEM, ver _ler_sysex_dsp addr 0x5A) -
                                # cada canal com envio > 0 entra no dicionário com o
                                # nível de verdade (não fixo em 127 igual antes).
                                ch_envio = d[4]
                                if d[6] > 0 and 0 <= ch_envio < TOTAL_CANAIS:
                                    self.dsp_variation['chs'][ch_envio] = d[6]
                            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in (0x72, 0x73):
                                # Multi Part, endereço 0x72 = Grave (Bass Gain) e
                                # 0x73 = Agudo (Treble Gain) do canal d[4] - EQ de
                                # 2 bandas por canal, 64 = centro/neutro (igual o
                                # Pan). Achado comparando um ritmo original com a
                                # edição de um cliente/programador terceiro.
                                ch_eq = d[4]
                                if 0 <= ch_eq < TOTAL_CANAIS:
                                    self.canais[ch_eq]["Grave" if d[5] == 0x72 else "Agudo"] = d[6]
                            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in (0x09, 0x0A):
                                # Detune: 2 bytes separados no fio (cada um só
                                # um nibble), 1 valor combinado só no modelo -
                                # ver detune_combinar em MHS_Utils.py.
                                ch_vc = d[4]
                                if 0 <= ch_vc < TOTAL_CANAIS:
                                    par = detune_nibbles[ch_vc]
                                    if d[5] == 0x09: par[0] = d[6] & 0x0F
                                    else: par[1] = d[6] & 0x0F
                                    self.canais[ch_vc].setdefault("VoiceCreator", {})
                                    self.canais[ch_vc]["VoiceCreator"][0x09] = detune_combinar(par[0], par[1])
                            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in VOICE_CREATOR_ADDRS:
                                # Multi Part, endereços da Síntese XG (Note Shift,
                                # Detune, Filtro, EG, LFO, Roda/Alavanca) - o
                                # timbre editado pelo Voice Creator deste canal (d[4]).
                                ch_vc = d[4]
                                if 0 <= ch_vc < TOTAL_CANAIS:
                                    self.canais[ch_vc].setdefault("VoiceCreator", {})
                                    self.canais[ch_vc]["VoiceCreator"][d[5]] = d[6]
                            elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x0A and d[5] in VOICE_CREATOR_ADDRS_0A:
                                # Portamento (Mono Priority/Modo/Modo do Tempo) -
                                # bloco SEPARADO 0x0A, não o 0x08 de sempre (ver
                                # comentário perto de VOICE_CREATOR_PARAMS_0A em
                                # MHS_Dialogs.py).
                                ch_vc = d[4]
                                if 0 <= ch_vc < TOTAL_CANAIS:
                                    self.canais[ch_vc].setdefault("VoiceCreator", {})
                                    self.canais[ch_vc]["VoiceCreator"][d[5]] = d[6]

            # O Grave/Agudo às vezes só existe DENTRO das seções, nunca na
            # Área de Configuração (achado comparando um ritmo original com
            # a edição de um cliente/programador terceiro - o editor dele
            # nunca escreve isso na Área de Configuração, só reafirma seção
            # por seção). Sem esta segunda varredura, no ARQUIVO INTEIRO
            # (sem o limite de primeiro_marker_tick de cima), o canal
            # ficava mostrando 64 (padrão) na lista de canais mesmo estando
            # bem grave/agudo de verdade.
            nrpn_socorro = {}
            curr_t = 0
            for msg in self.merged_track_cache:
                curr_t += msg.time
                if msg.type == 'control_change' and msg.control == 5:
                    # Portamento Time (CC5), mesma varredura de socorro - o
                    # mecanismo que funciona de verdade (ver comentário na
                    # 1ª varredura, mais acima).
                    if 0 <= msg.channel < TOTAL_CANAIS:
                        self.canais[msg.channel].setdefault("VoiceCreator", {})["porta_time"] = msg.value
                    continue
                if msg.type == 'control_change' and 0 <= msg.channel < TOTAL_CANAIS:
                    # Sound Controllers (Cutoff/Resonance/Attack/Decay/Release/
                    # Vibrato) como CC 71-78 e NRPN 01 xx - o jeito que o
                    # próprio SX grava (ver _VC_PARA_CC).
                    from MHS_MidiEngine import _CC_SOUND_MP, _NRPN_SOUND_MP
                    st = nrpn_socorro.setdefault(msg.channel, {'msb': None, 'lsb': None})
                    if msg.control in _CC_SOUND_MP:
                        self.canais[msg.channel].setdefault("VoiceCreator", {})[_CC_SOUND_MP[msg.control]] = msg.value
                    elif msg.control == 99:
                        st['msb'] = msg.value
                        st['lsb'] = None
                    elif msg.control == 98:
                        st['lsb'] = msg.value
                    elif msg.control == 6 and st['msb'] is not None and st['lsb'] is not None:
                        end_vc = _NRPN_SOUND_MP.get((st['msb'], st['lsb']))
                        if end_vc is not None:
                            self.canais[msg.channel].setdefault("VoiceCreator", {})[end_vc] = msg.value
                if msg.type != 'sysex':
                    continue
                d = bytes(msg.data)
                if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in (0x72, 0x73):
                    ch_eq = d[4]
                    if 0 <= ch_eq < TOTAL_CANAIS:
                        self.canais[ch_eq]["Grave" if d[5] == 0x72 else "Agudo"] = d[6]
                elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in (0x09, 0x0A):
                    ch_vc = d[4]
                    if 0 <= ch_vc < TOTAL_CANAIS:
                        par = detune_nibbles[ch_vc]
                        if d[5] == 0x09: par[0] = d[6] & 0x0F
                        else: par[1] = d[6] & 0x0F
                        self.canais[ch_vc].setdefault("VoiceCreator", {})
                        self.canais[ch_vc]["VoiceCreator"][0x09] = detune_combinar(par[0], par[1])
                elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] in VOICE_CREATOR_ADDRS:
                    # Mesma varredura de socorro pro Voice Creator: um editor de
                    # terceiro pode reafirmar o timbre só seção por seção, nunca
                    # na Área de Configuração.
                    ch_vc = d[4]
                    if 0 <= ch_vc < TOTAL_CANAIS:
                        self.canais[ch_vc].setdefault("VoiceCreator", {})
                        self.canais[ch_vc]["VoiceCreator"][d[5]] = d[6]
                elif len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x0A and d[5] in VOICE_CREATOR_ADDRS_0A:
                    # Portamento (Mono Priority/Modo/Modo do Tempo), mesma
                    # varredura de socorro - bloco 0x0A, não 0x08.
                    ch_vc = d[4]
                    if 0 <= ch_vc < TOTAL_CANAIS:
                        self.canais[ch_vc].setdefault("VoiceCreator", {})
                        self.canais[ch_vc]["VoiceCreator"][d[5]] = d[6]

            import copy
            self.canais_ao_carregar = copy.deepcopy(self.canais)
            
            self.atualizar_titulo()
            self.rebuild_sections_from_cache()
            self.send_initial_setup()
            falar(f"Estilo carregado. Compasso {self.beats_per_measure} por 4.", imediato=True)
            
        except Exception as e: 
            falar(f"Erro ao carregar o estilo: {str(e)}", imediato=True)
            with open(self.log_file, "a", encoding="utf-8") as log:
                log.write(f"Erro fatal ao abrir {path}: {e}\n")
    def send_initial_setup(self):
        self.midi_engine.send_initial_setup()
    def panic_reset(self):
        self.midi_engine.panic_reset()
    def reset_fisico_teclado(self):
        self.midi_engine.reset_fisico_teclado()
    def on_f3_panic(self, event=None):
        # F3 - trazido do MHS MIDI Sequencer: manda Note Off/Sustain Off em
        # todos os canais (nota presa não some sozinha), sem mexer em
        # Bank/Patch/CC como o reset físico completo faz.
        self.panic_reset()
        falar("Notas desligadas.", imediato=True)
    def toggle_local_control(self, event=None):
        ligado = self.midi_engine.toggle_local_control()
        estado = "Ligado" if ligado else "Desligado"
        falar(f"Som do Teclado (Local Control) {estado}", imediato=True)
    def contar_estado(self, prop, nome_estado):
        # Ctrl+Shift+F5/F6/F7 - trazido do MHS MIDI Sequencer: fala quais
        # canais estão com Mute/Solo/Arm ativado agora, sem mudar nada.
        if not self.canais:
            return
        canais_ativos = [i + 1 for i, c in enumerate(self.canais) if c.get(prop, False)]
        count = len(canais_ativos)
        if count == 0:
            falar(f"0 canais {nome_estado}.", imediato=True)
            return
        ranges = []
        start = canais_ativos[0]
        prev = canais_ativos[0]
        for n in canais_ativos[1:]:
            if n == prev + 1:
                prev = n
            else:
                ranges.append(str(start) if prev == start else (f"{start}, {prev}" if prev == start + 1 else f"{start} ao {prev}"))
                start = n
                prev = n
        ranges.append(str(start) if prev == start else (f"{start}, {prev}" if prev == start + 1 else f"{start} ao {prev}"))
        texto_canais = ", ".join(ranges)
        if count == 1:
            nome_sing = nome_estado[:-1] if nome_estado.endswith('s') else nome_estado
            falar(f"1 canal {nome_sing}: {texto_canais}", imediato=True)
        else:
            falar(f"{count} canais {nome_estado}: {texto_canais}", imediato=True)
    def limpar_estado(self, prop, nome_acao):
        # Alt+F5/F6/F7 - trazido do MHS MIDI Sequencer: desliga Mute/Solo/
        # Arm de TODOS os canais de uma vez. Mute/Solo/Arm são estado de
        # audição ao vivo (não fazem parte do arquivo salvo - ver
        # toggle_propriedade_direta), então isso não mexe em self.dirty.
        if not self.canais:
            return
        mudou = False
        for c in self.canais:
            if c.get(prop, False):
                c[prop] = False
                mudou = True
        if mudou:
            self.update_mixer_list()
            falar(f"Todos os {nome_acao}.", imediato=True)
        else:
            falar(f"Nenhum canal estava com {prop} ativado.", imediato=True)
    def enviar_dsp_global(self):
        self.midi_engine.enviar_dsp_global()
    def enviar_dsp_variation(self):
        self.midi_engine.enviar_dsp_variation()

    def _ler_sysex_dsp(self, d):
        # Lê um SysEx do bloco 02 01 (Effect Block) achado no cabeçalho do
        # arquivo carregado e preenche dsp_global/dsp_variation - endereços
        # confirmados contra o MHS MIDI Sequencer e o Força.sty genuíno.
        #
        # IMPORTANTE: só o endereço do TIPO (0x00 Reverb, 0x20 Chorus, 0x40
        # Variation/0x5B Conexão) liga o 'active' - um parâmetro solto (ex:
        # 0x02) sem o Tipo junto NÃO é prova de que o Reverb/Chorus global
        # está de verdade configurado. Sem essa blindagem, um byte qualquer
        # do cabeçalho (visto no Força.sty, endereço 0x02, que nem é do
        # Reverb - é algo do próprio Auto Wah que ainda não identificamos)
        # ativava o DSP Global sozinho e mandava Chorus com valor inventado
        # pro teclado, desafinando tudo.
        addr = d[5]
        if addr == 0x00 and len(d) >= 8:
            self.dsp_global['active'] = True
            vals = [v for _, v in REV_MSB_LIST]
            self.dsp_global['rev_msb_idx'] = vals.index(d[6]) if d[6] in vals else 1
            self.dsp_global['rev_lsb_idx'] = d[7]
        elif addr == 0x0C and len(d) >= 7:
            self.dsp_global['rev_ret'] = d[6]
        elif addr in REV_PARAM_INDEX and len(d) >= 7:
            self.dsp_global['rev_p'][REV_PARAM_INDEX[addr]] = d[6]
        elif addr == 0x20 and len(d) >= 8:
            self.dsp_global['active'] = True
            vals = [v for _, v in CHO_MSB_LIST]
            self.dsp_global['cho_msb_idx'] = vals.index(d[6]) if d[6] in vals else 1
            self.dsp_global['cho_lsb_idx'] = d[7]
        elif addr == 0x2C and len(d) >= 7:
            self.dsp_global['cho_ret'] = d[6]
        elif addr in CHO_PARAM_INDEX and len(d) >= 7:
            self.dsp_global['cho_p'][CHO_PARAM_INDEX[addr]] = d[6]
        elif addr == 0x5B and len(d) >= 7:
            # "Part Number" da Variation - usado por um arquivo genuíno de
            # canal único (modo Conexão=INSERTION, ex: Força.sty do Alex
            # Oliveira). Vira mais um canal na lista 'chs', do mesmo jeito
            # que os canais recebidos via Multi Part 0x14 (Conexão=SYSTEM,
            # ver load_style_data) - as duas formas convivem na leitura.
            self.dsp_variation['active'] = True
            if d[6] != 0x7F:
                self.dsp_variation['chs'][d[6]] = 127
        elif addr == 0x40 and len(d) >= 8:
            self.dsp_variation['active'] = True
            vals = [v for _, v in VARIATION_EFEITOS_LIST]
            self.dsp_variation['msb_val'] = d[6]
            self.dsp_variation['msb_idx'] = vals.index(d[6]) if d[6] in vals else 0
            self.dsp_variation['lsb_idx'] = d[7]
        elif addr == 0x54 and len(d) >= 8:
            # Esse endereço serve tanto pra Return quanto pro Param 10 (mesmo
            # atalho do sequenciador) - tratamos sempre como Return.
            self.dsp_variation['ret'] = d[7]
        elif addr in OFFSETS_VAR_2BYTES and len(d) >= 8:
            self.dsp_variation['p'][OFFSETS_VAR_2BYTES.index(addr)] = d[6] * 128 + d[7]
        elif addr in OFFSETS_VAR_1BYTE and len(d) >= 7:
            self.dsp_variation['p'][10 + OFFSETS_VAR_1BYTE.index(addr)] = d[6]

    def sincronizar_dsp_no_track(self):
        # Wrapper com log em arquivo: uma exceção aqui (ex: um byte de SysEx
        # fora do intervalo 0-127) antes travava tudo silenciosamente - o
        # app é um .exe sem console, então uma exceção não tratada em wx
        # simplesmente some, sem crash visível e sem gravar nada. Isso já
        # pegou um bug real (lsb_idx fora do intervalo da lista de presets),
        # então fica como rede de segurança permanente.
        try:
            self._sincronizar_dsp_no_track_impl()
        except Exception:
            import traceback
            debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dsp_debug.log")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write("Exceção em sincronizar_dsp_no_track:\n")
                f.write(traceback.format_exc())
                f.write("\n")
            raise

    def _sincronizar_dsp_no_track_impl(self):
        # Reconstrói, do zero, todo SysEx do bloco 02 01 no cabeçalho do
        # arquivo (merged_track_cache e midi_setup_msgs) a partir do que está
        # em dsp_global/dsp_variation agora - chamado sempre que as telas de
        # DSP fecham com OK, pra nunca sobrar um valor antigo conflitando com
        # o novo no arquivo salvo.
        def eh_dsp(msg):
            # CC94 = "Variation Send Level" por canal (confirmado em
            # arquivos genuínos - Teclado.sty, Rock.sty) - a SysEx de Multi
            # Part que eu tinha tentado antes (bloco 08, endereço 0x14)
            # nunca funcionou no teclado real; fica só reconhecida abaixo
            # pra limpar lixo de versões antigas do programa.
            if msg.type == 'control_change' and msg.control == 94: return True
            if msg.type != 'sysex': return False
            d = bytes(msg.data)
            if len(d) >= 5 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x02 and d[4] == 0x01: return True
            if len(d) >= 6 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[5] == 0x14: return True
            # Lixo de uma versão antiga do programa, que chegou a ter 6
            # gavetas de inserção extras (bloco 43 10 4C 03 <nn>) - esse
            # protocolo nunca existiu de verdade no PSR-SX600 (confirmado
            # no Data List oficial: só a Gaveta 1/Variation é editável) e
            # foi removido, mas arquivos salvos naquela fase ficaram com
            # esse SysEx órfão, sem ninguém mais pra reconhecer e desligar.
            # Varrer e limpar aqui garante que ele suma na próxima vez que
            # a tela de efeito for aberta e fechada.
            if len(d) >= 5 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x03: return True
            return False

        self.midi_setup_msgs = [m for m in self.midi_setup_msgs if not eh_dsp(m)]

        primeiro_marker_tick = float('inf')
        temp_abs = 0
        for m in self.merged_track_cache:
            temp_abs += m.time
            if m.type in ['marker', 'cuepoint'] and getattr(m, 'text', '') not in ['SFF1', 'SFF2', 'SInt']:
                primeiro_marker_tick = temp_abs
                break
        if primeiro_marker_tick == float('inf'):
            primeiro_marker_tick = (self.current_midi_data.ticks_per_beat if self.current_midi_data else 480) * self.beats_per_measure

        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            if curr_t <= primeiro_marker_tick and eh_dsp(msg):
                continue
            abs_msgs.append([curr_t, msg])

        novos = []
        c = self.dsp_global
        if c.get('active', False):
            r_msb = REV_MSB_LIST[c.get('rev_msb_idx', 1)][1] if c.get('rev_msb_idx', 1) < len(REV_MSB_LIST) else 1
            c_msb = CHO_MSB_LIST[c.get('cho_msb_idx', 1)][1] if c.get('cho_msb_idx', 1) < len(CHO_MSB_LIST) else 65
            dados = [
                (0x00, r_msb, c.get('rev_lsb_idx', 0)),
                (0x0C, c.get('rev_ret', 64)),
                (0x20, c_msb, c.get('cho_lsb_idx', 0)),
                (0x2C, c.get('cho_ret', 64)),
            ]
            rev_p = c.get('rev_p', [-1] * 16)
            for i in range(16):
                if rev_p[i] != -1:
                    dados.append((OFFSETS_REV_PARAMS[i], rev_p[i] & 0x7F))
            cho_p = c.get('cho_p', [-1] * 16)
            for i in range(16):
                if cho_p[i] != -1:
                    dados.append((OFFSETS_CHO_PARAMS[i], cho_p[i] & 0x7F))
            for data in dados:
                novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01) + data))
        v = self.dsp_variation
        if v.get('active', False):
            msb_val = v.get('msb_val', 0)
            # max(0, ...) protege contra um lsb_idx fora do intervalo 0-127
            # (ex: -1 do wx.NOT_FOUND, se algum controle de UI não tiver
            # seleção válida) - mido rejeita byte negativo e travava aqui,
            # abortando a função inteira antes de gravar qualquer coisa.
            lsb_val = max(0, min(127, v.get('lsb_idx', 0)))
            # Ordem Tipo -> Return -> parâmetros -> Conexão por ÚLTIMO, igual
            # ao arquivo genuíno do Alex Oliveira (ticks 318, 323, 328 no
            # Força.sty) - a conexão só acontece depois do efeito inteiro já
            # estar configurado, nunca antes.
            novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x40, msb_val, lsb_val)))
            novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x54, 0x00, v.get('ret', 64))))
            p_list = v.get('p', [-1] * 16)
            for i in range(16):
                if p_list[i] == -1:
                    continue
                if i < 10:
                    # MSB/LSB de verdade (não sempre 0x00) - as famílias de
                    # Delay/Echo/Cross Delay usam parâmetros em milissegundos
                    # (até 7150), que não cabem num byte só. Pra valores
                    # normais (<128) o resultado é idêntico a antes (MSB 0).
                    valor = max(0, min(16383, p_list[i]))
                    novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_VAR_2BYTES[i], valor // 128, valor % 128)))
                else:
                    novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_VAR_1BYTE[i - 10], p_list[i] & 0x7F)))
            chs = {ch: niv for ch, niv in v.get('chs', {}).items() if 0 <= ch < TOTAL_CANAIS}
            if len(chs) <= 1:
                # Um canal só (ou nenhum): usa o modo INSERTION com o Part
                # Number direto (0x5B) - é o único jeito confirmado de
                # verdade contra hardware real (Força.sty, Auto Wah 2 no
                # Alex Oliveira). Canal único vira 0x5B; sem canal nenhum,
                # manda 0x7F (desconectado).
                part_val = next(iter(chs), 0x7F)
                novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A, 0x00)))
                novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, part_val)))
            else:
                # Dois ou mais canais: Conexão em SYSTEM (0x5A=1) + um
                # Control Change 94 ("Variation Send Level") por canal -
                # confirmado em dois arquivos genuínos (Teclado.sty,
                # Rock.sty), mesma família do Reverb Send (CC91) e Chorus
                # Send (CC93) que já usamos. A SysEx de Multi Part que eu
                # tinha tentado antes (endereço 0x14) nunca soou no teclado
                # real - essa aqui é a de verdade.
                novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A, 0x01)))
                novos.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F)))
                for ch, niv in chs.items():
                    novos.append(mido.Message('control_change', channel=ch, control=94, value=max(0, min(127, niv))))

        # Espalha as mensagens em ticks diferentes (5 em 5), em vez de
        # empilhar tudo no mesmo instante - um arquivo genuíno do Alex
        # Oliveira (com o mesmo Auto Wah 2 funcionando de verdade no
        # teclado) faz exatamente isso (SysEx em ticks 313, 318, 323, 328,
        # nunca todas juntas). Com tudo no mesmo tick, o teclado tocando o
        # arquivo direto (sem as pausas manuais que o envio ao vivo usa)
        # não dava conta de processar todas as SysEx empilhadas e ignorava
        # parte delas - por isso o efeito não soava, mesmo com o arquivo e
        # o programa mostrando tudo certo. Fica sempre ANTES do
        # primeiro_marker_tick (nunca depois) pra continuar dentro do
        # intervalo que a leitura (abs_t <= primeiro_marker_tick) reconhece.
        n_novos = len(novos)
        for idx, msg in enumerate(novos):
            t = max(0, primeiro_marker_tick - (n_novos - idx) * 5)
            abs_msgs.append([t, msg])
            self.midi_setup_msgs.append(msg)

        abs_msgs.sort(key=lambda x: x[0])
        self.merged_track_cache = []
        last_t = 0
        for t, msg in abs_msgs:
            msg.time = int(round(t - last_t))
            self.merged_track_cache.append(msg)
            last_t = t
        self.dirty = True
        self.atualizar_titulo()

    def navegar_tempo(self, tipo):
        if not getattr(self, 'current_midi_data', None): return
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]
        tpq = getattr(self.current_midi_data, 'ticks_per_beat', 480)
        tpm = tpq * self.beats_per_measure
        section_start = sec.get('start', 0)
        section_end = sec.get('end', float('inf'))
        if section_end == float('inf'):
            section_end = sum(m.time for m in self.merged_track_cache)
            if section_end <= section_start: section_end = section_start + tpm
        section_length = section_end - section_start
        if not self.playing and tipo not in ["inicio_secao", "fim_secao"]:
            for win in wx.GetTopLevelWindows():
                if type(win).__name__ == "EventListDialog" and hasattr(win, 'get_playhead_tick'):
                    self.anchor_tick = win.get_playhead_tick()
        atual = self.current_accumulated_ticks if self.playing else self.anchor_tick
        novo_rel = atual
        if tipo == "compasso_frente": novo_rel += tpm
        elif tipo == "compasso_tras": novo_rel -= tpm
        elif tipo == "beat_frente": novo_rel += tpq
        elif tipo == "beat_tras": novo_rel -= tpq
        elif tipo == "inicio_secao":
            novo_rel = 0
            falar("Início da Seção", imediato=True)
        elif tipo == "fim_secao":
            novo_rel = section_length - 1
            if novo_rel < 0: novo_rel = 0
            falar("Fim da Seção", imediato=True)
        elif tipo == "home":
            if getattr(self, 'in_point', None) is not None and section_start <= self.in_point <= section_end:
                novo_rel = self.in_point - section_start
                falar("Ponto de Entrada", imediato=True)
            else: 
                novo_rel = 0
                falar("Início", imediato=True)
        elif tipo == "end":
            if getattr(self, 'out_point', None) is not None and section_start <= self.out_point <= section_end:
                novo_rel = self.out_point - section_start
                falar("Ponto de Saída", imediato=True)
            else: 
                novo_rel = section_length
                falar("Fim", imediato=True)
        if novo_rel < 0: novo_rel = 0
        if novo_rel >= section_length: novo_rel = section_length - 1
        self.anchor_tick = novo_rel
        self.current_accumulated_ticks = novo_rel
        if self.playing: self.force_reload_loop = True
        compasso = int(novo_rel // tpm) + 1
        beat = int((novo_rel % tpm) // tpq) + 1
        if tipo not in ["home", "end", "inicio_secao", "fim_secao"]: falar(f"Compasso {compasso}, Beat {beat}", imediato=True)
        for win in wx.GetTopLevelWindows():
            if type(win).__name__ == "EventListDialog" and hasattr(win, 'set_playhead_tick'):
                wx.CallAfter(win.set_playhead_tick, novo_rel)

    def OnExit(self, event):
        if not self.verificar_salvar_todas_abas():
            if getattr(event, 'CanVeto', lambda: False)(): event.Veto()
            return
        self.playing = False
        self.panic_reset()
        # Ao fechar o programa, devolve o Local Control Ligado - senão o
        # teclado fica mudo nas teclas físicas até alguém lembrar de
        # apertar F8 de novo.
        self.midi_engine.set_local_control(True)
        for porta in self.midi_ins:
            try: porta.close()
            except Exception: pass
        self.Destroy()

    def InitUI(self):
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        new_item = file_menu.Append(wx.ID_NEW, "&Novo Estilo\tCtrl+N")
        open_item = file_menu.Append(wx.ID_OPEN, "&Abrir Estilo\tCtrl+O")
        save_item = file_menu.Append(wx.ID_SAVE, "&Salvar\tCtrl+S")
        save_as_item = file_menu.Append(wx.ID_SAVEAS, "Salvar &Como\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        self.recent_menu = wx.Menu()
        file_menu.AppendSubMenu(self.recent_menu, "Abrir &Recente")
        file_menu.AppendSeparator()
        file_menu.Append(176, "Próxima Aba\tCtrl+Tab")
        file_menu.Append(177, "Aba Anterior\tCtrl+Shift+Tab")
        file_menu.Append(178, "Fechar Aba\tCtrl+F4")
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "Sair\tAlt+F4")

        edit_menu = wx.Menu()
        edit_menu.Append(wx.ID_UNDO, "Desfazer\tCtrl+Z")
        edit_menu.Append(wx.ID_REDO, "Refazer\tCtrl+Shift+Z")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_COPY, "Copiar Canal\tCtrl+C")
        edit_menu.Append(wx.ID_CUT, "Recortar Canal\tCtrl+X")
        edit_menu.Append(wx.ID_PASTE, "Colar Canal\tCtrl+V")
        edit_menu.Append(162, "Apagar Seleção\tDel")
        edit_menu.Append(160, "Marcar Entrada (In)\tI")
        edit_menu.Append(161, "Marcar Saída (Out)\tO")
        edit_menu.Append(163, "Limpar Marcas de Entrada/Saída e Seleção de Canais\tShift+Esc")
        edit_menu.Append(205, "Ir para a Entrada (In) ou Início\tHome")
        edit_menu.Append(206, "Ir para a Saída (Out) ou Fim\tEnd")
        edit_menu.AppendSeparator()
        edit_menu.Append(231, "Limpar Canal em Todas as Seções (Virgem)\tCtrl+Alt+R")
        edit_menu.Append(253, "Copiar Configurações do Canal para...\tCtrl+L")

        tool_menu = wx.Menu()
        tool_menu.Append(105, "Alterar Tamanho da Seção\tCtrl+T")
        tool_menu.Append(174, "Esvaziar Seção\tCtrl+Shift+R")
        tool_menu.Append(141, "Quantização Tempo Real (Input)...\tQ")
        tool_menu.Append(142, "Quantizar Offline (Canal Atual)...\tCtrl+Q")
        tool_menu.Append(150, "Event List (Lista de Eventos da Seção)\tCtrl+E")
        tool_menu.Append(170, "Drum Setup (Canal Selecionado)\tCtrl+D")
        tool_menu.Append(172, "Voice Creator (Edição de Timbre)...\tCtrl+Shift+T")
        tool_menu.Append(171, "Teste Passo a Passo de Drum Setup\tCtrl+Shift+D")
        tool_menu.Append(173, "Editor de Marcadores (Teste)\tCtrl+Alt+M")
        tool_menu.Append(232, "Fade In / Fade Out (Expression)...\tCtrl+Shift+F")
        tool_menu.Append(151, "Envelope de Automação de CC...\tShift+E")
        tool_menu.Append(233, "Efeitos MIDI Offline (Arpejo, Delay, Harpa, Bateria)...\tCtrl+K")
        tool_menu.Append(234, "Converter Estilo de SFF1 para SFF2 (CASM)...")
        tool_menu.Append(235, "Verificar e Corrigir Alinhamento de Compassos...")
        tool_menu.Append(236, "Travar Estilo Inteiro (Editável)...")
        tool_menu.Append(237, "Destravar Estilo Inteiro (Editável)...")
        tool_menu.Append(238, "Verificar e Corrigir Notas Cruzando Seções...")
        tool_menu.Append(239, "Alterar LSB do Ritmo Atual...")
        tool_menu.Append(241, "Alterar LSB de Ritmos em Massa...")
        self.metro_item = tool_menu.AppendCheckItem(104, "Ativar &Metrônomo\tCtrl+M")

        transp_menu = wx.Menu()
        transp_menu.Append(101, "Tocar / Parar\tSpace")
        transp_menu.Append(106, "Pausar / Continuar\tCtrl+Space")
        transp_menu.Append(116, "Armar Gravação (REC)\tR")
        transp_menu.AppendSeparator()
        transp_menu.Append(254, "Ir para o Início da Seção\tCtrl+Home")
        transp_menu.Append(255, "Ir para o Fim da Seção\tCtrl+End")
        transp_menu.AppendSeparator()
        transp_menu.Append(201, "Compasso Anterior\tPgUp")
        transp_menu.Append(202, "Próximo Compasso\tPgDn")
        transp_menu.Append(203, "Tempo (Beat) Anterior\tCtrl+PgUp")
        transp_menu.Append(204, "Próximo Tempo (Beat)\tCtrl+PgDn")
        transp_menu.AppendSeparator()
        transp_menu.Append(149, "Diminuir Andamento (Ctrl e sinal de menos)")
        transp_menu.Append(148, "Aumentar Andamento (Ctrl e sinal de mais)")

        voz_menu = wx.Menu()
        voz_menu.Append(260, "Importar Voz (.vce, .drm, .mgv, .sar, .liv) para o Canal Atual...")
        voz_menu.Append(261, "Exportar Voz do Canal Atual (.vce, .drm, .mgv, .sar, .liv)...")

        opt_menu = wx.Menu()
        opt_menu.Append(128, "Velocity Midi Control...\tCtrl+Shift+V")
        opt_menu.Append(129, "Conversor MIDI (Midi Convert to CC)...\tCtrl+Shift+C")
        opt_menu.Append(179, "Efeitos DSP Globais (Reverb e Chorus)...\tCtrl+Shift+G")
        opt_menu.Append(180, "Efeito de Inserção DSP (Variation)...\tCtrl+Shift+I")
        self.item_captura_dsp = opt_menu.AppendCheckItem(242, "Capturar Timbre/DSP do Teclado ao trocar a voz")
        self.item_captura_dsp.Check(True)
        self.item_log_midi = opt_menu.AppendCheckItem(240, "Registrar MIDI de Entrada (arquivo de log)")
        opt_menu.Append(198, "Desligar Notas Presas (Pânico)\tF3")
        opt_menu.Append(208, "Som do Teclado (Local Control) Liga/Desliga\tF8")
        opt_menu.Append(199, "&Configurações Gerais\tCtrl+P")

        ajuda_menu = wx.Menu()
        ajuda_menu.Append(270, "&Novidades desta Versão...")
        ajuda_menu.Append(271, "&Ir para a Página do Projeto")
        self.Bind(wx.EVT_MENU, self.OnMostrarNovidades, id=270)
        self.Bind(wx.EVT_MENU, self.OnAbrirPaginaProjeto, id=271)

        menubar.Append(file_menu, "&Arquivo")
        menubar.Append(edit_menu, "Editar")
        menubar.Append(tool_menu, "Ferramentas")
        menubar.Append(transp_menu, "Transporte")
        menubar.Append(voz_menu, "Vozes")
        menubar.Append(opt_menu, "&Opções")
        menubar.Append(ajuda_menu, "Aj&uda")
        self.SetMenuBar(menubar)

        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sectionList = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.sectionList.SetName("Seções")
        self.sizer.Add(self.sectionList, 1, wx.EXPAND | wx.ALL, 10)
        self.channelList = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.channelList.SetName("Canais")
        self.sizer.Add(self.channelList, 2, wx.EXPAND | wx.ALL, 10)
        self.panel.SetSizer(self.sizer)

        self.Bind(wx.EVT_MENU, self.OnNewStyle, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.OnOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnSave, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnSaveAs, id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self.undo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU, self.redo, id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU, self.mark_in, id=160)
        self.Bind(wx.EVT_MENU, self.mark_out, id=161)
        self.Bind(wx.EVT_MENU, lambda e: self.do_copy(e, cut=False), id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, lambda e: self.do_copy(e, cut=True), id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.do_paste, id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, self.do_delete, id=162)
        
        self.Bind(wx.EVT_MENU, self.OnOpenSettings, id=199)
        self.Bind(wx.EVT_MENU, self.OnResizeSection, id=105) 
        self.Bind(wx.EVT_MENU, self.OnEsvaziarSecao, id=174)
        self.Bind(wx.EVT_MENU, self.OnLimparCanalTodasSecoes, id=231)
        self.Bind(wx.EVT_MENU, self.corrigir_casm_secao_atual, id=175)
        self.Bind(wx.EVT_MENU, self.abrir_event_list, id=150)
        self.Bind(wx.EVT_MENU, self.abrir_drum_setup, id=170)
        self.Bind(wx.EVT_MENU, self.abrir_voice_creator, id=172)
        self.Bind(wx.EVT_MENU, self.abrir_teste_drum_setup, id=171)
        self.Bind(wx.EVT_MENU, self.abrir_editor_marcadores, id=173)
        self.Bind(wx.EVT_MENU, self.abrir_fade, id=232)
        self.Bind(wx.EVT_MENU, self.abrir_efeitos_midi, id=233)
        self.Bind(wx.EVT_MENU, self.converter_sff1_para_sff2, id=234)
        self.Bind(wx.EVT_MENU, self.verificar_e_corrigir_alinhamento_compassos, id=235)
        self.Bind(wx.EVT_MENU, self.travar_estilo_inteiro, id=236)
        self.Bind(wx.EVT_MENU, self.destravar_estilo_inteiro, id=237)
        self.Bind(wx.EVT_MENU, self.verificar_e_corrigir_notas_cruzando_secoes, id=238)
        self.Bind(wx.EVT_MENU, self.alterar_lsb_ritmo_atual, id=239)
        self.Bind(wx.EVT_MENU, self.alterar_lsb_ritmos_em_massa, id=241)
        self.Bind(wx.EVT_MENU, self.OnToggleMetronome, id=104)
        self.Bind(wx.EVT_MENU, self.OnExit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.abrir_quantizacao_realtime, id=141)
        self.Bind(wx.EVT_MENU, self.aplicar_quantizacao_offline, id=142)
        self.Bind(wx.EVT_MENU, self.toggle_gravacao, id=116)
        self.Bind(wx.EVT_MENU, self.abrir_conversor_midi, id=129)
        self.Bind(wx.EVT_MENU, self.abrir_velocity_control, id=128)
        self.Bind(wx.EVT_MENU, self.abrir_dsp_global, id=179)
        self.Bind(wx.EVT_MENU, self.abrir_dsp_variation, id=180)
        self.Bind(wx.EVT_MENU, self.OnToggleMidiLog, id=240)
        self.Bind(wx.EVT_MENU, self.OnToggleCapturaDSP, id=242)
        self.Bind(wx.EVT_MENU, self.proxima_aba, id=176)
        self.Bind(wx.EVT_MENU, self.aba_anterior, id=177)
        self.Bind(wx.EVT_MENU, self.fechar_aba_atual, id=178)
        self.atualizar_menu_recentes()

        self.sectionList.Bind(wx.EVT_LISTBOX, self.OnSectionSelect)
        self.sectionList.Bind(wx.EVT_KEY_DOWN, self.OnSectionListKeyDown)
        self.sectionList.Bind(wx.EVT_CHAR_HOOK, self.OnSectionListCharHook)
        self.sectionList.Bind(wx.EVT_CONTEXT_MENU, self.editar_secao)
        self.channelList.Bind(wx.EVT_LISTBOX, self.OnChannelSelect)
        self.channelList.Bind(wx.EVT_KEY_DOWN, self.OnChannelListKeyDown)
        self.channelList.Bind(wx.EVT_CHAR_HOOK, self.OnChannelListCharHook)
        self.channelList.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: wx.CallAfter(self.acao_enter_canal))

        # SetName() sozinho não faz o NVDA falar nada aqui - este app fala
        # via accessible_output2 (falar(), ver MHS_Utils), não pela árvore
        # nativa de acessibilidade do Windows. Por isso, igual já é feito
        # pros CheckListBox de grupo (ver fabrica_handler_foco), o rótulo só
        # sai de verdade com um handler de EVT_SET_FOCUS chamando falar().
        def _falar_rotulo_lista(rotulo):
            def handler(evt):
                falar(rotulo, imediato=True)
                evt.Skip()
            return handler
        self.sectionList.Bind(wx.EVT_SET_FOCUS, _falar_rotulo_lista("Seções"))
        self.channelList.Bind(wx.EVT_SET_FOCUS, _falar_rotulo_lista("Canais"))
        
        accel = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_SPACE, 101),
            (wx.ACCEL_CTRL, wx.WXK_SPACE, 106),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_SPACE, 290),
            (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, 102),
            (wx.ACCEL_SHIFT, wx.WXK_ESCAPE, 163),
            (wx.ACCEL_CTRL, ord('M'), 104),
            (wx.ACCEL_CTRL, ord('T'), 105),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('R'), 174),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord('R'), 231),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('K'), 175),
            (wx.ACCEL_CTRL, ord('K'), 233),
            (wx.ACCEL_CTRL, ord('Z'), wx.ID_UNDO),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('Z'), wx.ID_REDO),
            (wx.ACCEL_NORMAL, ord('I'), 160),
            (wx.ACCEL_NORMAL, ord('O'), 161),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_CTRL, ord('X'), wx.ID_CUT),
            (wx.ACCEL_CTRL, ord('V'), wx.ID_PASTE),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, 162),
            (wx.ACCEL_NORMAL, wx.WXK_F5, 195),
            (wx.ACCEL_NORMAL, wx.WXK_F6, 196),
            (wx.ACCEL_NORMAL, wx.WXK_F7, 197),
            (wx.ACCEL_NORMAL, wx.WXK_F3, 198),
            (wx.ACCEL_NORMAL, wx.WXK_F8, 208),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F5, 209),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F6, 210),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F7, 211),
            (wx.ACCEL_ALT, wx.WXK_F5, 212),
            (wx.ACCEL_ALT, wx.WXK_F6, 213),
            (wx.ACCEL_ALT, wx.WXK_F7, 214),
            (wx.ACCEL_NORMAL, ord('R'), 116),
            (wx.ACCEL_NORMAL, ord('Q'), 141),
            (wx.ACCEL_CTRL, ord('Q'), 142),
            (wx.ACCEL_NORMAL, ord('H'), 143),           
            (wx.ACCEL_SHIFT, ord('C'), 147),
            (wx.ACCEL_SHIFT, ord('E'), 151),
            (wx.ACCEL_CTRL, wx.WXK_ADD, 148),          
            (wx.ACCEL_CTRL, wx.WXK_NUMPAD_ADD, 148),   
            (wx.ACCEL_CTRL, ord('='), 148),            
            (wx.ACCEL_CTRL, wx.WXK_SUBTRACT, 149),     
            (wx.ACCEL_CTRL, wx.WXK_NUMPAD_SUBTRACT, 149),
            (wx.ACCEL_CTRL, ord('-'), 149),            
            (wx.ACCEL_CTRL, ord('E'), 150),
            (wx.ACCEL_CTRL, ord('D'), 170),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('D'), 171),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('T'), 172),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord('M'), 173),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('V'), 128),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('C'), 129),
            (wx.ACCEL_NORMAL, wx.WXK_HOME, 205),
            (wx.ACCEL_NORMAL, wx.WXK_END, 206),
            (wx.ACCEL_NORMAL, wx.WXK_PAGEUP, 201),
            (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN, 202),
            (wx.ACCEL_CTRL, wx.WXK_PAGEUP, 203),
            (wx.ACCEL_CTRL, wx.WXK_PAGEDOWN, 204),
            (wx.ACCEL_CTRL, wx.WXK_UP, 280),
            (wx.ACCEL_CTRL, wx.WXK_DOWN, 281),
            (wx.ACCEL_CTRL, wx.WXK_LEFT, 282),
            (wx.ACCEL_CTRL, wx.WXK_RIGHT, 283),
            (wx.ACCEL_CTRL, wx.WXK_TAB, 176),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_TAB, 177),
            (wx.ACCEL_CTRL, wx.WXK_F4, 178),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('G'), 179),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('I'), 180),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('E'), 250),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord('E'), 251),
            (wx.ACCEL_CTRL, ord('L'), 253),
        ])
        self.SetAcceleratorTable(accel)
        
        self.Bind(wx.EVT_MENU, self.OnTogglePlay, id=101)
        self.Bind(wx.EVT_MENU, self.OnTogglePause, id=106)
        self.Bind(wx.EVT_MENU, self.OnEscPress, id=102)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Mute"), id=195)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Solo"), id=196)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Arm"), id=197)
        self.Bind(wx.EVT_MENU, self.on_f3_panic, id=198)
        self.Bind(wx.EVT_MENU, self.toggle_local_control, id=208)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Mute", "mutados"), id=209)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Solo", "solados"), id=210)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Arm", "armados"), id=211)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Mute", "mutes desligados"), id=212)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Solo", "solos desligados"), id=213)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Arm", "desarmados"), id=214)
        self.Bind(wx.EVT_MENU, self.aplicar_humanizacao, id=143)
        self.Bind(wx.EVT_MENU, self.aplicar_envelope_tempo, id=147)
        self.Bind(wx.EVT_MENU, self.aplicar_envelope_cc, id=151)
        self.Bind(wx.EVT_MENU, self.abrir_exportar_canal, id=250)
        self.Bind(wx.EVT_MENU, self.abrir_copiar_canal_entre_secoes, id=251)
        self.Bind(wx.EVT_MENU, self.abrir_clonar_config_canal, id=253)
        self.Bind(wx.EVT_MENU, self.importar_voz_canal, id=260)
        self.Bind(wx.EVT_MENU, self.exportar_voz_canal, id=261)
        self.Bind(wx.EVT_MENU, lambda e: self.alterar_bpm_incremental(1), id=148)
        self.Bind(wx.EVT_MENU, lambda e: self.alterar_bpm_incremental(-1), id=149)
        self.Bind(wx.EVT_MENU, self.limpar_tudo_mestre, id=163)
        self.Bind(wx.EVT_MENU, self.relatar_selecoes_canais, id=290)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("inicio_secao"), id=254)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("fim_secao"), id=255)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("home"), id=205)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("end"), id=206)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("compasso_tras"), id=201)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("compasso_frente"), id=202)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("beat_tras"), id=203)
        self.Bind(wx.EVT_MENU, lambda e: self.navegar_tempo("beat_frente"), id=204)
        self.Bind(wx.EVT_MENU, self.transpor_midi_in, id=280, id2=283)
        self.Bind(wx.EVT_CLOSE, self.OnExit)
        
        self.Show()
        wx.CallLater(100, lambda: self.sectionList.SetFocus())
    def construir_casm_do_zero(self):
        nomes_padrao = {
            8: "Rhythm1 ", 9: "Rhythm2 ", 10: "Bass    ", 11: "Chord1  ",
            12: "Chord2  ", 13: "Pad     ", 14: "Phrase1 ", 15: "Phrase2 "
        }
        ntr_map = {'trans': 0, 'fixed': 1, 'gtr': 2}
        ntt_map = {
            'bypass': 0, 'melody': 1, 'chord': 2, 'melodic minor': 3,
            'melodic minor 5th': 4, 'harmonic minor': 5, 'harmonic minor 5th': 6,
            'natural minor': 7, 'natural minor 5th': 8, 'dorian': 9,
            'dorian 5th': 10, 'all purpose': 11, 'any chord': 12,
            'vocal': 13, 'pitch shift': 14
        }
        preset_todos_acordes = bytes([0x03, 0xff, 0xff, 0xff, 0xff])
        
        biblioteca = getattr(self, 'casm_rules_by_section', {}) or {}
        if not biblioteca:
            biblioteca = {"Main A": self.casm_rules}
            
        nomes_ja_usados = set()
        cseg_blocos = bytearray()
        
        for nome_secao, regras in biblioteca.items():
            chave = nome_secao.strip().lower()
            if chave in nomes_ja_usados:
                continue
            nomes_ja_usados.add(chave)
            
            sdec_texto = nome_secao.encode('latin-1', errors='ignore')
            sdec_bloco = b'Sdec' + len(sdec_texto).to_bytes(4, 'big') + sdec_texto
            
            ctb2_blocos = bytearray()
            for ch in range(16):
                regra = regras.get(ch, self.get_default_casm_rules()[ch])
                
                nome_voz = nomes_padrao.get(ch, f"Track{ch+1}")[:8].ljust(8).encode('latin-1', errors='ignore')
                dst = regra.get('dst', ch)
                editable = 1
                notemute = bytes([0, 0])
                chordmute = bytes(regra.get('active_chords', preset_todos_acordes))
                if len(chordmute) != 5:
                    chordmute = preset_todos_acordes
                chordroot = 0
                chordtype = 0
                
                split_val = max(0, min(127, regra.get('note_split_high', 127)))
                lowmidlim = 0
                midhighlim = split_val
                
                ntr = ntr_map.get(regra.get('play_type', 'trans').lower(), 0)
                ntt = ntt_map.get(regra.get('ntt_type', 'bypass').lower(), 0)
                if regra.get('ntt_bass', False):
                    ntt |= 0x80
                highkey = regra.get('high_key', 6)
                notelow = regra.get('note_limit_low', 0)
                notehigh = regra.get('note_limit_high', 127)
                
                ntr_hi = ntr_map.get(regra.get('ntr_hi', 'trans').lower(), 0)
                ntt_hi = ntt_map.get(regra.get('ntt_hi', 'bypass').lower(), 0)
                if regra.get('ntt_hi_bass', False):
                    ntt_hi |= 0x80
                highkey_hi = max(0, min(127, regra.get('high_key_hi', 6)))
                
                zona_vazia = bytes([0, 0, 64, 0, 127, 0])
                zona_media = bytes([ntr, ntt, highkey, notelow, notehigh, 0])
                zona_alta = bytes([ntr_hi, ntt_hi, highkey_hi, split_val, 127, 0])
                
                extrabreak = 0
                alwaysdrum = 1 if ch in (8, 9) else 0
                sempre00 = 0
                drumflag2 = 0
                instrumento = 0
                volume = 100
                fimregistro = 0
                
                registro = bytearray()
                registro.append(ch)
                registro += nome_voz
                registro.append(dst)
                registro.append(editable)
                registro += notemute
                registro += chordmute
                registro.append(chordroot)
                registro.append(chordtype)
                registro.append(lowmidlim)
                registro.append(midhighlim)
                registro += zona_vazia
                registro += zona_media
                registro += zona_alta
                registro.append(extrabreak)
                registro.append(alwaysdrum)
                registro.append(sempre00)
                registro.append(drumflag2)
                registro.append(instrumento)
                registro.append(volume)
                registro.append(fimregistro)
                
                ctb2_blocos += b'Ctb2' + len(registro).to_bytes(4, 'big') + bytes(registro)
                
            cseg_payload = sdec_bloco + bytes(ctb2_blocos)
            cseg_blocos += b'CSEG' + len(cseg_payload).to_bytes(4, 'big') + cseg_payload
            
        casm_payload = bytes(cseg_blocos)
        return b'CASM' + len(casm_payload).to_bytes(4, 'big') + casm_payload
    def _apply_casm_rule(self, rules, src, dst, ntr, ntt, hkey, l_lim, h_lim, canais_vistos, chordmute=None, note_split_high=None, ntr_hi=None, ntt_hi=None, hkey_hi=None, editable=None, raw_bytes=None,
                          rtr=None, note_split_low=None, ntr_lo=None, ntt_lo=None, hkey_lo=None, l_lim_lo=None, h_lim_lo=None, rtr_lo=None,
                          l_lim_hi=None, h_lim_hi=None, rtr_hi=None, source_chord_root=None, source_chord_type=None):
        if src >= 16: return # Ignora canais inválidos (ex: SysEx ou lixo de memória)

        canais_vistos.add(src)

        ntr_map = {0: 'trans', 1: 'fixed', 2: 'gtr'}
        ntt_map = {
            0: 'bypass', 1: 'melody', 2: 'chord', 3: 'melodic minor',
            4: 'melodic minor 5th', 5: 'harmonic minor', 6: 'harmonic minor 5th',
            7: 'natural minor', 8: 'natural minor 5th', 9: 'dorian',
            10: 'dorian 5th', 11: 'all purpose', 12: 'any chord',
            13: 'vocal', 14: 'pitch shift'
        }

        def rtr_nome(valor):
            return RTR_OPCOES[valor] if valor is not None and 0 <= valor < len(RTR_OPCOES) else 'pitch shift'

        rules[src]['play_type'] = ntr_map.get(ntr, 'trans')

        # O bit mais significativo do NTT define se o NTT Bass está ligado (0x80)
        ntt_bass = bool(ntt & 0x80)
        ntt_clean = ntt & 0x7F

        rules[src]['ntt_type'] = ntt_map.get(ntt_clean, 'bypass')
        rules[src]['ntt_bass'] = ntt_bass
        rules[src]['high_key'] = hkey
        rules[src]['note_limit_low'] = l_lim
        rules[src]['note_limit_high'] = h_lim
        rules[src]['dst'] = dst
        if chordmute is not None and len(chordmute) == 5:
            rules[src]['active_chords'] = bytes(chordmute)
        if rtr is not None:
            rules[src]['rtr'] = rtr_nome(rtr)
        if source_chord_root is not None:
            rules[src]['source_chord_root'] = (SOURCE_CHORD_ROOT_NAMES[source_chord_root]
                                                if 0 <= source_chord_root < len(SOURCE_CHORD_ROOT_NAMES) else 'C')
        if source_chord_type is not None:
            rules[src]['source_chord_type'] = (SOURCE_CHORD_TYPE_NAMES[source_chord_type]
                                                if 0 <= source_chord_type < len(SOURCE_CHORD_TYPE_NAMES) else 'Maj7')

        # A ZONA AGUDA: uma faixa de nota separada, com seu próprio NTR/NTT/Tecla
        # Pivô, independente da faixa média - normalmente usada pra proteger
        # gatilhos de MegaVoice/nuances de instrumento da transposição.
        if note_split_high is not None:
            rules[src]['note_split_high'] = note_split_high
        if ntr_hi is not None:
            rules[src]['ntr_hi'] = ntr_map.get(ntr_hi, 'trans')
        if ntt_hi is not None:
            ntt_hi_bass = bool(ntt_hi & 0x80)
            ntt_hi_clean = ntt_hi & 0x7F
            rules[src]['ntt_hi'] = ntt_map.get(ntt_hi_clean, 'bypass')
            rules[src]['ntt_hi_bass'] = ntt_hi_bass
        if hkey_hi is not None:
            rules[src]['high_key_hi'] = hkey_hi
        if l_lim_hi is not None:
            rules[src]['note_limit_low_hi'] = l_lim_hi
        if h_lim_hi is not None:
            rules[src]['note_limit_high_hi'] = h_lim_hi
        if rtr_hi is not None:
            rules[src]['rtr_hi'] = rtr_nome(rtr_hi)

        # A ZONA GRAVE: mesma ideia da Zona Aguda, só que pra faixa abaixo da
        # Zona Média - quase sempre desligada (note_split_low = 0) nos
        # arquivos genuínos, mas agora totalmente decifrada e editável.
        if note_split_low is not None:
            rules[src]['note_split_low'] = note_split_low
        if ntr_lo is not None:
            rules[src]['ntr_lo'] = ntr_map.get(ntr_lo, 'trans')
        if ntt_lo is not None:
            ntt_lo_bass = bool(ntt_lo & 0x80)
            ntt_lo_clean = ntt_lo & 0x7F
            rules[src]['ntt_lo'] = ntt_map.get(ntt_lo_clean, 'bypass')
            rules[src]['ntt_lo_bass'] = ntt_lo_bass
        if hkey_lo is not None:
            rules[src]['high_key_lo'] = hkey_lo
        if l_lim_lo is not None:
            rules[src]['note_limit_low_lo'] = l_lim_lo
        if h_lim_lo is not None:
            rules[src]['note_limit_high_lo'] = h_lim_lo
        if rtr_lo is not None:
            rules[src]['rtr_lo'] = rtr_nome(rtr_lo)

        if editable is not None:
            # Byte 10 - invertido em relação ao que a gente supunha (ver
            # "Como reverter" logo abaixo pro histórico): confirmado pelo
            # Michel testando no teclado real (SX600) - levando um estilo
            # com este byte=1 pro Style Creator do próprio teclado, o
            # canal fica PROTEGIDO (o usuário é obrigado a apagar a
            # gravação inteira e regravar do zero, não consegue sobrepor/
            # regravar por cima); byte=0 permite gravar por cima
            # normalmente. Byte 1 = PROTEGIDO, byte 0 = editável - o
            # oposto de "bool(editable)" puro.
            rules[src]['editable'] = not bool(editable)
        if raw_bytes is not None:
            rules[src]['raw_bytes'] = dict(raw_bytes)
    def obter_nome_peca_bateria(self, bank, patch, nota):
        from MHS_Utils import get_drum_name
        kit_name = getattr(self, 'patch_to_kit', {}).get((bank, patch))
        if kit_name:
            nome = getattr(self, 'ins_drum_kits', {}).get(kit_name, {}).get(nota)
            if nome:
                return nome
        return get_drum_name(nota)

    def abrir_drum_setup(self, event):
        ch = self.channelList.GetSelection()
        if ch == wx.NOT_FOUND:
            falar("Selecione um canal primeiro.", imediato=True)
            return
        original_params = dict(self.canais[ch].get("DrumParams", {}))
        original_maps = dict(self.canais[ch].get("CustomDrumMap", {}))
        original_nrpn = dict(self.canais[ch].get("DrumParamsNRPN", {}))
        dlg = DrumSetupDialog(self, ch)
        self.active_midi_dialog = dlg
        if dlg.ShowModal() == wx.ID_OK:
            drum_params, custom_maps, drum_params_nrpn = dlg.get_values()
            removido = getattr(dlg, 'removido', False)
            self.save_state(f"Remover Drum Setup Canal {ch+1}" if removido else f"Drum Setup Canal {ch+1}")
            self.aplicar_drum_setup(ch, drum_params, custom_maps, drum_params_nrpn)
            if not removido:
                falar("Configurações de bateria salvas.", imediato=True)
        else:
            self.canais[ch]["DrumParams"] = original_params
            self.canais[ch]["CustomDrumMap"] = original_maps
            self.canais[ch]["DrumParamsNRPN"] = original_nrpn
            falar("Alterações de bateria descartadas.", imediato=True)
        self.active_midi_dialog = None
        dlg.Destroy()

    def aplicar_drum_setup(self, canal_idx, drum_params, custom_maps, drum_params_nrpn=None):
        import mido
        part_byte = 0x30 if canal_idx == 9 else 0x31
        drum_params_nrpn = drum_params_nrpn or {}
        from MHS_Utils import DRUM_NRPN_MSBS

        def eh_sysex_deste_canal(msg):
            if msg.type != 'sysex': return False
            d = bytes(msg.data)
            return len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] == part_byte

        # Acha, numa passada com estado (99=MSB / 98=LSB / 6=valor), os 3
        # índices exatos de cada trinca NRPN de Drum Setup (Guia 3) JÁ
        # existente neste canal - só essas (endereço 14H-35H do Data List),
        # não qualquer NRPN (o canal pode ter vibrato/filtro do Multi Part
        # usando os mesmos 3 CCs pra outra coisa).
        indices_nrpn_antigos = set()
        nrpn_msb, nrpn_lsb, idx_msb, idx_lsb = None, None, None, None
        for idx, msg in enumerate(self.merged_track_cache):
            if getattr(msg, 'channel', None) != canal_idx or msg.type != 'control_change':
                continue
            if msg.control == 99:
                nrpn_msb, idx_msb = msg.value, idx
            elif msg.control == 98:
                nrpn_lsb, idx_lsb = msg.value, idx
            elif msg.control == 6:
                if nrpn_msb in DRUM_NRPN_MSBS and nrpn_lsb is not None:
                    indices_nrpn_antigos.update((idx_msb, idx_lsb, idx))

        # 1. Tira TODAS as ocorrências antigas desse Drum Setup na música
        # inteira (incluindo as cópias por seção de uma versão anterior
        # desta correção - ver comentário abaixo do porquê isso mudou).
        abs_msgs = []
        curr_t = 0
        for idx, msg in enumerate(self.merged_track_cache):
            curr_t += msg.time
            if eh_sysex_deste_canal(msg) or idx in indices_nrpn_antigos:
                continue
            abs_msgs.append((curr_t, msg))

        custom_maps_msgs = [mido.Message('sysex', data=(0x43, 0x10, 0x4C, part_byte, nota, 0x70, m['bank'] // 128, m['bank'] % 128, m['patch'], m['dest_note'])) for nota, m in custom_maps.items()]
        drum_params_msgs = [mido.Message('sysex', data=(0x43, 0x10, 0x4C, part_byte, nota, param_id, valor)) for (nota, param_id), valor in drum_params.items()]
        # Guia 3 (NRPN puro) - o canal já vem no próprio CC, não precisa de
        # part_byte. Cada trinca 99/98/6 vira 3 mensagens em sequência.
        nrpn_msgs = []
        for (nota, param_id), valor in drum_params_nrpn.items():
            nrpn_msgs.append(mido.Message('control_change', channel=canal_idx, control=99, value=param_id))
            nrpn_msgs.append(mido.Message('control_change', channel=canal_idx, control=98, value=nota))
            nrpn_msgs.append(mido.Message('control_change', channel=canal_idx, control=6, value=valor))
        novas_msgs_drum = custom_maps_msgs + drum_params_msgs + nrpn_msgs

        if novas_msgs_drum:
            # 2. A CORREÇÃO DE VERDADE (2ª volta): a primeira versão desta
            # correção reaplicava o Drum Setup em CADA seção, pra sobreviver
            # à troca de kit (Bank+Patch) que cada seção reenvia. Isso
            # deixou o Play do nosso programa perfeito, mas comparando byte
            # a byte um arquivo afinado por nós com dois arquivos que o
            # SX600 leu certo (um deles editado direto no próprio SX), a
            # afinação dos dois morava em UM lugar só: a Área de
            # Configuração, antes do primeiro marcador de seção (Main A,
            # Intro, etc) - nunca dentro das seções. O SX, carregando o
            # estilo sozinho (sem ser tocado nota a nota por nós), só lê
            # esse tipo de SysEx dali; reaplicar em cada seção fazia efeito
            # só pra quem estava sendo tocado por nós (mandamos tudo na hora
            # certa, não importa onde estava guardado no arquivo) - o SX
            # tocando o estilo sozinho ignorava as cópias no meio das seções
            # e só via a Área de Configuração vazia.
            primeiro_marker_tick = float('inf')
            temp_abs = 0
            for m in self.merged_track_cache:
                temp_abs += m.time
                if m.type in ('marker', 'cuepoint') and getattr(m, 'text', '') not in ('SFF1', 'SFF2', 'SInt'):
                    primeiro_marker_tick = temp_abs
                    break
            if primeiro_marker_tick == float('inf'):
                primeiro_marker_tick = 0

            limite = max(0, primeiro_marker_tick - 1)
            ponto_insercao = limite
            curr_t = 0
            for msg in self.merged_track_cache:
                curr_t += msg.time
                if curr_t >= primeiro_marker_tick: break
                if getattr(msg, 'channel', None) == canal_idx and msg.type == 'program_change':
                    ponto_insercao = curr_t

            # Mesmo tick do Banco/Patch desse canal (ponto_insercao) - não
            # precisa mais de +1 pra "vir depois" dele: _msg_priority agora
            # dá ao SysEx de Drum Setup uma prioridade própria (depois de
            # Program Change, antes de nota), então mesmo empatado no
            # mesmo tick ele já ordena certo sozinho. Isso importa quando
            # uma nota também cai bem nesse mesmo tick (uma gravação que já
            # começa tocando na cabeça da seção) - com o +1 antigo, o SysEx
            # chegava DEPOIS dessa nota (não só depois do Program Change),
            # e a primeira batida tocava com a peça antiga por um tick.
            for syx in custom_maps_msgs:
                abs_msgs.append((ponto_insercao, syx.copy()))
            for syx in drum_params_msgs:
                abs_msgs.append((ponto_insercao, syx.copy()))
            # A trinca de cada NRPN (99, depois 98, depois 6) precisa ficar
            # JUNTA e NESSA ordem - todas no mesmo tick do SysEx acima
            # (_msg_priority/rebuild_from_abs_list preservam a ordem relativa
            # de mensagens empatadas no mesmo tick, igual já acontece com os
            # vários SysEx de parâmetro aqui do lado).
            for msg_nrpn in nrpn_msgs:
                abs_msgs.append((ponto_insercao, msg_nrpn.copy()))

            # 3. Além da Área de Configuração (pro SX carregar sozinho), reaplica
            # também em TODA seção que resseleciona de verdade o kit deste canal
            # (ela manda o próprio Program Change desta seção) - resselecionar
            # reseta a afinação por nota no XG mesmo pro mesmo kit, e tem ritmo
            # genuíno (achado no "Ballada 3") que reenvia Banco/Patch deste canal
            # em TODAS as seções, não só de vez em quando. Sem isso, o Play do
            # nosso programa (que manda tudo na ordem certa, seção por seção)
            # perde a afinação assim que cruza pra qualquer uma dessas seções,
            # mesmo com a Área de Configuração certa. Seção que NÃO resseleciona
            # o kit (caso do "Ballada 1") não ganha cópia nenhuma aqui - a
            # comparação por bytes já mostrou que o SX não lê isso mesmo, então
            # só valeria a pena pro nosso próprio Play, que já está coberto pela
            # Área de Configuração nesse caso.
            starts = sorted({s['start'] for s in getattr(self, 'sections_info', []) if s.get('start') is not None})
            for i, start in enumerate(starts):
                if start < primeiro_marker_tick:
                    continue
                fim_secao = starts[i + 1] if i + 1 < len(starts) else float('inf')
                ponto_insercao_secao = None
                curr_t = 0
                for msg in self.merged_track_cache:
                    curr_t += msg.time
                    if curr_t < start: continue
                    if curr_t >= fim_secao: break
                    if getattr(msg, 'channel', None) == canal_idx and msg.type == 'program_change':
                        ponto_insercao_secao = curr_t
                if ponto_insercao_secao is None:
                    continue
                # Mesmo tick do Program Change desta seção - _msg_priority
                # já garante que o SysEx de Drum Setup ordena depois dele
                # (e antes de qualquer nota, mesmo uma que caia bem na
                # cabeça da seção, empatada nesse mesmo tick - era esse o
                # caso que o "+1" antigo furava: a nota ficava DEPOIS do
                # Program Change mas ANTES do SysEx reaplicado, então a
                # primeira batida tocava com a peça antiga por um tick).
                for syx in custom_maps_msgs:
                    abs_msgs.append((ponto_insercao_secao, syx.copy()))
                for syx in drum_params_msgs:
                    abs_msgs.append((ponto_insercao_secao, syx.copy()))
                for msg_nrpn in nrpn_msgs:
                    abs_msgs.append((ponto_insercao_secao, msg_nrpn.copy()))

        # Atualiza também o "instantâneo" de configuração inicial usado pelo
        # send_initial_setup - senão o próximo carregamento do arquivo
        # continuaria repetindo o Drum Setup antigo do arquivo original,
        # ignorando a edição que você acabou de confirmar.
        self.midi_setup_msgs = [m for m in getattr(self, 'midi_setup_msgs', []) if not eh_sysex_deste_canal(m)]
        self.midi_setup_msgs.extend(msg.copy() for msg in novas_msgs_drum)

        self.rebuild_from_abs_list(abs_msgs)

    def abrir_voice_creator(self, event):
        # Voice Creator trazido do MHS MIDI Sequencer (lá é Ctrl+T; aqui, como
        # Ctrl+T já é "Alterar Tamanho da Seção", ficou em Ctrl+Shift+T).
        ch = self.channelList.GetSelection()
        if ch == wx.NOT_FOUND:
            falar("Selecione um canal primeiro.", imediato=True)
            return
        original = dict(self.canais[ch].get("VoiceCreator", {}))
        falar(f"Abrindo Voice Creator para o canal {rotulo_canal(ch)}.", imediato=True)
        dlg = VoiceCreatorDialog(self, ch, self.canais[ch].get("VoiceCreator", {}))
        self.active_midi_dialog = dlg
        if dlg.ShowModal() == wx.ID_OK:
            valores = {int(k): v for k, v in dlg.get_valores().items()}
            self.save_state(f"Voice Creator Canal {ch + 1}")
            self.canais[ch]["VoiceCreator"] = dict(valores)
            self.aplicar_voice_creator(ch, valores)
            falar("Timbre salvo no canal.", imediato=True)
        else:
            self.canais[ch]["VoiceCreator"] = original
            falar("Alterações de timbre descartadas.", imediato=True)
        self.active_midi_dialog = None
        dlg.Destroy()

    def aplicar_voice_creator(self, canal_idx, valores):
        # Mesma estratégia do aplicar_drum_setup (ver os comentários longos
        # lá): grava o timbre como SysEx XG de Multi Part
        # (F0 43 10 4C 08 <canal> <end> <val> F7) na Área de Configuração,
        # no mesmo tick do Banco/Peça do canal, e reafirma em toda seção que
        # resseleciona Banco/Peça deste canal (resselecionar o timbre no XG
        # zera esses parâmetros, então sem reafirmar o Play perde o timbre ao
        # cruzar pra essas seções).
        import mido
        from MHS_Utils import detune_separar

        def eh_sysex_deste_canal(msg):
            # Apesar do nome, também reconhece CC5/CC65 (Portamento Time/
            # Switch) deste canal - o mecanismo que REALMENTE funciona (ver
            # comentário no laço de escrita, mais abaixo) - pra limpar o
            # antigo antes de escrever de novo, igual já faz com SysEx.
            if msg.type == 'control_change' and msg.channel == canal_idx and msg.control in (5, 65, 71, 72, 73, 74, 75, 76, 77, 78):
                return True
            if msg.type != 'sysex':
                return False
            d = bytes(msg.data)
            if len(d) < 7 or d[0] != 0x43 or d[2] != 0x4C or d[4] != canal_idx:
                return False
            # 0x0A é o 2º byte do Detune (nunca vira uma chave própria em
            # `valores`, mas precisa ser identificado aqui pra ser removido
            # junto do 0x09 antigo - senão sobra um byte "órfão" cada vez
            # que o Voice Creator é salvo de novo). Bloco 0x0A de verdade
            # (Portamento - Mono Priority/Modo/Modo do Tempo) é um bloco
            # SEPARADO, não o 0x08 de sempre.
            if d[3] == 0x08:
                return d[5] in VOICE_CREATOR_ADDRS or d[5] == 0x0A
            if d[3] == 0x0A:
                return d[5] in VOICE_CREATOR_ADDRS_0A
            return False

        # NRPN de Sound Controller (99=1 / 98=lsb / 6 / 38) deste canal: acha
        # os índices exatos (só os que este método gerencia) pra remover junto.
        idx_nrpn_remover = set()
        st_nrpn = {'msb': None, 'lsb': None, 'i99': None, 'i98': None}
        for i_msg, msg in enumerate(self.merged_track_cache):
            if msg.type != 'control_change' or msg.channel != canal_idx:
                continue
            if msg.control == 99:
                st_nrpn.update(msb=msg.value, i99=i_msg, lsb=None, i98=None)
            elif msg.control == 98:
                st_nrpn.update(lsb=msg.value, i98=i_msg)
            elif msg.control in (6, 38) and st_nrpn['msb'] == 1 and st_nrpn['lsb'] in _NRPN_LSB_GERENCIADOS:
                idx_nrpn_remover.add(i_msg)
                if st_nrpn['i99'] is not None: idx_nrpn_remover.add(st_nrpn['i99'])
                if st_nrpn['i98'] is not None: idx_nrpn_remover.add(st_nrpn['i98'])

        abs_msgs = []
        curr_t = 0
        for i_msg, msg in enumerate(self.merged_track_cache):
            curr_t += msg.time
            if i_msg in idx_nrpn_remover or eh_sysex_deste_canal(msg):
                continue
            abs_msgs.append((curr_t, msg))

        novas_msgs_vc = []
        for addr, val in sorted(valores.items(), key=lambda kv: str(kv[0])):
            if addr == "porta_time":
                # Portamento (Tempo + Liga/Desliga derivado) - CC 5 + CC 65,
                # NÃO SysEx. Os endereços 0x67/0x68 do Data List (MULTI
                # PART) foram testados de verdade pelo Michel e não tiveram
                # efeito nenhum no som - o teclado real só responde ao
                # padrão MIDI (mesmo mecanismo que o MHS MIDI Sequencer já
                # usa no campo "Porta Time").
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=5, value=val))
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=65, value=127 if val > 0 else 0))
            elif addr == 0x09:
                # Detune: o modelo guarda 1 valor combinado (0-255) - a
                # SysEx de verdade precisa de 2 mensagens, 1 nibble cada.
                alto, baixo = detune_separar(val)
                novas_msgs_vc.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, canal_idx, 0x09, alto)))
                novas_msgs_vc.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, canal_idx, 0x0A, baixo)))
            elif addr in _VC_PARA_CC:
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=_VC_PARA_CC[addr], value=val))
            elif addr in _VC_PARA_NRPN_LSB:
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=99, value=1))
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=98, value=_VC_PARA_NRPN_LSB[addr]))
                novas_msgs_vc.append(mido.Message('control_change', channel=canal_idx, control=6, value=val))
            elif addr in VOICE_CREATOR_ADDRS_0A:
                # Portamento (Mono Priority/Modo/Modo do Tempo) - bloco
                # 0x0A de verdade, não o 0x08 de sempre.
                novas_msgs_vc.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x0A, canal_idx, addr, val)))
            else:
                novas_msgs_vc.append(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, canal_idx, addr, val)))

        if novas_msgs_vc:
            primeiro_marker_tick = float('inf')
            temp_abs = 0
            for m in self.merged_track_cache:
                temp_abs += m.time
                if m.type in ('marker', 'cuepoint') and getattr(m, 'text', '') not in ('SFF1', 'SFF2', 'SInt'):
                    primeiro_marker_tick = temp_abs
                    break
            if primeiro_marker_tick == float('inf'):
                primeiro_marker_tick = 0

            ponto_insercao = max(0, primeiro_marker_tick - 1)
            curr_t = 0
            for msg in self.merged_track_cache:
                curr_t += msg.time
                if curr_t >= primeiro_marker_tick:
                    break
                if getattr(msg, 'channel', None) == canal_idx and msg.type == 'program_change':
                    ponto_insercao = curr_t
            for syx in novas_msgs_vc:
                abs_msgs.append((ponto_insercao, syx.copy()))

            starts = sorted({s['start'] for s in getattr(self, 'sections_info', []) if s.get('start') is not None})
            primeira_secao_idx = next((k for k, st_ in enumerate(starts) if st_ >= primeiro_marker_tick), None)
            for i, start in enumerate(starts):
                if start < primeiro_marker_tick:
                    continue
                fim_secao = starts[i + 1] if i + 1 < len(starts) else float('inf')
                ponto_insercao_secao = None
                curr_t = 0
                for msg in self.merged_track_cache:
                    curr_t += msg.time
                    if curr_t < start:
                        continue
                    if curr_t >= fim_secao:
                        break
                    if getattr(msg, 'channel', None) == canal_idx and msg.type == 'program_change':
                        ponto_insercao_secao = curr_t
                if ponto_insercao_secao is None:
                    # A primeira seção do arquivo leva os parâmetros mesmo sem
                    # Program Change: foi assim que o próprio SX gravou a voz
                    # ADA (CC 71-74 + NRPN logo na cabeça da Main A).
                    if i == primeira_secao_idx:
                        ponto_insercao_secao = start
                    else:
                        continue
                for syx in novas_msgs_vc:
                    abs_msgs.append((ponto_insercao_secao, syx.copy()))

        self.midi_setup_msgs = [m for m in getattr(self, 'midi_setup_msgs', []) if not eh_sysex_deste_canal(m)]
        self.midi_setup_msgs.extend(msg.copy() for msg in novas_msgs_vc)

        self.rebuild_from_abs_list(abs_msgs)

    def abrir_teste_drum_setup(self, event):
        ch = self.channelList.GetSelection()
        if ch == wx.NOT_FOUND:
            falar("Selecione um canal primeiro.", imediato=True)
            return

        c = self.canais[ch]
        bank = c.get("Bank", 0)
        patch = c.get("Patch", 0)
        custom_maps = c.get("CustomDrumMap", {})
        if custom_maps:
            nota_teste = next(iter(custom_maps))
            mapa = custom_maps[nota_teste]
        else:
            nota_teste = 40
            mapa = {'bank': 0, 'patch': 0, 'dest_note': nota_teste}

        part_byte = 0x30 if ch == 9 else 0x31

        class TesteDrumSetupDialog(wx.Dialog):
            def __init__(self, parent_frame, canal_idx, bank, patch, part_byte, nota_teste, mapa):
                super().__init__(parent_frame, title="Teste Passo a Passo - Drum Setup", size=(500, 400))
                self.parent_frame = parent_frame

                self.passos = [
                    ("Enviar XG System On", ('sysex', (0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00))),
                    (f"Enviar Bank Select MSB {bank // 128} no canal {canal_idx + 1} (real, CC 0)", ('cc', canal_idx, 0, bank // 128)),
                    (f"Enviar Bank Select LSB {bank % 128} no canal {canal_idx + 1} (real, CC 32)", ('cc', canal_idx, 32, bank % 128)),
                    (f"Enviar Program Change {patch} no canal {canal_idx + 1} (real)", ('pc', canal_idx, patch)),
                    (f"PARE E TOQUE a nota {nota_teste} agora. Deve soar o som original do kit.", None),
                    (f"Enviar mapeamento: nota {nota_teste} vira banco {mapa['bank']} patch {mapa['patch']} peça {mapa['dest_note']}",
                     ('sysex', (0x43, 0x10, 0x4C, part_byte, nota_teste, 0x70, mapa['bank'] // 128, mapa['bank'] % 128, mapa['patch'], mapa['dest_note']))),
                    (f"TOQUE a nota {nota_teste} de novo. Deve soar diferente agora, se funcionou.", None),
                ]

                self.list_box = wx.ListBox(self, choices=[p[0] for p in self.passos], style=wx.LB_SINGLE)
                sizer = wx.BoxSizer(wx.VERTICAL)
                sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 10)
                btn_close = wx.Button(self, wx.ID_CLOSE, "Fechar")
                sizer.Add(btn_close, 0, wx.ALIGN_CENTER | wx.ALL, 10)
                self.SetSizer(sizer)

                self.list_box.SetSelection(0)
                self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.executar_passo_atual())
                self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
                btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))

                wx.CallLater(100, self.list_box.SetFocus)

            def executar_passo_atual(self):
                idx = self.list_box.GetSelection()
                if idx == wx.NOT_FOUND: return
                label, comando = self.passos[idx]
                from MHS_Utils import falar
                porta = getattr(self.parent_frame, 'midi_out', None)
                if comando is not None and porta:
                    import mido
                    try:
                        tipo = comando[0]
                        if tipo == 'sysex':
                            porta.send(mido.Message('sysex', data=comando[1]))
                        elif tipo == 'cc':
                            _, canal, controle, valor = comando
                            porta.send(mido.Message('control_change', channel=canal, control=controle, value=valor))
                        elif tipo == 'pc':
                            _, canal, programa = comando
                            porta.send(mido.Message('program_change', channel=canal, program=programa))
                        falar(f"Enviado: {label}", imediato=True)
                    except Exception as e:
                        falar(f"Erro ao enviar: {e}", imediato=True)
                else:
                    falar(label, imediato=True)
                if idx < len(self.passos) - 1:
                    self.list_box.SetSelection(idx + 1)

            def on_key(self, event):
                code = event.GetKeyCode()
                if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
                    self.executar_passo_atual()
                    return
                elif code == wx.WXK_ESCAPE:
                    self.EndModal(wx.ID_CLOSE)
                    return
                event.Skip()

        dlg = TesteDrumSetupDialog(self, ch, bank, patch, part_byte, nota_teste, mapa)
        dlg.ShowModal()
        dlg.Destroy()

    def atualizar_apos_midi_in(self, ch, prop):
        from MHS_Utils import falar
        self.dirty = True
        
        if ch == self.canal_atual:
            if prop == "Patch":
                b = self.canais[ch]["Bank"]
                p = self.canais[ch]["Patch"]
                nome = self.ins_db.get(b, {}).get(p, f"Patch {p}").replace('PSR-SX600 ', '')
                falar(nome, imediato=True)
            elif prop == "Bank":
                b = self.canais[ch]["Bank"]
                nome_b = self.bank_names.get(b, "")
                falar(f"Banco {b}{' - ' + nome_b if nome_b else ''}", imediato=True)
        
        try:
            self.atualizar_titulo()
        except Exception:
            pass
        try:
            if hasattr(self, 'update_mixer_list'):
                self.update_mixer_list()
        except Exception:
            pass

    def transpor_midi_in(self, event):
        from MHS_Utils import falar
        eid = event.GetId()
        
        if not hasattr(self, 'midi_in_octave'): self.midi_in_octave = 0
        if not hasattr(self, 'midi_in_semitone'): self.midi_in_semitone = 0
        
        if eid == 280:  # Ctrl + Seta Cima
            if self.midi_in_octave < 2:
                self.midi_in_octave += 1
                falar(f"Oitava {self.midi_in_octave}", imediato=True)
            else:
                falar("Limite máximo de duas oitavas atingido", imediato=True)
        elif eid == 281:  # Ctrl + Seta Baixo
            if self.midi_in_octave > -2:
                self.midi_in_octave -= 1
                falar(f"Oitava {self.midi_in_octave}", imediato=True)
            else:
                falar("Limite mínimo de duas oitavas atingido", imediato=True)
        elif eid == 282:  # Ctrl + Seta Esquerda
            if self.midi_in_semitone > -12:
                self.midi_in_semitone -= 1
                falar(f"Semitom {self.midi_in_semitone}", imediato=True)
            else:
                falar("Limite mínimo de doze semitons atingido", imediato=True)
        elif eid == 283:  # Ctrl + Seta Direita
            if self.midi_in_semitone < 12:
                self.midi_in_semitone += 1
                falar(f"Semitom {self.midi_in_semitone}", imediato=True)
            else:
                falar("Limite máximo de doze semitons atingido", imediato=True)

    def remover_duplicatas_estado(self, abs_msgs):
        from MHS_Utils import CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS
        controles_de_estado = {CC_BANK_MSB, CC_BANK_LSB, CC_VOLUME, CC_PAN, CC_EXPRESSION, CC_REVERB, CC_CHORUS, 101, 100, 6}
        ultima_ocorrencia = {}
        for i, (t, msg) in enumerate(abs_msgs):
            ch = getattr(msg, 'channel', None)
            if ch is None: continue
            if msg.type == 'program_change':
                chave = (t, ch, 'program_change', None)
            elif msg.type == 'control_change' and msg.control in controles_de_estado:
                chave = (t, ch, 'control_change', msg.control)
            elif msg.type == 'pitchwheel':
                chave = (t, ch, 'pitchwheel', None)
            else:
                continue
            ultima_ocorrencia[chave] = i
        
        indices_manter = set(ultima_ocorrencia.values())
        resultado = []
        for i, (t, msg) in enumerate(abs_msgs):
            ch = getattr(msg, 'channel', None)
            eh_estado = False
            if ch is not None:
                if msg.type == 'program_change': eh_estado = True
                elif msg.type == 'control_change' and msg.control in controles_de_estado: eh_estado = True
                elif msg.type == 'pitchwheel': eh_estado = True
            if eh_estado and i not in indices_manter:
                continue
            resultado.append((t, msg))
        return resultado

    def abrir_editor_marcadores(self, event):
        if not getattr(self, 'merged_track_cache', None):
            falar("Nenhum estilo carregado.", imediato=True)
            return
            
        class EditorMarcadoresDialog(wx.Dialog):
            def __init__(self, parent_frame):
                super().__init__(parent_frame, title="Editor de Marcadores (Teste)", size=(500, 400), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
                self.parent_frame = parent_frame
                
                self.list_box = wx.ListBox(self, style=wx.LB_SINGLE)
                sizer = wx.BoxSizer(wx.VERTICAL)
                sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 10)
                btn_close = wx.Button(self, wx.ID_CLOSE, "Fechar")
                sizer.Add(btn_close, 0, wx.ALIGN_CENTER | wx.ALL, 10)
                self.SetSizer(sizer)
                
                self.carregar_marcadores()
                self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.editar_selecionado())
                self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
                btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
                
                from MHS_Utils import falar
                falar("Editor de Marcadores. Navegue com Seta, Enter para editar.", imediato=True)
                wx.CallLater(100, self.list_box.SetFocus)

            def carregar_marcadores(self):
                self.marcadores = []
                abs_t = 0
                for idx, msg in enumerate(self.parent_frame.merged_track_cache):
                    abs_t += msg.time
                    if msg.type == 'marker':
                        self.marcadores.append({'idx': idx, 'tick': abs_t, 'nome': msg.text})
                self.list_box.Clear()
                for m in self.marcadores:
                    self.list_box.Append(f"Tick {m['tick']}: {m['nome']}")
                if self.marcadores:
                    self.list_box.SetSelection(0)

            def editar_selecionado(self):
                sel = self.list_box.GetSelection()
                if sel == wx.NOT_FOUND: return
                m = self.marcadores[sel]
                dlg = wx.TextEntryDialog(self, f"Novo nome para o marcador no tick {m['tick']}:", "Editar Marcador", m['nome'])
                if dlg.ShowModal() == wx.ID_OK:
                    novo_nome = dlg.GetValue()
                    msg_original = self.parent_frame.merged_track_cache[m['idx']]
                    self.parent_frame.merged_track_cache[m['idx']] = msg_original.copy(text=novo_nome)
                    self.parent_frame.dirty = True
                    self.parent_frame.atualizar_titulo()
                    self.parent_frame.rebuild_sections_from_cache()
                    from MHS_Utils import falar
                    falar(f"Marcador alterado para {novo_nome}", imediato=True)
                    self.carregar_marcadores()
                    self.list_box.SetSelection(sel)
                dlg.Destroy()
                self.list_box.SetFocus()

            def on_key(self, event):
                k = event.GetKeyCode()
                if k == wx.WXK_ESCAPE:
                    self.EndModal(wx.ID_CLOSE)
                    return
                if k in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
                    self.editar_selecionado()
                    return
                event.Skip()
        
        dlg = EditorMarcadoresDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def OnLimparCanalTodasSecoes(self, event):
        # Pedido do Michel: gravou por engano num canal errado e precisava de
        # um jeito de deixar ESSE canal virgem em TODAS as seções de uma vez
        # (não só na seção atual) - notas, controles, program change, sysex
        # de afinação/Drum Setup e o CASM inteiro (NTR/NTT/High Key/Zona
        # Aguda/Redirecionar/Acordes) voltam ao zero, em todo o arquivo.
        ch = self.channelList.GetSelection()
        if ch == wx.NOT_FOUND:
            falar("Selecione um canal primeiro.", imediato=True)
            return
        if self.playing:
            falar("Pare a reprodução antes de limpar um canal.", imediato=True)
            return
        nome_canal = rotulo_canal(ch)
        dlg = wx.MessageDialog(
            self,
            f"Isso remove TUDO do canal {nome_canal} em TODAS as seções e na "
            f"área de configuração: notas, controles (volume/pan/banco/peça "
            f"etc.), sysex de afinação/Drum Setup e o CASM inteiro (NTR/NTT/"
            f"High Key/Zona Aguda/Redirecionar/Acordes), deixando o canal "
            f"virgem em todo o arquivo. Essa ação vai para o Ctrl+Z (Desfazer) "
            f"normalmente. Continuar?",
            "Limpar Canal em Todas as Seções", wx.YES_NO | wx.ICON_WARNING)
        resposta = dlg.ShowModal()
        dlg.Destroy()
        if resposta != wx.ID_YES:
            falar("Cancelado.", imediato=True)
            return
        self.save_state(f"Limpar Canal {nome_canal} em Todas as Seções")
        self.limpar_canal_em_tudo(ch)
        falar(f"Canal {nome_canal} limpo em todas as seções.", imediato=True)

    def limpar_canal_em_tudo(self, ch):
        # Faz o trabalho de verdade do OnLimparCanalTodasSecoes, separado pra
        # dar pra chamar de um teste sem precisar do MessageDialog/save_state.
        part_byte = 0x30 if ch == 9 else 0x31

        def eh_sysex_do_canal(msg):
            if msg.type != 'sysex':
                return False
            d = bytes(msg.data)
            # Grave/Agudo - o canal mora no próprio endereço (d[4]), não em
            # msg.channel (sysex não tem esse atributo).
            if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[4] == ch and d[5] in (0x72, 0x73):
                return True
            # Voice Creator (timbre XG de Multi Part) - o canal mora em d[4].
            # 0x0A é o 2º byte do Detune (não está em VOICE_CREATOR_ADDRS,
            # mas precisa ser limpo junto do 0x09).
            if len(d) >= 7 and d[0] == 0x43 and d[2] == 0x4C and d[3] == 0x08 and d[4] == ch and (d[5] in VOICE_CREATOR_ADDRS or d[5] == 0x0A):
                return True
            # Drum Setup (afinação por peça + mapeamento de peça custom) -
            # só existe de verdade nos dois canais de bateria.
            if ch in (8, 9) and len(d) >= 4 and d[0] == 0x43 and d[2] == 0x4C and d[3] == part_byte:
                return True
            return False

        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            if getattr(msg, 'channel', -1) == ch:
                continue
            if eh_sysex_do_canal(msg):
                continue
            abs_msgs.append((curr_t, msg))

        # CASM desse canal volta ao padrão de fábrica do papel dele em TODA
        # seção já conhecida (mesmo padrão que uma seção nova ganha na
        # primeira vez) - não é um apagamento físico do registro (isso exigiria
        # mexer no que ainda não decifremos do formato - ver comentário em
        # patch_casm_binary), mas garante que nada customizado sobra.
        padrao_canal = self.get_default_casm_rules()[ch]
        biblioteca = getattr(self, 'casm_rules_by_section', None)
        if biblioteca:
            for regras in biblioteca.values():
                regras[ch] = dict(padrao_canal)
        if getattr(self, 'casm_rules', None):
            self.casm_rules[ch] = dict(padrao_canal)

        # Config de Drum Setup guardada à parte (fora da trilha) também volta
        # a zero, senão ela mesma se reaplica sozinha na próxima vez que algo
        # mexer nesse canal.
        if 0 <= ch < len(self.canais):
            self.canais[ch]["DrumParams"] = {}
            self.canais[ch]["CustomDrumMap"] = {}
            self.canais[ch]["VoiceCreator"] = {}

        self.rebuild_from_abs_list(abs_msgs)

    def OnEsvaziarSecao(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]
        if not sec.get('present', False) or sec.get('start') is None:
            falar("Essa seção já está vazia.", imediato=True)
            return
        if self.playing:
            falar("Pare a reprodução antes de esvaziar uma seção.", imediato=True)
            return

        dlg = wx.MessageDialog(self, f"Isso remove TUDO da seção {sec['display_name']} (notas, configuração de canal e CASM), deixando ela vazia como se nunca tivesse sido criada. Essa ação não pode ser desfeita pelo Ctrl+Z. Continuar?", "Esvaziar Seção", wx.YES_NO | wx.ICON_WARNING)
        resposta = dlg.ShowModal()
        dlg.Destroy()
        if resposta != wx.ID_YES:
            falar("Cancelado.", imediato=True)
            return

        self.save_state(f"Esvaziar Seção {sec['display_name']}")

        t_start = sec['start']
        t_end = sec['end']
        if t_end == float('inf'):
            t_end = sum(m.time for m in self.merged_track_cache)

        duracao = t_end - t_start

        # Remove todo mundo que caía dentro da seção - notas, CCs locais,
        # marcador e o texto "fn:" que vem logo depois dele - e FECHA o buraco
        # de tempo que ela deixaria, empurrando pra trás tudo que vem depois.
        # Sem isso, o espaço da seção ficava reservado só que sem dono, e a
        # próxima seção criada ali herdava esse buraco fantasma (foi isso que
        # grudou um compasso mudo extra na seção anterior).
        abs_msgs = []
        curr_t = 0
        for msg in self.merged_track_cache:
            curr_t += msg.time
            if t_start <= curr_t < t_end:
                continue
            elif curr_t >= t_end:
                abs_msgs.append((curr_t - duracao, msg))
            else:
                abs_msgs.append((curr_t, msg))

        # Remove também a entrada dessa seção no CASM, se existir
        nome_alvo = sec['name'].strip().lower()
        biblioteca = getattr(self, 'casm_rules_by_section', {}) or {}
        chaves_remover = [k for k in biblioteca.keys() if k.strip().lower() == nome_alvo]
        for k in chaves_remover:
            del biblioteca[k]

        self.rebuild_from_abs_list(abs_msgs)
        falar(f"Seção {sec['display_name']} esvaziada.", imediato=True)

    def corrigir_casm_secao_atual(self, event):
        idx = self.sectionList.GetSelection()
        if idx == wx.NOT_FOUND or not getattr(self, 'sections_info', []): return
        sec = self.sections_info[idx]
        if not sec.get('present', False) or sec.get('start') is None:
            falar("Essa seção ainda está vazia - grave alguma coisa nela primeiro.", imediato=True)
            return

        # Uma seção só ganha CASM de verdade quando alguém abre "Editar Seção"
        # e clica em Salvar Alterações nela pelo menos uma vez - gravar (R)
        # sozinho nunca fazia isso. Se isso nunca aconteceu (ou o diálogo foi
        # cancelado sem querer), a seção fica com o CASM cru do molde -
        # editable/notemute/chordtype/byte 39 zerados - e o SX600 ignora ela
        # na hora de tocar, mesmo com notas de verdade gravadas.
        nome_alvo = sec['name'].strip().lower()
        biblioteca = getattr(self, 'casm_rules_by_section', {}) or {}
        ja_existia = any(k.strip().lower() == nome_alvo for k in biblioteca.keys())
        if ja_existia:
            falar(f"A seção {sec['display_name']} já tem CASM próprio - nada foi mudado.", imediato=True)
            return

        self.save_state(f"Corrigir CASM da Seção {sec['display_name']}")
        self.obter_casm_da_secao(sec['name'], criar_se_ausente=True)
        self.dirty = True
        self.atualizar_titulo()
        falar(f"CASM da seção {sec['display_name']} corrigido com os padrões. Salve o arquivo pra valer.", imediato=True)