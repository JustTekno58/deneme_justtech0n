'''
Araçlar: GS1 / ZPL mühendisliği
- GS (ASCII 29) karakterini Zebra ZPL'e uygun biçimde encode eder (^FH# + #1D)
- Zebra GS1 DataMatrix ZPL üretir
'''
from __future__ import annotations

def gs1_to_zpl_escaped(code: str) -> str:
    clean = (code or "").strip()
    temp = clean.replace("#", "#23")
    formatted = temp.replace(chr(29), "#1D").replace("", "#1D")
    # Not: GS1 için başa zorla GS eklemiyoruz; sadece mevcut GS ayraçlarını encode ediyoruz.
    return formatted

def mm_to_dots(mm: float, dpi: int = 203) -> int:
    """Zebra için mm -> dot dönüşümü (203 dpi varsayılan)."""
    try:
        mmf = float(mm)
    except Exception:
        mmf = 0.0
    return max(0, int(round((mmf / 25.4) * dpi)))


def generate_gs1_datamatrix_zpl(
    code: str,
    darkness: int = 20,
    width_mm: float = 50,
    height_mm: float = 30,
    x_mm: float = 0,
    y_mm: float = 0,
    dpi: int = 203,
    module_size: int = 6,
) -> str:
    """GS1 DataMatrix için ZPL üretir.

    Parametreler:
      - width_mm/height_mm: etiket boyutu (mm)
      - x_mm/y_mm: baskı ofseti (mm)  -> 'konum' ayarı
      - darkness: Zebra ~SD
      - dpi: 203 / 300 vb.
      - module_size: DataMatrix modül boyutu (2-12)
    """
    formatted_code = gs1_to_zpl_escaped(code)

    try:
        dark = int(darkness)
    except Exception:
        dark = 20

    pw = mm_to_dots(width_mm, dpi=dpi)
    ll = mm_to_dots(height_mm, dpi=dpi)
    xo = mm_to_dots(x_mm, dpi=dpi)
    yo = mm_to_dots(y_mm, dpi=dpi)

    # Basit yerleşim: etiket merkezine yakın
    base_x = max(0, (pw // 2) - 125)  # yaklaşık 250 dot DM alanı
    base_y = max(0, (ll // 2) - 125)
    fo_x = base_x + xo
    fo_y = base_y + yo

    try:
        ms = int(module_size)
    except Exception:
        ms = 6
    ms = max(2, min(12, ms))

    return (
        "^XA\n"
        f"~SD{dark:02d}\n"
        f"^PW{pw}\n"
        f"^LL{ll}\n"
        f"^FO{fo_x},{fo_y}\n"
        f"^BXN,{ms},200,,,,#\n"
        "^FH#\n"
        f"^FD{formatted_code}^FS\n"
        "^XZ"
    )
def format_to_gs1_short(text: str) -> str:
    raw_text = (text or "").replace("(", "").replace(")", "")
    if not raw_text.startswith("01") or len(raw_text) < 18:
        return raw_text
    gtin = raw_text[2:16]
    remainder = raw_text[16:]
    if remainder.startswith("21"):
        serial_raw = remainder[2:]
        cut_index = len(serial_raw)
        for marker in ["91", "92", "93"]:
            idx = serial_raw.find(marker)
            if idx != -1 and idx < cut_index:
                cut_index = idx
        serial = serial_raw[:cut_index]
        return f"01{gtin}21{serial}"
    return raw_text
