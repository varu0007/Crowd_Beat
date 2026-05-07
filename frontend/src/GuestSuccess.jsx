import { useI18n } from './i18n'

export default function GuestSuccess() {
  const { t } = useI18n()
  return (
    <div style={{padding:'3rem',textAlign:'center',fontSize:'1.2rem'}}>
      <div style={{fontSize:'3rem',marginBottom:'1rem'}}>🎵</div>
      <h2>{t.authSuccess}</h2>
      <p>{t.tasteAdded}</p>
    </div>
  )
}
