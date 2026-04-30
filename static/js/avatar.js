/**
 * avatar.js – Animated SVG therapist avatar with lip-sync, emotion expressions,
 *             and a full state machine.
 *
 * Public API:
 *   initAvatar(containerId)         → attach avatar to a container div
 *   setEmotion(label)               → transition to an emotion expression
 *   setState(stateName)             → switch state machine state
 *   startSpeaking(audioElement)     → begin lip-sync on an <audio> element
 *   stopSpeaking()                  → end lip-sync
 *
 * States:  idle | listening | thinking | speaking | empathy
 * Emotions: joy | sadness | anxiety | anger | neutral
 */

/* ========================================================================
   STYLES (injected into <head> once)
   ======================================================================== */
const AVATAR_STYLES = `
/* ---------- Container ---------- */
.avatar-container {
  position: relative;
  width: 100%;
  max-width: 280px;
  aspect-ratio: 1 / 1;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  -webkit-user-select: none;
}
.avatar-container svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

/* ---------- Base transitions ---------- */
.avatar-face,
.avatar-eyebrow,
.avatar-eye,
.avatar-pupil,
.avatar-mouth,
.avatar-blush,
.avatar-head {
  transition: all 0.30s cubic-bezier(.4, 0, .2, 1);
}

/* ---------- Idle breathing ---------- */
@keyframes avatar-breathe {
  0%, 100% { transform: translateY(0px); }
  50%      { transform: translateY(2px); }
}

/* ---------- Blink ---------- */
@keyframes avatar-blink {
  0%, 42%, 44%, 100% { transform: scaleY(1); }
  43%                { transform: scaleY(0.05); }
}

/* ---------- Idle eye float ---------- */
@keyframes avatar-eye-float {
  0%, 100% { transform: translateX(0px); }
  30%      { transform: translateX(1.5px); }
  70%      { transform: translateX(-1px); }
}

/* ---------- Thinking eye movement ---------- */
@keyframes avatar-thinking-eyes {
  0%, 100% { transform: translateX(0px); }
  25%      { transform: translateX(3px) translateY(-1px); }
  50%      { transform: translateX(-2px) translateY(1px); }
  75%      { transform: translateX(2px); }
}

/* ---------- Listening head tilt ---------- */
@keyframes avatar-listening-tilt {
  0%, 100% { transform: rotate(0deg) translateY(0px); }
  50%      { transform: rotate(3deg) translateY(1px); }
}

/* ---------- Empathy slow nod ---------- */
@keyframes avatar-empathy-nod {
  0%, 100% { transform: translateY(0px); }
  30%      { transform: translateY(3px); }
  60%      { transform: translateY(1px); }
}

/* ---------- Joy sparkle ---------- */
@keyframes avatar-joy-glow {
  0%, 100% { filter: brightness(1); }
  50%      { filter: brightness(1.08); }
}

/* ---------- Lip sync ---------- */
@keyframes avatar-mouth-speak {
  0%   { transform: scaleY(1); }
  50%  { transform: scaleY(1.5); }
  100% { transform: scaleY(1); }
}

/* ---------- Sadness gentle droop ---------- */
@keyframes avatar-sadness-droop {
  0%, 100% { transform: translateY(0px); }
  50%      { transform: translateY(1.5px); }
}

/* ---------- Responsive ---------- */
@media (max-width: 480px) {
  .avatar-container { max-width: 180px; }
}
@media (min-width: 481px) and (max-width: 768px) {
  .avatar-container { max-width: 220px; }
}
`;

/* ========================================================================
   SVG TEMPLATE
   ======================================================================== */
