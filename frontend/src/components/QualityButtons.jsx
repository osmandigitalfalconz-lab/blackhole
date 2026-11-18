import { useState } from 'react'
import { motion } from 'framer-motion'
import { downloadUrl } from '../lib.js'

const listVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
}

const spring = { type: 'spring', stiffness: 400, damping: 20 }

// Quality buttons for one video: one MP4 button per quality plus the
// MP3 audio button. Uses opt.kind and opt.id exactly as /api/info
// returned them. Clicking navigates to /api/download (same as before).
export default function QualityButtons({ url, options, title }) {
  const [preparing, setPreparing] = useState(null)

  const handleClick = (opt) => {
    setPreparing(opt.id)
    window.location.href = downloadUrl(url, opt, title)
    setTimeout(() => setPreparing((cur) => (cur === opt.id ? null : cur)), 4000)
  }

  return (
    <motion.div
      className="qualities"
      variants={listVariants}
      initial="hidden"
      animate="show"
    >
      {options.map((opt) => {
        const label = opt.kind === 'audio' ? '🎵 MP3 audio' : `${opt.label} MP4`
        const size = opt.size_human
          ? `${opt.size_human} · ${opt.ext.toUpperCase()}`
          : opt.ext.toUpperCase()
        const isPreparing = preparing === opt.id
        return (
          <motion.button
            key={opt.id}
            type="button"
            className={`q-btn${opt.kind === 'audio' ? ' mp3' : ''}`}
            variants={itemVariants}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.97 }}
            transition={spring}
            disabled={isPreparing}
            onClick={() => handleClick(opt)}
          >
            {isPreparing ? 'Preparing download…' : label}
            <small>{size}</small>
          </motion.button>
        )
      })}
    </motion.div>
  )
}
