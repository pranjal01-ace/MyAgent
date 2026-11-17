import os
import json
import logging
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal as Signal

from desktop.character_renderer import CharacterRenderer, Sprite2DRenderer

logger = logging.getLogger("desktop.renderer_3d")

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    logger.warning("QWebEngineView unavailable; 3D renderer will use fallback 2D engine.")


class Model3DRenderer(CharacterRenderer):
    """3D Desktop Companion Renderer utilizing WebGL/Three.js or OpenGL for 3D GLTF/GLB/VRM models."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "IDLE"
        self.current_expression = "NEUTRAL"
        self.current_gaze = (0.0, 0.0)
        self.manifest = {}
        self.character_dir = None
        self.scale_factor = 1.0
        self.opacity_val = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Opacity Effect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # Check if 3D WebGL is supported, otherwise fallback to 2D
        if WEBENGINE_AVAILABLE:
            self.web_view = QWebEngineView(self)
            self.web_view.setAttribute(Qt.WA_TranslucentBackground, True)
            self.web_view.page().setBackgroundColor(Qt.transparent)
            layout.addWidget(self.web_view)
            self.fallback_2d = None
        else:
            self.web_view = None
            self.fallback_2d = Sprite2DRenderer(self)
            layout.addWidget(self.fallback_2d)

    def load(self, character_path: Path) -> bool:
        character_path = Path(character_path)
        manifest_file = character_path / "character.json"

        if not manifest_file.exists():
            return False

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
        except Exception as e:
            logger.error(f"Error loading 3D manifest: {e}")
            return False

        self.character_dir = character_path
        assets = self.manifest.get("assets", {})
        model_file = assets.get("model_3d", "model.glb")
        model_path = character_path / model_file

        # If 3D WebEngine available and 3D model exists, load 3D Three.js canvas
        if self.web_view:
            html_content = self._generate_threejs_html(model_path)
            self.web_view.setHtml(html_content, baseUrl=QUrl(f"file:///{character_path.as_posix()}/"))
        elif self.fallback_2d:
            self.fallback_2d.load(character_path)

        self.set_state("IDLE")
        return True

    def set_state(self, state: str):
        self.current_state = state.upper()
        self.state_changed.emit(self.current_state)

        # Natural expression mapping on state transition
        state_expr_map = {
            "HAPPY": "HAPPY",
            "LAUGHING": "LAUGH",
            "SPEAKING": "SMILE",
            "TALKING": "SMILE",
            "THINKING": "THINKING",
            "LISTENING": "NEUTRAL",
            "IDLE": "NEUTRAL",
            "CONFUSED": "CONFUSED",
        }
        if self.current_state in state_expr_map:
            self.set_expression(state_expr_map[self.current_state])

        if self.web_view:
            js_code = f"if (window.setAvatarState) {{ window.setAvatarState('{self.current_state}'); }}"
            self.web_view.page().runJavaScript(js_code)
        elif self.fallback_2d:
            self.fallback_2d.set_state(state)

    def set_expression(self, expression: str):
        """Phase 3 — Sets facial expression (NEUTRAL, HAPPY, SMILE, LAUGH, THINKING, SURPRISED, CONFUSED, WINK)."""
        self.current_expression = expression.upper()
        if self.web_view:
            js_code = f"if (window.setAvatarExpression) {{ window.setAvatarExpression('{self.current_expression}'); }}"
            self.web_view.page().runJavaScript(js_code)
        elif self.fallback_2d and hasattr(self.fallback_2d, "set_expression"):
            self.fallback_2d.set_expression(self.current_expression)

    def set_gaze(self, x: float, y: float):
        """Phase 3 — Sets lookat eye and head gaze coordinates clamped to [-1.0, 1.0]."""
        clamped_x = max(-1.0, min(1.0, float(x)))
        clamped_y = max(-1.0, min(1.0, float(y)))
        self.current_gaze = (clamped_x, clamped_y)
        if self.web_view:
            js_code = f"if (window.setAvatarGaze) {{ window.setAvatarGaze({clamped_x}, {clamped_y}); }}"
            self.web_view.page().runJavaScript(js_code)
        elif self.fallback_2d and hasattr(self.fallback_2d, "set_gaze"):
            self.fallback_2d.set_gaze(clamped_x, clamped_y)

    def trigger_blink(self, blink_type: str = "NORMAL"):
        """Phase 3 — Triggers an immediate natural eye blink (NORMAL, DOUBLE, LONG)."""
        b_type = blink_type.upper()
        if self.web_view:
            js_code = f"if (window.triggerAvatarBlink) {{ window.triggerAvatarBlink('{b_type}'); }}"
            self.web_view.page().runJavaScript(js_code)

    def set_scale(self, scale: float):
        self.scale_factor = scale
        if self.web_view:
            js_code = f"if (window.setAvatarScale) {{ window.setAvatarScale({scale}); }}"
            self.web_view.page().runJavaScript(js_code)
        elif self.fallback_2d:
            self.fallback_2d.set_scale(scale)

    def set_opacity(self, opacity: float):
        self.opacity_val = opacity
        self.opacity_effect.setOpacity(opacity)

    def _generate_threejs_html(self, model_path: Path) -> str:
        """Generate embedded Three.js WebGL canvas with Phase 2 Animation Controller, cross-fading, lerp blending, and barge-in cancellation."""
        model_filename = model_path.name
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}
                canvas {{ width: 100vw; height: 100vh; display: block; }}
            </style>
            <!-- Three.js Core & GLTFLoader -->
            <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
        </head>
        <body>
            <div id="canvas-container"></div>
            <script>
                // =========================================================================
                // Phase 3 — Facial Expression, Smile, Laugh, Eye & Gaze Controllers
                // =========================================================================
                class FacialController3D {{
                    constructor() {{
                        this.currentExpression = "NEUTRAL";
                        this.targetSmile = 0.0;
                        this.currSmile = 0.0;
                        this.targetEyeSquint = 0.0;
                        this.currEyeSquint = 0.0;
                        this.targetEyebrowTilt = 0.0;
                        this.currEyebrowTilt = 0.0;
                        this.targetCheekRaise = 0.0;
                        this.currCheekRaise = 0.0;

                        // Eye Blinking State
                        this.blinkTimer = 0;
                        this.isBlinking = false;
                        this.nextBlinkTime = 2.5;
                        this.blinkProgress = 0;
                        this.blinkType = "NORMAL"; // NORMAL, DOUBLE, LONG

                        // LookAt Mouse Gaze Tracking Target
                        this.targetGazeX = 0;
                        this.targetGazeY = 0;
                        this.currGazeX = 0;
                        this.currGazeY = 0;
                    }}

                    setExpression(exprName) {{
                        this.currentExpression = exprName.toUpperCase();
                        const e = this.currentExpression;

                        if (e === "HAPPY" || e === "SMILE") {{
                            this.targetSmile = 1.0;
                            this.targetEyeSquint = 0.35;
                            this.targetEyebrowTilt = -0.1;
                            this.targetCheekRaise = 0.4;
                        }} else if (e === "LAUGH") {{
                            this.targetSmile = 1.4;
                            this.targetEyeSquint = 0.6;
                            this.targetEyebrowTilt = -0.15;
                            this.targetCheekRaise = 0.6;
                        }} else if (e === "THINKING" || e === "CONFINED") {{
                            this.targetSmile = 0.1;
                            this.targetEyeSquint = 0.2;
                            this.targetEyebrowTilt = 0.2;
                            this.targetCheekRaise = 0.0;
                        }} else if (e === "SURPRISED" || e === "EXCITED") {{
                            this.targetSmile = 0.5;
                            this.targetEyeSquint = -0.2;
                            this.targetEyebrowTilt = -0.3;
                            this.targetCheekRaise = 0.2;
                        }} else if (e === "CONFUSED") {{
                            this.targetSmile = -0.1;
                            this.targetEyeSquint = 0.15;
                            this.targetEyebrowTilt = 0.3;
                            this.targetCheekRaise = 0.0;
                        }} else if (e === "WINK") {{
                            this.targetSmile = 0.8;
                            this.targetEyeSquint = 0.3;
                            this.targetEyebrowTilt = -0.1;
                            this.targetCheekRaise = 0.35;
                        }} else {{ // NEUTRAL / DEFAULT
                            this.targetSmile = 0.0;
                            this.targetEyeSquint = 0.0;
                            this.targetEyebrowTilt = 0.0;
                            this.targetCheekRaise = 0.0;
                        }}
                    }}

                    updateGaze(mx, my) {{
                        // Clamp mouse gaze offsets
                        this.targetGazeX = Math.max(-0.35, Math.min(0.35, mx * 0.4));
                        this.targetGazeY = Math.max(-0.25, Math.min(0.25, my * 0.3));
                    }}

                    update(dt) {{
                        // Smooth Expression Interpolation
                        const lerpFactor = Math.min(1.0, dt * 6.0);
                        this.currSmile += (this.targetSmile - this.currSmile) * lerpFactor;
                        this.currEyeSquint += (this.targetEyeSquint - this.currEyeSquint) * lerpFactor;
                        this.currEyebrowTilt += (this.targetEyebrowTilt - this.currEyebrowTilt) * lerpFactor;
                        this.currCheekRaise += (this.targetCheekRaise - this.currCheekRaise) * lerpFactor;

                        // Gaze LookAt Interpolation
                        this.currGazeX += (this.targetGazeX - this.currGazeX) * (dt * 5.0);
                        this.currGazeY += (this.targetGazeY - this.currGazeY) * (dt * 5.0);

                        // Randomized Natural Eye Blinking System (2-5s)
                        this.blinkTimer += dt;
                        if (!this.isBlinking) {{
                            if (this.blinkTimer >= this.nextBlinkTime) {{
                                this.isBlinking = true;
                                this.blinkProgress = 0;
                                this.blinkTimer = 0;
                                // Randomize blink variation (normal vs double vs long)
                                const rand = Math.random();
                                if (rand > 0.85) this.blinkType = "DOUBLE";
                                else if (rand > 0.7) this.blinkType = "LONG";
                                else this.blinkType = "NORMAL";
                            }}
                        }} else {{
                            const speed = this.blinkType === "LONG" ? 5.0 : 10.0;
                            this.blinkProgress += dt * speed;
                            if (this.blinkProgress >= 1.0) {{
                                if (this.blinkType === "DOUBLE" && Math.random() > 0.4) {{
                                    this.blinkType = "NORMAL";
                                    this.blinkProgress = 0;
                                }} else {{
                                    this.isBlinking = false;
                                    this.blinkProgress = 0;
                                    this.nextBlinkTime = 2.0 + Math.random() * 3.5;
                                }}
                            }}
                        }}
                    }}
                }}

                let facialController = new FacialController3D();

                window.addEventListener('mousemove', (e) => {{
                    const cx = window.innerWidth / 2;
                    const cy = window.innerHeight / 2;
                    const mx = (e.clientX - cx) / cx;
                    const my = (e.clientY - cy) / cy;
                    facialController.updateGaze(mx, my);
                }});

                function init3D() {{
                    scene = new THREE.Scene();
                    camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
                    camera.position.set(0, 0, 4.5);

                    renderer = new THREE.WebGLRenderer({{ alpha: true, antialias: true }});
                    renderer.setSize(window.innerWidth, window.innerHeight);
                    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2.0));
                    document.body.appendChild(renderer.domElement);

                    // 3D Lighting Setup (Ambient, Directional, PointLight)
                    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
                    scene.add(ambientLight);

                    const dirLight = new THREE.DirectionalLight(0xffaa44, 1.4);
                    dirLight.position.set(3, 5, 4);
                    scene.add(dirLight);

                    const fireLight = new THREE.PointLight(0xff6600, 2.0, 12);
                    fireLight.position.set(0, -0.5, 2.5);
                    scene.add(fireLight);

                    // Attempt loading 3D GLTF/GLB model via GLTFLoader
                    if (typeof THREE.GLTFLoader !== 'undefined') {{
                        const loader = new THREE.GLTFLoader();
                        loader.load(
                            '{model_filename}',
                            function (gltf) {{
                                console.log("Loaded GLB Model successfully!", gltf);
                                characterMesh = gltf.scene;

                                // Auto-fit model scale and camera bounds
                                const box = new THREE.Box3().setFromObject(characterMesh);
                                const center = box.getCenter(new THREE.Vector3());
                                const size = box.getSize(new THREE.Vector3());
                                const maxDim = Math.max(size.x, size.y, size.z);
                                const scale = 2.0 / (maxDim || 1.0);

                                characterMesh.position.x = -center.x * scale;
                                characterMesh.position.y = -center.y * scale - 0.2;
                                characterMesh.position.z = -center.z * scale;
                                characterMesh.scale.set(scale, scale, scale);

                                scene.add(characterMesh);

                                // Setup Skeletal AnimationMixer if clips exist
                                if (gltf.animations && gltf.animations.length > 0) {{
                                    animationMixer = new THREE.AnimationMixer(characterMesh);
                                    gltf.animations.forEach((clip) => {{
                                        animController.animationsMap[clip.name.toLowerCase()] = animationMixer.clipAction(clip);
                                    }});
                                }}
                                animController.setState("IDLE");
                            }},
                            undefined,
                            function (error) {{
                                console.warn("GLB file load warning/fallback to procedural 3D rig:", error);
                                buildProcedural3DRig();
                            }}
                        );
                    }} else {{
                        buildProcedural3DRig();
                    }}

                    // Fire Flame Aura Particles (Ace Theme)
                    const pGeo = new THREE.BufferGeometry();
                    const pCount = 120;
                    const pPos = new Float32Array(pCount * 3);
                    for(let i = 0; i < pCount * 3; i += 3) {{
                        pPos[i] = (Math.random() - 0.5) * 2.2;
                        pPos[i+1] = (Math.random() - 0.5) * 2.5;
                        pPos[i+2] = (Math.random() - 0.5) * 2.2;
                    }}
                    pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
                    const pMat = new THREE.PointsMaterial({{ color: 0xff5500, size: 0.07, transparent: true, opacity: 0.75 }});
                    fireParticles = new THREE.Points(pGeo, pMat);
                    scene.add(fireParticles);

                    animate();
                }}

                function buildProcedural3DRig() {{
                    if (characterMesh) return;
                    const group = new THREE.Group();

                    // Head
                    const headGeo = new THREE.SphereGeometry(0.55, 32, 32);
                    const headMat = new THREE.MeshStandardMaterial({{ color: 0xffcc99, roughness: 0.4 }});
                    const head = new THREE.Mesh(headGeo, headMat);
                    head.position.y = 1.0;
                    group.add(head);

                    // Eyes
                    const leftEyeGeo = new THREE.SphereGeometry(0.08, 16, 16);
                    const eyeMat = new THREE.MeshStandardMaterial({{ color: 0x111111, roughness: 0.2 }});
                    window.leftEye = new THREE.Mesh(leftEyeGeo, eyeMat);
                    window.leftEye.position.set(-0.18, 1.1, 0.48);
                    group.add(window.leftEye);

                    window.rightEye = new THREE.Mesh(leftEyeGeo, eyeMat);
                    window.rightEye.position.set(0.18, 1.1, 0.48);
                    group.add(window.rightEye);

                    // Phase 3 — Eyebrows
                    const browGeo = new THREE.BoxGeometry(0.13, 0.025, 0.02);
                    const browMat = new THREE.MeshStandardMaterial({{ color: 0x221100, roughness: 0.4 }});
                    window.leftEyebrow = new THREE.Mesh(browGeo, browMat);
                    window.leftEyebrow.position.set(-0.18, 1.23, 0.5);
                    group.add(window.leftEyebrow);

                    window.rightEyebrow = new THREE.Mesh(browGeo, browMat);
                    window.rightEyebrow.position.set(0.18, 1.23, 0.5);
                    group.add(window.rightEyebrow);

                    // Phase 3 — Blush Cheeks
                    const cheekGeo = new THREE.SphereGeometry(0.065, 16, 16);
                    const cheekMat = new THREE.MeshStandardMaterial({{ color: 0xff6666, roughness: 0.6, transparent: true, opacity: 0.4 }});
                    window.leftCheek = new THREE.Mesh(cheekGeo, cheekMat);
                    window.leftCheek.position.set(-0.28, 0.96, 0.45);
                    window.leftCheek.scale.set(1.0, 0.6, 0.3);
                    group.add(window.leftCheek);

                    window.rightCheek = new THREE.Mesh(cheekGeo, cheekMat);
                    window.rightCheek.position.set(0.28, 0.96, 0.45);
                    window.rightCheek.scale.set(1.0, 0.6, 0.3);
                    group.add(window.rightCheek);

                    // Mouth
                    const mouthGeo = new THREE.BoxGeometry(0.2, 0.05, 0.05);
                    const mouthMat = new THREE.MeshStandardMaterial({{ color: 0x8c1414, roughness: 0.3 }});
                    window.mouthMesh = new THREE.Mesh(mouthGeo, mouthMat);
                    window.mouthMesh.position.set(0, 0.88, 0.5);
                    group.add(window.mouthMesh);

                    // Ace Hat
                    const hatGeo = new THREE.ConeGeometry(0.95, 0.4, 32);
                    const hatMat = new THREE.MeshStandardMaterial({{ color: 0xff4400, roughness: 0.3 }});
                    const hat = new THREE.Mesh(hatGeo, hatMat);
                    hat.position.y = 1.55;
                    group.add(hat);

                    // Body
                    const bodyGeo = new THREE.CylinderGeometry(0.48, 0.38, 1.3, 32);
                    const bodyMat = new THREE.MeshStandardMaterial({{ color: 0x222222, roughness: 0.5 }});
                    const body = new THREE.Mesh(bodyGeo, bodyMat);
                    body.position.y = -0.1;
                    group.add(body);

                    // Articulated Arms
                    const armMat = new THREE.MeshStandardMaterial({{ color: 0xffcc99, roughness: 0.4 }});
                    window.leftArmGroup = new THREE.Group();
                    window.leftArmGroup.position.set(-0.55, 0.4, 0);
                    const leftArmMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.75, 16), armMat);
                    leftArmMesh.position.y = -0.375;
                    window.leftArmGroup.add(leftArmMesh);
                    group.add(window.leftArmGroup);

                    window.rightArmGroup = new THREE.Group();
                    window.rightArmGroup.position.set(0.55, 0.4, 0);
                    const rightArmMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.75, 16), armMat);
                    rightArmMesh.position.y = -0.375;
                    window.rightArmGroup.add(rightArmMesh);
                    group.add(window.rightArmGroup);

                    characterMesh = group;
                    scene.add(characterMesh);
                    animController.setState("IDLE");
                }}

                let blinkTimer3D = 0;
                let isBlinking3D = false;
                let nextBlink3D = 2.5;
                let blinkProgress3D = 0;

                function animate() {{
                    requestAnimationFrame(animate);
                    const delta = clock.getDelta();
                    const time = clock.getElapsedTime();

                    if (animationMixer) {{
                        animationMixer.update(delta);
                    }}

                    animController.updateLerp(delta);
                    facialController.update(delta);

                    // Facial Controller Blinking & Eye Squint
                    let eyelidFactor = facialController.isBlinking ? Math.sin(facialController.blinkProgress * Math.PI) : 0;
                    let eyeScaleY = Math.max(0.1, (1.0 - facialController.currEyeSquint) * (1.0 - eyelidFactor * 0.9));
                    let isWink = facialController.currentExpression === "WINK";

                    if (window.leftEye && window.rightEye) {{
                        window.leftEye.scale.y = eyeScaleY;
                        window.rightEye.scale.y = isWink ? 0.08 : eyeScaleY;

                        // LookAt Gaze Tracking Offset
                        window.leftEye.position.x = -0.18 + facialController.currGazeX * 0.15;
                        window.leftEye.position.y = 1.1 + facialController.currGazeY * 0.1;
                        window.rightEye.position.x = 0.18 + facialController.currGazeX * 0.15;
                        window.rightEye.position.y = 1.1 + facialController.currGazeY * 0.1;
                    }}

                    // Phase 3 — Eyebrows Rotation & Tilt
                    if (window.leftEyebrow && window.rightEyebrow) {{
                        window.leftEyebrow.rotation.z = -facialController.currEyebrowTilt;
                        window.rightEyebrow.rotation.z = facialController.currEyebrowTilt;
                        window.leftEyebrow.position.y = 1.23 + facialController.currEyebrowTilt * 0.08;
                        window.rightEyebrow.position.y = 1.23 + (facialController.currentExpression === "CONFUSED" ? -0.04 : facialController.currEyebrowTilt * 0.08);
                    }}

                    // Phase 3 — Cheeks Raising & Blush Opacity
                    if (window.leftCheek && window.rightCheek) {{
                        const cheekScale = 1.0 + facialController.currCheekRaise * 0.5;
                        window.leftCheek.scale.set(cheekScale, cheekScale * 0.6, 0.3);
                        window.rightCheek.scale.set(cheekScale, cheekScale * 0.6, 0.3);
                        window.leftCheek.material.opacity = 0.3 + facialController.currCheekRaise * 0.4;
                        window.rightCheek.material.opacity = 0.3 + facialController.currCheekRaise * 0.4;
                    }}

                    // Apply lerped animation transformations & gaze head rotation
                    if (characterMesh) {{
                        const st = animController.currentState;
                        characterMesh.rotation.z = animController.currHeadTilt;
                        characterMesh.rotation.y = facialController.currGazeX * 0.35; // Head gaze tracking

                        if (st === "IDLE") {{
                            characterMesh.position.y = animController.currBodyY + Math.sin(time * 2.0) * 0.04;
                            characterMesh.rotation.y += Math.sin(time * 0.8) * 0.08;
                            if (window.leftArmGroup) window.leftArmGroup.rotation.z = animController.currLeftArmZ + Math.sin(time * 1.8) * 0.05;
                            if (window.rightArmGroup) window.rightArmGroup.rotation.z = animController.currRightArmZ - Math.sin(time * 1.8) * 0.05;
                            if (window.mouthMesh) {{
                                let smileScaleX = 1.0 + facialController.currSmile * 0.4;
                                window.mouthMesh.scale.set(smileScaleX, 0.4, 1.0);
                            }}
                        }} else if (st === "TALKING" || st === "SPEAKING") {{
                            characterMesh.position.y = animController.currBodyY + Math.sin(time * 12.0) * 0.07;
                            let talkOpen = 0.2 + 0.8 * Math.abs(Math.sin(time * 14.0));
                            if (window.mouthMesh) window.mouthMesh.scale.set(1.2 + facialController.currSmile * 0.3, talkOpen * 3.0, 1.2);
                            let gesturePhase = time * 6.0;
                            if (window.leftArmGroup) window.leftArmGroup.rotation.z = animController.currLeftArmZ + Math.sin(gesturePhase) * 0.3;
                            if (window.rightArmGroup) window.rightArmGroup.rotation.z = animController.currRightArmZ - Math.cos(gesturePhase * 0.9) * 0.3;
                        }} else if (st === "THINKING") {{
                            characterMesh.rotation.y += Math.sin(time * 1.5) * 0.15;
                            if (window.rightArmGroup) window.rightArmGroup.rotation.z = animController.currRightArmZ;
                            if (window.leftArmGroup) window.leftArmGroup.rotation.z = animController.currLeftArmZ;
                        }} else if (st === "LISTENING") {{
                            characterMesh.position.y = animController.currBodyY + Math.sin(time * 2.5) * 0.02;
                            if (window.leftArmGroup) window.leftArmGroup.rotation.z = animController.currLeftArmZ;
                            if (window.rightArmGroup) window.rightArmGroup.rotation.z = animController.currRightArmZ;
                        }} else if (st === "HAPPY" || st === "LAUGHING") {{
                            characterMesh.position.y = animController.currBodyY + Math.sin(time * 6.0) * 0.06;
                            if (window.leftArmGroup) window.leftArmGroup.rotation.z = animController.currLeftArmZ;
                            if (window.rightArmGroup) window.rightArmGroup.rotation.z = animController.currRightArmZ;
                            if (window.mouthMesh) window.mouthMesh.scale.set(1.4, 0.8, 1.2);
                        }}
                    }}

                    if (fireParticles) {{
                        fireParticles.rotation.y += 0.02;
                    }}

                    renderer.render(scene, camera);
                }}

                window.setAvatarState = function(state) {{
                    animController.setState(state);
                }};

                window.setAvatarExpression = function(expr) {{
                    if (facialController) {{
                        facialController.setExpression(expr);
                    }}
                }};

                window.setAvatarGaze = function(gx, gy) {{
                    if (facialController) {{
                        facialController.updateGaze(gx, gy);
                    }}
                }};

                window.triggerAvatarBlink = function(type) {{
                    if (facialController) {{
                        facialController.isBlinking = true;
                        facialController.blinkType = type || "NORMAL";
                        facialController.blinkProgress = 0;
                    }}
                }};

                window.setAvatarScale = function(scale) {{
                    if (characterMesh) {{
                        characterMesh.scale.set(scale, scale, scale);
                    }}
                }};

                window.addEventListener('resize', () => {{
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(window.innerWidth, window.innerHeight);
                }});

                init3D();
            </script>
        </body>
        </html>
        """


