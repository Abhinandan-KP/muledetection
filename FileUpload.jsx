import { useRef, useState } from 'react'
import axios from 'axios'
import './FileUpload.css'

const SAMPLE_CSV = `transaction_id,sender_id,receiver_id,amount,timestamp
TXN_001,ACC_A,ACC_B,500.00,2024-01-01 10:00:00
TXN_002,ACC_B,ACC_C,490.00,2024-01-01 11:00:00
TXN_003,ACC_C,ACC_A,480.00,2024-01-01 12:00:00
TXN_004,ACC_D,ACC_E,200.00,2024-01-02 09:00:00
TXN_005,ACC_F,ACC_E,210.00,2024-01-02 09:30:00
TXN_006,ACC_G,ACC_E,195.00,2024-01-02 10:00:00
TXN_007,ACC_H,ACC_E,185.00,2024-01-02 10:30:00
TXN_008,ACC_I,ACC_E,220.00,2024-01-02 11:00:00
TXN_009,ACC_J,ACC_E,205.00,2024-01-02 11:30:00
TXN_010,ACC_K,ACC_E,215.00,2024-01-02 12:00:00
TXN_011,ACC_L,ACC_E,190.00,2024-01-02 12:30:00
TXN_012,ACC_M,ACC_E,200.00,2024-01-02 13:00:00
TXN_013,ACC_N,ACC_E,180.00,2024-01-02 13:30:00
TXN_014,ACC_O,ACC_E,225.00,2024-01-02 14:00:00
TXN_015,ACC_E,ACC_P,1800.00,2024-01-03 08:00:00`

const COLUMNS = [
  { name: 'transaction_id', type: 'String', desc: 'Unique identifier' },
  { name: 'sender_id',      type: 'String', desc: 'Sender account ID' },
  { name: 'receiver_id',    type: 'String', desc: 'Receiver account ID' },
  { name: 'amount',         type: 'Float',  desc: 'Transaction amount' },
  { name: 'timestamp',      type: 'DateTime', desc: 'YYYY-MM-DD HH:MM:SS' },
]

export default function FileUpload({ onResult, onLoading, onError, loading }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState(null)

  const handleFile = async (file) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      onError('Please upload a valid CSV file.')
      return
    }
    onError(null)
    onLoading(true)
    onResult(null)
    setFileName(file.name)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const apiBase = import.meta.env.VITE_API_URL || ''
      const { data } = await axios.post(`${apiBase}/analyze?detail=true`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      })
      onResult(data)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Analysis failed.'
      onError(msg)
    } finally {
      onLoading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const handleDragLeave = () => setDragging(false)

  const downloadSample = (e) => {
    e.stopPropagation()
    const blob = new Blob([SAMPLE_CSV], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'sample_transactions.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="upload-section">
      <div
        className={`dropzone ${dragging ? 'dragging' : ''} ${loading ? 'disabled' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !loading && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          onChange={(e) => { handleFile(e.target.files[0]); e.target.value = '' }}
        />

        {/* Upload Icon */}
        <div className="dropzone-visual">
          <div className="upload-icon-ring">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
        </div>

        <div className="dropzone-text">
          <h3 className="dropzone-title">
            {loading ? 'Analyzing…' : fileName ? `Uploaded: ${fileName}` : 'Upload Transaction Data'}
          </h3>
          <p className="dropzone-subtitle">
            Drop your CSV file here or <span className="text-accent">click to browse</span>
          </p>
          <p className="dropzone-hint">Max file size: 20 MB &middot; Up to 10,000 transactions</p>
        </div>
      </div>

      {/* Schema & Actions */}
      <div className="upload-meta">
        <div className="schema-card">
          <div className="schema-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>Expected CSV Schema</span>
          </div>
          <div className="schema-cols">
            {COLUMNS.map(c => (
              <div key={c.name} className="schema-col">
                <code className="col-name">{c.name}</code>
                <span className="col-type">{c.type}</span>
                <span className="col-desc">{c.desc}</span>
              </div>
            ))}
          </div>
        </div>

        <button className="btn-sample" onClick={downloadSample}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Download Sample CSV
        </button>
      </div>
    </section>
  )
}
