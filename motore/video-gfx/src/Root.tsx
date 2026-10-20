import React from 'react';
import {Composition} from 'remotion';
import {MasterFull} from './scenes/MasterFull';
import {OverlayShort} from './scenes/OverlayShort';
import REGIA from './data/regia.json';

export const RemotionRoot: React.FC = () => {
  if (REGIA.fps !== 30) throw new Error('Native graphics require fps=30. Normalize the source before rendering.');
  return <>
    <Composition id="master-full" component={MasterFull} durationInFrames={Math.max(1, Math.round(REGIA.durSec * 30))} fps={30} width={1920} height={1080} />
    <Composition id="OV-short" component={OverlayShort} durationInFrames={240} fps={30} width={1080} height={1920}
      defaultProps={{events: [], durSec: 8}}
      calculateMetadata={({props}) => ({durationInFrames: Math.max(1, Math.ceil(((props as {durSec?: number}).durSec ?? 8) * 30))})} />
  </>;
};
