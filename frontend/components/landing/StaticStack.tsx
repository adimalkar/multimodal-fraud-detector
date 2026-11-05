/** Shown before the 3D scene loads, and instead of it where WebGL isn't available. */
const StaticStack = () => (
	<div aria-hidden="true" className="flex h-full items-center justify-center lg:justify-end lg:pr-[12%] [perspective:1400px]">
		<div className="relative aspect-[1/1.29] w-[46vmin] [transform-style:preserve-3d] [transform:rotateX(14deg)_rotateY(-26deg)]">
			{["#7df5d8", "#9a8cff", "#e2deff"].map((color, index) => (
				<div
					key={color}
					className="absolute inset-0 rounded-lg border bg-white/[.03]"
					style={{ borderColor: color, transform: `translateZ(${-(index + 1) * 46}px)`, opacity: 0.55 }}
				/>
			))}
			<div className="absolute inset-0 rounded-lg bg-[#f4f5f7]" />
		</div>
	</div>
);

export default StaticStack;