const AVATAR_SVG = `
<svg viewBox="0 0 200 220" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="Therapist avatar">

  <!-- Head group (for tilt / nod animations) -->
  <g class="avatar-head" id="avatar-head">

    <!-- Hair back -->
    <ellipse cx="100" cy="80" rx="78" ry="82"
             fill="#3E2723" class="avatar-hair-back"/>

    <!-- Face -->
    <ellipse cx="100" cy="100" rx="68" ry="74"
             fill="#F5D0A9" class="avatar-face" id="avatar-face"/>

    <!-- Hair front -->
    <path d="M32,72 Q40,28 100,22 Q160,28 168,72 Q160,50 100,46 Q40,50 32,72Z"
          fill="#4E342E" class="avatar-hair-front"/>

    <!-- Blush (left) -->
    <ellipse cx="60" cy="118" rx="14" ry="7"
             fill="#F8BBD0" opacity="0.35" class="avatar-blush" id="avatar-blush-l"/>

    <!-- Blush (right) -->
    <ellipse cx="140" cy="118" rx="14" ry="7"
             fill="#F8BBD0" opacity="0.35" class="avatar-blush" id="avatar-blush-r"/>

    <!-- Left eyebrow -->
    <path d="M58,76 Q72,68 86,76"
          stroke="#5D4037" stroke-width="2.5" fill="none"
          stroke-linecap="round"
          class="avatar-eyebrow" id="avatar-brow-l"/>

    <!-- Right eyebrow -->
    <path d="M114,76 Q128,68 142,76"
          stroke="#5D4037" stroke-width="2.5" fill="none"
          stroke-linecap="round"
          class="avatar-eyebrow" id="avatar-brow-r"/>

    <!-- Left eye group -->
    <g class="avatar-eye" id="avatar-eye-l"
       style="transform-origin: 72px 92px;">
      <ellipse cx="72" cy="92" rx="14" ry="14"
               fill="#FFFFFF" stroke="#8D6E63" stroke-width="1"/>
      <circle cx="72" cy="92" r="7"
              fill="#4E342E" class="avatar-pupil" id="avatar-pupil-l"/>
      <circle cx="68" cy="88" r="2.5"
              fill="#FFFFFF" opacity="0.8"/>
    </g>

    <!-- Right eye group -->
    <g class="avatar-eye" id="avatar-eye-r"
       style="transform-origin: 128px 92px;">
      <ellipse cx="128" cy="92" rx="14" ry="14"
               fill="#FFFFFF" stroke="#8D6E63" stroke-width="1"/>
      <circle cx="128" cy="92" r="7"
              fill="#4E342E" class="avatar-pupil" id="avatar-pupil-r"/>
      <circle cx="124" cy="88" r="2.5"
              fill="#FFFFFF" opacity="0.8"/>
    </g>

    <!-- Nose -->
    <path d="M97,108 Q100,116 103,108"
          stroke="#D7A98C" stroke-width="1.5" fill="none"
          stroke-linecap="round"/>

    <!-- Mouth -->
    <path d="M80,132 Q100,142 120,132"
          stroke="#C0705A" stroke-width="2.8" fill="none"
          stroke-linecap="round"
          class="avatar-mouth" id="avatar-mouth"/>

    <!-- Neck / body hint -->
    <rect x="86" y="168" width="28" height="30" rx="6"
          fill="#F5D0A9" opacity="0.9"/>
    <rect x="70" y="190" width="60" height="30" rx="10"
          fill="#7986CB"/>

  </g>
</svg>
`;


/* ========================================================================
   STATE MACHINE & EMOTION ENGINE
   ======================================================================== */

/** @type {string} */
let _currentState = 'idle';

/** @type {string} */
let _currentEmotion = 'neutral';

/** @type {number|null} */
let _blinkInterval = null;

/** @type {number|null} */
let _breatheRAF = null;

/** @type {AudioContext|null} */
let _audioCtx = null;

/** @type {AnalyserNode|null} */
let _analyser = null;

/** @type {MediaElementAudioSourceNode|null} */
let _audioSource = null;

/** @type {number|null} */
let _lipSyncRAF = null;

/** @type {HTMLElement|null} */
let _container = null;

/** Valid states */
const STATES = ['idle', 'listening', 'thinking', 'speaking', 'empathy'];

/** Valid emotions */
const EMOTIONS = ['joy', 'sadness', 'anxiety', 'anger', 'neutral'];


