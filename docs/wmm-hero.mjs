const panel = document.querySelector('[data-wmm-hero]');
const navigation = document.querySelectorAll('header nav a[href^="#"]');
function markSection() {
  for (const anchor of navigation) {
    if (anchor.hash === location.hash) anchor.setAttribute('aria-current', 'location');
    else anchor.removeAttribute('aria-current');
  }
}
markSection();
window.addEventListener('hashchange', markSection);
if (panel) {
  const stages = [
    ['Set your goal', 'Choose one app and one question worth answering.'],
    ['Watch the work', 'Review the plan, then approve the exact work your agent can carry out.'],
    ['Review results', 'Open the receipt, see what the sources show, and choose what to do next.'],
  ];
  const controls = [...panel.querySelectorAll('[data-stage]')];
  const viewport = panel.querySelector('.wmm-console-art');
  const label = panel.querySelector('[data-stage-label]');
  const description = panel.querySelector('[data-stage-description]');
  let selected = 0;
  let selectScene;
  for (const [index, control] of controls.entries()) {
    control.addEventListener('click', () => {
      selected = index;
      controls.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
      [label.textContent, description.textContent] = stages[index];
      selectScene?.(index);
    });
  }
  panel.dataset.controls = 'ready';

  async function load() {
    try {
      const canvas = viewport.querySelector('canvas');
      const context = canvas.getContext('webgl2', { antialias: true, alpha: true });
      if (!context) return;
      const three = await import('./vendor/three/three-wmm.mjs');
      selectScene = createScene(three, canvas, context, viewport, selected);
    } catch {
      // The poster and HTML controls are the complete fallback.
      viewport.dataset.render = 'poster';
    }
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      void load();
    });
    observer.observe(viewport);
  } else {
    void load();
  }
}

