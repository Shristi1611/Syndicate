import { useEffect, useRef, useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8000";

const EMPTY_PROFILE = {
  destination: null,
  nights: null,
  travellers: null,
  budget_total: null,
  stairs_free: false,
  interests: [],
};

const GREETING =
  "Hi! Tell me about your trip: where you'd like to go, for how long, who's travelling, and your budget.";

function ProfileRow({ label, value }) {
  const missing = value === null || value === undefined;
  return (
    <div className="profile-row">
      <span className="profile-label">{label}</span>
      <span className={missing ? "profile-value missing" : "profile-value"}>
        {missing ? "not set" : value}
      </span>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([{ role: "agent", text: GREETING }]);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [complete, setComplete] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, profile }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();

      setProfile(data.profile);
      setComplete(data.complete);
      setMessages((m) => [...m, { role: "agent", text: data.reply }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "system",
          text: `Could not reach the server (${err.message}). Is the backend running?`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1 className="brand">Syndicate</h1>
        <span className="tagline">A network of agents that negotiates your trip</span>
      </header>

      <div className="layout">
        <section className="panel chat">
          <h2 className="panel-title">Conversation</h2>
          <div className="messages">
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.text}
              </div>
            ))}
            {busy && <div className="msg agent">...</div>}
            <div ref={bottomRef} />
          </div>

          <form className="composer" onSubmit={send}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. Goa, 4 days, Rs 60k, my mom cannot climb stairs"
              maxLength={500}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !input.trim()}>
              Send
            </button>
          </form>
        </section>

        <aside className="panel">
          <h2 className="panel-title">Trip profile</h2>
          <ProfileRow label="Destination" value={profile.destination} />
          <ProfileRow label="Nights" value={profile.nights} />
          <ProfileRow label="Travellers" value={profile.travellers} />
          <ProfileRow
            label="Budget"
            value={
              profile.budget_total === null
                ? null
                : `₹${profile.budget_total.toLocaleString("en-IN")}`
            }
          />
          <ProfileRow
            label="Step-free access"
            value={profile.stairs_free ? "Required" : "Not needed"}
          />
          <div className="profile-row">
            <span className="profile-label">Interests</span>
            {profile.interests.length === 0 ? (
              <span className="profile-value missing">none yet</span>
            ) : (
              <span className="chips">
                {profile.interests.map((t) => (
                  <span key={t} className="chip">
                    {t}
                  </span>
                ))}
              </span>
            )}
          </div>

          <div className={complete ? "status ready" : "status"}>
            {complete
              ? "Profile complete. Ready to plan!"
              : "Answer the agent's questions to complete your profile."}
          </div>
        </aside>
      </div>
    </div>
  );
}