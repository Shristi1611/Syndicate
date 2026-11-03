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

const rupees = (n) => `₹${n.toLocaleString("en-IN")}`;

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

function TripResult({ trip }) {
  return (
    <section className="panel trip">
      <h2 className="panel-title">Your negotiated trip</h2>

      <div className="savings">
        <div>
          <div className="savings-big">{rupees(trip.saved)} saved</div>
          <div className="savings-sub">{trip.savings_pct}% below list price</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="trip-was">{rupees(trip.list_total)}</div>
          <div className="profile-value">{rupees(trip.final_total)}</div>
          <div className="savings-sub">
            {trip.within_budget
              ? `Within your ${rupees(trip.budget)} budget`
              : `Over your ${rupees(trip.budget)} budget`}
          </div>
        </div>
      </div>

      {trip.notes.map((note) => (
        <div key={note} className="status">
          {note}
        </div>
      ))}

      {trip.items.map((line) => (
        <div key={line.item_id} className="trip-line">
          <div>
            <div className="trip-name">{line.name}</div>
            <div className="trip-meta">
              {line.quantity} x {line.unit}
              {line.perks.length > 0 &&
                ` · includes ${line.perks.map((p) => p.replaceAll("_", " ")).join(", ")}`}
            </div>
          </div>
          <div className="trip-price">
            <span className="trip-was">{rupees(line.total)}</span>
            {rupees(line.final_total)}
          </div>
          <div />
          <div className="trip-saved">
            {line.saved > 0 ? `saved ${rupees(line.saved)}` : "list price"}
          </div>
        </div>
      ))}
    </section>
  );
}

export default function App() {
  const [messages, setMessages] = useState([{ role: "agent", text: GREETING }]);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [complete, setComplete] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [trip, setTrip] = useState(null);
  const [planning, setPlanning] = useState(false);
  const [tripError, setTripError] = useState("");
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
    setTrip(null); // the profile may change, so any old trip is out of date
    setTripError("");

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

  async function planTrip() {
    setPlanning(true);
    setTripError("");
    setTrip(null);

    try {
      const res = await fetch(`${API}/trip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Server returned ${res.status}`);
      }
      setTrip(await res.json());
    } catch (err) {
      setTripError(`Could not plan the trip: ${err.message}`);
    } finally {
      setPlanning(false);
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
            value={profile.budget_total === null ? null : rupees(profile.budget_total)}
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

          {complete && (
            <button className="plan-btn" onClick={planTrip} disabled={planning}>
              {planning ? "Negotiating with suppliers..." : "Plan my trip"}
            </button>
          )}
          {tripError && <div className="trip-error">{tripError}</div>}
        </aside>
      </div>

      {trip && <TripResult trip={trip} />}
    </div>
  );
}