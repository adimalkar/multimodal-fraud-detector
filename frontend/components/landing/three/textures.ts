import { CanvasTexture, SRGBColorSpace } from "three";

const W = 1024;
const H = 1320;

const sheet = (draw: (context: CanvasRenderingContext2D) => void) => {
	const canvas = document.createElement("canvas");
	canvas.width = W;
	canvas.height = H;
	const context = canvas.getContext("2d");
	if (context) draw(context);
	const texture = new CanvasTexture(canvas);
	texture.colorSpace = SRGBColorSpace;
	texture.anisotropy = 8;
	return texture;
};

const MONO = "ui-monospace, 'SFMono-Regular', Menlo, monospace";
const SANS = "system-ui, sans-serif";

const INVOICE_ROWS: Array<[string, string, number]> = [
	["Rear bumper, supply and fit", "1,180.00", 300],
	["Paint and finish", "860.00", 360],
	["Labour, 11 hours", "1,200.00", 420],
];

const lines = (
	context: CanvasRenderingContext2D,
	rows: Array<[string, string]>,
	top: number,
	color: string,
) => {
	rows.forEach(([key, value], index) => {
		context.fillStyle = "rgba(255,255,255,.55)";
		context.font = `32px ${MONO}`;
		context.fillText(key, 96, top + index * 74);
		context.fillStyle = color;
		context.font = `500 34px ${MONO}`;
		context.fillText(value, 400, top + index * 74);
	});
};

/** The visible page: a fictional invoice, as a person would see it. */
export const pageTexture = () =>
	sheet((c) => {
		c.fillStyle = "#f4f5f7";
		c.fillRect(0, 0, W, H);
		c.fillStyle = "#14161b";
		c.font = `600 56px ${SANS}`;
		c.fillText("Harbour Road Auto Body", 88, 130);
		c.font = `32px ${MONO}`;
		c.fillStyle = "#59616e";
		c.fillText("Invoice 20418   12 Mar 2026", 88, 186);
		c.fillStyle = "#14161b";
		c.fillRect(88, 232, W - 176, 3);
		c.font = `34px ${MONO}`;
		INVOICE_ROWS.forEach(([item, cost, y]) => {
			c.textAlign = "left";
			c.fillText(item, 88, y);
			c.textAlign = "right";
			c.fillText(cost, W - 88, y);
		});
		c.textAlign = "left";
		c.fillText("Subtotal", 480, 640);
		c.fillText("Tax 8%", 480, 704);
		c.font = `600 38px ${MONO}`;
		c.fillText("Total due", 480, 790);
		c.textAlign = "right";
		c.font = `34px ${MONO}`;
		c.fillText("3,240.00", W - 88, 640);
		c.fillText("259.20", W - 88, 704);
		c.font = `600 38px ${MONO}`;
		c.fillText("3,699.20", W - 88, 790);
		c.textAlign = "left";
		c.fillRect(480, 738, W - 568, 3);
		c.strokeStyle = "#14161b";
		c.lineWidth = 5;
		c.lineCap = "round";
		c.beginPath();
		c.moveTo(100, 1120);
		c.bezierCurveTo(160, 980, 220, 1000, 200, 1090);
		c.bezierCurveTo(190, 1160, 280, 1000, 320, 1060);
		c.bezierCurveTo(350, 1110, 400, 1040, 560, 1050);
		c.stroke();
		c.fillRect(88, 1160, 420, 3);
		c.fillStyle = "#59616e";
		c.font = `28px ${MONO}`;
		c.fillText("Authorised signature", 88, 1206);
	});

/** OCR: every word boxed, with the sum that doesn't reconcile. */
export const textTexture = () =>
	sheet((c) => {
		c.setLineDash([12, 8]);
		c.lineWidth = 3;
		c.strokeStyle = "rgba(125,245,216,.85)";
		const boxes = [
			[80, 86, 640, 62], [80, 156, 560, 44], [80, 268, 560, 46], [750, 268, 194, 46],
			[80, 328, 330, 46], [790, 328, 154, 46], [80, 388, 330, 46], [750, 388, 194, 46],
			[470, 608, 180, 46], [750, 608, 194, 46], [470, 672, 130, 46], [790, 672, 154, 46],
		];
		boxes.forEach(([x, y, w, h]) => c.strokeRect(x, y, w, h));
		c.strokeStyle = "#ffcb1f";
		c.lineWidth = 5;
		c.setLineDash([]);
		c.strokeRect(470, 752, 474, 58);
		c.fillStyle = "#7df5d8";
		c.font = `500 34px ${MONO}`;
		c.textAlign = "right";
		c.fillText("3,240.00 + 259.20 = 3,499.20", W - 80, 880);
		c.fillStyle = "#ffcb1f";
		c.font = `600 40px ${MONO}`;
		c.fillText("Off by 200.00", W - 80, 938);
	});

export const metadataTexture = () =>
	sheet((c) => {
		c.fillStyle = "#9a8cff";
		c.font = `600 40px ${SANS}`;
		c.fillText("File metadata", 96, 150);
		lines(
			c,
			[
				["Producer", "Image editor"],
				["Created", "14 Mar 2026"],
				["Modified", "14 Mar 2026"],
				["Pages", "1"],
				["Fonts", "2 embedded"],
				["Version", "PDF 1.7"],
			],
			250,
			"#e2deff",
		);
	});

export const signatureTexture = () =>
	sheet((c) => {
		c.strokeStyle = "#7df5d8";
		c.lineWidth = 7;
		c.lineCap = "round";
		c.beginPath();
		c.moveTo(100, 420);
		c.bezierCurveTo(160, 280, 220, 300, 200, 390);
		c.bezierCurveTo(190, 460, 280, 300, 320, 360);
		c.bezierCurveTo(350, 410, 400, 340, 560, 350);
		c.stroke();
		c.fillStyle = "#9a8cff";
		c.font = `600 40px ${SANS}`;
		c.fillText("Signature and revisions", 96, 150);
		lines(c, [["Revision 1", "Signed"], ["Revision 2", "Saved after signing"]], 560, "#ffcb1f");
	});
