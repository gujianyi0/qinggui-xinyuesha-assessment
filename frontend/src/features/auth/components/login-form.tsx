import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Fingerprint,
  MoonStar,
  Quote,
  ShieldCheck,
} from 'lucide-react'
import type { FormEvent } from 'react'
import { useState } from 'react'
import { ErrorNotice, Spinner } from '@/components/ui'
import { focusTextControlSurface } from '@/components/ui/input-surface'
import { isPublicMode } from '@/lib/runtime-config'
import { displayError } from '@/services/api'
import { signIn, signInGuest } from '@/services/auth'
import type { Auth } from '@/types/domain'

interface LoginFormProps {
  onLogin: (auth: Auth) => void
}
export default function LoginForm({ onLogin }: LoginFormProps) {
  const [username, setUsername] = useState('alice')
  const [password, setPassword] = useState('')
  const [isBusy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (isPublicMode) {
        let secret = localStorage.getItem('qinggui-visitor-secret')
        if (!secret) {
          secret = Array.from(
            crypto.getRandomValues(new Uint8Array(32)),
            (byte) => byte.toString(16).padStart(2, '0'),
          ).join('')
          localStorage.setItem('qinggui-visitor-secret', secret)
        }
        onLogin(await signInGuest(secret))
      } else onLogin(await signIn({ username, password }))
    } catch (error) {
      setError(displayError(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="login-shell">
      <section className="login-story" aria-label="轻归新月助手简介">
        <div className="brand">
          <span className="brand-mark">
            <MoonStar size={26} strokeWidth={1.5} />
          </span>
          <span>
            轻归 <span className="brand-separator">/</span> 新月助手
            <small>QINGGUI · GAME COMPANION</small>
          </span>
        </div>
        <div className="login-editorial">
          <div className="eyebrow">
            <span className="tiny-line" />
            新月杀 · 资料与反馈助手
          </div>
          <h1>
            每个结论，
            <br />
            都有<span>来处</span>
          </h1>
          <p>
            把规则查清，把条件说全。
            <br />
            从一句疑问，到有据可循的答案。
          </p>
          <div className="orbit-art" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="art-moon">
              <MoonStar size={104} strokeWidth={0.7} />
            </div>
            <span className="orbit-label label-one">
              <BookOpen size={14} /> 规则有出处
            </span>
            <span className="orbit-label label-two">
              <ShieldCheck size={14} /> 裁定有边界
            </span>
            <span className="orbit-point" />
          </div>
        </div>
        <div className="story-foot">
          <Quote size={18} />
          <span>资料检索 · 复杂裁定 · 玩家反馈</span>
          <span className="story-index">01 — 03</span>
        </div>
      </section>
      <section className="login-form-region">
        <div className="login-form-card">
          <span className="section-kicker">欢迎回来</span>
          <h2>开启一段有依据的对话</h2>
          <p className="muted">
            {isPublicMode
              ? '直接使用真实问答，模型费用由服务提供者承担'
              : '使用本地测试身份进入你的独立工作区'}
          </p>
          <form
            onSubmit={handleSubmit}
            className="login-form"
            onMouseDown={focusTextControlSurface}
          >
            {!isPublicMode && (
              <>
                <label htmlFor="username">测试身份</label>
                <fieldset className="account-switch" aria-label="选择测试身份">
                  {['alice', 'bob'].map((name) => (
                    <button
                      key={name}
                      type="button"
                      className={username === name ? 'selected' : ''}
                      onClick={() => setUsername(name)}
                      disabled={isBusy}
                    >
                      <span className={`avatar avatar-${name}`}>
                        {name[0].toUpperCase()}
                      </span>
                      <span>
                        {name}
                        <small>独立会话与记录</small>
                      </span>
                      {username === name && <CheckCircle2 size={16} />}
                    </button>
                  ))}
                </fieldset>
                <input
                  id="username"
                  className="sr-only"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                />
                <label htmlFor="password">登录密码</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入本地演示密码"
                  autoComplete="current-password"
                  required
                  disabled={isBusy}
                />
              </>
            )}
            {error && <ErrorNotice message={error} />}
            <button
              className="button primary login-submit"
              type="submit"
              disabled={isBusy || (!isPublicMode && !password)}
            >
              {isBusy ? (
                <Spinner label="正在登录" />
              ) : (
                <>
                  进入工作区
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
          <div className="privacy-note">
            <Fingerprint size={19} />
            <p>
              不同身份的数据分别保存
              <br />
              <span>
                {isPublicMode
                  ? '本浏览器保存访客身份；对话保存在提供者电脑。无需填写模型密钥。'
                  : '密码由本地环境配置，登录不会连接旧轻归记忆'}
              </span>
            </p>
          </div>
        </div>
        <footer className="login-footer">
          <span className="status-dot" />
          {isPublicMode ? '提供者电脑运行 · 内部考核测试' : '本地独立运行'}
          <span>新月杀学习项目</span>
        </footer>
      </section>
    </div>
  )
}
