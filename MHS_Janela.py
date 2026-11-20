# -*- coding: utf-8 -*-
"""Janela principal na frente, na abertura do programa.

Depois da instalação, com "Executar" marcado, o programa abria sem tomar o primeiro plano (e, para quem usa leitor de tela,
a janela parecia minimizada): o Windows só deixa um programa novo pegar o foco num instantinho, e o antivírus examinando o
executável recém-instalado faz a janela chegar depois dele. Aqui, nos primeiros instantes depois de abrir:
  - se a janela estiver minimizada, ela é restaurada;
  - se o programa não for a janela ativa, ela é trazida para a frente (se houver uma janela de diálogo aberta, como a das
    Novidades da versão, é ela que vai para a frente).
Só age na abertura (duas tentativas, a 0,3 s e a 2 s) e nunca esconde nada; qualquer erro é ignorado.
"""
import ctypes

import wx

ATRASOS_MS = (300, 2000)


def trazer_para_frente(frame):
    try:
        if not frame:
            return
        if frame.IsIconized():
            frame.Iconize(False)
        alvo = frame
        for w in wx.GetTopLevelWindows():
            if isinstance(w, wx.Dialog) and w.IsShown() and w.IsModal():
                alvo = w
        if alvo.IsIconized():
            alvo.Iconize(False)
        if wx.GetActiveWindow() is not None:
            return                                   # o programa já está na frente
        hwnd = alvo.GetHandle()
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)                    # SW_RESTORE
        tid_eu = k.GetCurrentThreadId()
        tid_fg = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        ligado = bool(tid_fg and tid_fg != tid_eu and u.AttachThreadInput(tid_eu, tid_fg, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if ligado:
                u.AttachThreadInput(tid_eu, tid_fg, False)
        alvo.Raise()
    except Exception:
        pass


def agendar(frame):
    """Chamado uma vez pelo bloco principal, logo depois de criar a janela."""
    for ms in ATRASOS_MS:
        wx.CallLater(ms, trazer_para_frente, frame)
