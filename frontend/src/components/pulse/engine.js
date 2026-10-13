/**
 * Procedural 2D pixel-art engine for the LLM Pulse Gateway world.
 * Every shape is drawn with canvas primitives — no image assets.
 *
 * The simulation is DATA-DRIVEN: beginFlow() starts a request journey and
 * handleSignal()/onResponse() feed it real SignalPacket events from the
 * backend. Nothing here invents routing decisions or metrics.
 */

const V_WIDTH = 1000;
const V_HEIGHT = 440;
// Extra world drawn beyond the viewport so the scene still fills the canvas
// edge-to-edge when it is letterboxed to preserve aspect ratio.
const PAD = 400;
const GROUND_Y = 328;
const PATH_Y = 338;

const TOWER_X = 160;
const VAULT_X = 395;
const FORTRESS_LOCAL_X = 740;
const FORTRESS_CLOUD_X = 850;

export function createPulseEngine(canvas, { onStatus, onFps } = {}) {
  const ctx = canvas.getContext('2d');

  /* ------------------------------ state ------------------------------ */

  const sim = {
    phase: 'IDLE', // IDLE | DISPATCH_TO_VAULT | AT_VAULT | AT_VAULT_HIT | AT_VAULT_MISS | TO_FORTRESS_LOCAL | TO_FORTRESS_CLOUD | COMPUTING_LOCAL | COMPUTING_CLOUD | RETURNING | DONE
    timer: 0,
    flowActive: false,
    routeDestination: null, // 'local_slm' | 'cloud_fortress'
    cacheSimilarity: null,
  };

  const status = (text) => {
    if (onStatus) onStatus(text);
  };

  const particles = [];
  function spawnBurst(x, y, color, count = 15, speed = 2.5) {
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const s = Math.random() * speed + 0.8;
      particles.push({
        x, y,
        vx: Math.cos(angle) * s,
        vy: Math.sin(angle) * s - 0.5,
        color,
        life: 1.0,
        decay: 0.02 + Math.random() * 0.03,
        size: Math.random() > 0.5 ? 4 : 2,
      });
    }
  }

  const clouds = [
    { x: 30, y: 35, speed: 0.22, scale: 1.3 },
    { x: 260, y: 58, speed: 0.3, scale: 0.95 },
    { x: 550, y: 28, speed: 0.25, scale: 1.4 },
    { x: 820, y: 65, speed: 0.18, scale: 1.1 },
  ];

  const courier = {
    x: TOWER_X, y: PATH_Y, targetX: TOWER_X, facing: 1, frame: 0,
    carrying: null, speed: 3.2,
    bubble: '', bubbleTimer: 0, bubbleColor: '#2563EB',
  };

  const courier2 = {
    x: 580, y: PATH_Y, targetX: 750, facing: 1, frame: 1,
    carrying: null, speed: 2.2,
    bubble: '', bubbleTimer: 0, bubbleColor: '#db2777',
  };

  function setCourierBubble(text, color = '#1e293b', duration = 140) {
    courier.bubble = text;
    courier.bubbleColor = color;
    courier.bubbleTimer = duration;
  }

  /* --------------------------- scene: world --------------------------- */

  function drawSkyAndEnvironment(t) {
    const skyGrad = ctx.createLinearGradient(0, 0, 0, GROUND_Y);
    skyGrad.addColorStop(0, '#7acaf9');
    skyGrad.addColorStop(0.55, '#a7e4fd');
    skyGrad.addColorStop(1, '#d8f4ff');
    ctx.fillStyle = skyGrad;
    ctx.fillRect(-PAD, -PAD, V_WIDTH + PAD * 2, V_HEIGHT + PAD * 2);

    clouds.forEach((c) => {
      c.x += c.speed;
      if (c.x > V_WIDTH + 100) c.x = -120;
      drawPixelCloud(c.x, c.y, c.scale);
    });

    ctx.fillStyle = '#8bc3da';
    ctx.beginPath();
    ctx.moveTo(0, 200); ctx.lineTo(80, 140); ctx.lineTo(190, 210); ctx.lineTo(290, 130);
    ctx.lineTo(440, 215); ctx.lineTo(550, 145); ctx.lineTo(690, 210); ctx.lineTo(830, 125);
    ctx.lineTo(950, 195); ctx.lineTo(1000, 160); ctx.lineTo(1000, GROUND_Y); ctx.lineTo(0, GROUND_Y);
    ctx.fill();

    ctx.fillStyle = '#d2edf9';
    ctx.beginPath(); ctx.moveTo(70, 148); ctx.lineTo(80, 140); ctx.lineTo(92, 148); ctx.lineTo(80, 153); ctx.fill();
    ctx.beginPath(); ctx.moveTo(280, 139); ctx.lineTo(290, 130); ctx.lineTo(302, 140); ctx.lineTo(290, 144); ctx.fill();
    ctx.beginPath(); ctx.moveTo(820, 134); ctx.lineTo(830, 125); ctx.lineTo(842, 135); ctx.lineTo(830, 139); ctx.fill();

    ctx.fillStyle = '#6ab875';
    ctx.beginPath();
    ctx.moveTo(0, 245);
    ctx.quadraticCurveTo(180, 190, 360, 235);
    ctx.quadraticCurveTo(550, 185, 780, 225);
    ctx.quadraticCurveTo(900, 200, 1000, 230);
    ctx.lineTo(1000, GROUND_Y); ctx.lineTo(0, GROUND_Y);
    ctx.fill();

    ctx.fillStyle = '#78c6e8';
    ctx.fillRect(0, 236, V_WIDTH, 7);
    ctx.fillStyle = '#a2ddf5';
    ctx.fillRect(120, 238, 90, 2);
    ctx.fillRect(480, 238, 120, 2);
    ctx.fillRect(780, 238, 140, 2);

    drawPixelPineTree(50, 225, 1.2); drawPixelPineTree(95, 230, 0.9);
    drawPixelPineTree(210, 220, 1.1); drawPixelPineTree(240, 228, 0.8);
    drawPixelPineTree(320, 232, 1.3); drawPixelPineTree(520, 215, 1.0);
    drawPixelPineTree(640, 222, 1.2); drawPixelPineTree(680, 230, 0.85);
    drawPixelPineTree(920, 218, 1.15); drawPixelPineTree(970, 226, 0.9);

    ctx.fillStyle = '#4ade80';
    ctx.fillRect(-PAD, GROUND_Y - 24, V_WIDTH + PAD * 2, V_HEIGHT - (GROUND_Y - 24) + PAD);
    ctx.fillStyle = '#86efac';
    ctx.fillRect(-PAD, GROUND_Y - 26, V_WIDTH + PAD * 2, 4);

    drawBush(35, GROUND_Y - 18, 16, '#22c55e');
    drawBush(190, GROUND_Y - 20, 14, '#16a34a');
    drawBush(320, GROUND_Y - 19, 18, '#22c55e');
    drawBush(530, GROUND_Y - 22, 15, '#16a34a');
    drawBush(680, GROUND_Y - 18, 17, '#22c55e');
    drawBush(960, GROUND_Y - 18, 20, '#16a34a');

    ctx.fillStyle = '#cbd5e1';
    ctx.fillRect(20, PATH_Y - 8, 960, 28);
    ctx.fillStyle = '#94a3b8';
    ctx.fillRect(20, PATH_Y + 20, 960, 3);
    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(20, PATH_Y - 9, 960, 2);
    for (let px = 25; px < 975; px += 26) {
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(px, PATH_Y - 5, 15, 8);
      ctx.fillStyle = '#e2e8f0';
      ctx.fillRect(px + 10, PATH_Y + 5, 13, 8);
      ctx.fillStyle = '#cbd5e1';
      ctx.fillRect(px + 3, PATH_Y + 14, 10, 4);
    }

    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 6]);
    ctx.lineDashOffset = -t * 0.04;
    ctx.beginPath();
    ctx.moveTo(120, PATH_Y - 12);
    ctx.lineTo(410, PATH_Y - 12);
    ctx.lineTo(790, PATH_Y - 12);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function drawPixelCloud(x, y, s) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
    ctx.beginPath();
    ctx.fillRect(x, y + 8 * s, 68 * s, 18 * s);
    ctx.fillRect(x + 12 * s, y, 44 * s, 26 * s);
    ctx.fillRect(x + 22 * s, y - 6 * s, 26 * s, 34 * s);
    ctx.fillStyle = 'rgba(224, 242, 254, 0.85)';
    ctx.fillRect(x + 6 * s, y + 20 * s, 58 * s, 6 * s);
  }

  function drawPixelPineTree(x, y, s) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(s, s);
    ctx.fillStyle = '#854d0e';
    ctx.fillRect(-2, 0, 4, 10);
    ctx.fillStyle = '#166534';
    ctx.beginPath();
    ctx.moveTo(0, -32); ctx.lineTo(12, -18); ctx.lineTo(6, -18); ctx.lineTo(15, -4);
    ctx.lineTo(9, -4); ctx.lineTo(17, 4); ctx.lineTo(-17, 4); ctx.lineTo(-9, -4);
    ctx.lineTo(-15, -4); ctx.lineTo(-6, -18); ctx.lineTo(-12, -18);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#22c55e';
    ctx.beginPath();
    ctx.moveTo(0, -32); ctx.lineTo(12, -18); ctx.lineTo(6, -18); ctx.lineTo(15, -4);
    ctx.lineTo(9, -4); ctx.lineTo(17, 4); ctx.lineTo(0, 4);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawBush(x, y, r, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.arc(x + r * 0.7, y + 2, r * 0.7, 0, Math.PI * 2);
    ctx.arc(x - r * 0.6, y + 3, r * 0.6, 0, Math.PI * 2);
    ctx.fill();
  }

  /* --------------------------- scene: towers --------------------------- */

  function drawWardenTower(t) {
    const cx = 118;
    const cy = GROUND_Y;

    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.beginPath(); ctx.ellipse(cx, cy + 4, 52, 14, 0, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(cx - 38, cy - 125, 76, 125);
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 2;
    ctx.strokeRect(cx - 38, cy - 125, 76, 125);

    ctx.fillStyle = '#cbd5e1';
    for (let r = 0; r < 6; r++) {
      ctx.fillRect(cx - 30 + (r % 2) * 22, cy - 115 + r * 18, 16, 6);
    }

    ctx.fillStyle = '#64748b';
    ctx.fillRect(cx - 44, cy - 134, 88, 10);
    ctx.fillStyle = '#94a3b8';
    ctx.fillRect(cx - 42, cy - 132, 84, 4);

    ctx.fillStyle = '#cbd5e1';
    ctx.fillRect(cx - 42, cy - 150, 16, 16);
    ctx.fillRect(cx - 14, cy - 150, 28, 16);
    ctx.fillRect(cx + 26, cy - 150, 16, 16);
    ctx.strokeRect(cx - 42, cy - 150, 16, 16);
    ctx.strokeRect(cx - 14, cy - 150, 28, 16);
    ctx.strokeRect(cx + 26, cy - 150, 16, 16);

    ctx.fillStyle = '#334155';
    ctx.fillRect(cx - 32, cy - 186, 3, 36);
    const wave = Math.sin(t * 0.007) * 4;
    ctx.fillStyle = '#2563eb';
    ctx.beginPath();
    ctx.moveTo(cx - 29, cy - 186);
    ctx.lineTo(cx - 4, cy - 180 + wave);
    ctx.lineTo(cx - 29, cy - 168);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(cx - 22, cy - 180 + wave * 0.5, 5, 5);

    ctx.fillStyle = '#78350f';
    ctx.beginPath();
    ctx.arc(cx, cy - 28, 16, Math.PI, 0);
    ctx.rect(cx - 16, cy - 28, 32, 28);
    ctx.fill();
    ctx.strokeStyle = '#451a03';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#fbbf24';
    ctx.fillRect(cx - 4, cy - 20, 8, 18);
    ctx.fillStyle = '#fef08a';
    ctx.fillRect(cx - 2, cy - 16, 4, 12);

    ctx.fillStyle = '#2563eb';
    ctx.beginPath();
    ctx.moveTo(cx - 12, cy - 90); ctx.lineTo(cx + 12, cy - 90); ctx.lineTo(cx + 12, cy - 70);
    ctx.lineTo(cx, cy - 58); ctx.lineTo(cx - 12, cy - 70);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(cx - 2, cy - 84, 4, 14);
    ctx.fillRect(cx - 7, cy - 79, 14, 4);

    ctx.fillStyle = '#451a03';
    ctx.fillRect(cx + 38, cy - 56, 7, 3);
    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(cx + 41, cy - 54, 6, 9);
    ctx.fillStyle = 'rgba(251, 191, 36, 0.4)';
    ctx.beginPath(); ctx.arc(cx + 44, cy - 50, 10, 0, Math.PI * 2); ctx.fill();

    drawPixelWorker(cx - 2, cy - 150, '#2563eb', '#fed7aa', true);

    if (sim.flowActive && towerBubbleText()) {
      drawSpeechBubble(cx + 46, cy - 162, towerBubbleText(), '#2563eb', 12);
    }

    drawFacilityBadge(cx, cy + 18, 'Warden Tower', 'Router / Orchestrator', '#2563eb');
  }

  function towerBubbleText() {
    switch (sim.phase) {
      case 'DISPATCH_TO_VAULT': return 'New request received';
      case 'AT_VAULT': return 'Probing cache…';
      case 'AT_VAULT_MISS': return 'Cache miss: routing…';
      case 'TO_FORTRESS_LOCAL': return 'To Local SLM…';
      case 'TO_FORTRESS_CLOUD': return 'To Cloud Fortress…';
      case 'COMPUTING_LOCAL': return 'Model is working…';
      case 'COMPUTING_CLOUD': return 'Cloud streaming…';
      case 'RETURNING': return 'Response inbound';
      default: return '';
    }
  }

  function drawMemoryVault(t) {
    const cx = 412;
    const cy = GROUND_Y;

    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.beginPath(); ctx.ellipse(cx, cy + 4, 64, 15, 0, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(cx - 56, cy - 10, 112, 10);
    ctx.fillStyle = '#cbd5e1';
    ctx.fillRect(cx - 50, cy - 20, 100, 10);
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(cx - 56, cy - 10, 112, 10);
    ctx.strokeRect(cx - 50, cy - 20, 100, 10);

    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(cx - 42, cy - 90, 84, 70);
    ctx.strokeRect(cx - 42, cy - 90, 84, 70);

    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(cx - 38, cy - 88, 10, 68);
    ctx.fillRect(cx - 12, cy - 88, 8, 68);
    ctx.fillRect(cx + 4, cy - 88, 8, 68);
    ctx.fillRect(cx + 28, cy - 88, 10, 68);

    ctx.fillStyle = '#059669';
    ctx.beginPath();
    ctx.moveTo(cx - 60, cy - 90); ctx.lineTo(cx, cy - 128); ctx.lineTo(cx + 60, cy - 90);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#064e3b';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#10b981';
    ctx.beginPath();
    ctx.moveTo(cx - 46, cy - 92); ctx.lineTo(cx, cy - 122); ctx.lineTo(cx + 46, cy - 92);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath(); ctx.arc(cx, cy - 104, 7, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#059669';
    ctx.fillRect(cx - 1, cy - 108, 2, 8);
    ctx.fillRect(cx - 4, cy - 105, 8, 2);

    ctx.fillStyle = '#064e3b';
    ctx.fillRect(cx - 20, cy - 70, 40, 50);

    const crystalBob = Math.sin(t * 0.005) * 5;
    const crystalScale = Math.sin(t * 0.009) * 0.15 + 0.95;
    const cryY = cy - 44 + crystalBob;

    const aura = ctx.createRadialGradient(cx, cryY, 2, cx, cryY, 28);
    aura.addColorStop(0, 'rgba(16, 185, 129, 0.9)');
    aura.addColorStop(1, 'rgba(16, 185, 129, 0)');
    ctx.fillStyle = aura;
    ctx.beginPath(); ctx.arc(cx, cryY, 28, 0, Math.PI * 2); ctx.fill();

    ctx.save();
    ctx.translate(cx, cryY);
    ctx.scale(crystalScale, 1.0);
    ctx.fillStyle = '#34d399';
    ctx.beginPath();
    ctx.moveTo(0, -15); ctx.lineTo(13, 0); ctx.lineTo(0, 15); ctx.lineTo(-13, 0);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#a7f3d0';
    ctx.beginPath();
    ctx.moveTo(0, -15); ctx.lineTo(13, 0); ctx.lineTo(0, 0);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#059669';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();

    drawPixelWorker(cx - 24, cy - 20, '#059669', '#fde047', false);

    const vaultBubble = vaultBubbleText();
    if (vaultBubble) {
      drawSpeechBubble(cx + 8, cy - 146, vaultBubble, vaultBubbleColor(), 8);
    }

    drawFacilityBadge(cx, cy + 18, 'Memory Vault', 'Semantic Cache (Qdrant)', '#059669');
  }

  function vaultBubbleText() {
    switch (sim.phase) {
      case 'AT_VAULT': return 'Checking for cached memory...';
      case 'AT_VAULT_HIT': {
        const pct = sim.cacheSimilarity != null ? ` ${(sim.cacheSimilarity * 100).toFixed(0)}% match` : '';
        return `Cache hit!${pct}`;
      }
      case 'AT_VAULT_MISS': return 'Cache miss';
      default: return '';
    }
  }

  function vaultBubbleColor() {
    if (sim.phase === 'AT_VAULT_HIT') return '#059669';
    if (sim.phase === 'AT_VAULT_MISS') return '#d97706';
    return '#0284c7';
  }

  function drawModelFortress(t) {
    const cx = 795;
    const cy = GROUND_Y;

    ctx.fillStyle = 'rgba(0,0,0,0.14)';
    ctx.beginPath(); ctx.ellipse(cx, cy + 4, 88, 16, 0, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = '#cbd5e1';
    ctx.fillRect(cx - 82, cy - 118, 164, 118);
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 2;
    ctx.strokeRect(cx - 82, cy - 118, 164, 118);

    ctx.fillStyle = '#94a3b8';
    ctx.fillRect(cx - 86, cy - 128, 172, 12);
    ctx.strokeRect(cx - 86, cy - 128, 172, 12);

    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(cx - 86, cy - 142, 18, 14);
    ctx.fillRect(cx - 52, cy - 142, 22, 14);
    ctx.fillRect(cx - 14, cy - 150, 28, 22);
    ctx.fillRect(cx + 30, cy - 142, 22, 14);
    ctx.fillRect(cx + 68, cy - 142, 18, 14);
    ctx.strokeRect(cx - 14, cy - 150, 28, 22);

    ctx.fillStyle = '#3b82f6';
    ctx.beginPath();
    ctx.moveTo(cx - 9, cy - 146); ctx.lineTo(cx + 9, cy - 146); ctx.lineTo(cx + 9, cy - 134);
    ctx.lineTo(cx, cy - 126); ctx.lineTo(cx - 9, cy - 134);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(cx - 1, cy - 142, 2, 10);
    ctx.fillRect(cx - 5, cy - 138, 10, 2);

    ctx.fillStyle = '#475569';
    ctx.fillRect(cx - 2, cy - 118, 4, 118);

    const ch1X = cx - 74;
    const ch1W = 66;
    ctx.fillStyle = '#e0f2fe';
    ctx.fillRect(ch1X, cy - 90, ch1W, 88);
    ctx.strokeStyle = '#0284c7';
    ctx.lineWidth = 2;
    ctx.strokeRect(ch1X, cy - 90, ch1W, 88);

    ctx.fillStyle = '#0284c7';
    ctx.fillRect(ch1X + 4, cy - 86, ch1W - 8, 16);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 8px "Geist", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Local SLM', ch1X + ch1W / 2, cy - 75);

    ctx.fillStyle = '#082f49';
    ctx.fillRect(ch1X + 8, cy - 64, ch1W - 16, 58);
    const blink = Math.floor(t * 0.008) % 3;
    ctx.fillStyle = blink === 0 ? '#38bdf8' : '#0369a1';
    ctx.fillRect(ch1X + 12, cy - 58, ch1W - 24, 6);
    ctx.fillStyle = blink === 1 ? '#38bdf8' : '#0369a1';
    ctx.fillRect(ch1X + 12, cy - 48, ch1W - 24, 6);
    ctx.fillStyle = blink === 2 ? '#38bdf8' : '#0369a1';
    ctx.fillRect(ch1X + 12, cy - 38, ch1W - 24, 6);

    drawPixelWorker(ch1X + 22, cy - 4, '#0891b2', '#fde047', false);

    const ch2X = cx + 8;
    const ch2W = 66;
    ctx.fillStyle = '#f3e8ff';
    ctx.fillRect(ch2X, cy - 90, ch2W, 88);
    ctx.strokeStyle = '#7c3aed';
    ctx.lineWidth = 2;
    ctx.strokeRect(ch2X, cy - 90, ch2W, 88);

    ctx.fillStyle = '#7c3aed';
    ctx.fillRect(ch2X + 4, cy - 86, ch2W - 8, 16);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 8px "Geist", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Cloud Fortress', ch2X + ch2W / 2, cy - 75);

    ctx.fillStyle = '#2e1065';
    ctx.fillRect(ch2X + 8, cy - 64, ch2W - 16, 58);
    const cloudP = Math.floor(t * 0.006) % 3;
    ctx.fillStyle = cloudP === 0 ? '#c084fc' : '#6b21a8';
    ctx.fillRect(ch2X + 12, cy - 58, ch2W - 24, 6);
    ctx.fillStyle = cloudP === 1 ? '#c084fc' : '#6b21a8';
    ctx.fillRect(ch2X + 12, cy - 48, ch2W - 24, 6);
    ctx.fillStyle = cloudP === 2 ? '#c084fc' : '#6b21a8';
    ctx.fillRect(ch2X + 12, cy - 38, ch2W - 24, 6);

    const satX = ch2X + ch2W / 2;
    const satY = cy - 130;
    ctx.fillStyle = '#475569';
    ctx.fillRect(satX - 2, satY - 14, 4, 16);
    ctx.strokeStyle = '#a855f7';
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.arc(satX, satY - 18, 12, Math.PI * 1.1, Math.PI * 1.9);
    ctx.stroke();

    const radT = (t * 0.004) % 1;
    ctx.strokeStyle = `rgba(168, 85, 247, ${1 - radT})`;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.arc(satX, satY - 26, 6 + radT * 18, Math.PI * 1.2, Math.PI * 1.8);
    ctx.stroke();

    drawPixelWorker(ch2X + 44, cy - 4, '#7c3aed', '#fde047', false);

    drawFacilityBadge(cx, cy + 18, 'Model Fortress', 'Local SLM / Cloud Fortress', '#6366f1');
  }

  function drawFacilityBadge(x, y, title, subtitle, color) {
    ctx.save();

    // Size the pill to fit BOTH the title and the (usually longer) subtitle,
    // otherwise the subtitle spills outside the rounded rectangle.
    ctx.font = 'bold 9px "Geist", "Inter", sans-serif';
    const titleW = ctx.measureText(title).width;
    ctx.font = '7.5px "JetBrains Mono", monospace';
    const subtitleW = ctx.measureText(subtitle).width;
    const boxW = Math.max(titleW, subtitleW) + 30;
    const boxH = 25;
    // Keep the whole pill inside the viewport.
    const boxX = Math.min(Math.max(x - boxW / 2, 8), V_WIDTH - boxW - 8);

    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(boxX, y, boxW, boxH, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(boxX + 10, y + 12, 3.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.textAlign = 'left';
    ctx.font = 'bold 9px "Geist", "Inter", sans-serif';
    ctx.fillStyle = '#0f172a';
    ctx.fillText(title, boxX + 18, y + 11);

    ctx.font = '7.5px "JetBrains Mono", monospace';
    ctx.fillStyle = '#64748b';
    ctx.fillText(subtitle, boxX + 18, y + 20);
    ctx.restore();
  }

  function drawSpeechBubble(x, y, text, color, tailOffset = 0) {
    ctx.save();
    ctx.font = 'bold 8px "Geist", "Inter", sans-serif';
    const txtW = ctx.measureText(text).width;
    const bW = txtW + 16;
    const bH = 19;
    const bx = x;
    const by = y;

    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1.5;

    ctx.beginPath();
    ctx.roundRect(bx - bW / 2, by - bH, bW, bH, 5);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.moveTo(bx + tailOffset - 4, by);
    ctx.lineTo(bx + tailOffset + 4, by);
    ctx.lineTo(bx + tailOffset, by + 5);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#cbd5e1';
    ctx.beginPath();
    ctx.moveTo(bx + tailOffset - 4, by);
    ctx.lineTo(bx + tailOffset, by + 5);
    ctx.lineTo(bx + tailOffset + 4, by);
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.fillText(text, bx, by - 7);
    ctx.restore();
  }

  function drawPixelWorker(x, y, uniformColor, skinColor, withLaptop = false) {
    ctx.fillStyle = skinColor;
    ctx.fillRect(x - 3, y - 18, 6, 6);
    ctx.fillStyle = uniformColor;
    ctx.fillRect(x - 4, y - 20, 8, 3);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(x + 1, y - 16, 2, 2);
    ctx.fillStyle = uniformColor;
    ctx.fillRect(x - 4, y - 12, 8, 10);
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(x - 3, y - 2, 2, 3);
    ctx.fillRect(x + 1, y - 2, 2, 3);

    if (withLaptop) {
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(x + 2, y - 11, 7, 2);
      ctx.fillStyle = '#38bdf8';
      ctx.fillRect(x + 7, y - 16, 2, 6);
    }
  }

  function drawCourierSprite(c) {
    const cx = c.x;
    const cy = c.y;
    const bob = Math.floor(c.frame) % 2 === 0 ? 0 : -2;

    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.18)';
    ctx.beginPath();
    ctx.ellipse(cx, cy + 3, 9, 3.5, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.translate(cx, cy);
    if (c.facing < 0) ctx.scale(-1, 1);

    ctx.fillStyle = '#0f172a';
    if (c.frame === 0) {
      ctx.fillRect(-3, -3, 2, 3);
      ctx.fillRect(2, -3, 2, 3);
    } else if (c.frame < 2) {
      ctx.fillRect(-5, -4, 2, 4);
      ctx.fillRect(3, -2, 2, 2);
    } else {
      ctx.fillRect(-2, -2, 2, 2);
      ctx.fillRect(4, -4, 2, 4);
    }

    ctx.fillStyle = '#2563eb';
    ctx.fillRect(-4, -14 + bob, 8, 11);
    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(-4, -6 + bob, 8, 2);

    ctx.fillStyle = '#fed7aa';
    ctx.fillRect(-3, -20 + bob, 6, 6);
    ctx.fillStyle = '#1e40af';
    ctx.fillRect(-4, -22 + bob, 8, 3);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(1, -18 + bob, 2, 2);

    if (c.carrying) {
      let boxColor = '#fbbf24';
      let boxBorder = '#d97706';
      if (c.carrying === 'RESPONSE_CACHE') { boxColor = '#10b981'; boxBorder = '#047857'; }
      else if (c.carrying === 'RESPONSE_SLM') { boxColor = '#06b6d4'; boxBorder = '#0891b2'; }
      else if (c.carrying === 'RESPONSE_CLOUD') { boxColor = '#a855f7'; boxBorder = '#7e22ce'; }

      ctx.fillStyle = boxColor;
      ctx.strokeStyle = boxBorder;
      ctx.lineWidth = 1;
      ctx.fillRect(4, -13 + bob, 8, 8);
      ctx.strokeRect(4, -13 + bob, 8, 8);

      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.fillRect(6, -11 + bob, 3, 3);
    }
    ctx.restore();

    if (c.bubble && c.bubbleTimer > 0) {
      drawSpeechBubble(c.x, c.y - 30, c.bubble, c.bubbleColor, 0);
    }
  }

  function drawCacheMissTag() {
    if (sim.phase !== 'AT_VAULT_MISS') return;
    const mx = 500;
    const my = PATH_Y - 45;
    ctx.save();
    ctx.fillStyle = '#fffbeb';
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(mx - 32, my - 10, 64, 20, 10);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#d97706';
    ctx.font = 'bold 8px "Geist", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Cache miss', mx, my + 3);

    ctx.fillStyle = '#f59e0b';
    ctx.beginPath();
    ctx.moveTo(mx - 4, my + 10);
    ctx.lineTo(mx + 4, my + 10);
    ctx.lineTo(mx, my + 15);
    ctx.fill();
    ctx.restore();
  }

  function updateAndDrawParticles() {
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.life -= p.decay;

      if (p.life <= 0) {
        particles.splice(i, 1);
        continue;
      }

      ctx.save();
      ctx.globalAlpha = p.life;
      ctx.fillStyle = p.color;
      ctx.fillRect(p.x, p.y, p.size, p.size);
      ctx.restore();
    }
  }

  /* ------------------------- flow state machine ------------------------- */

  function beginFlow() {
    sim.flowActive = true;
    sim.phase = 'DISPATCH_TO_VAULT';
    sim.timer = 0;
    sim.routeDestination = null;
    sim.cacheSimilarity = null;

    courier.x = TOWER_X;
    courier.targetX = VAULT_X;
    courier.facing = 1;
    courier.carrying = 'REQUEST';
    setCourierBubble('New request received', '#2563EB', 140);

    courier2.x = 580;
    courier2.targetX = 750;
    courier2.carrying = null;
    courier2.bubble = '';
    courier2.bubbleTimer = 0;

    status('Request dispatched: Warden Tower orchestrating…');
  }

  function handleSignal(packet) {
    if (!packet || !packet.event) return;
    const meta = packet.metadata || {};

    switch (packet.event) {
      case 'CACHE_HIT': {
        sim.cacheSimilarity = meta.similarity ?? null;
        if (sim.flowActive && (sim.phase === 'AT_VAULT' || sim.phase === 'DISPATCH_TO_VAULT')) {
          sim.phase = 'AT_VAULT_HIT';
          sim.timer = 60;
          setCourierBubble(
            sim.cacheSimilarity != null
              ? `Cache hit · ${(sim.cacheSimilarity * 100).toFixed(0)}% match`
              : 'Cache hit!',
            '#059669', 90
          );
          spawnBurst(420, 230, '#10b981', 30, 3.5);
          status('Semantic cache match: vector memory hit.');
        }
        break;
      }
      case 'CACHE_MISS': {
        if (sim.flowActive && (sim.phase === 'AT_VAULT' || sim.phase === 'DISPATCH_TO_VAULT')) {
          sim.phase = 'AT_VAULT_MISS';
          sim.timer = 45;
          setCourierBubble('Cache miss', '#d97706', 75);
          spawnBurst(420, 230, '#f59e0b', 18, 2.2);
          status('Cache miss: SmartRouter evaluating complexity heuristics…');
        }
        break;
      }
      case 'ROUTING_SIGNAL': {
        sim.routeDestination = packet.destination;
        if (sim.flowActive) {
          const reason = meta.reason ? `: ${meta.reason}` : '';
          status(`Routing decision${reason}`);
          if (sim.phase === 'AT_VAULT_MISS') {
            // Miss timer may still be counting; aim the courier now so it moves immediately.
            dispatchToFortress(packet.destination);
          }
        }
        break;
      }
      case 'MODEL_EXECUTION': {
        sim.routeDestination = packet.destination || sim.routeDestination;
        if (sim.flowActive) {
          dispatchToFortress(sim.routeDestination);
          status(`Executing on ${packet.destination}…`);
        }
        break;
      }
      case 'EVALUATION': {
        if (sim.flowActive) {
          const verdict = meta.passed == null ? '' : meta.passed ? ' · answer verified' : ' · no model answered';
          status(`Evaluating response${verdict}…`);
        }
        break;
      }
      case 'COMPLETION': {
        if (sim.flowActive) {
          const isCloud = sim.routeDestination === 'cloud_fortress';
          startReturn(isCloud ? 'RESPONSE_CLOUD' : 'RESPONSE_SLM');
          status('Response synthesized: returning to client.');
        }
        break;
      }
      case 'ERROR': {
        if (sim.flowActive) {
          startReturn(null);
          status(`Gateway error${meta.error ? `: ${meta.error}` : ''}`);
        }
        break;
      }
      default:
        break;
    }
  }

  function dispatchToFortress(destination) {
    if (sim.phase === 'TO_FORTRESS_LOCAL' || sim.phase === 'TO_FORTRESS_CLOUD') return;
    if (destination === 'cloud_fortress') {
      sim.phase = 'TO_FORTRESS_CLOUD';
      courier.targetX = FORTRESS_CLOUD_X;
      setCourierBubble('Routing to Cloud Fortress...', '#7c3aed', 110);
      courier2.carrying = 'REQUEST';
      courier2.targetX = FORTRESS_CLOUD_X - 60;
    } else {
      sim.phase = 'TO_FORTRESS_LOCAL';
      courier.targetX = FORTRESS_LOCAL_X;
      setCourierBubble('Routing to Local SLM...', '#0284c7', 90);
    }
  }

  function startReturn(carrying) {
    sim.phase = 'RETURNING';
    courier.carrying = carrying;
    courier.targetX = TOWER_X;
    setCourierBubble(
      carrying === 'RESPONSE_CACHE' ? 'Cached response ready!' :
      carrying === 'RESPONSE_CLOUD' ? 'Cloud response ready!' :
      carrying ? 'Response ready!' : 'Request failed: returning',
      carrying ? '#059669' : '#dc2626', 80
    );
    if (carrying) {
      const bx = sim.routeDestination === 'cloud_fortress' ? FORTRESS_CLOUD_X : FORTRESS_LOCAL_X;
      spawnBurst(bx, 250, sim.routeDestination === 'cloud_fortress' ? '#a855f7' : '#06b6d4', 24, 3.2);
    }
  }

  /** Fallback authority: the POST response replays anything the WS stream missed. */
  function onResponse(data) {
    if (!data) return;
    if (data.cache_hit) {
      sim.cacheSimilarity = sim.cacheSimilarity ?? null;
      if (sim.flowActive && sim.phase !== 'RETURNING' && sim.phase !== 'DONE') {
        sim.phase = 'AT_VAULT_HIT';
        sim.timer = Math.min(sim.timer, 30);
        setCourierBubble('Cache hit!', '#059669', 80);
        spawnBurst(420, 230, '#10b981', 24, 3);
      }
      return;
    }
    if (!sim.flowActive) return;
    if (sim.phase === 'RETURNING' || sim.phase === 'DONE') return;
    const isCloud = data.destination === 'cloud_fortress';
    sim.routeDestination = data.destination || sim.routeDestination;
    startReturn(isCloud ? 'RESPONSE_CLOUD' : 'RESPONSE_SLM');
  }

  function resetToIdle() {
    sim.flowActive = false;
    sim.phase = 'IDLE';
    sim.timer = 0;
    sim.routeDestination = null;
    sim.cacheSimilarity = null;
    courier.x = TOWER_X;
    courier.targetX = TOWER_X;
    courier.carrying = null;
    courier.bubble = '';
    courier.bubbleTimer = 0;
    courier2.x = 580;
    courier2.targetX = 750;
    courier2.carrying = null;
    courier2.bubble = '';
    courier2.bubbleTimer = 0;
    status('Gateway idle: vector cache ready.');
  }

  /* ------------------------------ update ------------------------------ */

  function updateSimulation() {
    const dx = courier.targetX - courier.x;
    if (Math.abs(dx) > courier.speed) {
      courier.x += Math.sign(dx) * courier.speed;
      courier.facing = Math.sign(dx);
      courier.frame = (courier.frame + 0.25) % 4;
    } else {
      courier.x = courier.targetX;
      courier.frame = 0;
    }
    if (courier.bubbleTimer > 0) courier.bubbleTimer--;

    const dx2 = courier2.targetX - courier2.x;
    if (Math.abs(dx2) > courier2.speed) {
      courier2.x += Math.sign(dx2) * courier2.speed;
      courier2.facing = Math.sign(dx2);
      courier2.frame = (courier2.frame + 0.2) % 4;
    } else {
      courier2.x = courier2.targetX;
      courier2.frame = 0;
      if (courier2.targetX >= 740 && courier2.targetX < 800) {
        courier2.targetX = 580;
        courier2.facing = -1;
      } else if (courier2.targetX <= 580) {
        courier2.targetX = 750;
        courier2.facing = 1;
      } else if (sim.flowActive && sim.routeDestination === 'cloud_fortress') {
        // hold position near the cloud bay
      } else {
        courier2.targetX = 580;
        courier2.facing = -1;
      }
    }
    if (courier2.bubbleTimer > 0) courier2.bubbleTimer--;

    switch (sim.phase) {
      case 'DISPATCH_TO_VAULT': {
        if (Math.abs(courier.x - VAULT_X) < 4) {
          courier.x = VAULT_X;
          sim.phase = 'AT_VAULT';
          setCourierBubble('Checking for cached memory...', '#0284c7', 160);
          status('Probing semantic cache (Ollama embeddings + vector index)…');
        }
        break;
      }
      case 'AT_VAULT_HIT': {
        sim.timer--;
        if (sim.timer <= 0) {
          startReturn('RESPONSE_CACHE');
        }
        break;
      }
      case 'AT_VAULT_MISS': {
        sim.timer--;
        if (sim.timer <= 0 && sim.routeDestination) {
          dispatchToFortress(sim.routeDestination);
        }
        break;
      }
      case 'TO_FORTRESS_LOCAL': {
        if (Math.abs(courier.x - FORTRESS_LOCAL_X) < 4) {
          courier.x = FORTRESS_LOCAL_X;
          sim.phase = 'COMPUTING_LOCAL';
          setCourierBubble('Model is working...', '#0284c7', 400);
          status('Local Ollama inference in progress…');
        }
        break;
      }
      case 'TO_FORTRESS_CLOUD': {
        if (Math.abs(courier.x - FORTRESS_CLOUD_X) < 4) {
          courier.x = FORTRESS_CLOUD_X;
          sim.phase = 'COMPUTING_CLOUD';
          setCourierBubble('Cloud streaming...', '#7c3aed', 400);
          status('Cloud provider inference in progress…');
        }
        break;
      }
      case 'COMPUTING_LOCAL': {
        if (Math.random() > 0.4) spawnBurst(FORTRESS_LOCAL_X, 260, '#06b6d4', 2, 1.8);
        break;
      }
      case 'COMPUTING_CLOUD': {
        if (Math.random() > 0.4) spawnBurst(FORTRESS_CLOUD_X, 240, '#a855f7', 3, 2.5);
        break;
      }
      case 'RETURNING': {
        if (Math.abs(courier.x - TOWER_X) < 4) {
          courier.x = TOWER_X;
          sim.phase = 'DONE';
          sim.flowActive = false;
          courier.carrying = null;
          setCourierBubble('Delivered to client', '#10b981', 120);
          spawnBurst(TOWER_X + 20, 280, '#2563eb', 20, 2.5);
          status('Cycle complete: gateway idle.');
        }
        break;
      }
      default:
        break;
    }
  }

  /* ------------------------------ render ------------------------------ */

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width || canvas.parentElement.clientWidth || 960;
    const h = rect.height || canvas.parentElement.clientHeight || 420;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    if (ctx) ctx.imageSmoothingEnabled = false;
  }

  let frameCount = 0;
  let lastFpsUpdate = performance.now();
  let rafId = null;
  let disposed = false;

  function render(time) {
    if (disposed) return;
    frameCount++;
    if (time - lastFpsUpdate >= 1000) {
      if (onFps) onFps(frameCount);
      frameCount = 0;
      lastFpsUpdate = time;
    }

    if (canvas.width === 0 || canvas.height === 0) {
      resizeCanvas();
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    // Uniform scale + centre so the world keeps its 1000x440 aspect ratio
    // instead of being stretched to the container.
    const scale = Math.min(canvas.width / V_WIDTH, canvas.height / V_HEIGHT);
    ctx.translate((canvas.width - V_WIDTH * scale) / 2, (canvas.height - V_HEIGHT * scale) / 2);
    ctx.scale(scale, scale);

    updateSimulation();

    drawSkyAndEnvironment(time);
    drawWardenTower(time);
    drawMemoryVault(time);
    drawModelFortress(time);
    drawCacheMissTag();
    drawCourierSprite(courier);
    drawCourierSprite(courier2);
    updateAndDrawParticles();

    ctx.restore();
    rafId = requestAnimationFrame(render);
  }

  function onResize() {
    resizeCanvas();
  }

  resizeCanvas();
  window.addEventListener('resize', onResize);
  rafId = requestAnimationFrame(render);
  status('Gateway idle: vector cache ready.');

  return {
    beginFlow,
    handleSignal,
    onResponse,
    resetToIdle,
    dispose() {
      disposed = true;
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
    },
  };
}
