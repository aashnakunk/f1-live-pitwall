import { Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Layout from "./components/Layout";
import SessionGate from "./components/SessionGate";
import Home from "./pages/Home";
import RaceCommand from "./pages/RaceCommand";
import TelemetryLab from "./pages/TelemetryLab";
import PerformanceLab from "./pages/PerformanceLab";
import PitStrategy from "./pages/PitStrategy";
import CircuitLab from "./pages/CircuitLab";
import EnergyMap from "./pages/EnergyMap";
import RaceReplay from "./pages/RaceReplay";
import LivePitWall from "./pages/LivePitWall";
import AIDebrief from "./pages/AIDebrief";
import CompareGP from "./pages/CompareGP";

function Gated({ children }) {
  return <SessionGate>{children}</SessionGate>;
}

export default function App() {
  return (
    <AnimatePresence mode="wait">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route element={<Layout />}>
          <Route path="/command" element={<Gated><RaceCommand /></Gated>} />
          <Route path="/telemetry" element={<Gated><TelemetryLab /></Gated>} />
          <Route path="/circuit" element={<Gated><CircuitLab /></Gated>} />
          <Route path="/performance" element={<Gated><PerformanceLab /></Gated>} />
          <Route path="/pitstrategy" element={<Gated><PitStrategy /></Gated>} />
          <Route path="/energy" element={<Gated><EnergyMap /></Gated>} />
          <Route path="/replay" element={<Gated><RaceReplay /></Gated>} />
          <Route path="/live" element={<LivePitWall />} />
          <Route path="/debrief" element={<Gated><AIDebrief /></Gated>} />
          <Route path="/compare" element={<CompareGP />} />
        </Route>
      </Routes>
    </AnimatePresence>
  );
}
