import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(username, password);
      localStorage.setItem("auth_token", res.data.token);
      navigate("/dashboard");
    } catch {
      setError("Invalid credentials. Try analyst / demo1234");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-800">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-4xl font-bold text-white">Breathe ESG</div>
          <div className="text-brand-200 mt-1 text-sm">Emissions Data Review Platform</div>
        </div>

        <div className="bg-white rounded-xl shadow-xl p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Sign in</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                required
              />
            </div>

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full btn-primary py-2.5 justify-center"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-4 text-xs text-gray-400 text-center">Demo: analyst / demo1234</p>
        </div>
      </div>
    </div>
  );
}
