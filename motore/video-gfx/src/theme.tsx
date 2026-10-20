import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {BEZIER_RIVISTA, BEZIER_WIPE, COLORI, FAMIGLIE} from './brand';

export const C = COLORI;
export const FONT = {
  display: `${FAMIGLIE.display}, sans-serif`,
  body: `${FAMIGLIE.testo}, sans-serif`,
  mono: `${FAMIGLIE.dati}, monospace`,
};
export const EASE_RIVISTA = Easing.bezier(...BEZIER_RIVISTA);
export const EASE_WIPE = Easing.bezier(...BEZIER_WIPE);
export const rev = (frame: number, start: number, dur: number, ease = EASE_RIVISTA) =>
  interpolate(frame, [start, start + dur], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});
// Compatibility hook: system fonts only; no font files or remote loading.
export const useBrandFonts = () => {};

// ---- Shared apparatus ----

// Masked-line reveal: the only entrance (yPercent 110 → 0)
export const MaskedLine: React.FC<{
  start: number;
  dur?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({start, dur = 27, children, style}) => {
  const frame = useCurrentFrame();
  const p = rev(frame, start, dur);
  return (
    <div style={{overflow: 'hidden', paddingTop: '0.14em', marginTop: '-0.14em', ...style}}>
      <div style={{transform: `translateY(${(1 - p) * 112}%)`}}>{children}</div>
    </div>
  );
};

export const Testatina: React.FC<{right?: string; dark?: boolean; start?: number}> = ({
  right = '',
  dark = false,
  start = 0,
}) => {
  const frame = useCurrentFrame();
  const p = rev(frame, start, 24);
  const ink = dark ? C.carta : C.inchiostro;
  return (
    <div
      style={{
        position: 'absolute',
        top: 54,
        left: 90,
        right: 90,
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: FONT.mono,
        fontSize: 22,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: ink,
        borderBottom: `1px solid ${dark ? 'rgba(255,255,255,.65)' : C.inchiostro}`,
        paddingBottom: 16,
        opacity: p,
      }}
    >
      <span />
      <span>{right}</span>
    </div>
  );
};

export const Folio: React.FC<{n: string; dark?: boolean}> = ({n, dark = false}) => (
  <div
    style={{
      position: 'absolute',
      bottom: 48,
      right: 90,
      fontFamily: FONT.mono,
      fontSize: 22,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: dark ? 'rgba(255,255,255,.65)' : C.inchiostro2,
    }}
  >
    p. {n}
  </div>
);

// Signature section opener: 3px rule + 1px rule, 2px apart, drawing left→right
export const FilettoDoppio: React.FC<{start: number; width?: number | string}> = ({
  start,
  width = '100%',
}) => {
  const frame = useCurrentFrame();
  const p = rev(frame, start, 30);
  return (
    <div style={{width}}>
      <div style={{height: 3, background: C.inchiostro, width: `${p * 100}%`}} />
      <div style={{height: 2}} />
      <div style={{height: 1, background: C.inchiostro, width: `${p * 100}%`}} />
    </div>
  );
};

export const Page: React.FC<{children: React.ReactNode; bg?: string}> = ({
  children,
  bg = C.carta,
}) => {
  useBrandFonts();
  return <AbsoluteFill style={{backgroundColor: bg}}>{children}</AbsoluteFill>;
};

// Mono caption (apparatus voice)
export const monoStyle = (size = 24, color = C.inchiostro2): React.CSSProperties => ({
  fontFamily: FONT.mono,
  fontSize: size,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color,
});

// Display voice (compressed grotesk)
export const displayStyle = (size: number, color = C.inchiostro): React.CSSProperties => ({
  fontFamily: FONT.display,
  fontWeight: 800,
  fontSize: size,
  lineHeight: 0.9,
  letterSpacing: '-0.02em',
  textTransform: 'uppercase',
  color,
});
