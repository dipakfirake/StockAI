import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send, X, Bot, Trash2, Sparkles } from 'lucide-react'
import { aiApi } from '../services/api'

const STORAGE_KEY = 'ai_assistant_history'
const MAX_PERSISTED = 12

const INITIAL_MSG = { role: 'assistant' as const, content: 'Hi! I am your StockAI assistant. Ask me about the market, e.g. "How is the market today?" or "Should I buy TCS.NS?"' }

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as { role: 'user' | 'assistant'; content: string }[]
  } catch { }
  return [INITIAL_MSG]
}

export default function AIAssistantWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>(loadHistory)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Persist chat history on every change
  useEffect(() => {
    const toSave = messages.slice(-MAX_PERSISTED)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  }, [messages])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  function clearHistory() {
    setMessages([INITIAL_MSG])
    localStorage.removeItem(STORAGE_KEY)
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return

    const userMsg = input.trim()
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setInput('')
    setLoading(true)

    // Extract symbol if present (basic regex for Indian symbols)
    const symbolMatch = userMsg.match(/[A-Z0-9-]+(?:\.NS)?/i)
    const symbol = symbolMatch ? symbolMatch[0] : undefined

    try {
      const res = await aiApi.chat(userMsg, symbol)
      const reply = res.data.reply || res.data.response || 'No response.'
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
    } catch (err: any) {
      console.error(err)
      if (err.response?.status === 403) {
        setMessages(prev => [...prev, { role: 'assistant', content: 'This feature requires a PRO subscription.' }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I am having trouble connecting to the server. Please try again in a moment.' }])
      }
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        id="ai-assistant-toggle"
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          color: 'white',
          border: 'none',
          borderRadius: '50%',
          width: 56,
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          boxShadow: '0 4px 20px rgba(59,130,246,0.4)',
          zIndex: 9000,
          transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.1)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = ''; }}
        title="AI Assistant (ask me anything!)"
      >
        <Sparkles size={22} />
      </button>
    )
  }

  return (
    <div
      className="animate-slide-right"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: 360,
        height: 520,
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
        borderRadius: 14,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(59,130,246,0.2)',
        zIndex: 9000,
        overflow: 'hidden'
      }}
    >
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #1e3a5f, #2d1b69)',
        padding: '14px 16px',
        borderBottom: '1px solid rgba(59,130,246,0.3)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: 'white', fontSize: 14 }}>
          <Sparkles size={16} color="#8b5cf6" />
          StockAI Assistant
          <span style={{ fontSize: 10, background: 'rgba(139,92,246,0.3)', color: '#c4b5fd', padding: '2px 6px', borderRadius: 10, marginLeft: 4 }}>AI</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={clearHistory}
            title="Clear history"
            style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer', padding: 5, borderRadius: 6, display: 'flex', alignItems: 'center' }}
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer', padding: 5, borderRadius: 6, display: 'flex', alignItems: 'center' }}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            background: m.role === 'user'
              ? 'linear-gradient(135deg, #3b82f6, #8b5cf6)'
              : 'var(--color-bg-card)',
            color: m.role === 'user' ? 'white' : 'var(--color-text-primary)',
            padding: '10px 13px',
            borderRadius: 12,
            borderBottomRightRadius: m.role === 'user' ? 3 : 12,
            borderBottomLeftRadius: m.role === 'assistant' ? 3 : 12,
            maxWidth: '87%',
            fontSize: 13,
            lineHeight: 1.5,
            border: m.role === 'assistant' ? '1px solid var(--color-border)' : 'none',
            animation: i === messages.length - 1 ? 'fadeInUp 0.25s ease forwards' : 'none',
          }}>
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={{
            alignSelf: 'flex-start',
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
            padding: '10px 14px',
            borderRadius: 12,
            fontSize: 13,
            display: 'flex',
            gap: 5,
            alignItems: 'center',
          }}>
            <span style={{ width: 6, height: 6, background: '#8b5cf6', borderRadius: '50%', animation: 'pulseDot 0.8s ease infinite' }} />
            <span style={{ width: 6, height: 6, background: '#8b5cf6', borderRadius: '50%', animation: 'pulseDot 0.8s ease 0.2s infinite' }} />
            <span style={{ width: 6, height: 6, background: '#8b5cf6', borderRadius: '50%', animation: 'pulseDot 0.8s ease 0.4s infinite' }} />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSend} style={{ borderTop: '1px solid var(--color-border)', padding: 10, display: 'flex', gap: 8 }}>
        <input
          className="input"
          style={{ flex: 1, borderRadius: 20, fontSize: 13, padding: '8px 14px' }}
          placeholder="Ask about stocks, market, signals..."
          value={input}
          onChange={e => setInput(e.target.value)}
        />
        <button type="submit" disabled={loading} style={{
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          color: 'white',
          border: 'none',
          borderRadius: '50%',
          width: 36,
          height: 36,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: loading ? 'not-allowed' : 'pointer',
          flexShrink: 0,
          opacity: loading ? 0.6 : 1,
          transition: 'opacity 0.2s',
        }}>
          <Send size={16} />
        </button>
      </form>
    </div>
  )
}
