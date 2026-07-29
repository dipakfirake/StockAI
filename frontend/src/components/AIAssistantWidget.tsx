import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send, X, Bot } from 'lucide-react'
import { aiApi } from '../services/api'

export default function AIAssistantWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<{role: 'user' | 'assistant', content: string}[]>([
    { role: 'assistant', content: 'Hi! I am your StockAI assistant. Ask me about the market, e.g. "How is the market today?" or "Should I buy RELIANCE.NS?"' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return

    const userMsg = input.trim()
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setInput('')
    setLoading(true)

    // Extract symbol if present (basic regex for Indian symbols)
    const symbolMatch = userMsg.match(/[A-Z0-9-]+\.NS/i)
    const symbol = symbolMatch ? symbolMatch[0] : undefined

    try {
      const res = await aiApi.chat(userMsg, symbol)
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }])
    } catch (err: any) {
      console.error(err)
      if (err.response?.status === 403) {
        setMessages(prev => [...prev, { role: 'assistant', content: 'This feature requires a PRO subscription.' }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I am having trouble connecting to the server.' }])
      }
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          background: 'var(--primary-color)',
          color: 'white',
          border: 'none',
          borderRadius: '50%',
          width: 60,
          height: 60,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          zIndex: 9999
        }}
      >
        <MessageSquare size={28} />
      </button>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      right: 24,
      width: 350,
      height: 500,
      background: 'var(--color-bg-primary)',
      border: '1px solid var(--color-border)',
      borderRadius: 12,
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
      zIndex: 9999,
      overflow: 'hidden'
    }}>
      <div style={{
        background: 'var(--color-bg-secondary)',
        padding: '16px',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
          <Bot size={20} color="var(--primary-color)" />
          StockAI Assistant
        </div>
        <button onClick={() => setIsOpen(false)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <X size={20} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            background: m.role === 'user' ? 'var(--primary-color)' : 'var(--color-bg-tertiary)',
            color: m.role === 'user' ? 'white' : 'var(--text-primary)',
            padding: '10px 14px',
            borderRadius: 12,
            borderBottomRightRadius: m.role === 'user' ? 2 : 12,
            borderBottomLeftRadius: m.role === 'assistant' ? 2 : 12,
            maxWidth: '85%',
            fontSize: 13,
            lineHeight: 1.5
          }}>
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: 'flex-start', background: 'var(--color-bg-tertiary)', padding: '10px 14px', borderRadius: 12, fontSize: 13, opacity: 0.7 }}>
            Typing...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSend} style={{ borderTop: '1px solid var(--color-border)', padding: 12, display: 'flex', gap: 8 }}>
        <input 
          className="input"
          style={{ flex: 1, borderRadius: 20 }}
          placeholder="Ask me anything..."
          value={input}
          onChange={e => setInput(e.target.value)}
        />
        <button type="submit" disabled={loading} style={{
          background: 'var(--primary-color)',
          color: 'white',
          border: 'none',
          borderRadius: '50%',
          width: 40,
          height: 40,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: loading ? 'not-allowed' : 'pointer'
        }}>
          <Send size={18} style={{ marginLeft: -2 }} />
        </button>
      </form>
    </div>
  )
}
