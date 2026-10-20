import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {C, FONT, EASE_WIPE} from './theme';

// Il Timbro Storto — cerchio interrotto in alto a dx, testo configurabile dentro, −7° fissi.
// dropAt: frame in cui il timbro cala. Cade secco (ease-in), settle senza rimbalzo elastico.
export const Timbro: React.FC<{
  size?: number;
  text?: string;
  dropAt: number;
  style?: React.CSSProperties;
}> = ({size = 260, dropAt, style, text = 'OK'}) => {
  const frame = useCurrentFrame();

  // fall: scale 2.6 → 1 in 7 frames, accelerating (stamp coming down)
  const fall = interpolate(frame, [dropAt, dropAt + 7], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE_WIPE,
  });
  // settle: tiny press 1 → 0.97 → 1 right after impact (ink pressed), no elastic bounce
  const settle = interpolate(frame, [dropAt + 7, dropAt + 9, dropAt + 12], [1, 0.97, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const scale = frame < dropAt ? 2.6 : (2.6 - 1.6 * fall) * (fall >= 1 ? settle : 1);
  const opacity = frame < dropAt ? 0 : Math.min(1, 0.35 + fall * 0.65);

  const r = size / 2 - 10;
  const circumference = 2 * Math.PI * r;
  // apertura ≈ 1/8 della circonferenza, posizionata in alto a destra
  const visible = circumference * (7 / 8);

  return (
    <div
      style={{
        width: size,
        height: size,
        transform: `rotate(-7deg) scale(${scale})`,
        opacity,
        position: 'relative',
        ...style,
      }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          {/* inchiostro leggermente irregolare, mai vettoriale perfetto */}
          <filter id="inchiostro" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" />
          </filter>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={C.rosso}
          strokeWidth={9}
          strokeDasharray={`${visible} ${circumference - visible}`}
          // gap centered top-right: rotate dash start so the opening sits at −45°
          transform={`rotate(90 ${size / 2} ${size / 2})`}
          filter="url(#inchiostro)"
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: FONT.display,
          fontWeight: 800,
          fontSize: size * 0.34,
          letterSpacing: '-0.01em',
          color: C.rosso,
          filter: 'url(#inchiostro)' as never,
        }}
      >
        {text}
      </div>
    </div>
  );
};
