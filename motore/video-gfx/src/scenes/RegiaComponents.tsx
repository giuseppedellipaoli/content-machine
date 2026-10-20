import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, EASE_WIPE, FONT, displayStyle, monoStyle, rev} from '../theme';
import {Timbro} from '../Timbro';

// REGIA COMPONENTS — libreria overlay per MasterFull (canone: entrata spring →
// vita con respiro/deriva → uscita wipe; mai un frame fermo; viso mai coperto).
// Ogni componente riceve l'evento (tempi in secondi) e si posiziona da solo.

export const F = (s: number) => Math.round(s * 30);
export const itNum = (v: number) => v.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');

// ---- testo ricco: *segmento* → rosso; \n → a capo ----
export const Rich: React.FC<{text: string}> = ({text}) => (
  <>
    {text.split('\n').map((line, li) => (
      <React.Fragment key={li}>
        {li > 0 && <br />}
        {line.split('*').map((seg, i) => (i % 2 === 1 ? <span key={i} style={{color: C.rosso}}>{seg}</span> : <React.Fragment key={i}>{seg}</React.Fragment>))}
      </React.Fragment>
    ))}
  </>
);

const CHARS_PER_FRAME = 0.9;
const Type: React.FC<{text: string; start: number}> = ({text, start}) => {
  const frame = useCurrentFrame();
  if (frame < start) return null;
  const n = Math.min(text.length, Math.floor((frame - start) * CHARS_PER_FRAME));
  return <Rich text={text.slice(0, n)} />;
};

// ---- vita dell'overlay: entrata + respiro/deriva continui + uscita ----
type Life = {p: number; out: number; alive: boolean; wrap: React.CSSProperties};
export const useLife = (t0: number, t1: number, enter: string, pos: string): Life => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f0 = F(t0);
  const f1 = F(t1);
  const alive = frame >= f0 && frame <= f1;
  const pSpring = frame >= f0 ? spring({frame: frame - f0, fps, config: {damping: 12, stiffness: 130, mass: 0.7}}) : 0;
  const pSoft = rev(frame, f0, 13);
  const p = enter === 'pop' ? pSpring : pSoft;
  const out = interpolate(frame, [f1 - 9, f1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE_WIPE});
  // respiro + deriva: MAI fermo
  const life = interpolate(frame, [f0, f1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const breathe = 1 + 0.032 * life;
  const drift = 8 - 16 * life;
  const enterT =
    enter === 'slide' ? `translateX(${(1 - p) * -46}px)` :
    enter === 'drop' ? `translateY(${(1 - p) * -60}px)` :
    enter === 'pop' ? `scale(${0.72 + 0.28 * p})` :
    enter === 'blur' ? `scale(${0.92 + 0.08 * p})` : '';
  const origin = pos === 'ADX' ? 'right top' : 'left top';
  return {
    p,
    out,
    alive,
    wrap: {
      opacity: (enter === 'pop' ? Math.min(1, p * 1.4) : p) * (1 - out),
      transform: `${enterT} scale(${breathe}) translateY(${drift}px)`,
      transformOrigin: origin,
      filter: enter === 'blur' ? `blur(${(1 - p) * 14}px)` : undefined,
    },
  };
};

export const posStyle = (pos: string): React.CSSProperties =>
  pos === 'SX' ? {position: 'absolute', left: 64, top: 100, width: 660} :
  pos === 'ADX' ? {position: 'absolute', right: 60, top: 80, width: 640, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', textAlign: 'right'} :
  pos === 'BSX' ? {position: 'absolute', left: 64, bottom: 84, width: 980} :
  {position: 'absolute', left: 0, right: 0, top: 60, textAlign: 'center'};

const SHADOW = '0 12px 34px rgba(0,0,0,.28)';
export const shell: React.CSSProperties = {
  background: C.carta,
  border: `2px solid ${C.inchiostro}`,
  padding: '22px 30px',
  boxShadow: SHADOW,
};

const filetto = (
  <div style={{marginBottom: 14}}>
    <div style={{height: 3, background: C.inchiostro}} />
    <div style={{height: 2}} />
    <div style={{height: 1, background: C.inchiostro}} />
  </div>
);

// ============================== CARD ==============================
// title, sub?, sub2?, rows?, fork?, loop?, tail?
export const Card: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, ev.enter ?? 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, display: 'inline-block', maxWidth: 660}}>
        <div style={displayStyle(46)}><Rich text={ev.title} /></div>
        {ev.sub && <div style={{...monoStyle(19), marginTop: 8, opacity: rev(frame, ev.k?.sub ? F(ev.k.sub) : F(ev.t0) + 8, 12)}}>{ev.sub}</div>}
        {ev.sub2 && (
          <div style={{...displayStyle(ev.sub2.big ? 54 : 40, C.inchiostro), marginTop: 10, opacity: rev(frame, F(ev.t0) + 12, 12)}}>
            <Rich text={ev.sub2.text} />
          </div>
        )}
        {ev.rows && (
          <div style={{marginTop: 8}}>
            {ev.rows.map((r: any, i: number) => {
              if (frame < F(r.t)) return null;
              return (
                <div key={i} style={{display: 'flex', gap: 12, padding: '8px 0', borderTop: i ? `1px solid ${C.filetto}` : 'none'}}>
                  <div style={{width: 13, height: 13, background: C.rosso, marginTop: 9, flexShrink: 0, transform: `scale(${rev(frame, F(r.t), 10)})`}} />
                  <div style={{fontFamily: FONT.body, fontWeight: 500, fontSize: 27, color: C.inchiostro, minHeight: 36}}>
                    <Type text={r.text} start={F(r.t)} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {ev.fork && frame >= F(ev.fork.t) && (() => {
          const p1 = rev(frame, F(ev.fork.t), 14);
          const p2 = rev(frame, ev.fork.t2 ? F(ev.fork.t2) : F(ev.fork.t) + 16, 14);
          return (
            <div style={{marginTop: 14}}>
              <div style={{display: 'flex', gap: 10, alignItems: 'center', opacity: p1, transform: `translateX(${(1 - p1) * -24}px)`}}>
                <div style={{width: 34, height: 3, background: C.blu}} />
                <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 26, color: C.blu}}>{ev.fork.yes}</div>
              </div>
              <div style={{display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, opacity: p2, transform: `translateX(${(1 - p2) * -24}px)`}}>
                <div style={{width: 34, height: 3, background: C.rosso}} />
                <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 26, color: C.rosso}}>{ev.fork.no}</div>
              </div>
            </div>
          );
        })()}
        {ev.loop && frame >= F(ev.loop.t) && (() => {
          const spin = ((frame - F(ev.loop.t)) / 30) * 40; // 40°/s continuo
          return (
            <div style={{display: 'flex', alignItems: 'center', gap: 18, marginTop: 14, opacity: rev(frame, F(ev.loop.t), 12)}}>
              <svg width="64" height="64" viewBox="0 0 64 64" style={{transform: `rotate(${spin}deg)`}}>
                <path d="M32 6 A26 26 0 1 1 10 18" fill="none" stroke={C.blu} strokeWidth="6" />
                <path d="M10 6 L10 20 L24 20" fill="none" stroke={C.blu} strokeWidth="6" />
              </svg>
              <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 26, color: C.inchiostro}}>
                {ev.loop.steps.map((s: string, i: number) => (
                  <span key={i}>
                    {i > 0 && <span style={{color: C.inchiostro2}}> → </span>}
                    <span style={{color: i === 1 ? C.rosso : C.inchiostro}}>{s}</span>
                  </span>
                ))}
              </div>
            </div>
          );
        })()}
        {ev.tail && frame >= F(ev.tail.t) && (
          <div style={{...displayStyle(32, ev.tail.red ? C.rosso : C.inchiostro), marginTop: 14, opacity: rev(frame, F(ev.tail.t), 12)}}>
            <Rich text={ev.tail.text} />
          </div>
        )}
      </div>
    </div>
  );
};

