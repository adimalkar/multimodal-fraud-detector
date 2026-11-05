import Link from "next/link";
import Coverage from "@/components/landing/Coverage";
import Custody from "@/components/landing/Custody";
import Limits from "@/components/landing/Limits";
import SiteFooter from "@/components/landing/SiteFooter";
import SiteHeader from "@/components/landing/SiteHeader";
import Specimen from "@/components/landing/Specimen";

const Home = () => (
	<>
		<SiteHeader />
		<main>
			<div aria-hidden="true" className="ruler" />
			<section className="wrap grid gap-10 pb-14 pt-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14 lg:pb-20 lg:pt-14">
				<div className="flex flex-col justify-center">
					<p className="label mb-5">For claims and investigation teams</p>
					<h1 className="display text-[clamp(3.5rem,8.6vw,7.25rem)]">Read the file behind the file</h1>
					<p className="mt-6 max-w-md text-lg leading-relaxed text-graphite md:text-xl">
						FraudSight screens the photos, PDFs and video attached to a claim. It reports what it saw, what it
						couldn’t check, and why. You make the call.
					</p>
					<div className="mt-8 flex flex-wrap gap-3">
						<Link href="/analyze" className="btn-primary">Screen a file</Link>
						<a href="#coverage" className="btn-quiet">See what it checks</a>
					</div>
				</div>
				<Specimen />
			</section>
			<Custody />
			<Coverage />
			<Limits />
		</main>
		<SiteFooter />
	</>
);

export default Home;
