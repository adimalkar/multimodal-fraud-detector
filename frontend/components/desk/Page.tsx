/** Standard padding for workspace pages. /analyze skips it to use the full width. */
const Page = ({ children, width = "max-w-6xl" }: { children: React.ReactNode; width?: string }) => (
	<div className={`mx-auto w-full ${width} px-4 py-8 md:px-8 md:py-12`}>{children}</div>
);

export default Page;
