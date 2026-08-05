import { useRef, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

const features = [
  {
    title: "Semantic Code Search",
    desc: "Ask natural language questions about your codebase. Librarian AI understands context, not just keywords.",
    metric: "HYBRID",
  },
  {
    title: "Multi-Language Support",
    desc: "Python, JavaScript, TypeScript, Rust, Go, Java, Kotlin, C, C++, C#, Ruby — AST-aware chunking for all.",
    metric: "12 LANG",
  },
  {
    title: "Streaming Responses",
    desc: "Real-time token-by-token answers with source citations. See the reasoning as it happens.",
    metric: "REALTIME",
  },
  {
    title: "Battle-Tested Pipeline",
    desc: "Clone, chunk, summarize, embed, and query in one seamless flow. Built for production.",
    metric: "5 STAGE",
  },
];

export default function LandingFeatures() {
  const section = useRef(null);
  const gridRef = useRef(null);
  const ready = useRef(false);

  useLayoutEffect(() => {
    if (ready.current) return;
    ready.current = true;

    const ctx = gsap.context(() => {
      const cards = gridRef.current.querySelectorAll(".feature-card");
      const badge = section.current.querySelector(".features-badge");
      const heading = section.current.querySelector(".features-heading");

      gsap.set([badge, heading], { opacity: 0, y: 30 });
      gsap.set(cards, { opacity: 0, y: 60 });

      ScrollTrigger.create({
        trigger: section.current,
        start: "top 50%",
        toggleActions: "play none none none",
        onEnter: () => {
          const tl = gsap.timeline();
          tl.to(badge, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" })
            .to(heading, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, "-=0.2")
            .to(cards, { opacity: 1, y: 0, duration: 0.7, stagger: 0.12, ease: "power3.out" }, "-=0.3");
        },
      });

      ScrollTrigger.refresh();
    }, section);

    return () => {
      ctx.revert();
      ready.current = false;
    };
  }, []);

  return (
    <section ref={section} className="border-b-2 border-base-300">
      <div className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-16 space-y-4">
          <p className="features-badge font-mono text-xs uppercase tracking-[0.2em] text-primary">
            [ CAPABILITIES ]
          </p>
          <h2 className="features-heading text-3xl lg:text-5xl font-black tracking-tight uppercase">
            What it does
          </h2>
        </div>

        <div
          ref={gridRef}
          className="grid grid-cols-1 md:grid-cols-2 gap-0 border-2 border-base-300"
        >
          {features.map((f, i) => (
            <div
              key={i}
              className={`feature-card p-8 lg:p-10 border-b-2 border-base-300 ${
                i % 2 === 0 && i < features.length - 1 ? "md:border-r-2" : ""
              } ${i >= features.length - 2 ? "md:border-b-0" : ""} ${
                i === features.length - 1 ? "border-b-0" : ""
              }`}
            >
              <div className="space-y-4">
                <p className="font-mono text-xs text-primary uppercase tracking-widest">
                  {f.metric}
                </p>
                <h3 className="text-xl font-bold uppercase tracking-tight">
                  {f.title}
                </h3>
                <p className="text-base-content/60 text-sm leading-relaxed">
                  {f.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