// ============================== QCARD ==============================
export const QCard: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'drop', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, width: 620}}>
        {filetto}
        <div style={{...displayStyle(ev.redTitle ? 52 : 44, ev.redTitle ? C.rosso : C.inchiostro), position: 'relative', display: 'inline-block'}}>
          <Rich text={ev.title} />
          {ev.cross && frame >= F(ev.cross) && (
            <svg width="100%" height="100%" viewBox="0 0 100 40" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
              <line x1="0" y1="34" x2={rev(frame, F(ev.cross), 12) * 100} y2="6" stroke={C.rosso} strokeWidth="5" />
            </svg>
          )}
        </div>
        {ev.bullets && (
          <div style={{marginTop: 12}}>
            {ev.bullets.map((b: any, i: number) => {
              const bp = rev(frame, F(b.t), 12);
              if (frame < F(b.t)) return null;
              return (
                <div key={i} style={{display: 'flex', gap: 13, padding: '9px 0', borderTop: i ? `1px solid ${C.filetto}` : 'none'}}>
                  {ev.checks ? (
                    <svg width="26" height="26" viewBox="0 0 26 26" style={{marginTop: 5, flexShrink: 0}}>
                      <path d="M4 14 L11 21 L23 5" fill="none" stroke={C.blu} strokeWidth="4.5"
                        strokeDasharray={34} strokeDashoffset={34 * (1 - bp)} />
                    </svg>
                  ) : (
                    <div style={{width: 14, height: 14, background: C.rosso, marginTop: 9, flexShrink: 0, transform: `scale(${bp})`}} />
                  )}
                  <div style={{fontFamily: FONT.body, fontWeight: 500, fontSize: 27, color: C.inchiostro, minHeight: 36}}>
                    <Type text={b.text} start={F(b.t)} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {ev.tail && frame >= F(ev.tail.t) && (
          <div style={{...displayStyle(30, ev.tail.red ? C.rosso : C.inchiostro), marginTop: 12, opacity: rev(frame, F(ev.tail.t), 12)}}>
            <Rich text={ev.tail.text} />
          </div>
        )}
      </div>
    </div>
  );
};

// ============================== BADGE ==============================
export const Badge: React.FC<{ev: any}> = ({ev}) => {
  const l = useLife(ev.t0, ev.t1, ev.enter ?? 'pop', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, display: 'inline-block', padding: ev.big ? '20px 34px' : '14px 26px'}}>
        <div style={displayStyle(ev.big ? 54 : 34)}><Rich text={ev.title} /></div>
      </div>
    </div>
  );
};

// ============================== PILLS ==============================
export const Pills: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      {ev.label && (
        <div style={{...monoStyle(20, C.carta), textShadow: '0 2px 12px rgba(0,0,0,.75)', marginBottom: 12}}>{ev.label}</div>
      )}
      <div style={{position: 'relative', display: 'inline-block'}}>
        {ev.pills.map((p: any, i: number) => {
          const sp = frame >= F(p.t) ? spring({frame: frame - F(p.t), fps, config: {damping: 12, stiffness: 150, mass: 0.7}}) : 0;
          return (
            <div key={i} style={{
              ...shell,
              padding: '12px 24px',
              marginTop: i ? 10 : 0,
              opacity: Math.min(1, sp * 1.5),
              transform: `translateY(${(1 - sp) * -34}px) scale(${0.85 + 0.15 * sp})`,
              transformOrigin: 'left center',
              display: 'block',
              width: 'fit-content',
            }}>
              <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 30, color: C.inchiostro}}>{p.text}</div>
            </div>
          );
        })}
        {ev.stamp && frame >= F(ev.stamp.t) && (() => {
          const sp = spring({frame: frame - F(ev.stamp.t), fps, config: {damping: 11, stiffness: 170, mass: 0.6}});
          return (
            <div style={{
              position: 'absolute', left: '6%', top: '32%',
              border: `5px solid ${C.rosso}`, color: C.rosso, padding: '8px 20px',
              transform: `rotate(-9deg) scale(${2.2 - 1.2 * Math.min(1, sp)})`,
              opacity: Math.min(1, sp * 1.6),
              background: 'rgba(255,255,255,.6)',
            }}>
              <div style={displayStyle(40, C.rosso)}>{ev.stamp.text}</div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

// ============================== FLOW ==============================
export const Flow: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
        {ev.steps.map((s: any, i: number) => {
          const sp = frame >= F(s.t) ? spring({frame: frame - F(s.t), fps, config: {damping: 12, stiffness: 150, mass: 0.7}}) : 0;
          return (
            <React.Fragment key={i}>
              {i > 0 && (
                <svg width="34" height="20" viewBox="0 0 34 20" style={{opacity: sp}}>
                  <path d="M2 10 H26 M20 3 L28 10 L20 17" fill="none" stroke={C.carta} strokeWidth="3.5" style={{filter: 'drop-shadow(0 2px 6px rgba(0,0,0,.6))'}} />
                </svg>
              )}
              <div style={{
                ...shell,
                padding: '10px 20px',
                borderColor: s.x ? C.rosso : C.inchiostro,
                opacity: Math.min(1, sp * 1.4),
                transform: `translateY(${(1 - sp) * 26}px)`,
                position: 'relative',
                flexShrink: 0,
              }}>
                <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 25, color: s.x ? C.rosso : C.inchiostro}}>{s.text}</div>
                {s.x && frame >= F(s.t) + 14 && (
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{position: 'absolute', inset: -6, width: 'calc(100% + 12px)', height: 'calc(100% + 12px)'}}>
                    <line x1="8" y1="8" x2={8 + rev(frame, F(s.t) + 14, 10) * 84} y2={8 + rev(frame, F(s.t) + 14, 10) * 84} stroke={C.rosso} strokeWidth="7" />
                    <line x1="92" y1="8" x2={92 - rev(frame, F(s.t) + 20, 10) * 84} y2={8 + rev(frame, F(s.t) + 20, 10) * 84} stroke={C.rosso} strokeWidth="7" />
                  </svg>
                )}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

// ============================== RACE ==============================
export const Race: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const fastStart = ev.k?.fast ? F(ev.k.fast) : f0 + 8;
  const slowStart = ev.k?.slow ? F(ev.k.slow) : f0 + 8;
  const fastP = rev(frame, fastStart, 26);
  const slowP = interpolate(frame, [slowStart, F(ev.t1)], [0, 0.3], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const Row = ({label, value, p, color, top}: {label: string; value: string; p: number; color: string; top: number}) => (
    <div style={{marginTop: top}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline'}}>
        <span style={monoStyle(20, C.carta)}>{label}</span>
        <span style={{...displayStyle(44, C.carta), textShadow: '0 2px 14px rgba(0,0,0,.7)'}}>{value}</span>
      </div>
      <div style={{height: 22, border: `2px solid ${C.carta}`, marginTop: 6, boxShadow: SHADOW, background: 'rgba(0,0,0,.25)'}}>
        <div style={{height: '100%', width: `${p * 100}%`, background: color}} />
      </div>
    </div>
  );
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap, width: 620}}>
      <Row label={ev.fast.label} value={ev.fast.value} p={fastP} color={C.blu} top={0} />
      <Row label={ev.slow.label} value={ev.slow.value} p={slowP} color={C.rosso} top={18} />
      {ev.tail && frame >= F(ev.tail.t) && (
        <div style={{...displayStyle(38, C.carta), marginTop: 18, textShadow: '0 3px 16px rgba(0,0,0,.8)', opacity: rev(frame, F(ev.tail.t), 12)}}>
          <Rich text={ev.tail.text} />
        </div>
      )}
    </div>
  );
};

// ============================== KEYWORD ==============================
// con k.red: la parte *rossa* si accende SOLO sul timestamp della parola detta
export const Keyword: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'blur', ev.pos === 'TOP' ? 'TOP' : ev.pos);
  if (!l.alive) return null;
  const shadow = '0 4px 26px rgba(0,0,0,.85), 0 0 6px rgba(0,0,0,.6)';
  const body = ev.k?.red
    ? (() => {
        const parts = ev.title.split('*');
        const rp = rev(frame, F(ev.k.red), 9);
        return (
          <>
            <Rich text={parts[0]} />
            <span style={{color: C.rosso, opacity: rp, filter: `blur(${(1 - rp) * 10}px)`}}>{parts[1]}</span>
          </>
        );
      })()
    : <Rich text={ev.title} />;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <span style={{...displayStyle(ev.size ?? 84, C.carta), textShadow: shadow}}>
        {body}
      </span>
    </div>
  );
};

