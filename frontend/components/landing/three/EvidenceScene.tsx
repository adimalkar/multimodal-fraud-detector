"use client";

import { Environment, Lightformer, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import type { MotionValue } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
	AdditiveBlending,
	BufferAttribute,
	BufferGeometry,
	CanvasTexture,
	type Group,
	MathUtils,
	type Material,
	type Mesh,
	type Points,
} from "three";
import { metadataTexture, pageTexture, signatureTexture, textTexture } from "./textures";

const WIDTH = 2.6;
const HEIGHT = WIDTH * (1320 / 1024);
const DEPTH_STEP = 0.7;
const SIDE_STEP = 0.5;

/* Front to back. The page sits in front and the rest fan out behind it. */
const LAYERS = [
	{ make: pageTexture, solid: true },
	{ make: textTexture, solid: false },
	{ make: metadataTexture, solid: false },
	{ make: signatureTexture, solid: false },
];

/* Must match the chapter ranges in LayerStage. */
const CHAPTER_STOPS = [0.2, 0.36, 0.52, 0.68, 0.82];

const activeLayer = (progress: number) => {
	const index = CHAPTER_STOPS.findIndex((stop, position) => progress >= stop && progress < (CHAPTER_STOPS[position + 1] ?? 0));
	return index;
};

const opening = (progress: number) => MathUtils.smoothstep(progress, 0.03, 0.26);
const closing = (progress: number) => MathUtils.smoothstep(progress, 0.84, 0.99);

const Layer = ({ index, solid, make, progress }: {
	index: number;
	solid: boolean;
	make: () => CanvasTexture;
	progress: { current: number };
}) => {
	const group = useRef<Group>(null);
	const body = useRef<Material>(null);
	const face = useRef<Material>(null);
	const texture = useMemo(make, [make]);
	const bodyOpacity = solid ? 1 : 0.3;

	useEffect(() => () => texture.dispose(), [texture]);

	useFrame((_, delta) => {
		if (!group.current) return;
		const p = progress.current;
		// Layers lift off one after another, then settle back together.
		const lift = MathUtils.smoothstep(p, 0.03 + index * 0.04, 0.2 + index * 0.04) * (1 - closing(p));
		const centre = (LAYERS.length - 1) / 2;
		const active = activeLayer(p);
		const focused = active === index;
		// The layer being described comes forward to the centre, so it can actually be read.
		const x = focused ? 0 : (index - centre) * SIDE_STEP * lift;
		const z = focused ? 0.55 : -index * (0.035 + DEPTH_STEP * lift);
		group.current.position.x = MathUtils.damp(group.current.position.x, x, 6, delta);
		group.current.position.z = MathUtils.damp(group.current.position.z, z, 6, delta);

		const lit = active < 0 || focused;
		const target = lit ? 1 : 0.08;
		if (face.current) face.current.opacity = MathUtils.damp(face.current.opacity, target, 6, delta);
		if (body.current) body.current.opacity = MathUtils.damp(body.current.opacity, bodyOpacity * target, 6, delta);
	});

	return (
		<group ref={group}>
			<RoundedBox args={[WIDTH, HEIGHT, 0.024]} radius={0.012} smoothness={2}>
				<meshPhysicalMaterial
					ref={body as never}
					color={solid ? "#e9ebf0" : "#262a48"}
					transparent
					opacity={bodyOpacity}
					roughness={0.25}
					clearcoat={1}
					depthWrite={false}
				/>
			</RoundedBox>
			<mesh position={[0, 0, 0.014]}>
				<planeGeometry args={[WIDTH, HEIGHT]} />
				<meshBasicMaterial
					ref={face as never}
					map={texture}
					transparent
					blending={solid ? undefined : AdditiveBlending}
					depthWrite={false}
					toneMapped={false}
				/>
			</mesh>
		</group>
	);
};

const beamTexture = () => {
	const canvas = document.createElement("canvas");
	canvas.width = 4;
	canvas.height = 128;
	const context = canvas.getContext("2d");
	if (context) {
		const fade = context.createLinearGradient(0, 0, 0, 128);
		fade.addColorStop(0, "rgba(125,245,216,0)");
		fade.addColorStop(0.97, "rgba(125,245,216,.5)");
		fade.addColorStop(1, "rgba(125,245,216,1)");
		context.fillStyle = fade;
		context.fillRect(0, 0, 4, 128);
	}
	return new CanvasTexture(canvas);
};

