# Dipendenze e licenze

La licenza MIT del repository riguarda il codice di Content Machine. Non sostituisce i termini delle dipendenze o degli asset usati dall'utilizzatore. Il repository non distribuisce eseguibili, node_modules, modelli, browser, font o media di terzi.

| Componente | Licenza / uso nel pacchetto |
|---|---|
| Python | PSF; runtime installato separatamente |
| NumPy | BSD-3-Clause; SFX e calcoli |
| Pillow | HPND; tavole contatti |
| Pydantic / pydantic-core | MIT; schemi di scambio |
| OpenCV Python headless | Apache-2.0 per il pacchetto/codice recente; rilevamento volto opzionale con pesi separati |
| fontTools | MIT; preparazione font propri |
| Brotli | MIT; decompressione font |
| React / React DOM / TypeScript | MIT; composizioni e controllo tipi |
| Remotion 4.0.371 e pacchetti @remotion | **Remotion License**, non MIT. Installati separatamente dal registro npm e fissati nei lockfile. |
| FFmpeg / FFprobe | Dipende dalla build: LGPL o GPL con componenti come libx264. Eseguibili di sistema, non redistribuiti nel repo. |
| faster-whisper / CTranslate2 | MIT; trascrizione opzionale, non richiesta con SRT/JSON |
| Pesi Whisper / YuNet | Non inclusi. Consultare la licenza del modello specifico prima dell'installazione/distribuzione. |
| Font / browser / media | Non inclusi. L'utilizzatore installa font e browser del proprio sistema e fornisce media con diritti appropriati. |

Remotion consente attualmente la creazione di video gratuita per individui, organizzazioni non profit e imprese fino a tre dipendenti; soggetti/usi diversi possono richiedere una licenza commerciale. Le condizioni limitano inoltre la rivendita di derivati del framework. Consultare la [licenza ufficiale](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md) e le [FAQ ufficiali](https://www.remotion.dev/docs/license) per il caso d'uso. Nessuna licenza o sottoscrizione viene acquistata da questo progetto.

I componenti React di questo progetto usano l'API pubblica di Remotion; il framework non è copiato o rilicenziato sotto MIT. Il ramo FFmpeg e le funzioni di montaggio restano utilizzabili senza Remotion per i passaggi che non richiedono animazioni.

Per ricostruire l'inventario delle versioni effettive: `python -m pip freeze` nel venv e i lockfile Node. Gli avvisi delle dipendenze rimangono nei pacchetti installati; includerli se si distribuisce un prodotto che incorpora quei runtime. Testi verificati il 20 ottobre 2026.
