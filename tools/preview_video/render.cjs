/* Use an already installed Remotion toolchain and browser; never install or download. */
const fs = require('node:fs/promises');
const path = require('node:path');
const { createRequire } = require('node:module');
const crypto = require('node:crypto');
async function main() {
  const [modules, browserExecutable] = process.argv.slice(2);
  if (!modules || !browserExecutable)
    throw new Error(
      'Usage: node tools/preview_video/render.cjs REMOTION_NODE_MODULES CHROMIUM_EXECUTABLE',
    );
  const req = createRequire(path.join(path.resolve(modules), 'remotion', 'package.json'));
  const { bundle } = req('@remotion/bundler');
  const { selectComposition, renderMedia } = req('@remotion/renderer');
  const root = path.resolve(__dirname, '../..');
  const work = path.join(root, '.factory/preview10-polish-audit');
  const capture = path.join(work, 'ui-capture');
  const manifest = JSON.parse(await fs.readFile(path.join(capture, 'captures.json'), 'utf8'));
  if (
    manifest.classification !== 'ACTUAL_WMM_UI_SYNTHETIC_WORKSPACE' ||
    manifest.social_publication !== 'NOT_RUN'
  )
    throw new Error('Synthetic UI capture proof required');
  for (const item of manifest.captures) {
    const data = await fs.readFile(path.join(capture, item.file));
    if (crypto.createHash('sha256').update(data).digest('hex') !== item.sha256)
      throw new Error('Capture changed');
  }
  const media = path.join(root, 'docs/media');
  await fs.mkdir(media, { recursive: true });
  const serveUrl = await bundle({
    entryPoint: path.join(__dirname, 'composition.mjs'),
    outDir: path.join(work, 'remotion-bundle'),
    publicDir: capture,
    enableCaching: false,
    webpackOverride: (config) => ({
      ...config,
      resolve: {
        ...config.resolve,
        modules: [path.resolve(modules), ...(config.resolve.modules || [])],
      },
    }),
  });
  const composition = await selectComposition({ serveUrl, id: 'WMMActualUI', browserExecutable });
  await renderMedia({
    serveUrl,
    composition,
    browserExecutable,
    codec: 'h264',
    outputLocation: path.join(media, 'video-production.mp4'),
    concurrency: 1,
    imageFormat: 'jpeg',
    jpegQuality: 80,
    crf: 25,
    x264Preset: 'fast',
  });
  console.log(
    JSON.stringify({
      status: 'PASS',
      engine: 'Remotion',
      frames: 225,
      social_publication: 'NOT_RUN',
    }),
  );
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