/** A band of light moving down the page. It fades out once the layers open. */
const ScanBeam = ({ still, progress }: { still: boolean; progress: { current: number } }) => {
	const beam = useRef<Mesh>(null);
	const material = useRef<Material>(null);
	const texture = useMemo(beamTexture, []);
	const band = 0.7;

	useEffect(() => () => texture.dispose(), [texture]);

	useFrame(({ clock }) => {
		if (!beam.current || !material.current) return;
		const travel = HEIGHT / 2 - band / 2;
		beam.current.position.y = still ? 0 : Math.sin(clock.elapsedTime * 0.6) * travel;
		material.current.opacity = 1 - MathUtils.smoothstep(progress.current, 0.02, 0.1);
		beam.current.visible = material.current.opacity > 0.01;
	});

	return (
		<mesh ref={beam} position={[0, 0, 0.02]}>
			<planeGeometry args={[WIDTH, band]} />
			<meshBasicMaterial ref={material as never} map={texture} transparent depthWrite={false} blending={AdditiveBlending} toneMapped={false} />
		</mesh>
	);
};

const Dust = ({ count }: { count: number }) => {
	const points = useRef<Points>(null);
	const geometry = useMemo(() => {
		const positions = new Float32Array(count * 3);
		for (let index = 0; index < count * 3; index += 1) positions[index] = (Math.random() - 0.5) * 12;
		const built = new BufferGeometry();
		built.setAttribute("position", new BufferAttribute(positions, 3));
		return built;
	}, [count]);
	useFrame((_, delta) => {
		if (points.current) points.current.rotation.y += delta * 0.012;
	});
	return (
		<points ref={points} geometry={geometry}>
			<pointsMaterial size={0.012} color="#b9b2ff" transparent opacity={0.4} depthWrite={false} sizeAttenuation />
		</points>
	);
};

const Stack = ({ progress, still }: { progress: { current: number }; still: boolean }) => {
	const rig = useRef<Group>(null);
	const { viewport, pointer } = useThree();
	const wide = viewport.aspect > 1.15;
	// Sized from the real view, so the sheet never runs under the nav or the headline.
	const scale = wide
		? (viewport.height * 0.64) / HEIGHT
		: Math.min((viewport.height * 0.36) / HEIGHT, (viewport.width * 0.56) / WIDTH);
	const homeX = wide ? viewport.width * 0.24 : 0;
	const homeY = wide ? -0.04 : viewport.height * 0.19;

	useFrame(({ clock }, delta) => {
		if (!rig.current) return;
		const p = progress.current;
		const open = opening(p) * (1 - closing(p));
		const floating = still ? 0 : Math.sin(clock.elapsedTime * 0.7) * 0.04;
		const pointerX = still ? 0 : pointer.x * 0.1;
		const pointerY = still ? 0 : -pointer.y * 0.06;
		rig.current.position.x = MathUtils.damp(rig.current.position.x, homeX * MathUtils.lerp(1, 0.86, open), 4, delta);
		rig.current.position.y = MathUtils.damp(rig.current.position.y, homeY + floating, 4, delta);
		rig.current.rotation.y = MathUtils.damp(rig.current.rotation.y, MathUtils.lerp(-0.34, -0.5, open) + pointerX, 4, delta);
		rig.current.rotation.x = MathUtils.damp(rig.current.rotation.x, MathUtils.lerp(0.1, 0.2, open) + pointerY, 4, delta);
		rig.current.scale.setScalar(scale * MathUtils.lerp(1, 0.84, open));
	});

	return (
		<group ref={rig} position={[homeX, homeY, 0]} scale={scale} rotation={[0.1, -0.34, 0]}>
			{LAYERS.map((layer, index) => (
				<Layer key={index} index={index} solid={layer.solid} make={layer.make} progress={progress} />
			))}
			<ScanBeam still={still} progress={progress} />
		</group>
	);
};

const EvidenceScene = ({ progress, still, active }: { progress: MotionValue<number>; still: boolean; active: boolean }) => {
	const value = useRef({ current: progress.get() }).current;
	const [mobile] = useState(() => window.matchMedia("(pointer: coarse)").matches);

	useEffect(() => progress.on("change", (next) => {
		value.current = next;
	}), [progress, value]);

	return (
		<Canvas
			dpr={mobile ? [1, 1.5] : [1, 1.75]}
			camera={{ position: [0, 0, 6.2], fov: 38 }}
			frameloop={active ? "always" : "never"}
			gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
			aria-hidden="true"
		>
			<ambientLight intensity={0.8} />
			<directionalLight position={[-3, 4, 5]} intensity={1.2} />
			<Environment resolution={64} frames={1}>
				<Lightformer form="rect" intensity={1.6} color="#ffffff" position={[-4, 2, 3]} scale={[4, 6, 1]} />
				<Lightformer form="rect" intensity={1} color="#7df5d8" position={[4, -2, 2]} scale={[3, 5, 1]} />
			</Environment>
			<Stack progress={value} still={still} />
			{!still && <Dust count={mobile ? 140 : 360} />}
		</Canvas>
	);
};

export default EvidenceScene;