// ============================== MINIBARS (meccanica V4 promossa) ==============================
export const MiniBars: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const cStart = ev.k?.counter ? F(ev.k.counter) : f0 + 10;
  const counter = Math.round(ev.counter.target * rev(frame, cStart, 70));
  const barsH = Math.max(...ev.bars.map((b: any) => b.h2)) + 12;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...displayStyle(100, C.rosso), textShadow: '0 3px 20px rgba(0,0,0,.45)'}}>
        {ev.counter.prefix ?? ''}{itNum(counter)}{ev.counter.suffix ?? ''}
      </div>
      <div style={{position: 'relative', height: barsH, marginTop: 16}}>
        {ev.bars.map((b: any, i: number) => {
          const enter = frame >= F(b.at) ? spring({frame: frame - F(b.at), fps, config: {damping: 12, stiffness: 130, mass: 0.7}}) : 0;
          const settleAt = i + 2 < ev.bars.length ? F(ev.bars[i + 2].at) : F(b.at) + 56;
          const settle = frame >= settleAt ? spring({frame: frame - settleAt, fps, config: {damping: 14, stiffness: 90, mass: 0.9}}) : 0;
          const h = Math.max(0, b.h1 * enter + (b.h2 - b.h1) * settle);
          return <div key={i} style={{position: 'absolute', left: i * 124, bottom: 0, width: 94, height: h, background: C.blu, boxShadow: SHADOW}} />;
        })}
      </div>
      <div style={{...monoStyle(20, C.carta), marginTop: 12, textShadow: '0 2px 12px rgba(0,0,0,.8)', opacity: rev(frame, ev.k?.label ? F(ev.k.label) : f0 + 26, 18)}}>
        <Rich text={ev.label} />
      </div>
    </div>
  );
};

