/* ========================================================================
   READYPLAYERME AVATAR SCRIPT (Three.js)
   Loads and animates a ReadyPlayerMe character with lip-sync and emotions
   ======================================================================== */

let scene, camera, renderer;
let avatarGroup, headGroup, jawGroup;
let audioCtx, analyser, lipSyncRAF;
let avatarCurrentEmotion = 'neutral';
let avatarCurrentState = 'idle';
let mixer, actions = {};
let clock = new THREE.Clock();

// ReadyPlayerMe model and animation data
let glbModel = null;           // GLB model for mesh/skin
let fbxAnimation = null;       // FBX animation data
let currentModel = null;       // Currently active model (will be GLB)
let faceRig = null;
let visemeWeights = null;
let blendShapes = null;

// Viseme mapping for phonemes to mouth shapes
const VISEME_MAP = {
    'sil': 0,  // Silence
    'aa': 1,   // Father
    'E': 2,    // Eat
    'I': 3,    // It
    'O': 4,    // Oak
    'U': 5,    // Hook
    'b': 6,    // Bob
    'C': 7,    // Chuck
    'd': 8,    // Did
    'f': 9,    // Fork
    'g': 10,   // Gut
    'h': 11,   // Help
    'l': 12,   // Lid
    'n': 13,   // Nit
    'p': 13,   // Pit (same as n)
    'r': 14,   // Red
    's': 15,   // Sit
    't': 16,   // Talk
    'th': 17,  // Thumb
    'v': 18,   // Van
    'w': 19,   // With
    'z': 20    // Zap
};

// Wait for Three.js and loaders to load
function waitForThreeJS(callback) {
    console.log('[RPM Avatar] Checking for Three.js, GLTFLoader and FBXLoader...');
    console.log('[RPM Avatar] THREE exists:', !!window.THREE);
    console.log('[RPM Avatar] GLTFLoader exists:', !!(window.THREE && window.THREE.GLTFLoader));
    console.log('[RPM Avatar] FBXLoader exists:', !!(window.THREE && window.THREE.FBXLoader));

    if (window.THREE && window.THREE.GLTFLoader && window.THREE.FBXLoader) {
        console.log('[RPM Avatar] All loaders ready!');
        callback();
    } else {
        console.log('[RPM Avatar] Loaders not ready, retrying in 100ms...');
        setTimeout(() => waitForThreeJS(callback), 100);
    }
}

function initAvatar(containerId) {
    console.log('[RPM Avatar] initAvatar called with container:', containerId);
    waitForThreeJS(() => {
        console.log('[RPM Avatar] Three.js loaded, starting initialization...');
        _initReadyPlayerMe(containerId);
    });
}

