import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

// ─── Theme ───────────────────────────────────────────────────────────────────

function getInitialTheme(): 'light' | 'dark' {
  try {
    const saved = localStorage.getItem('voxsync_theme')
    if (saved === 'dark' || saved === 'light') return saved
  } catch { /* ignore */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme)
  try { localStorage.setItem('voxsync_theme', theme) } catch { /* ignore */ }
}

// ─── Types ───────────────────────────────────────────────────────────────────

type JobStatus = {
  job_id: string
  status: 'queued' | 'processing' | 'done' | 'error'
  stage: string
  progress: number
  url?: string
  target_lang?: string
  video_url?: string | null
  subtitles_url?: string | null
  error?: string | null
  created_at?: string | null
  expires_at?: string | null
  files_deleted?: boolean
}

type AuthState = {
  token: string
  email: string
}

type View = 'home' | 'history' | 'login' | 'register'

// ─── Constants ───────────────────────────────────────────────────────────────

const LANGS: Array<{ code: string; label: string }> = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
  { code: 'it', label: 'Italiano' },
  { code: 'pt', label: 'Português' },
  { code: 'pl', label: 'Polski' },
  { code: 'nl', label: 'Nederlands' },
  { code: 'tr', label: 'Türkçe' },
  { code: 'uk', label: 'Українська' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'ar', label: 'العربية' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

function stageLabel(stage: string) {
  switch (stage) {
    case 'queued': return 'В очереди'
    case 'download': return 'Скачивание'
    case 'transcribe': return 'Распознавание'
    case 'translate': return 'Перевод'
    case 'tts': return 'Синтез речи'
    case 'mux': return 'Сборка видео'
    case 'done': return 'Готово'
    case 'error': return 'Ошибка'
    default: return stage
  }
}

function formatDate(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

// ─── API helpers ─────────────────────────────────────────────────────────────

async function apiRegister(email: string, password: string) {
  const body = new FormData()
  body.set('email', email)
  body.set('password', password)
  const res = await fetch('/api/register', { method: 'POST', body })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `Ошибка ${res.status}`)
  }
  return res.json() as Promise<{ access_token: string; email: string }>
}

async function apiLogin(email: string, password: string) {
  const body = new FormData()
  body.set('email', email)
  body.set('password', password)
  const res = await fetch('/api/login', { method: 'POST', body })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `Ошибка ${res.status}`)
  }
  return res.json() as Promise<{ access_token: string; email: string }>
}

