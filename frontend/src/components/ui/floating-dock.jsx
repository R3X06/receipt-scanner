import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { GridPattern } from "@/components/ui/grid-pattern";

export const FloatingDock = ({ items, onSelect, className }) => {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const segWidth = 100 / items.length;

  return (
    <div
      className={cn(
        "kalla-stagger ${GLASS} relative flex w-full items-stretch gap-0 overflow-hidden rounded-2xl border border-white/5 bg-white/[0.025] p-1.5 backdrop-blur-xl",
        className
      )}
      onMouseLeave={() => setHoveredIndex(null)}
    >
      <GridPattern
        width={25}
        height={25}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        className="[mask-image:radial-gradient(120%_170%_at_50%_0%,white,transparent)] fill-white/[0.02] stroke-white/[0.04]"
      />
      <motion.div
        className="absolute inset-y-1.5 rounded-xl border border-primary/40 bg-primary/15"
        animate={{
          left: hoveredIndex !== null ? `calc(${hoveredIndex * segWidth}% + 6px)` : "6px",
          width: `calc(${segWidth}% - 12px)`,
          opacity: hoveredIndex !== null ? 1 : 0,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 32 }}
      />
      {items.map((item, i) => (
        <IconContainer
          key={item.dockKey}
          onSelect={onSelect}
          onHover={() => setHoveredIndex(i)}
          {...item}
        />
      ))}
    </div>
  );
};

function IconContainer({ title, icon, onSelect, onHover, ...item }) {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={() => onSelect(item.dockKey)}
      onMouseEnter={() => { setHovered(true); onHover(); }}
      onMouseLeave={() => setHovered(false)}
      onTouchStart={() => onHover()}
      aria-label={title}
      className="relative flex flex-1 flex-col items-center justify-center gap-1 py-3"
    >
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 2 }}
            className="absolute -top-8 left-1/2 hidden w-fit -translate-x-1/2 whitespace-pre rounded-md border border-white/10 bg-[#0E141B] px-2 py-0.5 text-xs text-foreground shadow-lg sm:block"
          >
            {title}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="relative z-10 flex h-5 w-5 items-center justify-center text-primary">{icon}</div>
    </button>
  );
}