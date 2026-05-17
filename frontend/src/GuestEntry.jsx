import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from './api'
import { useI18n } from './i18n'

export default function GuestEntry() {
  const { t } = useI18n()
  const { sessionId } = useParams()
  useEffect(() => {
    if (sessionId) window.location.href = api.guestLoginUrl(sessionId)
  }, [sessionId])
  return <div style={{padding:'2rem',textAlign:'center'}}>{t.redirectingToSpotify}</div>
}
