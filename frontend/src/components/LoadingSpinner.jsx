export default function LoadingSpinner({ text = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="relative w-12 h-12">
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-f1-red animate-spin" />
        <div className="absolute inset-1 rounded-full border-2 border-transparent border-b-white/20 animate-spin" style={{ animationDirection: "reverse", animationDuration: "1.5s" }} />
      </div>
      <p className="text-f1-muted text-sm font-medium">{text}</p>
    </div>
  );
}