/* ========================================================================
   INIT
   ======================================================================== */

/**
 * Initialise the avatar and attach it to a container div.
 * @param {string} containerId - The id of the container element.
 */
function initAvatar(containerId) {
    const el = document.getElementById(containerId);
    if (!el) {
        console.error(`[avatar] Container '#${containerId}' not found.`);
        return;
    }
    _container = el;

    // Inject styles once
    if (!document.getElementById('avatar-styles')) {
        const style = document.createElement('style');
        style.id = 'avatar-styles';
        style.textContent = AVATAR_STYLES;
        document.head.appendChild(style);
    }

    // Inject SVG
    el.classList.add('avatar-container');
    el.innerHTML = AVATAR_SVG;

    // Start idle loop
    _startIdleAnimations();
    setState('idle');
    setEmotion('neutral');

    console.log('[avatar] Initialised in #' + containerId);
}


/* ========================================================================
   EMOTION EXPRESSIONS
   ======================================================================== */

/**
 * Transition the avatar face to an emotion expression.
 * @param {string} label - One of: joy, sadness, anxiety, anger, neutral.
 */
function setEmotion(label) {
    if (!EMOTIONS.includes(label)) {
        console.warn(`[avatar] Unknown emotion "${label}". Defaulting to neutral.`);
        label = 'neutral';
    }
    _currentEmotion = label;

    const mouth = document.getElementById('avatar-mouth');
    const browL = document.getElementById('avatar-brow-l');
    const browR = document.getElementById('avatar-brow-r');
    const eyeL = document.getElementById('avatar-eye-l');
    const eyeR = document.getElementById('avatar-eye-r');
    const blushL = document.getElementById('avatar-blush-l');
    const blushR = document.getElementById('avatar-blush-r');
    const face = document.getElementById('avatar-face');
    const head = document.getElementById('avatar-head');

    if (!mouth) return;

    // Reset
    _resetExpression(mouth, browL, browR, eyeL, eyeR, blushL, blushR, face, head);

    switch (label) {

        case 'joy':
            // Wide smile
            mouth.setAttribute('d', 'M76,130 Q100,150 124,130');
            mouth.setAttribute('stroke', '#E57373');
            mouth.setAttribute('stroke-width', '3');
            // Raised brows
            browL.setAttribute('d', 'M58,73 Q72,64 86,73');
            browR.setAttribute('d', 'M114,73 Q128,64 142,73');
            // Bright blush
            blushL.setAttribute('opacity', '0.55');
            blushR.setAttribute('opacity', '0.55');
            // Sparkle
            head.style.animation = 'avatar-joy-glow 2s ease-in-out infinite';
            break;

        case 'sadness':
            // Down-turned mouth
            mouth.setAttribute('d', 'M82,138 Q100,130 118,138');
            mouth.setAttribute('stroke', '#A1887F');
            mouth.setAttribute('stroke-width', '2.5');
            // Soft droopy brows
            browL.setAttribute('d', 'M58,74 Q72,72 86,78');
            browR.setAttribute('d', 'M114,78 Q128,72 142,74');
            // Dimmer face
            face.style.fill = '#ECC9A0';
            // Gentle droop
            head.style.animation = 'avatar-sadness-droop 4s ease-in-out infinite';
            // Reduced blush
            blushL.setAttribute('opacity', '0.15');
            blushR.setAttribute('opacity', '0.15');
            break;

        case 'anxiety':
            // Slightly open mouth
            mouth.setAttribute('d', 'M84,134 Q100,138 116,134');
            mouth.setAttribute('stroke-width', '2.2');
            // Widened eyes
            eyeL.querySelector('ellipse').setAttribute('ry', '16');
            eyeR.querySelector('ellipse').setAttribute('ry', '16');
            // Raised inner brows
            browL.setAttribute('d', 'M58,78 Q72,66 86,74');
            browR.setAttribute('d', 'M114,74 Q128,66 142,78');
            // Slight nod
            head.style.animation = 'avatar-empathy-nod 3s ease-in-out infinite';
            break;

        case 'anger':
            // Mouth – firm line
            mouth.setAttribute('d', 'M82,134 Q100,134 118,134');
            mouth.setAttribute('stroke', '#A1887F');
            mouth.setAttribute('stroke-width', '3');
            // Furrowed brows (V shape)
            browL.setAttribute('d', 'M58,80 Q72,72 86,74');
            browR.setAttribute('d', 'M114,74 Q128,72 142,80');
            browL.setAttribute('stroke-width', '3');
            browR.setAttribute('stroke-width', '3');
            // Slightly narrowed eyes
            eyeL.querySelector('ellipse').setAttribute('ry', '12');
            eyeR.querySelector('ellipse').setAttribute('ry', '12');
            break;

        case 'neutral':
        default:
            // Already reset
            break;
    }
}


