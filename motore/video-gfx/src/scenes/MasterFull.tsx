import React from 'react';
import {AbsoluteFill, OffthreadVideo, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {EASE_RIVISTA, useBrandFonts} from '../theme';
import REGIA_JSON from '../data/regia.json';
const REGIA: any = REGIA_JSON;
import {
  Arrow2, Avatar, Badge, BigOne, Card, Chat, Claim2, Cols2, Crash0, CrashDown,
  Cta, Flow, Grid, Keyword, Lista3, MiniBars, Network, Pills, Pipeline, QCard, Race, Six, Stamp,
} from './RegiaComponents';

// MASTER FULL v2 — regia word-level: ogni evento e ogni elemento interno scatta
// sul timestamp della parola detta. Componenti generici pilotati dal piano JSON.
// Video muto qui: la voce originale + sfx si muxano dopo in ffmpeg.

const OV_MAP: Record<string, React.FC<{ev: any}>> = {
  card: Card, qcard: QCard, badge: Badge, pills: Pills, flow: Flow, race: Race,
  keyword: Keyword, minibars: MiniBars, chat: Chat, claim2: Claim2, bigone: BigOne,
  arrow2: Arrow2, avatar: Avatar, cols2: Cols2, network: Network, pipeline: Pipeline,
  six: Six, crash0: Crash0, crashdown: CrashDown, grid: Grid, cta: Cta, stamp: Stamp,
  lista3: Lista3,
};

const BREATHE_PERIOD = 64; // s — ciclo respiro zoom dentro ogni take
const BREATHE_AMP = 0.06;

const zoomAt = (t: number): number => {
  const take = REGIA.takes.find((tk: any) => t >= tk.start && t < tk.end) ?? REGIA.takes[REGIA.takes.length - 1];
  const local = t - take.start;
  let base = 1 + BREATHE_AMP * 0.5 * (1 - Math.cos((2 * Math.PI * local) / BREATHE_PERIOD));
  for (const p of REGIA.punches) {
    if (t >= p.t - 0.55 && t <= p.t + 2.1) {
      const env = interpolate(t, [p.t - 0.55, p.t, p.t + 1.3, p.t + 2.1], [0, 1, 1, 0], {
        extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE_RIVISTA,
      });
      base = base + (p.scale - base) * env;
    }
  }
  return base;
};

export const MasterFull: React.FC = () => {
  useBrandFonts();
  const frame = useCurrentFrame();
  const t = frame / REGIA.fps;
  const scale = zoomAt(t);

  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{transform: `scale(${scale})`, transformOrigin: REGIA.faceOrigin}}>
        <OffthreadVideo src={staticFile(REGIA.source ?? 'base-master30.mp4')} muted style={{width: '100%', height: '100%'}} />
      </AbsoluteFill>

      {REGIA.events.map((ev: any) => {
        const OV = OV_MAP[ev.type];
        if (!OV) throw new Error(`Unsupported event type: ${ev.type}`);
        return <OV key={ev.id} ev={ev} />;
      })}
    </AbsoluteFill>
  );
};