// ============================== CHAT ==============================
export const Chat: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap, width: 640}}>
      {ev.bubbles.map((b: any, i: number) => {
        const p = rev(frame, F(b.t), 13);
        if (frame < F(b.t)) return null;
        const right = b.side === 'right';
        return (
          <div key={i} style={{display: 'flex', justifyContent: right ? 'flex-end' : 'flex-start', marginTop: i ? 12 : 0}}>
            <div style={{
              maxWidth: 560,
              background: right ? C.rosso : C.carta,
              color: right ? C.carta : C.inchiostro,
              border: right ? 'none' : `2px solid ${C.inchiostro}`,
              borderRadius: 16,
              padding: '14px 22px',
              boxShadow: SHADOW,
              opacity: p,
              transform: `translateY(${(1 - p) * 22}px) scale(${0.92 + 0.08 * p})`,
              transformOrigin: right ? 'right bottom' : 'left bottom',
            }}>
              <div style={{...monoStyle(15, right ? 'rgba(255,255,255,.8)' : C.inchiostro2), marginBottom: 4}}>{b.who}</div>
              <div style={{fontFamily: FONT.body, fontWeight: 500, fontSize: 26, lineHeight: 1.22}}>{b.text}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ============================== CLAIM2 ==============================
export const Claim2: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const isTop = ev.pos === 'TOP';
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      {ev.lines.map((ln: any, i: number) => {
        const sp = frame >= F(ln.t) ? spring({frame: frame - F(ln.t), fps, config: {damping: 12, stiffness: 140, mass: 0.7}}) : 0;
        return (
          <div key={i} style={{
            ...displayStyle(ev.size ?? 72, ln.red ? C.rosso : C.carta),
            textShadow: ln.red ? '0 4px 24px rgba(0,0,0,.55)' : '0 4px 24px rgba(0,0,0,.8)',
            transform: isTop ? `translateY(${(1 - sp) * -36}px)` : `translateX(${(1 - sp) * (ev.pos === 'ADX' ? 70 : -70)}px)`,
            opacity: sp,
            marginTop: i ? 8 : 0,
          }}>
            {ln.text}
          </div>
        );
      })}
    </div>
  );
};

// ============================== BIGONE ==============================
export const BigOne: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'pop', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const pulse = 1 + 0.045 * Math.sin(((frame - f0) / 30) * Math.PI * 1.4);
  const sp = frame >= f0 ? spring({frame: frame - f0, fps, config: {damping: 11, stiffness: 120, mass: 0.8}}) : 0;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{
        ...displayStyle(300, C.rosso),
        textShadow: '0 6px 40px rgba(0,0,0,.5)',
        transform: `scale(${(0.6 + 0.4 * sp) * pulse})`,
        transformOrigin: 'left top',
        lineHeight: 1,
      }}>
        {ev.value ?? 1}
      </div>
      <div style={{...monoStyle(24, C.carta), marginTop: 18, textShadow: '0 2px 14px rgba(0,0,0,.85)', opacity: rev(frame, ev.k?.sola ? F(ev.k.sola) : f0 + 16, 14)}}>
        {ev.sub}
      </div>
    </div>
  );
};