/**
 * Reset all facial features to the neutral base.
 * @private
 */
function _resetExpression(mouth, browL, browR, eyeL, eyeR, blushL, blushR, face, head) {
    mouth.setAttribute('d', 'M80,132 Q100,142 120,132');
    mouth.setAttribute('stroke', '#C0705A');
    mouth.setAttribute('stroke-width', '2.8');

    browL.setAttribute('d', 'M58,76 Q72,68 86,76');
    browR.setAttribute('d', 'M114,76 Q128,68 142,76');
    browL.setAttribute('stroke-width', '2.5');
    browR.setAttribute('stroke-width', '2.5');

    eyeL.querySelector('ellipse').setAttribute('ry', '14');
    eyeR.querySelector('ellipse').setAttribute('ry', '14');

    blushL.setAttribute('opacity', '0.35');
    blushR.setAttribute('opacity', '0.35');

    face.style.fill = '#F5D0A9';
    head.style.animation = '';
}


/* ========================================================================
   STATE MACHINE
   ======================================================================== */

/**
 * Switch the avatar to a named state.
 * @param {string} stateName - One of: idle, listening, thinking, speaking, empathy.
 */
function setState(stateName) {
    if (!STATES.includes(stateName)) {
        console.warn(`[avatar] Unknown state "${stateName}". Defaulting to idle.`);
        stateName = 'idle';
    }

    const prev = _currentState;
    _currentState = stateName;

    const head = document.getElementById('avatar-head');
    const eyeL = document.getElementById('avatar-eye-l');
    const eyeR = document.getElementById('avatar-eye-r');
    const pupilL = document.getElementById('avatar-pupil-l');
    const pupilR = document.getElementById('avatar-pupil-r');

    if (!head) return;

    // Clear state-specific animations (keep emotion animations)
    _clearStateAnimations(head, eyeL, eyeR, pupilL, pupilR);

    switch (stateName) {

        case 'idle':
            _startIdleAnimations();
            break;

        case 'listening':
            head.style.animation = 'avatar-listening-tilt 4s ease-in-out infinite';
            // Pupils look slightly toward the user (left)
            pupilL.setAttribute('cx', '70');
            pupilR.setAttribute('cx', '126');
            break;

        case 'thinking':
            pupilL.style.animation = 'avatar-thinking-eyes 3s ease-in-out infinite';
            pupilR.style.animation = 'avatar-thinking-eyes 3s ease-in-out infinite';
            break;

        case 'speaking':
            // Lip-sync managed by startSpeaking() / _lipSyncLoop()
            break;

        case 'empathy':
            head.style.animation = 'avatar-empathy-nod 4s ease-in-out infinite';
            // Soft gaze
            pupilL.setAttribute('cx', '71');
            pupilR.setAttribute('cx', '127');
            break;
    }

    console.log(`[avatar] State: ${prev} → ${stateName}`);
}


/**
 * Remove state-level animations so a new state starts clean.
 * @private
 */
function _clearStateAnimations(head, eyeL, eyeR, pupilL, pupilR) {
    // Don't wipe emotion animation on head (we re-apply in setEmotion)
    if (_currentEmotion === 'neutral') {
        head.style.animation = '';
    }
    pupilL.style.animation = '';
    pupilR.style.animation = '';
    // Reset pupil positions
    pupilL.setAttribute('cx', '72');
    pupilR.setAttribute('cx', '128');
}


