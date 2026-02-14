"""
code_parser.py
Chestny ZNAK / GS1 / "short code" otomatik algılama + normalize.

Amaç:
- Scanner'dan gelen ham veriyi (raw) al
- Türünü algıla (PLAIN / GS1_SHORT / CTRL_MIXED)
- Eşleştirme için normalize et (kontrol karakterlerini temizle, istenirse GS(0x1D) kaldır)

Not:
- GS (0x1D) bazı GS1 akışlarında ayırıcıdır. Liste verileri çoğu zaman "printable" düz metin olduğundan
  eşleştirme için GS kaldırılmış (nogs) varyantı da gerekir.
"""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata


GS = chr(29)  # ASCII Group Separator

# Bazı kaynaklarda GS karakteri dosyalarda yazılamadığı için "!s!", "!j!" gibi placeholder ayraçlar kullanılır.
# Bu tokenlar geldiğinde de veriyi "ShortKod/GS1" olarak algılamak gerekir.
PLACEHOLDER_GS_TOKENS = ["!s!", "!j!"]


@dataclass(frozen=True)
class CodeInfo:
    raw: str
    cleaned_keep_gs: str
    normalized_nogs: str
    code_type: str  # PLAIN | GS1_SHORT | CTRL_MIXED
    has_gs: bool
    has_other_ctrl: bool
    raw_len: int
    cleaned_len: int
    normalized_len: int


def _strip_invisible(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    # BOM ve tipik görünmezler
    return (s.replace("\ufeff", "")
             .replace("\u200b", "")
             .replace("\u200c", "")
             .replace("\u200d", "")
             .replace("\u2060", ""))


def _clean(s: str, keep_gs: bool) -> str:
    """Görünmez/format kontrol karakterlerini temizler.
    keep_gs=True ise GS (0x1D) korunur, aksi halde kaldırılır.
    """
    s = _strip_invisible(s)
    s = unicodedata.normalize("NFKC", s)

    out = []
    for ch in s:
        o = ord(ch)
        if o == 29:
            if keep_gs:
                out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("C"):  # control/format/surrogate/private/unassigned
            continue
        if ch in ("\r", "\n", "\t"):
            continue
        out.append(ch)
    return "".join(out).strip()


def detect_type(raw: str) -> dict:
    """Ham veriden tür algılar."""
    raw_s = "" if raw is None else str(raw)
    raw_s = _strip_invisible(raw_s)
    has_gs = (GS in raw_s) or any(tok in raw_s for tok in PLACEHOLDER_GS_TOKENS)
    # GS1 AI yapısı: 01 + 14 haneli GTIN + 21 (Serial) ile başlıyorsa ShortKod kabul et
    import re as _re
    is_gs1_ai = bool(_re.match(r"^01\d{14}21", raw_s))

    has_other_ctrl = False
    for ch in raw_s:
        o = ord(ch)
        if o == 29:
            continue
        # 0-31 kontrol; ayrıca DEL (127)
        if (0 <= o < 32) or (o == 127):
            has_other_ctrl = True
            break
        # unicode kategori C de kontrol/format olabilir
        if unicodedata.category(ch).startswith("C"):
            has_other_ctrl = True
            break

    if has_gs and has_other_ctrl:
        typ = "CTRL_MIXED"
    elif has_gs or is_gs1_ai:
        typ = "GS1_SHORT"
    elif has_other_ctrl:
        typ = "CTRL_MIXED"
    else:
        typ = "PLAIN"

    return {"type": typ, "has_gs": has_gs, "has_other_ctrl": has_other_ctrl}


def analyze(raw: str) -> CodeInfo:
    """Tek çağrıda: detect + iki varyant normalize."""
    det = detect_type(raw)
    cleaned_keep = _clean(raw, keep_gs=True)
    normalized_nogs = _clean(raw, keep_gs=False).replace(GS, "")  # güvenlik

    return CodeInfo(
        raw="" if raw is None else str(raw),
        cleaned_keep_gs=cleaned_keep,
        normalized_nogs=normalized_nogs,
        code_type=det["type"],
        has_gs=det["has_gs"],
        has_other_ctrl=det["has_other_ctrl"],
        raw_len=len("" if raw is None else str(raw)),
        cleaned_len=len(cleaned_keep),
        normalized_len=len(normalized_nogs),
    )


def parse_gs1(normalized: str) -> dict:
    """Basit GS1 AI ayrıştırma.

    Şu an en çok kullanılan AI'lar hedeflenir:
    - 01: GTIN (14 hane, sabit uzunluk)
    - 21: Serial (değişken uzunluk, genelde sona kadar)
    Not: Bazı sistemler GS yerine '!s!'/'!j!' gibi placeholder bırakabilir. Bu fonksiyon onları da ayıraç gibi ele alır.
    """
    if normalized is None:
        return {}

    s = str(normalized)

    # Placeholder'ları görünür ayıraca çevir (parse için)
    for tok in PLACEHOLDER_GS_TOKENS:
        s = s.replace(tok, GS)

    # Kontrol karakterlerini temizle ama GS kalsın
    s = _clean(s, keep_gs=True)

    # GS ile segmentlere ayır
    parts = [p for p in s.split(GS) if p]

    # Eğer hiç GS yoksa tek parça
    if not parts:
        parts = [s]

    out = {}
    # Her parçada AI'ları sırayla okuyalım
    for part in parts:
        p = part.strip()
        # En basit: 01 + 14 hane ile başlıyorsa GTIN al
        if p.startswith("01") and len(p) >= 16:
            gtin = p[2:16]
            out["01"] = gtin
            rest = p[16:]
        else:
            rest = p

        # 21 varsa serial al (21 + kalan)
        idx = rest.find("21")
        if idx != -1:
            serial = rest[idx+2:]
            out["21"] = serial
        else:
            # bazı akışlarda direkt 21 ile başlar
            if rest.startswith("21"):
                out["21"] = rest[2:]

    return out
