import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BlackHole from './components/BlackHole.jsx'
import QualityButtons from './components/QualityButtons.jsx'
import ResultCard from './components/ResultCard.jsx'
import { fetchInfo, fmtDuration } from './lib.js'

const PILLS = [
  { b: 'YouTube', rest: ' · videos & Shorts' },
  { b: 'Facebook', rest: ' · videos & reels' },
  { b: 'Instagram', rest: ' · reels & videos' },
  { b: 'X', rest: '' },
  { b: 'Pinterest', rest: '' },
  { b: 'Threads', rest: '' },
  { b: 'Reddit', rest: '' },
  { b: 'Dailymotion', rest: '' },
  { b: 'Snapchat', rest: '' },
  { b: 'RedNote', rest: '' },
]

const STEPS = [
  { n: 1, h: 'Copy the link', p: 'Open the video in its app and tap Share, then Copy link.' },
  { n: 2, h: 'Paste it here', p: 'Drop the link in the box above and pick a quality — or MP3 audio.' },
  { n: 3, h: 'Save the file', p: 'Click a quality and the video downloads straight to your device.' },
]

const FAQS = [
  { q: 'Is BlackHole free?', a: 'Yes — it is completely free, with no signup and no limits for normal use.' },
  { q: 'Which sites can I download from?', a: 'YouTube (videos and Shorts), Facebook, Instagram (reels and videos), X, Pinterest, Threads, Reddit, Dailymotion, Snapchat and RedNote. Just paste any public link.' },
  { q: 'What quality and formats can I download?', a: 'MP4 video up to 4K where available (4K, 1080p, 720p, 480p, 360p) and MP3 audio.' },
  { q: 'Can I use it on my phone?', a: 'Yes — it works in any phone or computer browser. No app needed.' },
  { q: 'Do I need to install anything or sign up?', a: 'No. There is nothing to install and no account needed — just paste a link and download.' },
  { q: 'Is it safe?', a: 'Yes. We do not ask for any personal information and only work with public videos. Files are removed from our server after they are sent to you.' },
]

const easeOut = [0.22, 1, 0.36, 1]
const spring = { type: 'spring', stiffness: 400, damping: 20 }

const heroVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1, delayChildren: 0.05 } },
}
const heroItem = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: easeOut } },
}
const pillsVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04, delayChildren: 0.35 } },
}
const pillItem = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: easeOut } },
}