/* ========================================================================
   IDLE ANIMATIONS (blink + breathing)
   ======================================================================== */

/** Start the idle loop: periodic blinking + subtle breathing. @private */
function _startIdleAnimations() {
    _startBlinking();
    _startBreathing();
}

/** Periodic random blink. @private */
function _startBlinking() {
    if (_blinkInterval) clearInterval(_blinkInterval);

    const blink = () => {
        const eyeL = document.getElementById('avatar-eye-l');
        const eyeR = document.getElementById('avatar-eye-r');
        if (!eyeL || !eyeR) return;

        // Quick scale to 0 and back
        eyeL.style.transition = 'transform 0.08s ease-in';
        eyeR.style.transition = 'transform 0.08s ease-in';
        eyeL.style.transform = 'scaleY(0.05)';
        eyeR.style.transform = 'scaleY(0.05)';

        setTimeout(() => {
            eyeL.style.transition = 'transform 0.10s ease-out';
            eyeR.style.transition = 'transform 0.10s ease-out';
            eyeL.style.transform = 'scaleY(1)';
            eyeR.style.transform = 'scaleY(1)';
        }, 90);
    };

    // Blink every 2.5–5.5 s (randomised to feel natural)
    const scheduleNext = () => {
        const delay = 2500 + Math.random() * 3000;
        _blinkInterval = setTimeout(() => {
            blink();
            scheduleNext();
        }, delay);
    };
    scheduleNext();
}

/** Subtle breathing (vertical float). @private */
function _startBreathing() {
    const head = document.getElementById('avatar-head');
    if (!head) return;

    // Only apply breathing if no other head animation is active
    if (!head.style.animation || head.style.animation === '') {
        head.style.animation = 'avatar-breathe 4s ease-in-out infinite';
    }
}


/* ========================================================================
   LIP SYNC (Web Audio API)
   ======================================================================== */

/**
 * Begin lip-sync animation tied to an <audio> element.
 * @param {HTMLAudioElement} audioElement - The audio element playing TTS.
 */
function startSpeaking(audioElement) {
    if (!audioElement || !(audioElement instanceof HTMLAudioElement)) {
        console.error('[avatar] startSpeaking requires an HTMLAudioElement.');
        return;
    }

    setState('speaking');

    try {
        // Create audio context on first use
        if (!_audioCtx) {
            _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }

        // Resume if suspended (autoplay policy)
        if (_audioCtx.state === 'suspended') {
            _audioCtx.resume();
        }

        // Create analyser
        _analyser = _audioCtx.createAnalyser();
        _analyser.fftSize = 256;
        _analyser.smoothingTimeConstant = 0.75;

        // Connect source → analyser → destination
        // Only create source once per audio element
        if (!audioElement._avatarSource) {
            _audioSource = _audioCtx.createMediaElementSource(audioElement);
            audioElement._avatarSource = _audioSource;
        } else {
            _audioSource = audioElement._avatarSource;
        }

        _audioSource.connect(_analyser);
        _analyser.connect(_audioCtx.destination);

        // Start the lip-sync render loop
        _lipSyncLoop();

        // Auto-stop when audio ends
        audioElement.addEventListener('ended', stopSpeaking, { once: true });
        audioElement.addEventListener('pause', stopSpeaking, { once: true });

    } catch (err) {
        console.error('[avatar] Web Audio setup failed:', err);
        // Fallback: simple mouth animation via CSS
        _fallbackSpeakingAnimation(true);
    }
}


/**
 * Stop lip-sync and return to idle.
 */
