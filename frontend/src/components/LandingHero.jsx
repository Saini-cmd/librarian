import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";

export default function LandingHero() {
  const container = useRef(null);
  const { isSignedIn } = useAuth();
  const navigate = useNavigate();

  useGSAP(() => {
    const tl = gsap.timeline({ defaults: { ease: "power4.out" } });

    tl.from(".hero-badge", {
      opacity: 0,
      y: -30,
      duration: 0.7,
    })
      .from(".hero-line-top", {
        opacity: 0,
        x: -80,
        duration: 0.9,
      }, "-=0.3")
      .from(".hero-line-bottom", {
        opacity: 0,
        x: 80,
        duration: 0.9,
      }, "-=0.6")
      .from(".hero-ai", {
        opacity: 0,
        scale: 0.6,
        duration: 0.8,
        ease: "back.out(1.7)",
      }, "-=0.5")
      .from(".hero-sub", {
        opacity: 0,
        y: 20,
        duration: 0.6,
      }, "-=0.3")
      .from(".hero-actions", {
        opacity: 0,
        y: 30,
        duration: 0.5,
      }, "-=0.2");
  }, { scope: container });

  return (
    <section ref={container} className="relative border-b-2 border-base-300 min-h-screen flex items-center">
      <div className="max-w-6xl mx-auto px-6 py-24 lg:py-32 w-full">
        <div className="max-w-3xl mx-auto text-center space-y-8">
          <p className="hero-badge font-mono text-xs uppercase tracking-[0.2em] text-primary">
            [ CODE INTELLIGENCE SYSTEM ]
          </p>

          <h1 className="text-6xl lg:text-9xl font-black tracking-tight leading-[0.85] uppercase flex flex-col">
            <span className="hero-line-top">Librarian</span>
            <span className="hero-line-bottom flex items-center justify-center gap-4">
              <span className="hero-ai text-primary">AI</span>
            </span>
          </h1>

          <p className="hero-sub text-base-content/70 text-sm lg:text-base max-w-xl mx-auto leading-relaxed font-mono uppercase tracking-wider">
            Navigate and understand any codebase with AI-powered semantic search
            and natural language queries.
          </p>

          <div className="hero-actions">
            {isSignedIn ? (
              <button
                className="btn btn-lg px-12 text-lg"
                onClick={() => navigate("/app")}
              >
                Enter App
              </button>
            ) : (
              <div className="flex items-center justify-center gap-4">
                <SignInButton mode="modal">
                  <button className="btn btn-lg px-10">Sign In</button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button className="btn btn-lg btn-outline px-10">
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