async function apiStart(url: string, target_lang: string, token: string) {
  const body = new FormData()
  body.set('url', url)
  body.set('target_lang', target_lang)
  const res = await fetch('/api/process', {
    method: 'POST',
    body,
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json() as Promise<{ job_id: string }>
}

async function apiStatus(jobId: string, token: string): Promise<JobStatus> {
  const res = await fetch(`/api/status/${encodeURIComponent(jobId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

async function apiJobs(token: string): Promise<JobStatus[]> {
  const res = await fetch('/api/jobs', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

// ─── Auth storage ─────────────────────────────────────────────────────────────

function loadAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem('voxsync_auth')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveAuth(auth: AuthState) {
  localStorage.setItem('voxsync_auth', JSON.stringify(auth))
}

function clearAuth() {
  localStorage.removeItem('voxsync_auth')
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme)
  const [auth, setAuth] = useState<AuthState | null>(loadAuth)
  const [view, setView] = useState<View>('home')

  // Применяем тему при монтировании и при изменении
  useEffect(() => { applyTheme(theme) }, [theme])

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light')

  // Форма авторизации
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)

  // Задача
  const [url, setUrl] = useState('')
  const [targetLang, setTargetLang] = useState('ru')
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)

  // История
  const [history, setHistory] = useState<JobStatus[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const pollTimer = useRef<number | null>(null)

  const canStart = useMemo(() => url.trim().length > 0 && !isStarting && !!auth, [url, isStarting, auth])

  // Очистка таймера при размонтировании
  useEffect(() => {
    return () => { if (pollTimer.current) window.clearInterval(pollTimer.current) }
  }, [])

  // Polling статуса задачи
  useEffect(() => {
    if (!jobId || !auth) return

    const tick = async () => {
      try {
        const s = await apiStatus(jobId, auth.token)
        setJob(s)
        setTaskError(null)
        if (s.status === 'done' || s.status === 'error') {
          if (pollTimer.current) window.clearInterval(pollTimer.current)
          pollTimer.current = null
        }
      } catch (e) {
        setTaskError(e instanceof Error ? e.message : 'Ошибка опроса')
      }
    }

    void tick()
    if (pollTimer.current) window.clearInterval(pollTimer.current)
    pollTimer.current = window.setInterval(() => void tick(), 1500)

    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }, [jobId, auth])

  // Загрузка истории при переключении на вкладку
  useEffect(() => {
    if (view === 'history' && auth) {
      setHistoryLoading(true)
      apiJobs(auth.token)
        .then(setHistory)
        .catch(() => setHistory([]))
        .finally(() => setHistoryLoading(false))
    }
  }, [view, auth])

  // ── Handlers ──

  const handleLogin = async () => {
    setAuthLoading(true)
    setAuthError(null)
    try {
      const data = await apiLogin(authEmail, authPassword)
      const a: AuthState = { token: data.access_token, email: data.email }
      saveAuth(a)
      setAuth(a)
      setView('home')
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : 'Ошибка входа')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleRegister = async () => {
    setAuthLoading(true)
    setAuthError(null)
    try {
      const data = await apiRegister(authEmail, authPassword)
      const a: AuthState = { token: data.access_token, email: data.email }
      saveAuth(a)
      setAuth(a)
      setView('home')
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : 'Ошибка регистрации')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = () => {
    clearAuth()
    setAuth(null)
    setJobId(null)
    setJob(null)
    setView('login')
  }

  const onStart = async () => {
    if (!auth) return
    setIsStarting(true)
    setTaskError(null)
    setJob(null)
    try {
      const { job_id } = await apiStart(url.trim(), targetLang, auth.token)
      setJobId(job_id)
    } catch (e) {
      setTaskError(e instanceof Error ? e.message : 'Ошибка запуска')
    } finally {
      setIsStarting(false)
    }
  }

  const onReset = () => {
    if (pollTimer.current) window.clearInterval(pollTimer.current)
    pollTimer.current = null
    setJobId(null)
    setJob(null)
    setTaskError(null)
    setUrl('')
  }

  const progress = clamp(job?.progress ?? 0, 0, 100)

  // ── Auth views ──

  if (view === 'login' || view === 'register') {
    const isLogin = view === 'login'
    return (
      <div className="page">
        <header className="header">
          <div className="brand">VOXsync</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="muted">Дубляж видео: ASR → перевод → TTS → mux</div>
            <button className="themeBtn" onClick={toggleTheme} title="Переключить тему">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </header>
        <main className="main">
          <section className="card" style={{ maxWidth: 400, margin: '0 auto' }}>
            <h1>{isLogin ? 'Вход' : 'Регистрация'}</h1>
            <label className="label">
              Email
              <input className="input" type="email" value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)} placeholder="user@example.com" />
            </label>
            <label className="label">
              Пароль
              <input className="input" type="password" value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)} placeholder="минимум 6 символов" />
            </label>
            {authError && <div className="alert error">{authError}</div>}
            <div className="row" style={{ marginTop: 16 }}>
              <button className="button" disabled={authLoading}
                onClick={isLogin ? handleLogin : handleRegister}>
                {authLoading ? '...' : isLogin ? 'Войти' : 'Зарегистрироваться'}
              </button>
              <button className="button secondary"
                onClick={() => { setAuthError(null); setView(isLogin ? 'register' : 'login') }}>
                {isLogin ? 'Регистрация' : 'Уже есть аккаунт'}
              </button>
            </div>
          </section>
        </main>
      </div>
    )
  }

  // ── History view ──

  if (view === 'history') {
    return (
      <div className="page">
        <header className="header">
          <div className="brand">VOXsync</div>
          <nav className="nav">
            <button className="navBtn" onClick={() => setView('home')}>Новая задача</button>
            <button className="navBtn active" onClick={() => setView('history')}>История</button>
            <span className="muted">{auth?.email}</span>
            <button className="navBtn" onClick={handleLogout}>Выйти</button>
            <button className="themeBtn" onClick={toggleTheme} title="Переключить тему">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </nav>
        </header>
        <main className="main">
          <section className="card">
            <h1>История задач</h1>
            {historyLoading && <div className="muted">Загрузка...</div>}
            {!historyLoading && history.length === 0 && (
              <div className="muted">Задач пока нет.</div>
            )}
            {history.map((j) => (
              <div key={j.job_id} className="historyItem">
                <div className="historyMeta">
                  <span className={`badge ${j.status}`}>{stageLabel(j.stage ?? j.status)}</span>
                  <span className="muted">{formatDate(j.created_at)}</span>
                  {j.expires_at && !j.files_deleted && (
                    <span className="muted">Удалится: {formatDate(j.expires_at)}</span>
                  )}
                  {j.files_deleted && <span className="muted badge error">Файлы удалены</span>}
                </div>
                <div className="historyUrl muted">{j.url}</div>
                <div className="historyLinks">
                  {j.video_url && !j.files_deleted && (
                    <a className="link" href={j.video_url} target="_blank" rel="noreferrer">
                      Скачать видео ({j.target_lang})
                    </a>
                  )}
                  {j.subtitles_url && !j.files_deleted && (
                    <a className="link" href={j.subtitles_url} target="_blank" rel="noreferrer">
                      Субтитры
                    </a>
                  )}
                  {j.status === 'error' && (
                    <span className="alert error" style={{ display: 'inline', padding: '2px 8px' }}>
                      {j.error ?? 'Ошибка'}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </section>
        </main>
      </div>
    )
  }

  // ── Home view ──

  return (
    <div className="page">
      <header className="header">
        <div className="brand">VOXsync</div>
        <nav className="nav">
          <button className="navBtn active" onClick={() => setView('home')}>Новая задача</button>
          <button className="navBtn" onClick={() => setView('history')}>История</button>
          {auth
            ? <><span className="muted">{auth.email}</span><button className="navBtn" onClick={handleLogout}>Выйти</button></>
            : <button className="navBtn" onClick={() => setView('login')}>Войти</button>
          }
          <button className="themeBtn" onClick={toggleTheme} title="Переключить тему">
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </nav>
      </header>

      <main className="main">
        <section className="card">
          <h2>Создать задачу</h2>

          {!auth && (
            <div className="alert">
              <a className="link" onClick={() => setView('login')} style={{ cursor: 'pointer' }}>Войдите</a>, чтобы запустить дубляж.
            </div>
          )}

          <label className="label">
            Ссылка на видео
            <input className="input" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..." inputMode="url" />
          </label>

          <div className="row">
            <label className="label" style={{ flex: 1 }}>
              Язык
              <select className="input" value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
                {LANGS.map((l) => (
                  <option key={l.code} value={l.code}>{l.label} ({l.code})</option>
                ))}
              </select>
            </label>
            <div className="actions">
              <button className="button" onClick={onStart} disabled={!canStart}>
                {isStarting ? 'Запуск…' : 'Запустить'}
              </button>
              <button className="button secondary" onClick={onReset} disabled={!jobId && !job}>
                Сброс
              </button>
            </div>
          </div>

          {taskError && <div className="alert error">{taskError}</div>}
        </section>

        <section className="card">
          <h2>Статус</h2>

          {!jobId && !job && <div className="muted">Задача ещё не запущена.</div>}

          {(jobId || job) && (
            <>
              <div className="kv">
                <div className="k">job_id</div>
                <div className="v mono">{job?.job_id ?? jobId}</div>
                <div className="k">status</div>
                <div className="v">{job?.status ?? 'queued'}</div>
                <div className="k">stage</div>
                <div className="v">{stageLabel(job?.stage ?? 'queued')}</div>
              </div>

              <div className="progress">
                <div className="progressBar" style={{ width: `${progress}%` }} />
              </div>
              <div className="muted">{progress}%</div>

              {job?.status === 'error' && (
                <div className="alert error">{job.error ?? 'Ошибка обработки'}</div>
              )}

              {job?.status === 'done' && job.video_url && (
                <div className="result">
                  <h3>Результат</h3>
                  <video className="video" controls crossOrigin="anonymous">
                    <source src={job.video_url} type="video/mp4" />
                    {job.subtitles_url && (
                      <track default kind="subtitles" srcLang={targetLang}
                        src={job.subtitles_url} label={`Subtitles (${targetLang})`} />
                    )}
                  </video>
                  <div className="row" style={{ marginTop: 12 }}>
                    <a className="link" href={job.video_url} target="_blank" rel="noreferrer">Скачать видео</a>
                    {job.subtitles_url && (
                      <a className="link" href={job.subtitles_url} target="_blank" rel="noreferrer">Скачать субтитры</a>
                    )}
                  </div>
                  {job.expires_at && (
                    <div className="muted" style={{ marginTop: 8 }}>
                      ⏳ Файлы доступны до {formatDate(job.expires_at)}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </main>

      <footer className="footer muted">
        API: /api/process · /api/status/{'{job_id}'} · /api/jobs · Артефакты: /storage/jobs/{'<job_id>'}
      </footer>
    </div>
  )
}
