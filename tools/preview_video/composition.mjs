import React from 'react';
import {
  AbsoluteFill,
  Composition,
  Img,
  registerRoot,
  staticFile,
  useCurrentFrame,
} from 'remotion';
const names = ['01-workspace', '02-render-options', '03-edit', '04-taste', '05-save'];
const captions = [
  'Open your app’s creative workspace',
  'Choose the brief, renderer and format',
  'Revise the timeline, captions and crop',
  'Inspect and apply the taste proposal',
  'Save a revision for the next review',
];
function ActualUI() {
  const step = Math.min(4, Math.floor(useCurrentFrame() / 45));
  return React.createElement(
    AbsoluteFill,
    { style: { backgroundColor: '#142f37', fontFamily: 'Arial, sans-serif' } },
    React.createElement(Img, {
      src: staticFile(names[step] + '.png'),
      style: { width: 1440, height: 900 },
    }),
    React.createElement(
      'div',
      {
        style: { position: 'absolute', top: 912, left: 28, right: 28, color: '#fff', fontSize: 26 },
      },
      captions[step],
    ),
    React.createElement(
      'div',
      { style: { position: 'absolute', bottom: 12, left: 28, color: '#d4e3ac', fontSize: 17 } },
      'Actual WMM interface · synthetic workspace · no social publication or marketing result',
    ),
  );
}
registerRoot(() =>
  React.createElement(Composition, {
    id: 'WMMActualUI',
    component: ActualUI,
    durationInFrames: 225,
    fps: 15,
    width: 1440,
    height: 1000,
  }),
);
