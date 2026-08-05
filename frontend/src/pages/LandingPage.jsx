import LandingHero from "../components/LandingHero";
import LandingFeatures from "../components/LandingFeatures";
import LandingHowItWorks from "../components/LandingHowItWorks";
import LandingFooter from "../components/LandingFooter";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-base-100 text-base-content">
      <LandingHero />
      <LandingFeatures />
      <LandingHowItWorks />
      <LandingFooter />
    </div>
  );
}
