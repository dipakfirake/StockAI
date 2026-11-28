import { useState, useRef, useEffect } from 'react'
import { MessageSquare, Send, X, Bot, Trash2, Sparkles, Zap } from 'lucide-react'
import { aiApi, stocksApi } from '../services/api'

const STORAGE_KEY = 'ai_assistant_history'
const MAX_PERSISTED = 12

interface StockSuggestion {
  symbol: string
  name: string
  exchange: string
  type?: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  cached?: boolean
}

const INITIAL_MSG = { 
  role: 'assistant' as const, 
  content: 'Hi! I am your StockAI Institutional Assistant powered by Groq & Advanced Multi-Cap RAG. Ask me for setups on any Large, Mid, or Small-Cap stock (e.g. "Should I buy TCS?", "Analyze Suzlon", "IREDA target"), market regime ("How is Nifty today?"), or technical concepts ("What is Anchor VWAP?").' 
}

const QUICK_PROMPTS = [
  'Nifty Regime',
  'Should I buy TCS?',
  'Polycab Setup',
  'Analyze Suzlon',
  'What is Anchor VWAP?',
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

function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as ChatMessage[]
  } catch { }
  return [INITIAL_MSG]
}

export default function AIAssistantWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>(loadHistory)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // '@' Stock Mention Autocomplete State
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([])
  const [selectedIdx, setSelectedIdx] = useState<number>(0)
  const [showSuggestions, setShowSuggestions] = useState(false)

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

  // Debounced search for '@' stock mentions
  useEffect(() => {
    if (mentionQuery === null || !showSuggestions) {
      setSuggestions([])
      return
    }

    const timer = setTimeout(async () => {
      try {
        const q = mentionQuery.trim()
        if (q.length === 0) {
          // Default popular multi-cap suggestions when user just types '@'
          setSuggestions([
            { symbol: 'PCJEWELLER.NS', name: 'PC Jeweller', exchange: 'NSE' },
            { symbol: 'RELIANCE.NS', name: 'Reliance Industries', exchange: 'NSE' },
            { symbol: 'TCS.NS', name: 'Tata Consultancy Services', exchange: 'NSE' },
            { symbol: 'POLYCAB.NS', name: 'Polycab India', exchange: 'NSE' },
            { symbol: 'SUZLON.NS', name: 'Suzlon Energy', exchange: 'NSE' },
            { symbol: 'IREDA.NS', name: 'Indian Renewable Energy', exchange: 'NSE' },
            { symbol: 'TATAMOTORS.NS', name: 'Tata Motors', exchange: 'NSE' },
            { symbol: 'CDSL.NS', name: 'Central Depository Services', exchange: 'NSE' }
          ])
          return
        }

        const res = await stocksApi.search(q)
        const results = res.data?.results || []
        setSuggestions(results.slice(0, 7))
      } catch (err) {
        console.debug('Mention search error:', err)
      }
    }, 120)

    return () => clearTimeout(timer)
  }, [mentionQuery, showSuggestions])

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setInput(val)

    // Check if there's an '@' mention query before cursor
    const cursorPos = e.target.selectionStart || val.length
    const textBeforeCursor = val.slice(0, cursorPos)
    const match = textBeforeCursor.match(/@([a-zA-Z0-9-]*)$/)

    if (match) {
      setMentionQuery(match[1])
      setShowSuggestions(true)
      setSelectedIdx(0)
    } else {
      setShowSuggestions(false)
      setMentionQuery(null)
    }
  }

  function selectSuggestion(s: StockSuggestion) {
    const rawSymbol = s.symbol.replace('.NS', '').replace('.BO', '')
    const inputVal = input
    const cursorPos = inputRef.current?.selectionStart || inputVal.length
    const textBeforeCursor = inputVal.slice(0, cursorPos)
    const textAfterCursor = inputVal.slice(cursorPos)

    // Replace '@mentionQuery' with '@RAW_SYMBOL '
    const updatedBefore = textBeforeCursor.replace(/@([a-zA-Z0-9-]*)$/, `@${rawSymbol} `)
    const newInput = updatedBefore + textAfterCursor

    setInput(newInput)
    setShowSuggestions(false)
    setMentionQuery(null)

    // Restore focus to input
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus()
        const newPos = updatedBefore.length
        inputRef.current.setSelectionRange(newPos, newPos)
      }
    }, 10)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestions || suggestions.length === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx(prev => (prev + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx(prev => (prev - 1 + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      if (suggestions[selectedIdx]) {
        e.preventDefault()
        selectSuggestion(suggestions[selectedIdx])
      }
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  function clearHistory() {
    setMessages([INITIAL_MSG])
    localStorage.removeItem(STORAGE_KEY)
  }

  async function sendMessage(text: string) {
    if (!text.trim()) return

    const userMsg = text.trim()
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setInput('')
    setShowSuggestions(false)
    setLoading(true)

    try {
      const res = await aiApi.chat(userMsg)
      const reply = res.data.reply || res.data.response || 'No response.'
      const isCached = Boolean(res.data.cached)
      setMessages(prev => [...prev, { role: 'assistant', content: reply, cached: isCached }])
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
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.06)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = ''; }}
        title="Market Assistant"
        aria-label="Open Market Assistant"
      >
        <MessageSquare size={18} />
      </button>
    )
  }

  return (
    <div
      className="ai-assistant-chat-panel animate-slide-right"
    >
      {/* Header */}
      <div style={{
        background: 'var(--color-bg-secondary)',
        padding: '13px 16px',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: 'var(--color-text-primary)', fontSize: 14 }}>
          <MessageSquare size={16} color="var(--color-accent-blue)" />
          <span>Market Assistant</span>
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
            {m.cached && (
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#34d399', background: 'rgba(16, 185, 129, 0.15)', padding: '2px 6px', borderRadius: 4, marginBottom: 4 }}>
                <Zap size={10} /> Instant Cached (0 tokens)
              </div>
            )}
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

      {/* Floating '@' Stock Mention Autocomplete Dropdown */}
      <div style={{ position: 'relative' }}>
        {showSuggestions && suggestions.length > 0 && (
          <div style={{
            position: 'absolute',
            bottom: 56,
            left: 10,
            right: 10,
            background: 'var(--color-bg-card, #1a2234)',
            border: '1px solid rgba(59, 130, 246, 0.4)',
            borderRadius: 10,
            boxShadow: '0 -10px 25px rgba(0,0,0,0.6)',
            maxHeight: 220,
            overflowY: 'auto',
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
            padding: 4
          }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: '#38bdf8',
              padding: '5px 8px',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span>TAG STOCK (@)</span>
              <span style={{ fontSize: 9, color: 'var(--color-text-secondary, #94a3b8)', fontWeight: 400 }}>↑↓ to navigate, Enter to select</span>
            </div>
            {suggestions.map((s, idx) => (
              <div
                key={s.symbol}
                onClick={() => selectSuggestion(s)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '7px 9px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: idx === selectedIdx ? 'rgba(59, 130, 246, 0.25)' : 'transparent',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={() => setSelectedIdx(idx)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                  <span style={{
                    background: 'rgba(16, 185, 129, 0.18)',
                    color: '#34d399',
                    fontWeight: 700,
                    fontSize: 11,
                    padding: '2px 6px',
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    flexShrink: 0
                  }}>
                    @{s.symbol.replace('.NS', '').replace('.BO', '')}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--color-text-primary, #fff)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.name}
                  </span>
                </div>
                <span style={{
                  fontSize: 10,
                  color: 'var(--color-text-secondary, #94a3b8)',
                  background: 'rgba(255,255,255,0.06)',
                  padding: '1px 5px',
                  borderRadius: 4,
                  flexShrink: 0
                }}>
                  {s.exchange || 'NSE'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSend} style={{ borderTop: '1px solid var(--color-border)', padding: 10, display: 'flex', gap: 8 }}>
        <input
          ref={inputRef}
          className="input"
          style={{ flex: 1, borderRadius: 20, fontSize: 13, padding: '8px 14px' }}
          placeholder="Ask anything or type @ to mention stock (e.g. @PC)..."
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
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
