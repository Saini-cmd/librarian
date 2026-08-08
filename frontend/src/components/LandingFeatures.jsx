import { useRef, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import ClayShapes from "./ClayShapes";

const features = [
  {
    title: "Semantic Code Search",
    desc: "Ask natural language questions about your codebase. Librarian AI understands context, not just keywords — so you get answers about intent, not string matches.",
    metric: "HYBRID",
    chip: "bg-primary/15 text-primary",
    span: "md:col-span-2",
  },
  {
    title: "Multi-Language Support",
    desc: "AST-aware chunking for a dozen+ languages.",
    metric: "12 LANG",
    chip: "bg-accent/15 text-accent",
    span: "md:col-span-1",
  },
  {
    title: "Streaming Responses",
    desc: "Token-by-token answers with source citations.",
    metric: "REALTIME",
    chip: "bg-success/15 text-success",
    span: "md:col-span-1",
  },
  {
    title: "Battle-Tested Pipeline",
    desc: "Clone, chunk, summarize, embed, and query in one seamless flow. Built for production from day one — every stage is observable and recoverable.",
    metric: "5 STAGE",
    chip: "bg-warning/15 text-warning",
    span: "md:col-span-2",
  },
];

const SECTION_SHAPES = [
  { type: "circle", size: 36, x: 4, y: 12, color: "text-primary/20", float: 12, duration: 6 },
  { type: "squircle", size: 44, x: 94, y: 20, color: "text-accent/20", spin: 360, float: 10, duration: 9 },
  { type: "ring", size: 40, x: 96, y: 80, color: "text-success/20", spin: -360, duration: 8 },
  { type: "egg", size: 34, x: 2, y: 82, color: "text-warning/25", float: 12, duration: 7 },
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
        start: "top 55%",
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
    <section ref={section} className="relative bg-base-100">
      <ClayShapes shapes={SECTION_SHAPES} />

      <div className="max-w-6xl mx-auto px-6 py-24 relative">
        <div className="text-center mb-14 space-y-4">
          <span className="features-badge inline-block rounded-full bg-white px-5 py-2 text-sm font-semibold text-primary clay">
            Capabilities
          </span>
          <h2 className="features-heading text-4xl lg:text-5xl font-extrabold tracking-tight text-base-content">
            What it does
          </h2>
        </div>

        <div ref={gridRef} className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {features.map((f, i) => (
            <div
              key={i}
              className={`feature-card clay rounded-3xl bg-white p-8 space-y-4 ${f.span}`}
            >
              <span
                className={`inline-flex items-center justify-center w-12 h-12 rounded-2xl font-bold text-lg ${f.chip}`}
              >
                ▣
              </span>
              <p className="font-mono text-xs font-semibold text-primary">
                {f.metric}
              </p>
              <h3 className="text-xl font-bold text-base-content">
                {f.title}
              </h3>
              <p className="text-base-content/60 text-sm leading-relaxed">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
