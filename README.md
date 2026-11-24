# Card contatto

Biglietto da visita digitale con contatti e CV **cifrati**.

- La pagina (`index.html`) è pubblica, ma contatti e CV sono salvati in `c/` cifrati con AES-256-GCM: senza chiave sono illeggibili.
- La chiave è solo nel link del QR, dopo il `#`. Quella parte dell'indirizzo non viene mai inviata al server: il telefono di chi scansiona decifra tutto in locale.
- Ci sono due QR con chiavi diverse:
  - **QR 1, Contatto**: apre la card con i contatti e il pulsante "Salva contatto".
  - **QR 2, Contatto + CV**: come sopra, più il CV in PDF da aprire o scaricare.
- Per disattivare un QR basta generare una chiave nuova (`--rotate`): il vecchio link smette di funzionare.

## Aggiornare i dati

```
pip install cryptography segno pillow
python3 tools/build.py /percorso/cartella-privata        # stessa chiave, stessi QR
python3 tools/build.py /percorso/cartella-privata --rotate cv   # nuova chiave per il QR del CV
```

La cartella privata (fuori dalla repo) contiene `profile.json` (vedi `tools/profile.example.json`), `cv.pdf`, la foto e `keys.json`. Poi si pubblicano i file in `c/`.
