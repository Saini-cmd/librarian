import { useRef, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import ClayShapes from "./ClayShapes";

const steps = [
  {
    num: "01",
    title: "Paste a Repo URL",
    desc: "Enter any public GitHub repository URL. Librarian AI clones it and prepares for analysis.",
  },
  {
    num: "02",
    title: "Automatic Ingestion",
    desc: "The pipeline scans, chunks, summarizes, and embeds your codebase — no configuration needed.",
  },
  {
    num: "03",
    title: "Ask Questions",
    desc: "Chat naturally about the code. Find functions, understand logic, trace dependencies instantly.",
  },
];

const SECTION_SHAPES = [
  { type: "blob", size: 56, x: 6, y: 10, color: "text-primary/20", float: 14, duration: 7 },
  { type: "egg", size: 42, x: 92, y: 12, color: "text-success/20", float: 10, duration: 8 },
  { type: "circle", size: 28, x: 90, y: 84, color: "text-accent/25", float: 12, duration: 6 },
  { type: "ring", size: 36, x: 8, y: 86, color: "text-warning/25", spin: -360, duration: 8 },
];

export default function LandingHowItWorks() {
  const section = useRef(null);
  const gridRef = useRef(null);
  const ready = useRef(false);

  useLayoutEffect(() => {
    if (ready.current) return;
    ready.current = true;

    const ctx = gsap.context(() => {
      const cards = gridRef.current.querySelectorAll(".step-card");
      const badge = section.current.querySelector(".workflow-badge");
      const heading = section.current.querySelector(".workflow-heading");

      gsap.set([badge, heading], { opacity: 0, y: 30 });
      gsap.set(cards, { opacity: 0, x: -80, rotateX: 10 });

      ScrollTrigger.create({
        trigger: section.current,
        start: "top 55%",
        toggleActions: "play none none none",
        onEnter: () => {
          const tl = gsap.timeline();
          tl.to(badge, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" })
            .to(heading, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, "-=0.2")
            .to(cards, { opacity: 1, x: 0, rotateX: 0, duration: 0.8, stagger: 0.15, ease: "power3.out" }, "-=0.3");
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
          <span className="workflow-badge inline-block rounded-full bg-white px-5 py-2 text-sm font-semibold text-primary clay">
            Workflow
          </span>
          <h2 className="workflow-heading text-4xl lg:text-5xl font-extrabold tracking-tight text-base-content">
            How it works
          </h2>
        </div>

        <div ref={gridRef} className="relative grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((step, i) => (
            <div
              key={i}
              className={`step-card clay relative rounded-3xl bg-white p-8 space-y-4 ${
                i === 1 ? "md:translate-y-10" : ""
              }`}
              style={{ perspective: "1000px" }}
            >
              <span className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary text-primary-content text-xl font-extrabold clay relative">
                {step.num}
              </span>
              <div className="space-y-2">
                <h3 className="text-xl font-bold text-base-content">
                  {step.title}
                </h3>
                <p className="text-base-content/60 text-sm leading-relaxed">
                  {step.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
