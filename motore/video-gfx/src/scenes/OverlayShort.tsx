import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {C, EASE_WIPE, FONT, MaskedLine, displayStyle, monoStyle, rev, useBrandFonts} from '../theme';
import {Timbro} from '../Timbro';

// Overlay generico per shorts 9:16, pilotato da props.events (fx_plans.json).
// Regola: card COMPATTE in alto (bottom max ~330px), MAI sulla faccia (y>350) né sui sottotitoli (y~1420).
const F = (s: number) => Math.round(s * 30);

type Ev =
  | {type: 'pill'; text: string}
  | {type: 'hook'; t0: number; t1: number; kicker?: string; text: string; red?: string}
  | {type: 'card'; t0: number; t1: number; text: string; red?: string}
  | {type: 'counter'; t0: number; t1: number; to: number; label: string; redLabel?: string}
  | {type: 'list'; t0: number; t1: number; header: string; items: {t: number; text: string}[]}
  | {type: 'claim'; t0: number; text: string; red?: string}
  // Chiamata all'azione: grande, su blocco pieno, sotto il viso e sopra i
  // sottotitoli. Serve dove `claim` non basta — testo bianco con ombra sparisce
  // su un girato all'aperto chiaro — e dove il messaggio deve pesare, non
  // accompagnare. Ha t0/t1 come gli altri, quindi può restare fino alla fine.
  | {type: 'cta'; t0: number; t1: number; kicker?: string; text: string; red?: string}
  | {type: 'stamp'; t: number};

const Box: React.FC<{
  inAt: number;
  outAt: number;
  children: React.ReactNode;
}> = ({inAt, outAt, children}) => {
  const frame = useCurrentFrame();
  if (frame < inAt || frame > outAt + 13) return null;
  const p = rev(frame, inAt, 16);
  const out = interpolate(frame, [outAt, outAt + 11], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE_WIPE,
  });
  return (
    <div
      style={{
        position: 'absolute',
        top: 84,
        left: 54,
        maxWidth: 800,
        background: C.carta,
        border: `2px solid ${C.inchiostro}`,
        padding: '20px 30px',
        transform: `translateY(${(1 - p) * -34}px)`,
        opacity: p,
        clipPath: `inset(0 0 ${out * 100}% 0)`,
      }}
    >
      {children}
    </div>
  );
};

const RedText: React.FC<{text: string; red?: string; size: number}> = ({text, red, size}) => (
  <div style={{...displayStyle(size), lineHeight: 0.95}}>
    {text}
    {red ? <span style={{color: C.rosso}}> {red}</span> : null}
  </div>
);

