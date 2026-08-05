import { useRef, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

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
        start: "top 50%",
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
    <section ref={section} className="border-b-2 border-base-300">
      <div className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-16 space-y-4">
          <p className="workflow-badge font-mono text-xs uppercase tracking-[0.2em] text-primary">
            [ WORKFLOW ]
          </p>
          <h2 className="workflow-heading text-3xl lg:text-5xl font-black tracking-tight uppercase">
            How it works
          </h2>
        </div>

        <div
          ref={gridRef}
          className="grid grid-cols-1 md:grid-cols-3 gap-0 border-2 border-base-300"
        >
          {steps.map((step, i) => (
            <div
              key={i}
              className={`step-card p-8 lg:p-10 border-b-2 md:border-b-0 ${
                i < steps.length - 1 ? "md:border-r-2" : ""
              } ${i === steps.length - 1 ? "border-b-0" : ""}`}
              style={{ perspective: "1000px" }}
            >
              <div className="space-y-4">
                <p className="font-mono text-5xl font-black text-primary">
                  {step.num}
                </p>
                <h3 className="text-xl font-bold uppercase tracking-tight">
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
