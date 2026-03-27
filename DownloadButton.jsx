import { useState } from 'react'
import './DownloadButton.css'

export default function DownloadButton({ result }) {
  const [downloaded, setDownloaded] = useState(false)

  const handleDownload = () => {
    // Strip internal-only fields: graph, parse_stats, risk_explanation
    const cleanAccounts = (result.suspicious_accounts || []).map(
      ({ risk_explanation, ...rest }) => rest
    )
    const output = {
      suspicious_accounts: cleanAccounts,
      fraud_rings: result.fraud_rings,
      summary: result.summary,
    }
    // JavaScript loses the decimal point for whole-number floats (36.0 → 36).
    // Re-add ".0" suffix to score fields so the JSON matches the float type.
    const jsonStr = JSON.stringify(output, null, 2)
      .replace(/("(?:suspicion_score|risk_score)": )(\d+)(?![\d.])/g, '$1$2.0')
    const blob = new Blob(
      [jsonStr],
      { type: 'application/json' }
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `forensics_report_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    setDownloaded(true)
    setTimeout(() => setDownloaded(false), 2200)
  }

  return (
    <button className={`download-btn${downloaded ? ' done' : ''}`} onClick={handleDownload}>
      {downloaded ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      )}
      {downloaded ? 'Downloaded' : 'Export Report'}
    </button>
  )
}
