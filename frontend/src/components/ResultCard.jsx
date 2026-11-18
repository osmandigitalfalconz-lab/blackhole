import { motion } from 'framer-motion'
import { fmtDuration } from '../lib.js'
import QualityButtons from './QualityButtons.jsx'

// Single-video result card: thumbnail, title, uploader/duration,
// platform badge, and the quality buttons. Pops in with a spring.
export default function ResultCard({ url, data }) {
  return (
    <motion.div
      className="result"
      initial={{ opacity: 0, scale: 0.97, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 22 }}
    >
      <div className="result-top">
        {data.thumbnail ? (
          <img src={data.thumbnail} alt="Video thumbnail" />
        ) : null}
        <div className="result-meta">
          <h3>{data.title}</h3>
          <div className="meta">
            {data.uploader || ''}
            {data.duration ? ` · ${fmtDuration(data.duration)}` : ''}
          </div>
          {data.platform ? (
            <span className="platform">{data.platform}</span>
          ) : null}
        </div>
      </div>
      <QualityButtons url={url} options={data.options} title={data.title} />
    </motion.div>
  )
}
