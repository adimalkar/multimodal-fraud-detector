import Closing from "@/components/landing/Closing";
import Coverage from "@/components/landing/Coverage";
import LayerStage from "@/components/landing/LayerStage";
import { SiteFooter, SiteHeader } from "@/components/landing/SiteChrome";

const Home = () => (
	<>
		<SiteHeader />
		<main>
			<LayerStage />
			<Coverage />
			<Closing />
		</main>
		<SiteFooter />
	</>
);

export default Home;
