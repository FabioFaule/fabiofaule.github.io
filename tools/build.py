#!/usr/bin/env python3
"""
Cifra i dati della card e genera i QR.

Uso:
    python3 tools/build.py PRIVATE_DIR [--rotate contact|cv|all]

PRIVATE_DIR deve stare FUORI dalla repo e contiene:
    profile.json   dati del contatto (vedi tools/profile.example.json)
    cv.pdf         (opzionale) il CV
    photo.jpg      (opzionale) la foto, indicata in profile.json come "photo"
    keys.json      creato al primo avvio: id e chiavi delle due card.
                   Chi ha questo file (o i link dei QR) puo' leggere i dati.

Scrive i file cifrati in c/ (da pubblicare) e i QR in PRIVATE_DIR/qr/.
--rotate genera chiavi nuove: i vecchi QR smettono di funzionare.

Dipendenze: pip install cryptography segno pillow
"""
import argparse
import base64
import io
import json
import secrets
import string
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "c"
BASE_URL = "https://fabiofaule.github.io/"
FONT_DIR = Path("/usr/share/fonts/opentype/inter")


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def new_id(n=10) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def new_card(with_cv=False) -> dict:
    card = {"id": new_id(), "key": b64u(AESGCM.generate_key(bit_length=256))}
    if with_cv:
        card["cvFile"] = new_id()
    return card


def seal(key_b64u: str, data: bytes) -> bytes:
    key = base64.urlsafe_b64decode(key_b64u + "=" * (-len(key_b64u) % 4))
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def photo_data_uri(path: Path, size=360) -> str:
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img = ImageOps.fit(img, (size, size), Image.LANCZOS, centering=(0.5, 0.4))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def card_url(card: dict) -> str:
    return f"{BASE_URL}#{card['id']}.{card['key']}"


def make_qr_poster(url: str, title: str, subtitle: str, label: str, dest: Path):
    import segno
    from PIL import Image, ImageDraw, ImageFont

    qr = segno.make(url, error="m")
    qr.save(str(dest.with_suffix(".svg")), scale=10, border=4, dark="#111111")

    W, H = 1080, 1440
    # scala intera: tutti i moduli della stessa dimensione
    modules = qr.symbol_size(scale=1, border=0)[0]
    scale = 820 // modules
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=0)
    buf.seek(0)
    code = Image.open(buf).convert("RGB")
    qr_size = code.width

    def font(name, size):
        p = FONT_DIR / name
        return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default(size)

    ink, muted, accent = (21, 23, 28), (94, 101, 113), (31, 79, 209)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def center(text, y, f, fill):
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=fill)

    center(title, 110, font("Inter-Bold.otf", 64), ink)
    if subtitle:
        center(subtitle, 196, font("Inter-Medium.otf", 36), muted)

    qy = 330 + (820 - qr_size) // 2
    img.paste(code, ((W - qr_size) // 2, qy))

    f_label = font("Inter-SemiBold.otf", 44)
    tw = d.textlength(label, font=f_label)
    pw, ph = tw + 96, 88
    px, py = (W - pw) / 2, 330 + 820 + 56
    d.rounded_rectangle((px, py, px + pw, py + ph), radius=ph / 2, fill=accent)
    d.text((W / 2, py + ph / 2), label, font=f_label, fill="white", anchor="mm")

    center("Inquadra con la fotocamera", py + ph + 36, font("Inter-Regular.otf", 32), muted)
    img.save(dest.with_suffix(".png"), optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("private_dir", type=Path)
    ap.add_argument("--rotate", choices=["contact", "cv", "all"])
    args = ap.parse_args()

    priv = args.private_dir.resolve()
    if REPO in priv.parents or priv == REPO:
        sys.exit("PRIVATE_DIR non deve stare dentro la repo.")

    profile = json.loads((priv / "profile.json").read_text(encoding="utf-8"))
    if not profile.get("name"):
        profile["name"] = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    if profile.get("photo"):
        profile["photo"] = photo_data_uri(priv / profile["photo"])

    keys_path = priv / "keys.json"
    keys = json.loads(keys_path.read_text()) if keys_path.exists() else {}
    if "contact" not in keys or args.rotate in ("contact", "all"):
        keys["contact"] = new_card()
    if "cv" not in keys or args.rotate in ("cv", "all"):
        keys["cv"] = new_card(with_cv=True)
    keys_path.write_text(json.dumps(keys, indent=2))

    OUT.mkdir(exist_ok=True)
    written = set()

    def put(name, blob):
        (OUT / f"{name}.bin").write_bytes(blob)
        written.add(f"{name}.bin")

    # Card 1: solo contatto
    c1 = keys["contact"]
    put(c1["id"], seal(c1["key"], json.dumps(profile, ensure_ascii=False).encode()))

    # Card 2: contatto + CV (CV cifrato con la stessa chiave della card 2)
    c2 = keys["cv"]
    cv_pdf = priv / "cv.pdf"
    profile_cv = dict(profile)
    if cv_pdf.exists():
        put(c2["cvFile"], seal(c2["key"], cv_pdf.read_bytes()))
        cv_name = profile.get("cvName") or f"CV-{profile['name'].replace(' ', '-')}.pdf"
        profile_cv["cv"] = {"file": f"c/{c2['cvFile']}.bin", "name": cv_name}
    else:
        print("Attenzione: cv.pdf non trovato, la card 2 non avra' il CV.")
    put(c2["id"], seal(c2["key"], json.dumps(profile_cv, ensure_ascii=False).encode()))

    # Rimuove i file cifrati di chiavi vecchie
    for f in OUT.glob("*.bin"):
        if f.name not in written:
            f.unlink()

    # QR
    qr_dir = priv / "qr"
    qr_dir.mkdir(exist_ok=True)
    sub = " · ".join(x for x in (profile.get("role"), profile.get("company")) if x)
    make_qr_poster(card_url(c1), profile["name"], sub, "Contatto", qr_dir / "qr-1-contatto")
    make_qr_poster(card_url(c2), profile["name"], sub, "Contatto + CV", qr_dir / "qr-2-contatto-cv")

    print("Card 1 (contatto):     ", card_url(c1))
    print("Card 2 (contatto + CV):", card_url(c2))
    print("QR salvati in", qr_dir)


if __name__ == "__main__":
    main()
