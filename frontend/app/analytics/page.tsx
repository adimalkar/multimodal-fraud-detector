import Header from "@/components/Header";
import Footer from "@/components/Footer";
import AnalyticsDashboard from "@/components/AnalyticsDashboard";

export const metadata = {
  title: "Analytics & Forensics Audit Log — FraudSight AI",
  description: "Visual screening history, provisional risk tiers, and review records.",
};

const AnalyticsPage = () => {
  return (
    <>
      <Header />
      <div className="pt-6 min-h-[80vh]">
        <AnalyticsDashboard />
      </div>
      <Footer />
    </>
  );
};

export default AnalyticsPage;
