import { Drawer } from "vaul";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useMediaQuery } from "@/hooks/useMediaQuery";

const NOISE_MASK =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

function NoiseOverlay({ color = "#5b33a4", opacity = 0.15 }) {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-0"
      style={{
        backgroundColor: color,
        WebkitMaskImage: NOISE_MASK,
        maskImage: NOISE_MASK,
        WebkitMaskSize: "120px 120px",
        maskSize: "120px 120px",
        opacity,
      }}
    />
  );
}

export function ResponsiveDialog({ open, onOpenChange, title, className, children }) {
  const isDesktop = useMediaQuery("(min-width: 640px)");

  if (isDesktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={className}>
          <div className="relative overflow-hidden rounded-[inherit]">
            <NoiseOverlay />
            <div className="relative z-10">
              <DialogTitle className="sr-only">{title}</DialogTitle>
              {children}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs" />
        <Drawer.Content className="fixed inset-x-0 bottom-0 z-50 flex max-h-[88vh] flex-col overflow-hidden rounded-t-2xl border-t border-white/10 bg-[#0E141B] outline-none">
          <NoiseOverlay />
          <div className="relative z-10 mx-auto mt-3 h-1.5 w-10 shrink-0 rounded-full bg-white/20" />
          <Drawer.Title className="sr-only">{title}</Drawer.Title>
          <div className="relative z-10 overflow-y-auto glass-scroll px-4 pb-6 pt-2">{children}</div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}