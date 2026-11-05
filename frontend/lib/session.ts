/**
 * Local previews live only in this tab. The engine never returns the original,
 * and a report reopened elsewhere simply shows no preview.
 */
const previews = new Map<string, { url: string; type: string; name: string; size: number }>();

export const rememberPreview = (jobId: string, file: File) => {
	previews.set(jobId, {
		url: URL.createObjectURL(file),
		type: file.type,
		name: file.name,
		size: file.size,
	});
};

export const previewFor = (jobId: string) => previews.get(jobId);
