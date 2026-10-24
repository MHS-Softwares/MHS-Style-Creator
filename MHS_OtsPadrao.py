# -*- coding: utf-8 -*-
"""Trilha-modelo de um One Touch Setting (MTrk gravado pelo teclado), usada para criar OTS em estilos que não têm.

É um OTS de verdade, só as partes em branco (Right 3) servem de padrão: MHS_Ots.Trilha.restaurar_padrao refaz as outras três a partir dela."""

import base64
import zlib

_DADOS = (
    "eNrtlttqG1cUhtdBI41GMlFC24tiwli2SdqADQ5NoSfkQ6kd7CIbh6YYp6SVgyFtWiyQe2foE2lmXqCHF8qdL901M57176s+QFvBtr81s9des/"
    "bnrfHB8cVrojszetvdnvI4Yv7w2lk2Go6Jrq5pTkTzdIt+H9N890ea/8A0//4Vzdsjmu+NbuNJHVfcDTgOOKn4bbw92I8pIlRpTaxKJ6V5YlO/"
    "svHUxplVnXCdvnlF82ixSe2PrhtcGGEVbS4nJOSo5JNnA8cLLHG57ji1q3VdG22h+cljmp9Omtv3UWCE/DRxXEKtIfBrpG0hbYwJh8Aj4AnSdp"
    "B2igkvgN+VmGwPjh4OTFYYcBhIGGgQMMEGl84zWyVLZ/THc8p2X1Nm/jJznpmMzJzX8aSOK+4GHAecVFw/JkeMKq03VqXziDJznpnzzJxntveZ"
    "Oa/SN40jalL7B02zHDhnOGcRR2WfPLvnCOd8+dixdF7XtdG2Yc6z07PmNpwznHMaOcI5D3EVzhnOGc4ZzhnOGc4ZzhnOGc45cM6hcw6dc+icQ+"
    "ccOpeSc1slT4n+tF+7I8rNX27Oc5OR7zXxpI4r7gYcB5xUXD+mBM6lZX9ZeeeKcnOem/PcnOe297k5r9LNee7OBedcAucC54JzLjjnMus7wrlc"
    "PnEsndd1bdg5z08WKT/1unAucC445wLngnMucC5wLnAucC5wLnAucC5wLnAugXMJnUvoXELnEjqX0LmWXNA5Feb8r2+p2P2VCvNXmPPCZBR7n9"
    "/GkzquuBtwHHBScf2YGjjX8ru96PxEhTkvzHnx9DMqbO8Lc16lm/PCnSuca+BcdbPZJIVzhXOd3XG8SB0vP3Asndd1bdg5L06eU3H6prl9/9BX"
    "hXNNUQDOdYgCcK5wrnCucK5wrnCucK5wrnCugXMNnWvoXEPnGjrX2nnP9vEwprtC3WpXB/u22HvBOzgOmJvqSr13HCV2VGDrlWPEju3EsTNyjL"
    "FuF5gAU+AScLjouIzFVtYcV8ur/brDe9ZXNwy5Cuv+2fpfaPpneneAN0l8BUb/3HvfUXqOOnZseacc7Tu2/Tm5g8XQP6N/Rv+M/vFeUUb/jP55"
    "JXVc/cIb5rL/hTBkOvL+5a7cfgNYmtAoeAME/gX9Sw8oN44KbAEjYBvYAcbALjABpsAl4BC4DFwBrt54h2odPmg6VPoGhjUwrOhQeyuO8qmjYk"
    "ILGAHbQBhWGFYYVhjWtO+49KXj8InjMq6uIG2VXKmWhh+gFXFxLcJRb5X/7QV3oglYBmAN5rQ8u2PZHf8St8iyb65+a21P+7zzyfrBs/3jvXS8"
    "ubO+dfFyOh2f28+zmrfPf76YTDfWjjc++njtl5cT+vd9SiVHD+u9rrH8a7rdnoj+65//t+cfPzfr9Dccr1TJ"
)


def modelo():
    return zlib.decompress(base64.b64decode(_DADOS))