function stopSpeaking() {
    if (_lipSyncRAF) {
        cancelAnimationFrame(_lipSyncRAF);
        _lipSyncRAF = null;
    }

    // Disconnect analyser (keep audio context alive for reuse)
    if (_analyser) {
        try { _analyser.disconnect(); } catch (e) { /* ignore */ }
        _analyser = null;
    }
    if (_audioSource) {
        try { _audioSource.disconnect(); } catch (e) { /* ignore */ }
        // Reconnect source directly to destination so audio still plays
        try { _audioSource.connect(_audioCtx.destination); } catch (e) { /* ignore */ }
    }

    _fallbackSpeakingAnimation(false);

    // Reset mouth
    const mouth = document.getElementById('avatar-mouth');
    if (mouth) {
        // Restore emotion-appropriate mouth
        setEmotion(_currentEmotion);
    }

    setState('idle');
}


/**
 * Render loop: read audio amplitude and animate the mouth.
 * @private
 */
function _lipSyncLoop() {
    if (!_analyser) return;

    const mouth = document.getElementById('avatar-mouth');
    if (!mouth) return;

    const dataArray = new Uint8Array(_analyser.frequencyBinCount);
    _analyser.getByteFrequencyData(dataArray);

    // Compute average amplitude in the vocal range (roughly bins 2–30)
    let sum = 0;
    const start = 2;
    const end = Math.min(30, dataArray.length);
    for (let i = start; i < end; i++) {
        sum += dataArray[i];
    }
    const avg = sum / (end - start);
    const amplitude = Math.min(avg / 180, 1);  // normalise to 0–1

    // Map amplitude to mouth opening
    _animateMouth(mouth, amplitude);

    _lipSyncRAF = requestAnimationFrame(_lipSyncLoop);
}


/**
 * Animate the SVG mouth path based on amplitude (0–1).
 * @private
 * @param {SVGPathElement} mouth
 * @param {number} amplitude – 0 (closed) to 1 (wide open)
 */
function _animateMouth(mouth, amplitude) {
    const openness = Math.min(Math.max(amplitude, 0), 1);

    const baseY = 132;
    const closedCurveY = 142; // default resting curve

    if (openness > 0.08) {
        // Mouth is speaking / open
        // Make the mouth slightly narrower as it opens wider vertically for 'O' sounds
        let w = 40;
        if (openness > 0.4) {
            w = 40 - ((openness - 0.4) * 15);
        }
        const x1 = 100 - (w / 2);
        const x2 = 100 + (w / 2);

        // Top lip curves upwards
        const topY = baseY - (openness * 7);
        // Bottom lip curves downwards
        const bottomY = baseY + 6 + (openness * 18);

        // Create a closed loop with curved upper and lower lips
        const path = `M${x1},${baseY} Q100,${topY} ${x2},${baseY} Q100,${bottomY} ${x1},${baseY}`;

        mouth.setAttribute('d', path);
        mouth.setAttribute('fill', '#8B4513');
        mouth.setAttribute('fill-opacity', String(Math.min(openness * 1.5, 0.85)));
    } else {
        // Resting / nearly closed
        mouth.setAttribute('d', `M80,${baseY} Q100,${closedCurveY} 120,${baseY}`);
        mouth.setAttribute('fill', 'none');
        mouth.setAttribute('fill-opacity', '0');
    }
}


/**
 * Fallback: toggle a simple CSS mouth animation when Web Audio isn't available.
 * @private
 * @param {boolean} start
 */
function _fallbackSpeakingAnimation(start) {
    const mouth = document.getElementById('avatar-mouth');
    if (!mouth) return;

    if (start) {
        mouth.style.animation = 'avatar-mouth-speak 0.35s ease-in-out infinite';
    } else {
        mouth.style.animation = '';
    }
}


/* ========================================================================
   EXPORTS
   ======================================================================== */

// Support both ES modules and plain script tags
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { initAvatar, setEmotion, setState, startSpeaking, stopSpeaking };
}

// Always expose on window for script-tag usage
if (typeof window !== 'undefined') {
    window.initAvatar = initAvatar;
    window.setEmotion = setEmotion;
    window.setState = setState;
    window.startSpeaking = startSpeaking;
    window.stopSpeaking = stopSpeaking;
}
