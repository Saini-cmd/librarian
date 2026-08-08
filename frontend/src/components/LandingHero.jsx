import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import ClayShapes from "./ClayShapes";

const HERO_SHAPES = [
  { type: "circle", size: 44, x: 8, y: 14, color: "text-primary/25", float: 16, duration: 5 },
  { type: "blob", size: 64, x: 16, y: 68, color: "text-accent/20", float: -18, duration: 7 },
  { type: "ring", size: 56, x: 30, y: 10, color: "text-primary/30", spin: 360, float: 12, duration: 9 },
  { type: "egg", size: 48, x: 42, y: 74, color: "text-warning/25", float: 14, duration: 8 },
  { type: "squircle", size: 52, x: 58, y: 12, color: "text-success/25", spin: -360, float: 14, duration: 8 },
  { type: "pill", size: 20, x: 66, y: 70, color: "text-primary/20", float: -12, duration: 6 },
  { type: "blob", size: 46, x: 78, y: 24, color: "text-info/20", float: 10, duration: 7 },
  { type: "circle", size: 30, x: 86, y: 64, color: "text-accent/25", float: 14, duration: 5.5 },
  { type: "squircle", size: 88, x: 90, y: 6, color: "text-success/15", spin: -180, duration: 12 },
];

export default function LandingHero() {
  const container = useRef(null);
  const { isSignedIn } = useAuth();
  const navigate = useNavigate();

  useGSAP(() => {
    const tl = gsap.timeline({ defaults: { ease: "power4.out" } });

    tl.from(".hero-badge", { opacity: 0, y: -20, duration: 0.6 })
      .from(".hero-title", { opacity: 0, y: 30, duration: 0.8 }, "-=0.2")
      .from(".hero-sub", { opacity: 0, y: 20, duration: 0.6 }, "-=0.3")
      .from(".hero-actions", { opacity: 0, y: 24, duration: 0.5 }, "-=0.2");
  }, { scope: container });

  return (
    <section ref={container} className="relative min-h-screen flex items-center bg-base-100 overflow-hidden">
      <ClayShapes shapes={HERO_SHAPES} />

      <div className="max-w-6xl mx-auto px-6 py-24 lg:py-28 w-full relative">
        <div className="max-w-3xl mx-auto text-center space-y-7">
          <span className="hero-badge inline-block rounded-full bg-white px-5 py-2 text-sm font-semibold text-primary clay">
            ✦ Code intelligence, naturally
          </span>

          <h1 className="hero-title text-5xl lg:text-7xl font-extrabold tracking-tight text-base-content leading-[1.05]">
            Understand any codebase with{" "}
            <span className="text-primary">Librarian AI</span>
          </h1>

          <p className="hero-sub text-base-content/60 text-lg max-w-xl mx-auto leading-relaxed">
            Navigate and understand any codebase with AI-powered semantic search
            and natural language queries.
          </p>

          <div className="hero-actions pt-2">
            {isSignedIn ? (
              <button
                className="clay-press bg-primary text-primary-content px-10 py-4 text-base font-bold rounded-full"
                onClick={() => navigate("/app")}
              >
                Enter App
              </button>
            ) : (
              <div className="flex flex-wrap items-center justify-center gap-4">
                <SignInButton mode="modal">
                  <button className="clay-press bg-primary text-primary-content px-10 py-4 text-base font-bold rounded-full">
                    Sign In
                  </button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button className="clay-press bg-white text-primary px-10 py-4 text-base font-bold rounded-full">
                    Sign Up
                  </button>
                </SignUpButton>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