// ============================== ARROW2 ==============================
export const Arrow2: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'blur', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const draw = rev(frame, f0 + 10, 20);
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
        <span style={{...displayStyle(56, C.carta), textShadow: '0 3px 18px rgba(0,0,0,.8)'}}>{ev.from}</span>
        <svg width="120" height="40" viewBox="0 0 120 40">
          <path d="M4 20 H100 M88 8 L104 20 L88 32" fill="none" stroke={C.rosso} strokeWidth="6"
            strokeDasharray={160} strokeDashoffset={160 * (1 - draw)} style={{filter: 'drop-shadow(0 2px 8px rgba(0,0,0,.5))'}} />
        </svg>
        <span style={{...displayStyle(56, C.rosso), textShadow: '0 3px 18px rgba(0,0,0,.5)', opacity: draw}}>{ev.to}</span>
      </div>
    </div>
  );
};

// ============================== AVATAR ==============================
export const Avatar: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'drop', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const orbit = ((frame - f0) / 30) * 120; // gradi/s
  const xAt = ev.k?.x ? F(ev.k.x) : f0 + Math.round((ev.t1 - ev.t0) * 30 * 0.62);
  const xp = rev(frame, xAt, 12);
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, display: 'inline-flex', gap: 24, alignItems: 'center', position: 'relative'}}>
        <div style={{position: 'relative', width: 120, height: 130}}>
          <svg width="120" height="130" viewBox="0 0 120 130">
            <circle cx="60" cy="42" r="26" fill="none" stroke={C.inchiostro} strokeWidth="5" />
            <path d="M18 126 C18 92 42 80 60 80 C78 80 102 92 102 126" fill="none" stroke={C.inchiostro} strokeWidth="5" />
          </svg>
          <div style={{
            position: 'absolute', left: 60 - 8, top: 42 - 10,
            transform: `rotate(${orbit}deg) translateX(52px) rotate(${-orbit}deg)`,
            ...displayStyle(30, C.blu),
          }}>?</div>
          {frame >= xAt && (
            <svg width="120" height="130" viewBox="0 0 120 130" style={{position: 'absolute', inset: 0}}>
              <line x1="16" y1="16" x2={16 + xp * 88} y2={16 + xp * 98} stroke={C.rosso} strokeWidth="9" />
              <line x1="104" y1="16" x2={104 - rev(frame, xAt + 7, 10) * 88} y2={16 + rev(frame, xAt + 7, 10) * 98} stroke={C.rosso} strokeWidth="9" />
            </svg>
          )}
        </div>
        <div>
          <div style={displayStyle(40)}>{ev.title}</div>
          <div style={{...monoStyle(19), marginTop: 6}}>{ev.sub}</div>
        </div>
      </div>
    </div>
  );
};

// ============================== COLS2 ==============================
export const Cols2: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const p1 = rev(frame, f0, 13);
  const p2 = rev(frame, ev.k?.dx ? F(ev.k.dx) : f0 + 10, 13);
  const Col = ({label, text, red, p, dir}: any) => (
    <div style={{...shell, flex: 1, opacity: p, transform: `translateX(${(1 - p) * dir * 60}px)`}}>
      <div style={monoStyle(19, red ? C.rosso : C.inchiostro2)}>{label}</div>
      <div style={{...displayStyle(34, red ? C.rosso : C.inchiostro), marginTop: 6}}>{text}</div>
    </div>
  );
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap, display: 'flex', gap: 18, width: 900}}>
      <Col {...ev.left} p={p1} dir={-1} />
      <Col {...ev.right} p={p2} dir={1} />
    </div>
  );
};

