import { cn } from "@/lib/utils";
import { IconLayoutNavbarCollapse } from "@tabler/icons-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { GridPattern } from "@/components/ui/grid-pattern";

export const FloatingDock = ({ items, onSelect, desktopClassName, mobileClassName }) => {
  return (
    <>
      <FloatingDockDesktop items={items} onSelect={onSelect} className={desktopClassName} />
      <FloatingDockMobile items={items} onSelect={onSelect} className={mobileClassName} />
    </>
  );
};

const FloatingDockMobile = ({ items, onSelect, className }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn("relative block sm:hidden", className)}>
      <AnimatePresence>
        {open && (
          <motion.div layoutId="nav" className="absolute inset-x-0 bottom-full mb-2 flex flex-col gap-2">
            {items.map((item, idx) => (
              <motion.div
                key={item.dockKey}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10, transition: { delay: idx * 0.05 } }}
                transition={{ delay: (items.length - 1 - idx) * 0.05 }}
              >
                <button
                  onClick={() => { onSelect(item.dockKey); setOpen(false); }}
                  aria-label={item.title}
                  className="flex h-10 w-full items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-3 backdrop-blur-xl"
                >
                  <div className="h-4 w-4 text-primary">{item.icon}</div>
                  <span className="text-sm font-medium">{item.title}</span>
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <button
        onClick={() => setOpen(!open)}
        aria-label="Open menu"
        className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] backdrop-blur-xl"
      >
        <IconLayoutNavbarCollapse className="h-5 w-5 text-muted-foreground" />
      </button>
    </div>
  );
};

const FloatingDockDesktop = ({ items, onSelect, className }) => {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const segWidth = 100 / items.length;

  return (
    <div
      className={cn(
        "relative hidden w-full items-stretch gap-0 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.05] p-1.5 backdrop-blur-xl sm:flex",
        className
      )}
      onMouseLeave={() => setHoveredIndex(null)}
    >
      <GridPattern
        width={24}
        height={24}
        className="[mask-image:radial-gradient(120%_100%_at_50%_0%,white,transparent)] fill-white/[0.04] stroke-white/[0.08]"
      />
      <motion.div
        className="absolute inset-y-1.5 rounded-xl bg-primary/15 border border-primary/40"
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
      aria-label={title}
      className="relative flex flex-1 flex-col items-center justify-center gap-1 py-3"
    >
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 2 }}
            className="absolute -top-8 left-1/2 w-fit -translate-x-1/2 whitespace-pre rounded-md border border-white/10 bg-[#0E141B] px-2 py-0.5 text-xs text-foreground shadow-lg"
          >
            {title}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="relative z-10 flex h-5 w-5 items-center justify-center text-primary">{icon}</div>
    </button>
  );
}