export const OverlayShort: React.FC<{events?: Ev[]}> = ({events = []}) => {
  useBrandFonts();
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      {events.map((ev, i) => {
        switch (ev.type) {
          case 'pill': {
            // banner contesto: rosso pieno, bianco bold, fisso 0-4.6s poi via
            const IN = F(0.15);
            const OUT = F(4.6);
            if (frame > OUT + 10) return null;
            const p = rev(frame, IN, 14);
            const out = interpolate(frame, [OUT, OUT + 9], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: EASE_WIPE,
            });
            const scale = (0.86 + 0.14 * p) * (1 - 0.12 * out);
            return (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  top: 1130,
                  left: 70,
                  right: 70,
                  display: 'flex',
                  justifyContent: 'center',
                  opacity: p * (1 - out),
                  transform: `scale(${scale})`,
                }}
              >
                <div
                  style={{
                    background: C.rosso,
                    border: '5px solid #ffffff',
                    borderRadius: 30,
                    padding: '24px 44px',
                    maxWidth: 900,
                    boxShadow: '0 10px 40px rgba(0,0,0,.35)',
                  }}
                >
                  <div style={{...displayStyle(58, C.carta), textAlign: 'center', lineHeight: 1.02}}>
                    {ev.text}
                  </div>
                </div>
              </div>
            );
          }
          case 'hook':
            return (
              <Box key={i} inAt={F(ev.t0)} outAt={F(ev.t1)}>
                {ev.kicker ? <div style={{...monoStyle(17), marginBottom: 8}}>{ev.kicker}</div> : null}
                <RedText text={ev.text} red={ev.red} size={50} />
              </Box>
            );
          case 'card':
            return (
              <Box key={i} inAt={F(ev.t0)} outAt={F(ev.t1)}>
                <RedText text={ev.text} red={ev.red} size={46} />
              </Box>
            );
          case 'counter': {
            const val = Math.round(ev.to * rev(frame, F(ev.t0 + 0.2), F(2.6)));
            return (
              <Box key={i} inAt={F(ev.t0)} outAt={F(ev.t1)}>
                <div style={{fontFamily: FONT.mono, fontSize: 66, color: C.inchiostro, fontVariantNumeric: 'tabular-nums'}}>
                  {val.toLocaleString('it-IT')}
                </div>
                <div style={{...monoStyle(18), marginTop: 6}}>
                  {ev.label}
                  {ev.redLabel ? <span style={{color: C.rosso}}> {ev.redLabel}</span> : null}
                </div>
              </Box>
            );
          }
          case 'list':
            return (
              <Box key={i} inAt={F(ev.t0)} outAt={F(ev.t1)}>
                <div style={{...monoStyle(17), borderBottom: `2px solid ${C.inchiostro}`, paddingBottom: 8, marginBottom: 2}}>
                  {ev.header}
                </div>
                {ev.items.map((it) => {
                  const p = rev(frame, F(it.t), 13);
                  return (
                    <div
                      key={it.text}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 16,
                        padding: '7px 0',
                        borderBottom: `1px solid ${C.filetto}`,
                        opacity: p,
                        transform: `translateX(${(1 - p) * -20}px)`,
                      }}
                    >
                      <div style={{width: 14, height: 14, background: C.rosso, flexShrink: 0}} />
                      <div style={{fontFamily: FONT.body, fontWeight: 500, fontSize: 25, color: C.inchiostro}}>{it.text}</div>
                    </div>
                  );
                })}
              </Box>
            );
          case 'claim':
            if (frame < F(ev.t0)) return null;
            return (
              <div key={i} style={{position: 'absolute', top: 84, left: 54, right: 260}}>
                <MaskedLine start={F(ev.t0)}>
                  <div style={{...displayStyle(46, C.carta), textShadow: '0 0 22px rgba(0,0,0,.6)', lineHeight: 0.95}}>
                    {ev.text}
                    {ev.red ? <span style={{color: C.rosso}}> {ev.red}</span> : null}
                  </div>
                </MaskedLine>
              </div>
            );
          case 'cta': {
            const IN = F(ev.t0);
            const OUT = F(ev.t1);
            if (frame < IN - 6 || frame > OUT + 10) return null;
            const p = rev(frame, IN, 12);
            const out = interpolate(frame, [OUT, OUT + 9], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: EASE_WIPE,
            });
            // respiro lento: il canone non ammette elementi fermi
            const respiro = 1 + 0.012 * Math.sin((frame - IN) / 26);
            return (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  top: 1010,
                  left: 48,
                  right: 48,
                  display: 'flex',
                  justifyContent: 'center',
                  opacity: p * (1 - out),
                  transform: `scale(${(0.88 + 0.12 * p) * respiro * (1 - 0.1 * out)})`,
                }}
              >
                <div
                  style={{
                    background: C.inchiostro,
                    border: `6px solid ${C.rosso}`,
                    borderRadius: 26,
                    padding: '22px 40px 26px',
                    maxWidth: 960,
                    boxShadow: '0 14px 50px rgba(0,0,0,.45)',
                    textAlign: 'center',
                  }}
                >
                  {ev.kicker ? (
                    <div style={{...monoStyle(22, C.carta), opacity: 0.75, marginBottom: 10}}>
                      {ev.kicker}
                    </div>
                  ) : null}
                  <div style={{...displayStyle(96, C.carta), lineHeight: 0.92}}>
                    {ev.text}
                    {ev.red ? <span style={{color: C.rosso}}> {ev.red}</span> : null}
                  </div>
                </div>
              </div>
            );
          }
          case 'stamp':
            if (frame < F(ev.t) - 30) return null;
            return (
              <div key={i} style={{position: 'absolute', right: 44, top: 110}}>
                <Timbro size={185} dropAt={F(ev.t)} />
              </div>
            );
          default:
            // Un tipo che questo montatore non conosce non deve sparire in silenzio:
            // è successo con `cols2`, che esiste solo nel montatore del video lungo.
            // Il render riusciva, la grafica non c'era, e nessuno se ne accorgeva.
            throw new Error(
              `[OverlayShort] tipo sconosciuto "${(ev as {type: string}).type}" ` +
                `ignorato. Tipi validi: pill, hook, card, counter, list, claim, cta, stamp.`,
            );
            return null;
        }
      })}
    </AbsoluteFill>
  );
};
