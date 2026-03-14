import { motion } from "framer-motion";

export default function GlassCard({ children, className = "", hover = false, glow = false, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.4, 0, 0.2, 1] }}
      className={`glass ${hover ? "glass-hover cursor-pointer" : ""} ${glow ? "glow-red" : ""} p-6 ${className}`}
    >
      {children}
    </motion.div>
  );
}
