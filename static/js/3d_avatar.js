/* ========================================================================
   3D AVATAR SCRIPT (Three.js)
   Renders a stylized 3D human avatar that lip-syncs to audio
   ======================================================================== */

let scene, camera, renderer;
let avatarGroup, headGroup, jawGroup, leftEye, rightEye, mouthInner;
let leftBrow, rightBrow;
let audioCtx, analyser, lipSyncRAF;
let avatarCurrentEmotion = 'neutral';
let avatarCurrentState = 'idle';

// Wait for Three.js to load
function waitForThreeJS(callback) {
    if (window.THREE) {
        callback();
    } else {
        setTimeout(() => waitForThreeJS(callback), 100);
    }
}

function initAvatar(containerId) {
    waitForThreeJS(() => _initThreeJS(containerId));
}

function _initThreeJS(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Set explicit size explicitly to match container
    let width = container.clientWidth;
    let height = container.clientHeight;

    // Fallback if container is not styled or visible yet
    if (width === 0 || height === 0) {
        width = 220;
        height = 220;
    }

    container.innerHTML = '';

    // Add simple CSS directly to avoid external stylesheet dependency
    container.style.position = 'relative';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';

    // Create Scene
    scene = new THREE.Scene();

    // Create Camera
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.z = 4.5;
    camera.position.y = 0;

    // Create Renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.7);
    dirLight.position.set(2, 4, 4);
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-2, 0, 2);
    scene.add(fillLight);

    // Avatar Group
    avatarGroup = new THREE.Group();
    scene.add(avatarGroup);

    headGroup = new THREE.Group();
    avatarGroup.add(headGroup);

    // Materials
    const skinMat = new THREE.MeshPhongMaterial({ color: 0xFAD6B1, shininess: 15 });
    const hairMat = new THREE.MeshPhongMaterial({ color: 0x2A1A14, shininess: 10 });
    const eyeWhiteMat = new THREE.MeshPhongMaterial({ color: 0xffffff, shininess: 60 });
    const pupilMat = new THREE.MeshPhongMaterial({ color: 0x332211, shininess: 80 });
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x5C2424 });

    // Head / Face (slightly wider and softer)
    const headGeom = new THREE.SphereGeometry(1.2, 32, 32);
    headGeom.scale(1.05, 1.1, 0.95);
    const head = new THREE.Mesh(headGeom, skinMat);
    headGroup.add(head);

    // Hair Base (Back/Top)
    const hairGeom = new THREE.SphereGeometry(1.23, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.52);
    const hairBase = new THREE.Mesh(hairGeom, hairMat);
    hairBase.position.y = 0.08;
    hairBase.rotation.x = -0.15;
    headGroup.add(hairBase);

    // Front Bangs / Fringe
    const bangsGeom = new THREE.SphereGeometry(1.26, 32, 16, Math.PI * 0.7, Math.PI * 0.6, 0, Math.PI * 0.45);
    const bangs = new THREE.Mesh(bangsGeom, hairMat);
    bangs.position.set(0, 0.1, 0.05);
    bangs.rotation.x = 0.15;
    headGroup.add(bangs);

    // Side hair volume (left)
    const sideHairGeom = new THREE.CylinderGeometry(0.3, 0.3, 1.2, 16);
    sideHairGeom.scale(1, 1, 0.6); // fallback roundness

    const leftSideHair = new THREE.Mesh(sideHairGeom, hairMat);
    leftSideHair.position.set(-1.05, -0.2, 0.4);
    leftSideHair.rotation.z = -0.15;
    leftSideHair.rotation.x = 0.2;
    headGroup.add(leftSideHair);

    // Side hair volume (right)
    const rightSideHair = new THREE.Mesh(sideHairGeom, hairMat);
    rightSideHair.position.set(1.05, -0.2, 0.4);
    rightSideHair.rotation.z = 0.15;
    rightSideHair.rotation.x = 0.2;
    headGroup.add(rightSideHair);

    // Eyes (larger and softer)
    const eyeGeom = new THREE.SphereGeometry(0.24, 24, 24);
    eyeGeom.scale(1, 0.85, 0.4);

    leftEye = new THREE.Mesh(eyeGeom, eyeWhiteMat);
    leftEye.position.set(-0.45, 0.15, 1.05);
    leftEye.rotation.y = -0.15;
    leftEye.rotation.z = 0.05;
    headGroup.add(leftEye);

    rightEye = new THREE.Mesh(eyeGeom, eyeWhiteMat);
    rightEye.position.set(0.45, 0.15, 1.05);
    rightEye.rotation.y = 0.15;
    rightEye.rotation.z = -0.05;
    headGroup.add(rightEye);

    // Pupils (larger for a friendlier cartoon look)
    const pupilGeom = new THREE.SphereGeometry(0.12, 24, 24);
    pupilGeom.scale(1, 1, 0.4);

    const leftPupil = new THREE.Mesh(pupilGeom, pupilMat);
    leftPupil.position.set(0, 0, 0.12);
    leftEye.add(leftPupil);

    const rightPupil = new THREE.Mesh(pupilGeom, pupilMat);
    rightPupil.position.set(0, 0, 0.12);
    rightEye.add(rightPupil);

    // Eyebrows (softer and slightly curved)
    const browGeom = new THREE.CylinderGeometry(0.03, 0.03, 0.35, 12);
    browGeom.rotateZ(Math.PI / 2);

    leftBrow = new THREE.Mesh(browGeom, hairMat);
    leftBrow.position.set(-0.45, 0.45, 1.12);
    leftBrow.rotation.z = 0.15;
    leftBrow.rotation.x = 0.1;
    headGroup.add(leftBrow);

    rightBrow = new THREE.Mesh(browGeom, hairMat);
    rightBrow.position.set(0.45, 0.45, 1.12);
    rightBrow.rotation.z = -0.15;
    rightBrow.rotation.x = 0.1;
    headGroup.add(rightBrow);

    // Nose (softer and rounder, using Cylinder as Capsule is not in r128)
    const noseGeom = new THREE.CylinderGeometry(0.06, 0.08, 0.2, 16);
    // Round the ends a bit using scale
    noseGeom.scale(1, 1, 0.8);
    const nose = new THREE.Mesh(noseGeom, skinMat);
    nose.rotation.x = Math.PI / 2 + 0.2;
    nose.position.set(0, -0.1, 1.18);
    headGroup.add(nose);

    // Jaw / Mouth
    jawGroup = new THREE.Group();
    jawGroup.position.set(0, -0.4, 1.10);
    headGroup.add(jawGroup);

    // Chin (smaller and smoothly integrated)
    const chinGeom = new THREE.SphereGeometry(0.35, 24, 24);
    chinGeom.scale(1, 0.5, 0.5);
    const chin = new THREE.Mesh(chinGeom, skinMat);
    chin.position.set(0, -0.15, 0.05);
    jawGroup.add(chin);

    // Mouth inner opening (resting state is barely visible / slightly curved)
    const mouthInnerGeom = new THREE.PlaneGeometry(0.4, 0.08);
    mouthInner = new THREE.Mesh(mouthInnerGeom, mouthMat);
    mouthInner.position.set(0, 0.05, 0.15);
    jawGroup.add(mouthInner);

    // Add resize listener
    window.addEventListener('resize', () => {
        if (!container) return;
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    // Interaction vars
    let targetRotX = 0;
    let targetRotY = 0;

    // Mouse movement to look around
    document.addEventListener('mousemove', (e) => {
        if (avatarCurrentState === 'speaking' || avatarCurrentState === 'listening') {
            const x = (e.clientX / window.innerWidth) * 2 - 1;
            const y = -(e.clientY / window.innerHeight) * 2 + 1;
            targetRotY = x * 0.4;
            targetRotX = y * 0.2;
        } else {
            targetRotY = 0;
            targetRotX = 0;
        }
    });

    let time = 0;
    let blinkTimer = Math.random() * 3 + 2;
    let isBlinking = false;
    let blinkProgress = 0;

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);
        time += 0.02;

        // Smooth rotation
        headGroup.rotation.y += (targetRotY - headGroup.rotation.y) * 0.05;
        headGroup.rotation.x += (targetRotX - headGroup.rotation.x) * 0.05;

        // Breathing
        if (avatarCurrentState === 'idle' || avatarCurrentState === 'listening') {
            avatarGroup.position.y = Math.sin(time) * 0.03;
        } else if (avatarCurrentState === 'thinking') {
            avatarGroup.position.y = Math.sin(time) * 0.05 + 0.05;
            leftEye.children[0].position.x = Math.sin(time * 3) * 0.05;
            rightEye.children[0].position.x = Math.sin(time * 3) * 0.05;
        } else {
            avatarGroup.position.y += (0 - avatarGroup.position.y) * 0.1;
            leftEye.children[0].position.x += (0 - leftEye.children[0].position.x) * 0.1;
            rightEye.children[0].position.x += (0 - rightEye.children[0].position.x) * 0.1;
        }

        // Smooth Blinking
        blinkTimer -= 0.02;
        if (blinkTimer <= 0 && !isBlinking) {
            isBlinking = true;
            blinkTimer = Math.random() * 3 + 2; // next blink in 2-5 sec
        }

        if (isBlinking) {
            blinkProgress += 0.2;
            if (blinkProgress >= Math.PI) {
                isBlinking = false;
                blinkProgress = 0;
                leftEye.scale.y = 1;
                rightEye.scale.y = 1;
            } else {
                // scale.y down and up smoothly
                const blinkScale = 1 - Math.sin(blinkProgress) * 0.95;
                leftEye.scale.y = Math.max(blinkScale, 0.05);
                rightEye.scale.y = Math.max(blinkScale, 0.05);
            }
        }

        renderer.render(scene, camera);
    }

    animate();
    console.log('[3D Avatar] Initialized in', containerId);
    setState('idle');
    setEmotion('neutral');
}