async function _initReadyPlayerMe(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Set explicit size
    let width = container.clientWidth || 600;
    let height = container.clientHeight || 600;

    container.innerHTML = '';
    container.style.position = 'relative';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';

    // Create Scene
    scene = new THREE.Scene();
    scene.background = null; // Transparent background

    // Create Camera — wider FOV so avatar is visible, lookAt head-height
    camera = new THREE.PerspectiveCamera(12, width / height, 2, 100);
    camera.position.set(0, 1.6, 4);
    camera.lookAt(0, 1.6, 0);

    // Create Renderer
    renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "high-performance"
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // Set canvas CSS to ensure emotion bar stays visible
    renderer.domElement.style.position = 'absolute';
    renderer.domElement.style.top = '0';
    renderer.domElement.style.left = '0';
    renderer.domElement.style.zIndex = '1';
    renderer.domElement.style.pointerEvents = 'none';

    container.appendChild(renderer.domElement);

    // Enhanced Lighting for realistic avatar
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const mainLight = new THREE.DirectionalLight(0xffffff, 0.8);
    mainLight.position.set(1, 2, 3);
    mainLight.castShadow = true;
    mainLight.shadow.mapSize.width = 1024;
    mainLight.shadow.mapSize.height = 1024;
    scene.add(mainLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-1, 1, 2);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.2);
    rimLight.position.set(0, -1, -2);
    avatarGroup = new THREE.Group();
    scene.add(avatarGroup);
    console.log('[RPM Avatar] Avatar group created');

    // Mouse interaction
    let targetRotX = 0;
    let targetRotY = 0;

    document.addEventListener('mousemove', (e) => {
        if (avatarCurrentState === 'speaking' || avatarCurrentState === 'listening') {
            const x = (e.clientX / window.innerWidth) * 2 - 1;
            const y = -(e.clientY / window.innerHeight) * 2 + 1;
            targetRotY = x * 0.3;
            targetRotX = y * 0.15;
        } else {
            targetRotY = 0;
            targetRotX = 0;
        }
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        const delta = clock.getDelta();

        // Update animation mixer
        if (mixer) {
            mixer.update(delta);
        }

        // Smooth head rotation (only for GLB model)
        if (headGroup && currentModel === glbModel) {
            const targetRotX = 0;
            const targetRotY = 0;
            headGroup.rotation.x += (targetRotX - headGroup.rotation.x) * 0.05;
            headGroup.rotation.y += (targetRotY - headGroup.rotation.y) * 0.05;
        }

        // Breathing animation — use base position offset, NOT additive (avoids drift)
        if (currentModel === glbModel && avatarGroup) {
            avatarGroup.position.y = Math.sin(clock.elapsedTime * 1.5) * 0.008;
        }

        renderer.render(scene, camera);
    }

    animate();
    console.log('[RPM Avatar] Animation loop started');

    try {
        console.log('[RPM Avatar] Starting to load avatar models...');
        await loadReadyPlayerMeAvatar();
        console.log('[RPM Avatar] Avatar models loaded successfully');
    } catch (error) {
        console.error('[RPM Avatar] Failed to load avatar models:', error);
        // Fallback to placeholder
        createPlaceholderAvatar();
    }

    // Add resize listener
    window.addEventListener('resize', () => {
        if (!container) return;
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    console.log('[RPM Avatar] Initialized in', containerId);
    setState('idle');
    setEmotion('neutral');
    console.log('[RPM Avatar] Initial state set to idle');
}

async function loadReadyPlayerMeAvatar() {
    console.log('[RPM Avatar] Starting GLB model and FBX animation load...');

    try {
        // Step 1: Load GLB model for mesh/skin
        console.log('[RPM Avatar] Loading GLB model...');
        const gltfLoader = new THREE.GLTFLoader();
        const glbUrl = '/static/models/avatar.glb';

        const gltf = await new Promise((resolve, reject) => {
            gltfLoader.load(glbUrl, resolve,
                (progress) => console.log('[RPM Avatar] GLB loading progress:', (progress.loaded / progress.total * 100) + '%'),
                reject);
        });

        console.log('[RPM Avatar] GLB model loaded successfully!');
        glbModel = gltf.scene;

        // Auto-fit: compute bounding box and centre the model
        const box = new THREE.Box3().setFromObject(glbModel);
        const boxSize = new THREE.Vector3();
        const boxCenter = new THREE.Vector3();
        box.getSize(boxSize);
        box.getCenter(boxCenter);
        console.log('[RPM Avatar] Model size:', boxSize, 'center:', boxCenter);

        // Centre model at origin, shift down so feet are at y=0
        glbModel.position.set(-boxCenter.x, -box.min.y, -boxCenter.z);

        // Scale so the full model fits in ~2 units tall
        const targetHeight = 2.0;
        const scale = targetHeight / boxSize.y;
        glbModel.scale.setScalar(scale);

        glbModel.visible = true;

        avatarGroup.add(glbModel);
        currentModel = glbModel;
        console.log('[RPM Avatar] GLB model added to scene');

        // Step 2: Skip GLB animations and force FBX loading for dual animation system
        console.log('[RPM Avatar] Skipping GLB animations to use dual FBX system');

        if (false && gltf.animations && gltf.animations.length > 0) {
            console.log('[RPM Avatar] GLB has built-in animations:', gltf.animations.map(a => a.name));
            mixer = new THREE.AnimationMixer(glbModel);
            gltf.animations.forEach((clip) => {
                const action = mixer.clipAction(clip);
                actions[clip.name] = action;
                action.setLoop(THREE.LoopRepeat);
            });
            const firstKey = Object.keys(actions)[0];
            if (firstKey) {
                actions[firstKey].play();
                console.log('[RPM Avatar] GLB built-in animation playing:', firstKey);
            }
        } else {
            // Step 3: Load both idle and talking FBX animations
            console.log('[RPM Avatar] Loading dual FBX animations...');
            try {
                const fbxLoader = new THREE.FBXLoader();

                // Load both animations
                const [idleFbx, talkFbx] = await Promise.all([
                    new Promise((resolve, reject) => {
                        fbxLoader.load('/static/models/action_pose.fbx', resolve,
                            (progress) => {
                                if (progress.total > 0)
                                    console.log('[RPM Avatar] Idle FBX loading:', Math.round(progress.loaded / progress.total * 100) + '%');
                            }, reject);
                    }),
                    new Promise((resolve, reject) => {
                        fbxLoader.load('/static/models/action_talk.fbx', resolve,
                            (progress) => {
                                if (progress.total > 0)
                                    console.log('[RPM Avatar] Talk FBX loading:', Math.round(progress.loaded / progress.total * 100) + '%');
                            }, reject);
                    })
                ]);

                console.log('[RPM Avatar] Both FBX animations loaded');

                if ((idleFbx.animations && idleFbx.animations.length > 0) || (talkFbx.animations && talkFbx.animations.length > 0)) {

                    // ── Collect all bone names from the GLB skeleton ──────────
                    const glbBoneNames = new Set();
                    glbModel.traverse(node => {
                        if (node.isBone || node.type === 'Bone') glbBoneNames.add(node.name);
                    });
                    console.log('[RPM Avatar] GLB bones:', [...glbBoneNames]);

                    // Process both animations
                    const allAnimations = [
                        ...(idleFbx.animations || []),
                        ...(talkFbx.animations || [])
                    ];

                    mixer = new THREE.AnimationMixer(glbModel);

                    // ── Name remapping: FBX prefix → RPM/Mixamo bone name ─────
                    // Handles prefixes like "mixamorig:", "mixamorig_", etc.
                    function remapBoneName(fbxName) {
                        // Strip common prefixes
                        let cleaned = fbxName
                            .replace(/^mixamorig[_:]?/i, '')
                            .replace(/^rig[_:]?/i, '')
                            .replace(/^chr[_:]?/i, '')
                            .replace(/^Bip001\s?/i, '')
                            .replace(/^Armature[_:]?/i, '');

                        // Map common variations (FBX -> RPM GLB)
                        const variations = {
                            'ForeArm': 'ForeArm',
                            'UpperArm': 'Arm',
                            'Hand': 'Hand',
                            'L_': 'Left',
                            'R_': 'Right',
                            'Left': 'Left',
                            'Right': 'Right'
                        };

                        // Additional common mappings for RPM
                        if (cleaned.includes('Left')) cleaned = cleaned.replace('Left', 'Left');
                        if (cleaned.includes('Right')) cleaned = cleaned.replace('Right', 'Right');

                        return cleaned;
                    }

                    // Helper for fuzzy bone name matching
                    function findBestBoneMatch(fbxName, availableBones) {
                        const cleaned = remapBoneName(fbxName);
                        // Case-insensitive direct match
                        for (const bone of availableBones) {
                            if (bone.toLowerCase() === cleaned.toLowerCase()) return bone;
                        }

                        // Handle L/R vs Left/Right
                        const withLR = cleaned.replace('Left', 'L').replace('Right', 'R');
                        for (const bone of availableBones) {
                            if (bone.toLowerCase() === withLR.toLowerCase()) return bone;
                        }

                        const withLeftRight = cleaned.replace(/^L(?=[A-Z])/, 'Left').replace(/^R(?=[A-Z])/, 'Right');
                        for (const bone of availableBones) {
                            if (bone.toLowerCase() === withLeftRight.toLowerCase()) return bone;
                        }

                        return null;
                    }

                    // Process animations and track their source
                    const idleAnimations = [];
                    const talkAnimations = [];

                    allAnimations.forEach((clip, index) => {
                        let stripped = 0;
                        let remapped = 0;
                        let kept = 0;

                        clip.tracks = clip.tracks.filter(track => {
                            // Track name format: "BoneName.property" or "BoneName.position" etc.
                            const dotIdx = track.name.indexOf('.');
                            if (dotIdx === -1) return true;

                            const fbxBone = track.name.substring(0, dotIdx);
                            const property = track.name.substring(dotIdx + 1);

                            // Strip root position (prevents flying off-screen)
                            const cleanedName = remapBoneName(fbxBone).toLowerCase();
                            if ((cleanedName === 'hips' || cleanedName === 'root') && property === 'position') {
                                stripped++;
                                return false;
                            }

                            // Try fuzzy match
                            const bestMatch = findBestBoneMatch(fbxBone, glbBoneNames);
                            if (bestMatch) {
                                track.name = bestMatch + '.' + property;
                                remapped++;
                                return true;
                            }

                            // No match — drop this track
                            return false;
                        });

                        console.log(`[RPM Avatar] Clip "${clip.name}": kept=${kept} remapped=${remapped} stripped=${stripped} remaining=${clip.tracks.length}`);

                        if (clip.tracks.length > 0) {
                            // Assign a unique name to avoid collisions if multiple FBX files use the same internal clip name (e.g., "mixamo.com")
                            const uniqueName = (index < (idleFbx.animations || []).length) ? `idle_${clip.name}` : `talk_${clip.name}`;
                            clip.name = uniqueName;

                            const action = mixer.clipAction(clip);
                            actions[clip.name] = action;
                            action.setLoop(THREE.LoopRepeat);

                            // Track which file this animation came from
                            if (index < (idleFbx.animations || []).length) {
                                idleAnimations.push(clip.name);
                            } else {
                                talkAnimations.push(clip.name);
                            }
                        }
                    });

                    // Set up animation actions based on source file
                    const idleAnimName = idleAnimations[0];
                    const talkAnimName = talkAnimations[0] || idleAnimations[1] || idleAnimName;

                    if (idleAnimName) actions.idle = actions[idleAnimName];
                    if (talkAnimName) actions.talk = actions[talkAnimName];

                    console.log('[RPM Avatar] Final Mapping - actions.idle:', idleAnimName);
                    console.log('[RPM Avatar] Final Mapping - actions.talk:', talkAnimName);

                    if (idleAnimName === talkAnimName) {
                        console.warn('[RPM Avatar] WARNING: Using the same animation for both idle and talk!');
                    }

                    console.log('[RPM Avatar] Animation mapping - Idle:', idleAnimName, 'Talk:', talkAnimName);
                    console.log('[RPM Avatar] Idle animations:', idleAnimations);
                    console.log('[RPM Avatar] Talk animations:', talkAnimations);

                    // Start with idle animation
                    if (actions.idle) {
                        actions.idle.play();
                        console.log('[RPM Avatar] Playing idle animation');
                    } else {
                        const firstKey = Object.keys(actions)[0];
                        if (firstKey) {
                            actions[firstKey].play();
                            console.log('[RPM Avatar] Playing fallback animation:', firstKey);
                        }
                    }

                    console.log('[RPM Avatar] Available animations:', Object.keys(actions));
                } else {
                    console.warn('[RPM Avatar] FBX has no animation clips — using breathing idle only.');
                }

            } catch (fbxErr) {
                console.warn('[RPM Avatar] FBX load failed, using breathing idle:', fbxErr.message);
            }
        }

        // Step 4: Find blendshapes on GLB model
        console.log('[RPM Avatar] Starting blendshape detection on GLB model...');
        findHeadAndFaceRig(glbModel);

        console.log('[RPM Avatar] Avatar setup complete!');

    } catch (error) {
        console.error('[RPM Avatar] Failed to load model/animation:', error);
        console.log('[RPM Avatar] Error details:', error.message);
        throw error;
    }
}

function findHeadAndFaceRig(model) {
    console.log('[RPM Avatar] Scanning GLB model structure...');
    console.log('[RPM Avatar] Model children count:', model.children.length);

    let blendshapeMeshFound = false;

    glbModel.traverse((child) => {
        if (child.isMesh) {
            console.log('[RPM Avatar] Found mesh:', child.name, 'has blendshapes:', !!(child.morphTargetInfluences && child.morphTargetInfluences.length > 0));

            // Look for head bone/mesh
            if (child.name.toLowerCase().includes('head') ||
                child.name.toLowerCase().includes('neck') ||
                child.name.toLowerCase().includes('face')) {
                headGroup = child;
                console.log('[RPM Avatar] Found head group:', child.name);
            }

            // Look for face blendshapes
            if (child.morphTargetInfluences && child.morphTargetInfluences.length > 0) {
                blendShapes = child.morphTargetInfluences;
                console.log('[RPM Avatar] Found blendshapes on mesh:', child.name);
                console.log('[RPM Avatar] Blendshape count:', child.morphTargetInfluences.length);
                console.log('[RPM Avatar] Blendshape dictionary:', child.morphTargetDictionary);
                console.log('[RPM Avatar] Available blendshapes:', Object.keys(child.morphTargetDictionary || {}));

                // Store the mesh that has blendshapes for later use
                if (!glbModel.blendshapeMesh) {
                    glbModel.blendshapeMesh = child;
                    glbModel.blendshapeDictionary = child.morphTargetDictionary;
                    blendshapeMeshFound = true;
                    console.log('[RPM Avatar] Blendshape mesh stored:', child.name);
                }
            }
        }
    });

    // If no explicit head found, use the model's root
    if (!headGroup) {
        headGroup = model;
        console.log('[RPM Avatar] Using model root as head group');
    }

    // Final check for blendshapes
    if (!blendshapeMeshFound) {
        console.warn('[RPM Avatar] No blendshape mesh found in GLB model!');
        console.log('[RPM Avatar] Available meshes:',
            glbModel.children.filter(child => child.isMesh).map(child => child.name)
        );
    } else {
        console.log('[RPM Avatar] Blendshape detection successful!');
    }
}

function createPlaceholderAvatar() {
    // Create a simple placeholder if RPM loading fails
    const geometry = new THREE.CapsuleGeometry(0.3, 0.8, 4, 8);
    const material = new THREE.MeshPhongMaterial({
        color: 0x4A90E2,
        emissive: 0x112244,
        emissiveIntensity: 0.1
    });
    const placeholder = new THREE.Mesh(geometry, material);
    placeholder.position.y = 0;
    avatarGroup.add(placeholder);
    headGroup = placeholder;

    console.log('[RPM Avatar] Using placeholder avatar');
}

function setEmotion(label) {
    if (!glbModel) return;

    avatarCurrentEmotion = label;

    // Apply emotion through blendshapes if available
    if (blendShapes) {
        applyEmotionBlendshapes(label);
    }

    // You can also trigger emotion-specific animations
    if (actions[label]) {
        // Stop current animations
        Object.values(actions).forEach(action => action.stop());
        actions[label].play();
    }
}

function applyEmotionBlendshapes(emotion) {
    if (!glbModel || !glbModel.blendshapeMesh) {
        console.log('[RPM Avatar] No blendshapes available for emotion:', emotion);
        return;
    }

    console.log('[RPM Avatar] Applying emotion:', emotion);

    // Reset all blendshapes first
    const influences = glbModel.blendshapeMesh.morphTargetInfluences;
    for (let i = 0; i < influences.length; i++) {
        influences[i] = 0;
    }

    // Use the actual blendshape names from your ReadyPlayerMe avatar
    switch (emotion) {
        case 'joy':
            setBlendshape('mouthSmile', 0.5);
            setBlendshape('mouthSmileLeft', 0.5);
            setBlendshape('mouthSmileRight', 0.5);
            setBlendshape('browOuterUpLeft', 0.3);
            setBlendshape('browOuterUpRight', 0.3);
            setBlendshape('eyeSquintLeft', 0.2);
            setBlendshape('eyeSquintRight', 0.2);
            setBlendshape('cheekPuff', 0.1);
            break;

        case 'sadness':
            setBlendshape('mouthFrownLeft', 0.7);
            setBlendshape('mouthFrownRight', 0.7);
            setBlendshape('mouthLowerDownLeft', 0.4);
            setBlendshape('mouthLowerDownRight', 0.4);
            setBlendshape('browInnerUp', 0.3);
            setBlendshape('eyeSquintLeft', 0.4);
            setBlendshape('eyeSquintRight', 0.4);
            setBlendshape('mouthShrugLower', 0.2);
            break;

        case 'anger':
            setBlendshape('browDownLeft', 0.6);
            setBlendshape('browDownRight', 0.6);
            setBlendshape('eyeSquintLeft', 0.5);
            setBlendshape('eyeSquintRight', 0.5);
            setBlendshape('mouthStretchLeft', 0.3);
            setBlendshape('mouthStretchRight', 0.3);
            setBlendshape('noseSneerLeft', 0.2);
            setBlendshape('noseSneerRight', 0.2);
            break;

        case 'anxiety':
            setBlendshape('browInnerUp', 0.5);
            setBlendshape('browOuterUpLeft', 0.3);
            setBlendshape('browOuterUpRight', 0.3);
            setBlendshape('eyeWideLeft', 0.6);
            setBlendshape('eyeWideRight', 0.6);
            setBlendshape('mouthPucker', 0.3);
            setBlendshape('jawForward', 0.1);
            setBlendshape('cheekSquintLeft', 0.2);
            setBlendshape('cheekSquintRight', 0.2);
            break;

        case 'neutral':
        default:
            // Set neutral resting face
            setBlendshape('mouthClose', 0.2);
            break;
    }
}

function setBlendshape(name, value) {
    if (!glbModel || !glbModel.blendshapeMesh) {
        console.log('[RPM Avatar] Cannot set blendshape - missing GLB blendshape mesh');
        console.log('[RPM Avatar] glbModel exists:', !!glbModel);
        console.log('[RPM Avatar] blendshapeMesh exists:', !!(glbModel && glbModel.blendshapeMesh));
        return;
    }

    const dictionary = glbModel.blendshapeDictionary;
    const influences = glbModel.blendshapeMesh.morphTargetInfluences;

    if (!dictionary || !influences) {
        console.log('[RPM Avatar] Cannot set blendshape - missing dictionary or influences');
        console.log('[RPM Avatar] dictionary exists:', !!dictionary);
        console.log('[RPM Avatar] influences exists:', !!influences);
        return;
    }

    const index = dictionary[name];
    if (index !== undefined) {
        influences[index] = value;
        console.log(`[RPM Avatar] Set ${name} to ${value}`);
        return true;
    } else {
        console.log(`[RPM Avatar] Blendshape '${name}' not found. Available:`, Object.keys(dictionary));
        return false;
    }
}

function setState(stateName) {
    if (avatarCurrentState === stateName) return;

    const prevState = avatarCurrentState;
    avatarCurrentState = stateName;
    console.log('[RPM Avatar] State changed from', prevState, 'to:', stateName);

    // Animation switching with cross-fade
    const duration = 0.5; // cross-fade duration in seconds

    if (actions.talk && actions.idle) {
        if (stateName === 'speaking') {
            actions.idle.fadeOut(duration);
            actions.talk.reset().fadeIn(duration).play();
            console.log('[RPM Avatar] Animation: Cross-fading IDLE -> TALK');
        } else if (prevState === 'speaking') {
            actions.talk.fadeOut(duration);
            actions.idle.reset().fadeIn(duration).play();
            console.log('[RPM Avatar] Animation: Cross-fading TALK -> IDLE');
        }
    }

    switch (stateName) {
        case 'speaking':
            console.log('[RPM Avatar] State Logic: Speaking');
            break;

        case 'listening':
            console.log('[RPM Avatar] State Logic: Listening');
            break;

        case 'thinking':
            console.log('[RPM Avatar] State Logic: Thinking');
            break;

        case 'idle':
        default:
            console.log('[RPM Avatar] State Logic: Idle');
            break;
    }
}

function startSpeaking(audioElement) {
    setState('speaking');

    if (!audioElement || !(audioElement instanceof HTMLAudioElement)) {
        console.error('[RPM Avatar] startSpeaking requires an HTMLAudioElement.');
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
            analyser.smoothingTimeConstant = 0.8;
        }

        // Create audio source only once per element
        if (!audioElement._avatarSource) {
            audioElement._avatarSource = audioCtx.createMediaElementSource(audioElement);
        }

        audioElement._avatarSource.disconnect();
        audioElement._avatarSource.connect(analyser);
        analyser.connect(audioCtx.destination);

        startLipSync();

        audioElement.addEventListener('ended', stopSpeaking, { once: true });
        audioElement.addEventListener('pause', stopSpeaking, { once: true });

    } catch (e) {
        console.error('[RPM Avatar] Audio sync error:', e);
    }
}

function startLipSync() {
    if (!analyser) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    function lipSyncLoop() {
        if (!analyser) return;

        analyser.getByteFrequencyData(dataArray);

        // Calculate average amplitude
        let sum = 0;
        for (let i = 2; i < 30; i++) {
            sum += dataArray[i];
        }
        const avg = sum / 28;
        const amplitude = Math.min(avg / 150, 1);

        // Apply viseme based on amplitude
        applyVisemeFromAmplitude(amplitude);

        lipSyncRAF = requestAnimationFrame(lipSyncLoop);
    }

    lipSyncLoop();
}

function applyVisemeFromAmplitude(amplitude) {
    if (!glbModel || !glbModel.blendshapeMesh) {
        console.log('[RPM Avatar] No blendshapes for lip-sync (GLB model)');
        return;
    }

    // Simple amplitude-to-viseme mapping using GLB blendshapes
    // Reduced intensity for more natural mouth movement
    if (amplitude > 0.05) {
        // Reset emotion expressions during speech
        setBlendshape('mouthSmile', 0);
        setBlendshape('mouthFrownLeft', 0);
        setBlendshape('mouthFrownRight', 0);

        if (amplitude > 0.7) {
            // Wide open - use viseme_aa (ah sound) and jawOpen - REDUCED
            setBlendshape('viseme_aa', amplitude * 0.4);  // Reduced from 1.0
            setBlendshape('jawOpen', amplitude * 0.3);    // Reduced from 0.8
        } else if (amplitude > 0.5) {
            // Rounded - use viseme_O (oh sound) - REDUCED
            setBlendshape('viseme_O', amplitude * 0.3);   // Reduced from 1.0
            setBlendshape('jawOpen', amplitude * 0.2);    // Reduced from 0.6
            setBlendshape('mouthFunnel', amplitude * 0.15); // Reduced from 0.3
        } else if (amplitude > 0.3) {
            // Medium - use viseme_E (eh sound) - REDUCED
            setBlendshape('viseme_E', amplitude * 0.25);  // Reduced from 1.0
            setBlendshape('jawOpen', amplitude * 0.15);   // Reduced from 0.4
        } else {
            // Small - use viseme_I (ee sound) - REDUCED
            setBlendshape('viseme_I', amplitude * 0.2);   // Reduced from 1.0
            setBlendshape('jawOpen', amplitude * 0.1);    // Reduced from 0.2
        }
    } else {
        // Closed mouth - use silence viseme
        setBlendshape('viseme_sil', 0.8);  // Reduced from 1.0
        setBlendshape('jawOpen', 0);
        setBlendshape('mouthClose', 0.2);  // Reduced from 0.3
    }
}

function applyViseme(visemeIndex, intensity) {
    if (!blendShapes) return;

    // Reset mouth blendshapes
    const mouthShapes = [
        'mouthSmile', 'mouthSad', 'mouthAngry', 'mouthDimple',
        'mouthPress', 'mouthUpperLip', 'mouthLowerLip'
    ];

    mouthShapes.forEach(shape => setBlendshape(shape, 0));

    // Apply viseme-specific blendshapes
    // These blendshape names depend on your ReadyPlayerMe avatar
    switch (visemeIndex) {
        case VISEME_MAP['aa']:
            setBlendshape('mouthWide', intensity);
            break;
        case VISEME_MAP['O']:
            setBlendshape('mouthRound', intensity);
            break;
        case VISEME_MAP['E']:
            setBlendshape('mouthMedium', intensity);
            break;
        case VISEME_MAP['I']:
            setBlendshape('mouthNarrow', intensity);
            break;
        default:
            // Closed mouth
            break;
    }
}

function stopSpeaking() {
    if (lipSyncRAF) {
        cancelAnimationFrame(lipSyncRAF);
        lipSyncRAF = null;
    }

    setState('idle');

    // Reset all speaking blendshapes
    if (glbModel && glbModel.blendshapeMesh) {
        console.log('[RPM Avatar] Stopping speaking - resetting mouth');

        // Reset visemes and jaw
        const visemes = ['viseme_sil', 'viseme_PP', 'viseme_FF', 'viseme_TH', 'viseme_DD',
            'viseme_kk', 'viseme_CH', 'viseme_SS', 'viseme_nn', 'viseme_RR',
            'viseme_aa', 'viseme_E', 'viseme_I', 'viseme_O', 'viseme_U'];

        visemes.forEach(viseme => setBlendshape(viseme, 0));
        setBlendshape('jawOpen', 0);
        setBlendshape('mouthClose', 0);
        setBlendshape('mouthFunnel', 0);

        // Restore current emotion expression
        setEmotion(avatarCurrentEmotion);
    }

    setState('idle');
}

// Export functions for global access
window.initAvatar = initAvatar;
window.setEmotion = setEmotion;
window.setState = setState;
window.startSpeaking = startSpeaking;
window.stopSpeaking = stopSpeaking;
