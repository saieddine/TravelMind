import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MapPin, Compass, Wallet, CalendarDays, Sparkles, ShieldCheck, ArrowRight, LoaderCircle, ExternalLink } from 'lucide-react'
import './style.css'

const API = 'http://127.0.0.1:8000'

function App() {
  const [form, setForm] = useState({
    departure_city: "Xi'an", budget_cny: 1500, duration_days: 5,
    interests: ['nature', 'local food', 'culture'], destination: '', pace: 'normal'
  })
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const interestOptions = ['nature', 'local food', 'culture', 'photography', 'less crowded']
  function update(key, value) { setForm(prev => ({ ...prev, [key]: value })) }
  function toggleInterest(item) {
    setForm(prev => ({ ...prev, interests: prev.interests.includes(item)
      ? prev.interests.filter(x => x !== item) : [...prev.interests, item] }))
  }

  async function planTrip(e) {
    e.preventDefault(); setLoading(true); setError(''); setResult(null)
    try {
      const response = await fetch(`${API}/api/plan`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, budget_cny: Number(form.budget_cny), duration_days: Number(form.duration_days), destination: form.destination || null })
      })
      const data = await response.json()
      if (!response.ok || data.error) throw new Error(data.error || 'Unable to create plan.')
      setResult(data)
    } catch (err) {
      setError(`${err.message}. Make sure the FastAPI backend is running at ${API}.`)
    } finally { setLoading(false) }
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand-mark"><Compass size={25}/></div>
      <div><div className="brand">Travel<span>Mind</span></div><div className="tagline">Your trip, planned by collaborating AI agents</div></div>
      <div className="prototype-pill">30-DAY MVP</div>
    </header>

    <main className="layout">
      <section className="intro">
        <div className="eyebrow"><Sparkles size={15}/> MULTI-AGENT TRAVEL PLANNER</div>
        <h1>Less searching.<br/><span>More discovering.</span></h1>
        <p>Tell us your budget, time, and travel style. TravelMind coordinates specialized agents to propose a trip and check whether the estimated cost fits.</p>
        <div className="trust-row"><span><ShieldCheck size={16}/> Budget check</span><span><MapPin size={16}/> Place links</span><span><CalendarDays size={16}/> Day-by-day plan</span></div>
      </section>

      <section className="planner-card">
        <div className="section-heading"><div><div className="step-label">YOUR JOURNEY</div><h2>Plan a trip</h2></div><span className="tiny-icon"><Compass size={19}/></span></div>
        <form onSubmit={planTrip}>
          <label>Leaving from<input value={form.departure_city} onChange={e=>update('departure_city',e.target.value)} required placeholder="e.g. Xi'an"/></label>
          <label>Destination <span className="optional">optional</span>
            <select value={form.destination} onChange={e=>update('destination',e.target.value)}>
              <option value="">Surprise me — choose for me</option><option>Chengdu</option><option>Lanzhou</option><option>Luoyang</option>
            </select>
          </label>
          <div className="two-fields">
            <label><span className="label-icon"><Wallet size={14}/> Budget (CNY)</span><input type="number" min="100" max="100000" value={form.budget_cny} onChange={e=>update('budget_cny',e.target.value)} required/></label>
            <label><span className="label-icon"><CalendarDays size={14}/> Days</span><select value={form.duration_days} onChange={e=>update('duration_days',e.target.value)}>{[1,2,3,4,5,6,7,8,9,10,11,12,13,14].map(n=><option key={n} value={n}>{n} days</option>)}</select></label>
          </div>
          <fieldset><legend>What do you enjoy?</legend><div className="chips">{interestOptions.map(item=><button type="button" key={item} onClick={()=>toggleInterest(item)} className={`chip ${form.interests.includes(item)?'selected':''}`}>{item}</button>)}</div></fieldset>
          <label>Travel pace<select value={form.pace} onChange={e=>update('pace',e.target.value)}><option value="relaxed">Relaxed — fewer stops</option><option value="normal">Balanced</option><option value="intensive">Intensive — more stops</option></select></label>
          <button className="primary-button" type="submit" disabled={loading}>{loading?<><LoaderCircle className="spin" size={18}/> Agents are planning...</>:<><Sparkles size={17}/> Plan my trip <ArrowRight size={17}/></>}</button>
          <p className="fine-print">Prototype estimates only. No tickets or hotels are booked.</p>
        </form>
      </section>

      <section className="results">
        {!result && !error && <div className="empty-state"><div className="empty-art"><Compass size={54}/><span>✦</span></div><h2>Your next story starts here</h2><p>Your agent team will rank supported destinations, draft a day-by-day plan, and check the estimated budget.</p><div className="agent-mini-grid"><div><span className="agent-dot purple"/>Destination</div><div><span className="agent-dot blue"/>Itinerary</div><div><span className="agent-dot green"/>Validation</div></div></div>}
        {error && <div className="error-box"><strong>Couldn't plan the trip</strong><p>{error}</p></div>}
        {result && <div className="result-content">
          <div className="result-heading"><div><div className="step-label">YOUR TRAVEL PLAN</div><h2>{result.itinerary.destination}</h2><p>{result.itinerary.summary}</p></div><div className="destination-icon"><MapPin size={24}/></div></div>
          <div className="metric-grid">
            <div className="metric"><span>Estimated total</span><strong>¥{result.itinerary.estimated_total_cny.toLocaleString()}</strong></div>
            <div className="metric"><span>Your budget</span><strong>¥{result.itinerary.budget_cny.toLocaleString()}</strong></div>
            <div className={`metric ${result.validation.valid?'good':'bad'}`}><span>Budget status</span><strong>{result.validation.valid?'Within budget':'Over budget'}</strong></div>
          </div>
          {!result.validation.valid && <div className="warning">{result.validation.issues.join(' ')}</div>}
          <p className="disclaimer">{result.itinerary.cost_disclaimer}</p>
          <h3>Day-by-day itinerary</h3>
          <div className="day-list">{result.itinerary.days.map(day=><article className="day-card" key={day.day}><div className="day-number">DAY {day.day}</div><div className="day-main"><h4>{day.title}</h4>{day.activities.map((a,i)=><div className="activity" key={i}><div><strong>{a.name}</strong><small>{a.category} · about {a.duration_hours}h</small></div><span>¥{a.estimated_cost_cny}<a href={a.map_search_url} target="_blank" rel="noreferrer" aria-label={`Search ${a.name} on Baidu Maps`}><ExternalLink size={14}/></a></span></div>)}</div><div className="day-cost">¥{day.estimated_cost_cny}<small>estimated</small></div></article>)}</div>
          <div className="agent-log"><h3><ShieldCheck size={17}/> Agent activity</h3>{result.agent_events.map((ev,i)=><div className="log-row" key={i}><span className="log-check">✓</span><div><strong>{ev.agent}</strong><p>{ev.message}</p></div></div>)}</div>
          <details className="candidate-details"><summary>See destination ranking data</summary>{result.destination_candidates.map((d,i)=><div key={d.name} className="candidate-row"><span>{i+1}. {d.name}</span><span>score {d.score} · transport estimate ¥{d.estimated_transport_cny}</span></div>)}</details>
          <button className="secondary-button" onClick={()=>{setResult(null);window.scrollTo({top:0,behavior:'smooth'})}}>Plan another trip</button>
        </div>}
      </section>
    </main>
    <footer><span>TravelMind · Student project prototype</span><span>Reasoning + deterministic checks, with transparent estimates</span></footer>
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
