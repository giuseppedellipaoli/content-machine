// GENERATO da ../../brand-kit.json — non modificare a mano.
// Rigenera con:  py sincronizza_brand.py

// Niente `as const` qui: stringerebbe i tipi a letterali, e le firme che
// hanno un colore come valore di default smetterebbero di accettarne altri.
export const COLORI: Record<string, string> = {
  "carta": "#ffffff",
  "inchiostro": "#101010",
  "inchiostro2": "#4a4a4a",
  "rosso": "#e2231a",
  "blu": "#1d4ed8",
  "filetto": "#d9d9d9",
  "lastra": "#14181d",
};

export const FAMIGLIE: Record<string, string> = {
  display: "Arial",
  testo: "Arial",
  dati: "Courier New",
};

// bezier delle due sole curve ammesse dal canone
export const BEZIER_RIVISTA = [0.16, 1, 0.3, 1] as const;
export const BEZIER_WIPE = [0.77, 0, 0.175, 1] as const;