function createScene(T, canvas, context, viewport, initiallySelected) {
  const renderer = new T.WebGLRenderer({ canvas, context, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.28;
  const scene = new T.Scene();
  const camera = new T.OrthographicCamera(-4, 4, 3, -3, 0.1, 50);
  camera.position.set(7, 9.8, 12);
  camera.lookAt(0, 0.16, 0);
  const console = new T.Group();
  console.rotation.y = -0.13;
  scene.add(console, new T.HemisphereLight(0xffedce, 0x274d3c, 2.05));
  for (const [color, strength, x, y, z] of [
    [0xffd1a0, 3.3, -5, 8, 5],
    [0xadf5c2, 2.8, 5, 2, -5],
  ]) {
    const light = new T.DirectionalLight(color, strength);
    light.position.set(x, y, z);
    scene.add(light);
  }

  const material = (color, metalness = 0.25, roughness = 0.46) =>
    new T.MeshStandardMaterial({ color, metalness, roughness });
  const shell = material(0x233e36);
  const deck = material(0x172a24);
  const trim = material(0xb48148, 0.48);
  const paper = material(0xe9debd, 0.02, 0.78);
  const ink = material(0x3b5143);
  const bright = new T.MeshStandardMaterial({
    color: 0xd7e99d,
    emissive: 0x87bd38,
    emissiveIntensity: 0.35,
    roughness: 0.42,
  });

  function add(geometry, surface, x, y, z, parent = console) {
    const mesh = new T.Mesh(geometry, surface);
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }

  function slab(w, depth, height, radius, surface, x, y, z, parent) {
    const s = new T.Shape();
    const a = w / 2;
    const b = depth / 2;
    s.moveTo(-a + radius, -b);
    s.lineTo(a - radius, -b);
    s.quadraticCurveTo(a, -b, a, -b + radius);
    s.lineTo(a, b - radius);
    s.quadraticCurveTo(a, b, a - radius, b);
    s.lineTo(-a + radius, b);
    s.quadraticCurveTo(-a, b, -a, b - radius);
    s.lineTo(-a, -b + radius);
    s.quadraticCurveTo(-a, -b, -a + radius, -b);
    const geometry = new T.ExtrudeGeometry(s, {
      depth: height,
      bevelEnabled: true,
      bevelSize: 0.045,
      bevelThickness: 0.045,
      bevelSegments: 2,
      curveSegments: 6,
    });
    const mesh = add(geometry, surface, x, y, z, parent);
    mesh.rotation.x = -Math.PI / 2;
    return mesh;
  }

  slab(7.4, 3.15, 0.28, 0.32, shell, 0, -0.29, 0);
  slab(7.25, 3, 0.095, 0.27, trim, 0, 0, 0);
  slab(7.16, 2.91, 0.15, 0.25, deck, 0, 0.1, 0);
  const positions = [-2.28, 0, 2.28];
  const stations = positions.map((x, index) => {
    const stage = new T.Group();
    stage.position.set(x, 0.28, -0.09);
    console.add(stage);
    const key = material(0x36564a, 0.21, 0.4);
    slab(1.91, 2.05, 0.25, 0.25, key, 0, 0, 0, stage);
    slab(1.62, 0.07, 0.015, 0.025, trim, 0, 0.29, 0.78, stage);
    if (index === 0) {
      for (const radius of [0.29, 0.51]) {
        const ring = add(new T.TorusGeometry(radius, 0.04, 8, 36), bright, 0, 0.33, -0.04, stage);
        ring.rotation.x = -Math.PI / 2;
      }
      add(new T.SphereGeometry(0.12, 16, 12), trim, 0, 0.36, -0.04, stage);
    } else if (index === 1) {
      slab(0.98, 0.68, 0.12, 0.09, shell, -0.12, 0.34, -0.18, stage);
      slab(0.98, 0.68, 0.1, 0.09, paper, 0.11, 0.52, 0.04, stage);
      const play = add(new T.CylinderGeometry(0.18, 0.18, 0.04, 3), ink, 0.13, 0.67, 0.04, stage);
      play.rotation.y = Math.PI / 2;
    } else {
      const receipt = new T.Group();
      receipt.position.set(0, 0.46, -0.05);
      receipt.rotation.x = -0.41;
      stage.add(receipt);
      slab(0.81, 1.14, 0.05, 0.09, paper, 0, 0, 0, receipt);
      for (const [i, w] of [0.49, 0.52, 0.36].entries()) {
        slab(w, 0.036, 0.008, 0.01, ink, (w - 0.52) / 2, 0.105, -0.28 + i * 0.19, receipt);
      }
    }
    for (let i = 0; i <= index; i++) {
      add(
        new T.CylinderGeometry(0.033, 0.033, 0.03, 10),
        trim,
        (i - index / 2) * 0.155,
        0.31,
        0.58,
        stage,
      );
    }
    return { stage, key };
  });
  const signal = new T.MeshStandardMaterial({
    color: 0xffbc5b,
    emissive: 0xff8b26,
    emissiveIntensity: 0.55,
    roughness: 0.32,
  });
  add(new T.SphereGeometry(0.09, 16, 10), signal, -1.14, 0.35, 1.09);
  add(new T.CylinderGeometry(0.13, 0.13, 0.075, 18), trim, -1.14, 0.28, 1.09);

  let frame = 0;
  let unavailable = false;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const observer = new ResizeObserver(size);

  function fallback() {
    if (unavailable) return;
    unavailable = true;
    cancelAnimationFrame(frame);
    observer.disconnect();
    viewport.dataset.render = 'poster';
  }

  function render() {
    try {
      renderer.render(scene, camera);
    } catch {
      fallback();
    }
  }
  function size() {
    if (unavailable) return;
    const { clientWidth: width, clientHeight: height } = viewport;
    if (!width || !height) return;
    const aspect = width / height;
    const halfHeight = Math.max(2.85, 4.08 / aspect);
    Object.assign(camera, {
      left: -halfHeight * aspect,
      right: halfHeight * aspect,
      top: halfHeight,
      bottom: -halfHeight,
    });
    camera.updateProjectionMatrix();
    try {
      renderer.setSize(width, height, false);
    } catch {
      fallback();
      return;
    }
    render();
    if (!unavailable) viewport.dataset.render = 'webgl';
  }

  function select(index, animate = true) {
    if (unavailable) return;
    cancelAnimationFrame(frame);
    const from = stations.map(({ stage }) => stage.position.y);
    const to = stations.map((_, i) => (i === index ? 0.55 : 0.28));
    stations.forEach(({ key }, i) => key.color.setHex(i === index ? 0x688756 : 0x36564a));
    signal.emissiveIntensity = index === 1 ? 1.7 : 0.55;
    const started = performance.now();
    const step = (time) => {
      if (unavailable) return;
      const p = !animate || motion.matches ? 1 : Math.min(1, (time - started) / 300);
      const ease = 1 - (1 - p) ** 3;
      stations.forEach(({ stage }, i) => (stage.position.y = from[i] + (to[i] - from[i]) * ease));
      render();
      if (!unavailable && p < 1) frame = requestAnimationFrame(step);
    };
    step(started);
  }

  canvas.addEventListener('webglcontextlost', fallback, { once: true });
  select(initiallySelected, false);
  size();
  if (!unavailable) observer.observe(viewport);
  return select;
}
