import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Sparkles, Mail, Lock, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [signUpSuccess, setSignUpSuccess] = useState(false);
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    if (isSignUp) {
      const { error } = await signUp(email, password);
      if (error) {
        setError(error);
      } else {
        setSignUpSuccess(true);
      }
    } else {
      const { error } = await signIn(email, password);
      if (error) {
        setError(error);
      } else {
        navigate('/');
      }
    }

    setLoading(false);
  };

  if (signUpSuccess) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <div className="w-full max-w-sm px-6 text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 border border-border/40 flex items-center justify-center mx-auto">
            <Mail className="w-7 h-7 text-primary/70" />
          </div>
          <h2 className="text-xl font-bold text-foreground">验证邮件已发送</h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            请检查你的邮箱 <span className="text-foreground font-medium">{email}</span>，点击验证链接完成注册。
          </p>
          <Button
            variant="ghost"
            className="mt-4 cursor-pointer"
            onClick={() => {
              setSignUpSuccess(false);
              setIsSignUp(false);
            }}
          >
            返回登录
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm px-6">
        <div className="space-y-6">
          {/* Logo */}
          <div className="text-center space-y-3">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 border border-border/40 flex items-center justify-center mx-auto">
              <Sparkles className="w-7 h-7 text-primary/70" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              {isSignUp ? '创建账户' : '登录灵构 LingForge'}
            </h1>
            <p className="text-sm text-muted-foreground">
              {isSignUp ? '注册后即可开始使用' : '登录后开始构建你的项目'}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-3">
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="邮箱地址"
                  required
                  className="w-full h-10 pl-10 pr-4 rounded-lg border border-border/80 bg-secondary/30 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition-all"
                />
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="密码"
                  required
                  minLength={6}
                  className="w-full h-10 pl-10 pr-4 rounded-lg border border-border/80 bg-secondary/30 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition-all"
                />
              </div>
            </div>

            {error && (
              <p className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-10 cursor-pointer transition-all duration-200"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : isSignUp ? (
                '注册'
              ) : (
                '登录'
              )}
            </Button>
          </form>

          {/* Toggle */}
          <p className="text-center text-xs text-muted-foreground">
            {isSignUp ? '已有账户？' : '没有账户？'}
            <button
              onClick={() => {
                setIsSignUp(!isSignUp);
                setError(null);
              }}
              className="text-primary hover:text-primary/80 font-medium ml-1 cursor-pointer transition-colors"
            >
              {isSignUp ? '登录' : '注册'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}