// ============================== NETWORK ==============================
export const Network: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'pop', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const cx = 320, cy = 250, R = 195;
  const slow = ((frame - f0) / 30) * 4; // rotazione lentissima del ring
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap, top: 110, width: 660, height: 520}}>
      <svg width="660" height="520" viewBox="0 0 660 520" style={{overflow: 'visible'}}>
        {ev.nodes.map((n: any, i: number) => {
          const ang = ((i / ev.nodes.length) * 360 + slow - 90) * (Math.PI / 180);
          const nx = cx + R * Math.cos(ang);
          const ny = cy + R * 0.86 * Math.sin(ang);
          const draw = rev(frame, F(n.t), 14);
          return <line key={i} x1={cx} y1={cy} x2={cx + (nx - cx) * draw} y2={cy + (ny - cy) * draw} stroke={C.carta} strokeWidth="3" style={{filter: 'drop-shadow(0 1px 4px rgba(0,0,0,.5))'}} />;
        })}
      </svg>
      <div style={{position: 'absolute', left: cx - 52, top: cy - 52}}>
        <div style={{width: 104, height: 104, background: C.rosso, boxShadow: SHADOW, display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${0.7 + 0.3 * spring({frame: Math.max(0, frame - f0), fps, config: {damping: 12, stiffness: 130, mass: 0.7}})}) rotate(45deg)`}}>
          <span style={{...displayStyle(40, C.carta), transform: 'rotate(-45deg)'}}>{ev.center}</span>
        </div>
      </div>
      {ev.nodes.map((n: any, i: number) => {
        const ang = ((i / ev.nodes.length) * 360 + slow - 90) * (Math.PI / 180);
        const nx = cx + R * Math.cos(ang);
        const ny = cy + R * 0.86 * Math.sin(ang);
        const sp = frame >= F(n.t) ? spring({frame: frame - F(n.t), fps, config: {damping: 12, stiffness: 150, mass: 0.7}}) : 0;
        if (frame < F(n.t)) return null;
        return (
          <div key={i} style={{
            position: 'absolute', left: nx, top: ny,
            transform: `translate(-50%, -50%) scale(${0.7 + 0.3 * sp})`,
            opacity: Math.min(1, sp * 1.4),
            ...shell, padding: '8px 18px',
          }}>
            <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 23, color: C.inchiostro, whiteSpace: 'nowrap'}}>{n.text}</div>
          </div>
        );
      })}
    </div>
  );
};

// ============================== PIPELINE ==============================
export const Pipeline: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      {ev.label && <div style={{...monoStyle(20, C.carta), textShadow: '0 2px 12px rgba(0,0,0,.75)', marginBottom: 12}}>{ev.label}</div>}
      <div style={{display: 'flex', flexDirection: 'column', gap: 0}}>
        {ev.nodes.map((n: any, i: number) => {
          const sp = frame >= F(n.t) ? spring({frame: frame - F(n.t), fps, config: {damping: 12, stiffness: 150, mass: 0.7}}) : 0;
          if (frame < F(n.t)) return null;
          return (
            <React.Fragment key={i}>
              {i > 0 && (
                <svg width="26" height="26" viewBox="0 0 26 26" style={{marginLeft: 44, opacity: sp}}>
                  <path d="M13 2 V18 M5 12 L13 21 L21 12" fill="none" stroke={C.carta} strokeWidth="3.5" style={{filter: 'drop-shadow(0 1px 5px rgba(0,0,0,.6))'}} />
                </svg>
              )}
              <div style={{
                ...shell,
                padding: '9px 22px',
                width: 'fit-content',
                borderColor: n.red ? C.rosso : C.inchiostro,
                opacity: Math.min(1, sp * 1.4),
                transform: `translateX(${(1 - sp) * -40}px)`,
              }}>
                <div style={{...displayStyle(30, n.red ? C.rosso : C.inchiostro)}}>{n.text}</div>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

// ============================== SIX ==============================
export const Six: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const sixAt = ev.k?.six ? F(ev.k.six) : f0 + 22;
  const outAt = ev.k?.out ? F(ev.k.out) : f0 + Math.round((ev.t1 - ev.t0) * 30 * 0.68);
  const op = frame >= outAt ? spring({frame: frame - outAt, fps, config: {damping: 12, stiffness: 140, mass: 0.7}}) : 0;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, padding: '12px 24px', display: 'inline-block'}}>
        <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 26, color: C.inchiostro}}>{ev.seed}</div>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 150px)', gap: 12, marginTop: 16}}>
        {Array.from({length: 6}, (_, i) => {
          const at = sixAt + i * 7;
          const sp = frame >= at ? spring({frame: frame - at, fps, config: {damping: 12, stiffness: 160, mass: 0.6}}) : 0;
          if (frame < at) return null;
          return (
            <div key={i} style={{
              height: 92, background: C.carta, border: `2px solid ${C.inchiostro}`, boxShadow: SHADOW,
              opacity: Math.min(1, sp * 1.4), transform: `scale(${0.7 + 0.3 * sp})`,
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6,
            }}>
              <div style={{width: 96, height: 8, background: i % 2 ? C.blu : C.rosso}} />
              <div style={{width: 70, height: 6, background: C.filetto}} />
              <div style={{...monoStyle(14, C.inchiostro2)}}>modello {i + 1}</div>
            </div>
          );
        })}
      </div>
      {frame >= outAt && (
        <div style={{
          marginTop: 16, background: C.rosso, color: C.carta, padding: '12px 26px', width: 'fit-content',
          boxShadow: SHADOW, opacity: Math.min(1, op * 1.4), transform: `translateY(${(1 - op) * 24}px)`,
        }}>
          <div style={displayStyle(34, C.carta)}>→ {ev.out}</div>
        </div>
      )}
    </div>
  );
};

// ============================== CRASH0 ==============================
export const Crash0: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const crashAt = ev.k?.crash ? F(ev.k.crash) : f0 + 40;
  const cp = frame >= crashAt ? spring({frame: frame - crashAt, fps, config: {damping: 13, stiffness: 110, mass: 0.9}}) : 0;
  const hours = Math.round((ev.from ?? 0) * (1 - cp));
  const pulse = 1 + 0.05 * Math.sin(((frame - f0) / 30) * Math.PI * 1.6) * cp;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...monoStyle(20, C.carta), textShadow: '0 2px 12px rgba(0,0,0,.8)'}}>{ev.label}</div>
      <div style={{
        ...displayStyle(190, hours === 0 ? C.rosso : C.carta),
        textShadow: '0 5px 30px rgba(0,0,0,.6)',
        transform: `scale(${pulse})`, transformOrigin: 'left center', lineHeight: 1.05,
      }}>
        {hours}{ev.unit ? ` ${ev.unit}` : ''}
      </div>
      <div style={{...monoStyle(22, C.carta), marginTop: 10, textShadow: '0 2px 12px rgba(0,0,0,.8)', opacity: rev(frame, ev.k?.lbl ? F(ev.k.lbl) : crashAt + 14, 14)}}>
        {ev.tail}
      </div>
    </div>
  );
};

// ============================== CRASHDOWN ==============================
export const CrashDown: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const p = rev(frame, f0 + 6, 50);
  const val = Math.round((ev.value ?? 0) * p);
  const shake = p >= 1 ? Math.sin(frame * 2.2) * 2.5 : 0;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{
        ...displayStyle(120, C.rosso),
        textShadow: '0 4px 26px rgba(0,0,0,.5)',
        transform: `translateX(${shake}px)`,
      }}>
        {ev.prefix ?? '−'}{itNum(val)}{ev.unit ? ` ${ev.unit}` : ''}
      </div>
      <div style={{...monoStyle(21, C.carta), marginTop: 10, textShadow: '0 2px 12px rgba(0,0,0,.8)'}}>{ev.sub}</div>
      {ev.tail && frame >= F(ev.tail.t) && (
        <div style={{...displayStyle(34, C.carta), marginTop: 16, textShadow: '0 3px 16px rgba(0,0,0,.8)', opacity: rev(frame, F(ev.tail.t), 12)}}>
          <Rich text={ev.tail.text} />
        </div>
      )}
    </div>
  );
};

// ============================== GRID ==============================
export const Grid: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      {ev.label && <div style={{...monoStyle(20, C.carta), textShadow: '0 2px 12px rgba(0,0,0,.75)', marginBottom: 12}}>{ev.label}</div>}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 300px)', gap: 14}}>
        {ev.cells.map((c: any, i: number) => {
          const sp = frame >= F(c.t) ? spring({frame: frame - F(c.t), fps, config: {damping: 12, stiffness: 150, mass: 0.7}}) : 0;
          const chk = rev(frame, F(c.t) + 10, 12);
          if (frame < F(c.t)) return null;
          return (
            <div key={i} style={{
              ...shell, padding: '16px 22px', display: 'flex', alignItems: 'center', gap: 14,
              opacity: Math.min(1, sp * 1.4), transform: `translateY(${(1 - sp) * 30}px) scale(${0.85 + 0.15 * sp})`,
            }}>
              <svg width="30" height="30" viewBox="0 0 30 30" style={{flexShrink: 0}}>
                <rect x="2" y="2" width="26" height="26" fill="none" stroke={C.inchiostro} strokeWidth="3" />
                <path d="M7 16 L13 23 L24 7" fill="none" stroke={C.blu} strokeWidth="4" strokeDasharray={36} strokeDashoffset={36 * (1 - chk)} />
              </svg>
              <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 25, color: C.inchiostro}}>{c.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ============================== CTA ==============================
export const Cta: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'drop', ev.pos);
  if (!l.alive) return null;
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{...shell, width: 620}}>
        {filetto}
        {ev.rows.map((r: any, i: number) => {
          const sp = frame >= F(r.t) ? spring({frame: frame - F(r.t), fps, config: {damping: 12, stiffness: 140, mass: 0.7}}) : 0;
          if (frame < F(r.t)) return null;
          return (
            <div key={i} style={{marginTop: i ? 14 : 0, opacity: Math.min(1, sp * 1.4), transform: `translateX(${(1 - sp) * -34}px)`}}>
              {r.mail ? (
                <div style={{display: 'flex', gap: 16, alignItems: 'center'}}>
                  <svg width="66" height="48" viewBox="0 0 66 48" style={{flexShrink: 0}}>
                    <rect x="3" y="3" width="60" height="42" fill="none" stroke={C.rosso} strokeWidth="4" />
                    <path d="M3 6 L33 28 L63 6" fill="none" stroke={C.rosso} strokeWidth="4" />
                  </svg>
                  <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 28, color: C.inchiostro}}>{r.text}</div>
                </div>
              ) : (
                <div style={{...displayStyle(34)}}>{r.text}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ============================== LISTA3 ==============================
// "le prime 3 voci della lista valgono ore": foglio-lista, le prime 3 righe si
// evidenziano a penna una a una, accanto il contatore di ore che si accumula.
export const Lista3: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = useLife(ev.t0, ev.t1, 'slide', ev.pos);
  if (!l.alive) return null;
  const f0 = F(ev.t0);
  const hlF = F(ev.k.hl);
  const oreF = F(ev.k.ore);
  const WIDTHS = [430, 360, 470, 320, 400, 290];
  const ore = Math.round((ev.value ?? 0) * rev(frame, oreF, 40));
  const clock = ((frame - oreF) / 30) * 260; // lancetta veloce: il tempo si accumula
  return (
    <div style={{...posStyle(ev.pos), ...l.wrap}}>
      <div style={{display: 'flex', gap: 24, alignItems: 'flex-start'}}>
        <div style={{...shell, padding: '20px 26px', width: 560}}>
          <div style={{...monoStyle(19, C.inchiostro2), marginBottom: 12}}>{ev.title ?? 'Lista'}</div>
          {WIDTHS.map((w, i) => {
            const born = rev(frame, f0 + 6 + i * 3, 8);
            const isTop = i < 3;
            const hlAt = hlF + i * 15;
            const hl = isTop ? rev(frame, hlAt, 11) : 0;
            const dim = !isTop && frame >= hlF ? 0.35 : 1;
            return (
              <div key={i} style={{position: 'relative', height: 34, marginTop: i ? 10 : 0, opacity: born * dim}}>
                {isTop && hl > 0 && (
                  <div style={{position: 'absolute', left: -8, top: -3, height: 40, width: (w + 18) * hl, background: C.filetto, borderLeft: `6px solid ${C.rosso}`}} />
                )}
                <div style={{position: 'absolute', left: 8, top: 6, width: w, height: 18, background: isTop ? C.inchiostro : C.filetto}} />
                {isTop && (
                  <svg width="26" height="26" viewBox="0 0 26 26" style={{position: 'absolute', right: -2, top: 2}}>
                    <path d="M4 14 L11 21 L23 5" fill="none" stroke={C.rosso} strokeWidth="4.5"
                      strokeDasharray={34} strokeDashoffset={34 * (1 - hl)} />
                  </svg>
                )}
              </div>
            );
          })}
        </div>
        {frame >= oreF - 4 && (
          <div style={{opacity: rev(frame, oreF - 4, 10)}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
              <svg width="64" height="64" viewBox="0 0 64 64">
                <circle cx="32" cy="32" r="27" fill="none" stroke={C.inchiostro} strokeWidth="5" style={{filter: 'drop-shadow(0 2px 6px rgba(0,0,0,.4))'}} />
                <line x1="32" y1="32" x2={32 + 19 * Math.sin((clock * Math.PI) / 180)} y2={32 - 19 * Math.cos((clock * Math.PI) / 180)} stroke={C.rosso} strokeWidth="5" />
              </svg>
              <div style={{...displayStyle(110, C.rosso), textShadow: '0 3px 18px rgba(0,0,0,.45)'}}>{ore}</div>
            </div>
            <div style={{...monoStyle(20, C.carta), marginTop: 8, textShadow: '0 2px 12px rgba(0,0,0,.8)'}}>
              {ev.label ?? ''}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ============================== STAMP ==============================
export const Stamp: React.FC<{ev: any}> = ({ev}) => {
  const frame = useCurrentFrame();
  if (frame < F(ev.t0) - 20) return null;
  return (
    <div style={{position: 'absolute', right: 70, top: 84}}>
      <Timbro size={210} dropAt={F(ev.t0) + 6} text={ev.text} />
      <div style={{...monoStyle(19, C.carta), marginTop: 12, textAlign: 'center', textShadow: '0 2px 12px rgba(0,0,0,.8)', opacity: rev(frame, F(ev.t0) + 22, 14)}}>
        {ev.label ?? ''}
      </div>
    </div>
  );
};
