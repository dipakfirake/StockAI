import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send, X, Bot, Trash2, Sparkles, Zap } from 'lucide-react'
import { aiApi } from '../services/api'

const STORAGE_KEY = 'ai_assistant_history'
const MAX_PERSISTED = 12

const INITIAL_MSG = { 
  role: 'assistant' as const, 
  content: 'Hi! I am your StockAI Institutional Assistant powered by Groq & Advanced Quantitative RAG. Ask me for stock setups (e.g. "Should I buy TCS?"), market regime ("How is Nifty today?"), or technical concepts ("What is Anchor VWAP?").' 
}

const QUICK_PROMPTS = [
  '📊 Nifty Regime',
  '🎯 Should I buy TCS?',
  '🚀 Tata Motors Setup',
  '💡 What is Anchor VWAP?',
]

function renderFormattedMessage(content: string) {
  const lines = content.split('\n')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {lines.map((line, idx) => {
        const trimmed = line.trim()
        if (!trimmed) return <div key={idx} style={{ height: 4 }} />
        
        // Header ###
        if (trimmed.startsWith('### ')) {
          return (
            <div key={idx} style={{ fontWeight: 700, fontSize: 13, color: '#38bdf8', marginBottom: 2 }}>
              {trimmed.replace('### ', '')}
            </div>
          )
        }
        
        // Bullet point - ...
        const isBullet = trimmed.startsWith('- ') || trimmed.startsWith('• ')
        const cleanLine = isBullet ? trimmed.substring(2) : trimmed

        // Parse bold **text**
        const parts = cleanLine.split(/(\*\*.*?\*\*)/g)
        const renderedParts = parts.map((part, pIdx) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={pIdx} style={{ color: 'var(--color-text-primary)' }}>{part.slice(2, -2)}</strong>
          }
          return part
        })

        if (isBullet) {
          return (
            <div key={idx} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
              <span style={{ color: '#8b5cf6', flexShrink: 0 }}>•</span>
              <span style={{ flex: 1 }}>{renderedParts}</span>
            </div>
          )
        }

        return <div key={idx}>{renderedParts}</div>
      })}
    </div>
  )
}

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

  async function sendMessage(text: string) {
    if (!text.trim()) return

    const userMsg = text.trim()
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

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    await sendMessage(input)
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        id="ai-assistant-toggle"
        className="ai-assistant-toggle-btn"
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.08)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = ''; }}
        title="AI Assistant (ask me anything!)"
      >
        <Sparkles size={20} />
      </button>
    )
  }

  return (
    <div
      className="ai-assistant-chat-panel animate-slide-right"
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
          <span style={{ fontSize: 10, background: 'rgba(16, 185, 129, 0.25)', color: '#34d399', padding: '2px 6px', borderRadius: 10, marginLeft: 4, display: 'flex', alignItems: 'center', gap: 3 }}>
            <Zap size={10} /> Groq + RAG
          </span>
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
            {m.role === 'assistant' ? renderFormattedMessage(m.content) : m.content}
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

      {/* Quick Prompts */}
      <div style={{ padding: '6px 12px', display: 'flex', gap: 6, overflowX: 'auto', borderTop: '1px solid rgba(255,255,255,0.05)', scrollbarWidth: 'none' }}>
        {QUICK_PROMPTS.map((prompt, pIdx) => (
          <button
            key={pIdx}
            type="button"
            onClick={() => sendMessage(prompt)}
            disabled={loading}
            style={{
              fontSize: 11,
              whiteSpace: 'nowrap',
              padding: '3px 8px',
              borderRadius: 12,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'var(--color-text-secondary)',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(59, 130, 246, 0.15)'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#3b82f6'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.04)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.1)'; }}
          >
            {prompt}
          </button>
        ))}
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
