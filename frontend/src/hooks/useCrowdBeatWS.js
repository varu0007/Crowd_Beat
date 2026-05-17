import { useState, useEffect, useRef, useCallback } from 'react'

export function useCrowdBeatWS(sessionId) {
  const [recommendations, setRecommendations] = useState([])
  const [guestCount, setGuestCount] = useState(0)
  const [isColdStart, setIsColdStart] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const MAX_RETRY = 5

  const connect = useCallback(() => {
    if (!sessionId) return
    const WS_BASE = import.meta.env.VITE_WS_URL
    const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`)
    wsRef.current = ws

    ws.onopen = () => { setIsConnected(true); retryRef.current = 0 }
    ws.onclose = () => {
      setIsConnected(false)
      if (retryRef.current < MAX_RETRY) {
        retryRef.current += 1
        setTimeout(connect, 3000)
      }
    }
    ws.onerror = () => ws.close()
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'recommendations_update') {
        const recs = msg.recommendations ?? []
        setRecommendations(recs)
        // guest_count 和 is_cold_start 嵌在每条推荐记录里
        if (recs.length > 0) {
          setIsColdStart(recs[0].is_cold_start ?? false)
        }
      } else if (msg.type === 'guest_joined') {
        // 后端不发 guest_count，前端自增
        setGuestCount(prev => prev + 1)
      } else if (msg.type === 'session_closed') {
        setRecommendations([])
        setGuestCount(0)
        ws.close()
      }
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    connect()
    return () => {
      retryRef.current = MAX_RETRY  // 阻止 cleanup 后继续重连
      wsRef.current?.close()
    }
  }, [sessionId, connect])

  return { recommendations, guestCount, isColdStart, isConnected }
}