function FaqItem({ q, a, open, onToggle }) {
  return (
    <div className="faq">
      <button type="button" className="faq-q" onClick={onToggle} aria-expanded={open}>
        {q}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="faq-a"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <p>{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function App() {
  const [url, setUrl] = useState('')
  const [multiOpen, setMultiOpen] = useState(false)
  const [multiText, setMultiText] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'loading' | 'error', text }
  const [result, setResult] = useState(null)
  const [multiResults, setMultiResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [openFaq, setOpenFaq] = useState(0)
  const keyRef = useRef(0)

  const handleSubmit = async (e) => {
    e.preventDefault()
    const urls = multiOpen
      ? multiText.split(/\n+/).map((s) => s.trim()).filter(Boolean).slice(0, 20)
      : [url.trim()].filter(Boolean)
    if (!urls.length) {
      setStatus({ kind: 'error', text: 'Please paste a video link first.' })
      return
    }
    setResult(null)
    setMultiResults([])
    setBusy(true)

    if (!multiOpen) {
      const link = urls[0]
      setStatus({ kind: 'loading', text: 'Reading link…' })
      try {
        const data = await fetchInfo(link)
        setStatus(null)
        setResult({ url: link, data })
      } catch (err) {
        setStatus({ kind: 'error', text: err.message })
      } finally {
        setBusy(false)
      }
      return
    }

    // Multiple links: fetch each in turn, one compact card per video.
    setStatus({ kind: 'loading', text: `Reading ${urls.length} link${urls.length > 1 ? 's' : ''}…` })
    for (const link of urls) {
      const key = ++keyRef.current
      setMultiResults((prev) => [...prev, { key, url: link, state: 'loading' }])
      try {
        const data = await fetchInfo(link)
        setMultiResults((prev) =>
          prev.map((item) => (item.key === key ? { ...item, state: 'done', data } : item)),
        )
      } catch (err) {
        setMultiResults((prev) =>
          prev.map((item) => (item.key === key ? { ...item, state: 'error', error: err.message } : item)),
        )
      }
    }
    setStatus(null)
    setBusy(false)
  }

  return (
    <div className="wrap">
      <header>
        <nav className="nav">
          <a className="logo" href="/"><span className="hole"></span>BLACKHOLE</a>
          <div className="nav-links">
            <a href="/">Home</a>
            <a href="/how-to.html">How to download</a>
            <a href="/terms.html">Terms</a>
            <a href="/privacy.html">Privacy</a>
          </div>
        </nav>
      </header>

      <main>
        <motion.section
          className="hero"
          variants={heroVariants}
          initial="hidden"
          animate="show"
        >
          <motion.div variants={heroItem}>
            <BlackHole />
          </motion.div>
          <motion.h1 variants={heroItem}>
            Download videos free, <span className="accent">online</span>
          </motion.h1>
          <motion.p variants={heroItem}>
            Pull any public video into the hole — no signup, no watermark, no app needed.
          </motion.p>
        </motion.section>

        <motion.section
          className="dl-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.28, ease: easeOut }}
        >
          <form onSubmit={handleSubmit}>
            <div className="dl-row">
              <input
                type="url"
                placeholder="Paste a video link here — YouTube, Facebook, Instagram…"
                autoComplete="off"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <motion.button
                className="btn"
                type="submit"
                disabled={busy}
                whileHover={busy ? {} : { scale: 1.02, y: -1 }}
                whileTap={busy ? {} : { scale: 0.97 }}
                transition={spring}
              >
                Download
              </motion.button>
            </div>
            <div className="multi-toggle">
              <button type="button" onClick={() => setMultiOpen((v) => !v)}>
                {multiOpen ? '– Hide multiple links' : '＋ Multiple links'}
              </button>
            </div>
            <AnimatePresence initial={false}>
              {multiOpen && (
                <motion.div
                  className="multi-area"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: 'easeInOut' }}
                >
                  <textarea
                    placeholder="Paste one link per line (up to 20)…"
                    value={multiText}
                    onChange={(e) => setMultiText(e.target.value)}
                  />
                </motion.div>
              )}
            </AnimatePresence>
            <p className="fineprint">
              By using our service you accept our <a href="/terms.html">Terms of Service</a> and{' '}
              <a href="/privacy.html">Privacy Policy</a>. Only public videos — private or login-only
              content is not supported.
            </p>
          </form>

          {status && (
            <div className="status" style={{ display: 'block' }}>
              {status.kind === 'loading' ? (
                <span><span className="spin"></span>{status.text}</span>
              ) : (
                <div className="error">{status.text}</div>
              )}
            </div>
          )}

          <AnimatePresence>
            {result && (
              <ResultCard key={result.url} url={result.url} data={result.data} />
            )}
          </AnimatePresence>

          <div className="multi-result">
            {multiResults.map((item) => (
              <motion.div
                key={item.key}
                className="mr-item"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: easeOut }}
              >
                {item.state === 'done' && item.data.thumbnail ? (
                  <img src={item.data.thumbnail} alt="" />
                ) : null}
                <div>
                  <div className="t">
                    {item.state === 'done' ? item.data.title : item.url}
                  </div>
                  <div className="s" style={item.state === 'error' ? { color: '#fca5a5' } : undefined}>
                    {item.state === 'loading'
                      ? 'Reading link…'
                      : item.state === 'error'
                        ? item.error
                        : `${item.data.uploader || ''}${item.data.duration ? ` · ${fmtDuration(item.data.duration)}` : ''}`}
                  </div>
                </div>
                {item.state === 'done' && (
                  <div className="q">
                    <QualityButtons
                      url={item.url}
                      options={item.data.options.slice(0, 4)}
                      title={item.data.title}
                    />
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.div
          className="pills"
          variants={pillsVariants}
          initial="hidden"
          animate="show"
        >
          {PILLS.map((pill) => (
            <motion.span key={pill.b} className="pill" variants={pillItem}>
              <b>{pill.b}</b>{pill.rest}
            </motion.span>
          ))}
        </motion.div>

        <motion.section
          className="block"
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.6, ease: easeOut }}
        >
          <h2>How it works</h2>
          <div className="steps">
            {STEPS.map((step) => (
              <div className="step" key={step.n}>
                <div className="n">{step.n}</div>
                <h3>{step.h}</h3>
                <p>{step.p}</p>
              </div>
            ))}
          </div>
        </motion.section>

        <motion.section
          className="block"
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.6, ease: easeOut }}
        >
          <h2>Frequently asked questions</h2>
          {FAQS.map((faq, i) => (
            <FaqItem
              key={faq.q}
              q={faq.q}
              a={faq.a}
              open={openFaq === i}
              onToggle={() => setOpenFaq(openFaq === i ? -1 : i)}
            />
          ))}
        </motion.section>
      </main>

      <footer>
        <div className="links">
          <a href="/how-to.html">How to download</a>
          <a href="/terms.html">Terms of Service</a>
          <a href="/privacy.html">Privacy Policy</a>
          <a href="/disclaimer.html">Disclaimer &amp; DMCA</a>
        </div>
        <p>BlackHole does not host any videos. It only helps you save public content for personal use — you are responsible for respecting copyright. Not affiliated with, endorsed by or sponsored by any of the platforms named; all trademarks belong to their respective owners.</p>
        <p>© 2026 BlackHole · For personal use only</p>
      </footer>
    </div>
  )
}
