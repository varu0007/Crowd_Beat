import React from 'react'
import { useI18n } from './i18n'
import { Music } from 'lucide-react'

export default function GuestSuccess() {
  const { t } = useI18n()

  return (
    <div style={{ padding: '3rem', textAlign: 'center', fontSize: '1.2rem' }}>
      <div style={{ marginBottom: '1rem' }}><Music size={48} /></div>
      <h2>{t.authSuccess}</h2>
      <p>{t.tasteAdded}</p>
    </div>
  )
}

