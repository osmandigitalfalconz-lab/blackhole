import { motion, useReducedMotion } from 'framer-motion'

// Animated black hole for the hero: a swirling accretion disk around a
// black core, with a pulsing glow, gently floating. Pure framer-motion
// (no CSS keyframes); honours prefers-reduced-motion.
export default function BlackHole() {
  const reduceMotion = useReducedMotion()

  if (reduceMotion) {
    return (
      <div className="hero-hole" aria-hidden="true">
        <div className="glow" />
        <div className="disk" />
        <div className="core" />
      </div>
    )
  }

  return (
    <motion.div
      className="hero-hole"
      aria-hidden="true"
      animate={{ y: [0, -8, 0] }}
      transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
    >
      <motion.div
        className="glow"
        animate={{ opacity: [0.5, 1, 0.5], scale: [1, 1.08, 1] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="disk"
        animate={{ rotate: 360 }}
        transition={{ duration: 7, repeat: Infinity, ease: 'linear' }}
      />
      <div className="core" />
    </motion.div>
  )
}
