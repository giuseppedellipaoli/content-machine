"""Prove del rettangolo di ritaglio: non deforma, e non cambia il presente.

    py prova_ritaglio.py

Due gruppi, e il secondo conta piu' del primo.

  A) il rettangolo ha SEMPRE il rapporto d'uscita, qualunque sia il sorgente;
  B) sui girati VERI il rettangolo e' identico a quello che usciva prima,
     cioe' `min(CROP_W, src_w)` per tutta l'altezza. E' la prova che si e'
     chiuso un difetto latente senza toccare i video gia' prodotti.

Il gruppo B e' scritto contro la formula VECCHIA riportata qui sotto apposta:
se un domani qualcuno cambia il rettangolo in modo che i girati di produzione
escano diversi, questa prova lo dice invece di lasciarlo scoprire dal cliente.
"""
from __future__ import annotations

import fondamenta

OUT_W, OUT_H = 1080, 1920
CROP_W_STORICO = 608  # config.CROP_W: 9:16 a piena altezza da 1920x1080

passate = 0
fallite: list[str] = []


def prova(nome: str, ottenuto, atteso) -> None:
    global passate
    if ottenuto == atteso:
        passate += 1
        print(f"  ok   {nome}")
    else:
        fallite.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso!r}\n       ottenuto {ottenuto!r}")


def rapporto_giusto(nome: str, src_w: int, src_h: int, tolleranza: float = 0.005) -> None:
    """Il rapporto del ritaglio deve stare a filo di quello d'uscita.

    La tolleranza non e' pigrizia: i lati vanno portati a un numero pari per
    il sottocampionamento del colore, e quell'arrotondamento sposta il
    rapporto di qualche decimillesimo. Su 1080 px di larghezza mezzo punto
    percentuale e' meno di sei pixel.
    """
    global passate
    larghezza, altezza = fondamenta.rettangolo_di_ritaglio(src_w, src_h, OUT_W, OUT_H)
    scarto = abs((larghezza / altezza) / (OUT_W / OUT_H) - 1)
    if scarto <= tolleranza and larghezza <= src_w and altezza <= src_h:
        passate += 1
        print(f"  ok   {nome} ({src_w}x{src_h} -> {larghezza}x{altezza}, {scarto * 100:+.2f}%)")
    else:
        fallite.append(nome)
        print(f"  NO   {nome}: {src_w}x{src_h} -> {larghezza}x{altezza}, "
              f"scarto {scarto * 100:.2f}% (dentro il sorgente: "
              f"{larghezza <= src_w and altezza <= src_h})")


print("A) il rettangolo non deforma, qualunque sia il sorgente")
rapporto_giusto("orizzontale 1080p", 1920, 1080)
rapporto_giusto("orizzontale 4K", 3840, 2160)
rapporto_giusto("verticale gia' 9:16", 1080, 1920)
rapporto_giusto("verticale WhatsApp", 478, 850)
rapporto_giusto("registrazione schermo iPhone", 1170, 2532)
rapporto_giusto("piu' stretto di 9:16", 886, 1920)
rapporto_giusto("molto piu' stretto", 400, 1000)
rapporto_giusto("quadrato", 1000, 1000)
rapporto_giusto("4:3 vecchio", 640, 480)
rapporto_giusto("un pixel di troppo in larghezza", 609, 1080)
rapporto_giusto("un pixel di meno in larghezza", 607, 1080)

print("\nB) sui girati VERI non cambia niente rispetto a prima")
for nome, src_w, src_h in (
    ("1920x1080 (il formato lungo del kit)", 1920, 1080),
    ("478x850 (i sei girati di produzione)", 478, 850),
):
    vecchio = (min(CROP_W_STORICO, src_w), src_h)
    prova(f"{nome}: rettangolo identico a prima",
          fondamenta.rettangolo_di_ritaglio(src_w, src_h, OUT_W, OUT_H), vecchio)

print("\nC) i lati sono sempre pari, e almeno 2")
for src_w, src_h in ((1920, 1080), (478, 850), (1170, 2532), (3, 5), (2, 2)):
    larghezza, altezza = fondamenta.rettangolo_di_ritaglio(src_w, src_h, OUT_W, OUT_H)
    prova(f"{src_w}x{src_h}: lati pari",
          (larghezza % 2, altezza % 2, larghezza >= 2, altezza >= 2), (0, 0, True, True))

print("\nD) le misure impossibili si rifiutano, non si indovinano")
for src_w, src_h in ((0, 1080), (1920, 0), (-10, 100)):
    try:
        fondamenta.rettangolo_di_ritaglio(src_w, src_h, OUT_W, OUT_H)
        prova(f"{src_w}x{src_h}: solleva", "nessun errore", "ValueError")
    except ValueError:
        prova(f"{src_w}x{src_h}: solleva", "ValueError", "ValueError")

print()
if fallite:
    print(f"{passate} passate, FALLITE: {', '.join(fallite)}")
    raise SystemExit(1)
print(f"{passate} passate, nessuna fallita")
