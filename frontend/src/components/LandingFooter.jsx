import { useRef, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

export default function LandingFooter() {
  const section = useRef(null);
  const ready = useRef(false);

  useLayoutEffect(() => {
    if (ready.current) return;
    ready.current = true;

    const ctx = gsap.context(() => {
      const content = section.current.querySelector(".footer-content");

      gsap.set(content, { opacity: 0, y: 30 });

      ScrollTrigger.create({
        trigger: section.current,
        start: "top 95%",
        toggleActions: "play none none none",
        onEnter: () => {
          gsap.to(content, {
            opacity: 1,
            y: 0,
            duration: 0.8,
            ease: "power3.out",
          });
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
    <footer ref={section} className="footer footer-horizontal footer-center p-10 bg-base-200 border-t-2 border-base-300">
      <div className="footer-content space-y-2">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
          [ LIBRARIAN AI ]
        </p>
        <p className="text-base-content/40 text-xs font-mono uppercase tracking-wider">
          &copy; {new Date().getFullYear()} — Built with React, FastAPI &amp; Qdrant
        </p>
      </div>
    </footer>
  );
}
