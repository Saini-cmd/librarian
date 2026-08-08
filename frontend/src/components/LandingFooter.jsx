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
    <footer ref={section} className="bg-base-100 border-t border-base-content/10">
      <div className="footer-content max-w-6xl mx-auto px-6 py-10 text-center space-y-2">
        <p className="text-sm font-semibold text-base-content/70">
          Librarian AI
        </p>
        <p className="text-xs text-base-content/40">
          &copy; {new Date().getFullYear()} — Built with React, FastAPI &amp; Qdrant
        </p>
      </div>
    </footer>
  );
}
