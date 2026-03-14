import { motion } from "framer-motion";

export default function PageHeader({ title, subtitle, icon: Icon }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="mb-8"
    >
      <div className="flex items-center gap-3 mb-2">
        {Icon && <Icon size={28} className="text-f1-red" />}
        <h1 className="text-3xl font-bold text-gradient">{title}</h1>
      </div>
      {subtitle && <p className="text-f1-muted text-sm ml-[40px]">{subtitle}</p>}
      <div className="mt-4 h-[1px] bg-gradient-to-r from-f1-red/40 via-f1-red/10 to-transparent" />
    </motion.div>
  );
}
