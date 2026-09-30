import sys
import wx
import mido
import mido.backends.rtmidi
import MHS_CasmTemplate
import MHS_DrumSetup
from MHS_MainFrame import StyleCreatorFrame

if __name__ == '__main__':
    app = wx.App()
    # sys.argv[1] = caminho do arquivo, quando o Windows chama o programa
    # por associação de extensão (duplo clique / "Abrir com") num .sty/.prs/.cte.
    arquivo_inicial = sys.argv[1] if len(sys.argv) > 1 else None
    frame = StyleCreatorFrame(arquivo_inicial)
    # Só na abertura de verdade do programa (não em teste automatizado, que
    # constrói StyleCreatorFrame() direto sem passar por main.py) - mostra a
    # tela de Changelog na primeira vez que uma versão nova é aberta.
    wx.CallAfter(frame.mostrar_changelog_se_necessario)
    # Checagem de atualização (opcional, ver aba "Atualizações" em
    # Configurações Gerais) - mesmo motivo do changelog acima: só dispara na
    # abertura de verdade do programa, nunca em teste automatizado.
    wx.CallAfter(frame.verificar_atualizacoes_ao_iniciar)
    app.MainLoop()
