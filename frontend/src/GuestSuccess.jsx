import React from 'react'
import { useParams } from 'react-router-dom'
import { useI18n } from './i18n'
import { Music, Download } from 'lucide-react'
import { api } from './api'

function toCSV(rows) {
  const headers = Object.keys(rows[0] || {})
  const escape = (v) => {
    const s = String(v ?? '')
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  return [headers.join(','), ...rows.map(r => headers.map(h => escape(r[h])).join(','))].join('\n')
}

export default function GuestSuccess() {
  const { t } = useI18n()
  const { guestId } = useParams()

  const handleDownload = () => {
    const data = api.getGuestProfileCsvRows(guestId)
    const csv = toCSV(data)

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'guest_profile.csv'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ padding: '3rem', textAlign: 'center', fontSize: '1.2rem' }}>
      <div style={{ marginBottom: '1rem' }}><Music size={48} /></div>
      <h2>{t.authSuccess}</h2>
      <p>{t.tasteAdded}</p>

      <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center', gap: 12 }}>
        <button
          className="nb-btn nb-btn--primary"
          onClick={handleDownload}
          style={{ fontWeight: 900, display: 'inline-flex', gap: 8, alignItems: 'center' }}
        >
          <Download size={16} /> Download CSV
        </button>
      </div>
    </div>
  )
}