function setEmotion(label) {
    if (!leftBrow) return;
    avatarCurrentEmotion = label;

    // Reset brows
    leftBrow.rotation.z = 0.15;
    rightBrow.rotation.z = -0.15;
    leftBrow.position.y = 0.45;
    rightBrow.position.y = 0.45;

    switch (label) {
        case 'joy':
            leftBrow.position.y = 0.52;
            rightBrow.position.y = 0.52;
            leftBrow.rotation.z = 0.2;
            rightBrow.rotation.z = -0.2;
            break;
        case 'sadness':
            leftBrow.position.y = 0.48;
            rightBrow.position.y = 0.48;
            leftBrow.rotation.z = -0.15;
            rightBrow.rotation.z = 0.15;
            break;
        case 'anger':
            leftBrow.position.y = 0.4;
            rightBrow.position.y = 0.4;
            leftBrow.rotation.z = -0.25;
            rightBrow.rotation.z = 0.25;
            break;
        case 'anxiety':
            leftBrow.position.y = 0.5;
            rightBrow.position.y = 0.5;
            leftBrow.rotation.z = -0.1;
            rightBrow.rotation.z = 0.1;
            break;
    }
}

function setState(stateName) {
    avatarCurrentState = stateName;
}

function startSpeaking(audioElement) {
    setState('speaking');

    if (!audioElement || !(audioElement instanceof HTMLAudioElement)) {
        console.error('[3D Avatar] startSpeaking requires an HTMLAudioElement.');
        return;
    }

    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }

        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }

        if (!analyser) {
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 256;
            analyser.smoothingTimeConstant = 0.7;
        }

        // It's important to only create the MediaElementAudioSourceNode ONCE per audio element
        if (!audioElement._avatarSource) {
            audioElement._avatarSource = audioCtx.createMediaElementSource(audioElement);
        }

        // Connect the source differently:
        // Source -> Analyser -> context.destination
        audioElement._avatarSource.disconnect();
        audioElement._avatarSource.connect(analyser);
        analyser.connect(audioCtx.destination);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);

        function lipSyncLoop() {
            if (!analyser || !jawGroup || !mouthInner) return;
            analyser.getByteFrequencyData(dataArray);

            let sum = 0;
            for (let i = 2; i < 30; i++) sum += dataArray[i];
            const avg = sum / 28;

            const amplitude = Math.min(avg / 150, 1);

            if (amplitude > 0.02) {
                // Open jaw proportional to volume, stretch mouth inner vertically
                jawGroup.position.y = -0.4 - (amplitude * 0.12);
                mouthInner.scale.y = 1 + (amplitude * 12);
                // Slightly narrow the mouth as it opens wider (making an 'O' shape)
                mouthInner.scale.x = 1 - (amplitude * 0.3);
            } else {
                jawGroup.position.y = -0.4;
                mouthInner.scale.y = 1;
                mouthInner.scale.x = 1;
            }

            lipSyncRAF = requestAnimationFrame(lipSyncLoop);
        }
        lipSyncLoop();

        // When audio completes or pauses, stop lip-sync
        audioElement.addEventListener('ended', stopSpeaking, { once: true });
        audioElement.addEventListener('pause', stopSpeaking, { once: true });

    } catch (e) {
        console.error('[3D Avatar] Audio sync error:', e);
    }
}

function stopSpeaking() {
    if (lipSyncRAF) {
        cancelAnimationFrame(lipSyncRAF);
        lipSyncRAF = null;
    }
    if (jawGroup && mouthInner) {
        jawGroup.position.y = -0.4;
        mouthInner.scale.y = 1;
        mouthInner.scale.x = 1;
    }
    setState('idle');
}

// Attach to window so index.html can call them
window.initAvatar = initAvatar;
window.setEmotion = setEmotion;
window.setState = setState;
window.startSpeaking = startSpeaking;
window.stopSpeaking = stopSpeaking;
