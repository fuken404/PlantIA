// PlantIA · lee la API y compone una lámina por planta.
const REFRESH_MS = 60_000

const TEXT = {
  es: {
    kicker: 'Registro de cultivo · vol. II',
    lead: 'Dos plantas de interior medidas cada treinta minutos. Las lecturas viajan de un sensor a una API en FastAPI, se archivan en Firestore y Gemini redacta la nota de cuidado.',
    place: 'Bogotá · 2.640 m s. n. m.',
    loading: 'Revisando los sensores…',
    error: 'Los sensores no responden en este momento. Vuelve a intentarlo en un rato.',
    plate: (n) => `Lámina ${n}`,
    humidity: 'Humedad del suelo', temperature: 'Temperatura',
    idealHumidity: 'Rango de humedad', idealTemperature: 'Rango de temperatura',
    lastReading: 'Última lectura', state: 'Estado', idealBand: 'rango ideal',
    stamp: { healthy: 'En orden', attention: 'Atención', critical: 'Crítico', none: 'Sin datos' },
    waiting: 'Esperando más lecturas para trazar la curva.',
    noNote: 'La nota de cuidado aparecerá con la primera lectura.',
    signedBy: { gemini: 'Nota redactada por Gemini', rules: 'Nota del asesor por reglas' },
    updated: (when) => `actualizado ${when}`,
    hoursAgo: (h) => `−${h} h`, now: 'ahora',
    methodTitle: 'Método',
    m1: 'Un ESP32 —o el simulador, mientras tanto— envía humedad y temperatura cada 30 minutos.',
    m2: 'FastAPI valida la llave del dispositivo y archiva la lectura en Firestore.',
    m3: 'Gemini lee la lectura, el historial y el rango ideal y redacta una nota; si no responde, la escribe un asesor por reglas.',
    docs: 'Documentación de la API', code: 'Código fuente', by: 'Cultivado por',
  },
  en: {
    kicker: 'Growing log · vol. II',
    lead: 'Two houseplants measured every thirty minutes. Readings travel from a sensor to a FastAPI service, get filed in Firestore, and Gemini writes the care note.',
    place: 'Bogotá · 2,640 m above sea level',
    loading: 'Checking the sensors…',
    error: 'The sensors are not responding right now. Please try again shortly.',
    plate: (n) => `Plate ${n}`,
    humidity: 'Soil moisture', temperature: 'Temperature',
    idealHumidity: 'Moisture range', idealTemperature: 'Temperature range',
    lastReading: 'Last reading', state: 'Status', idealBand: 'ideal range',
    stamp: { healthy: 'Thriving', attention: 'Attention', critical: 'Critical', none: 'No data' },
    waiting: 'Waiting for more readings to draw the curve.',
    noNote: 'The care note will appear with the first reading.',
    signedBy: { gemini: 'Note written by Gemini', rules: 'Note from the rule-based advisor' },
    updated: (when) => `updated ${when}`,
    hoursAgo: (h) => `−${h} h`, now: 'now',
    methodTitle: 'Method',
    m1: 'An ESP32 —or, for now, the simulator— sends moisture and temperature every 30 minutes.',
    m2: 'FastAPI checks the device key and files the reading in Firestore.',
    m3: 'Gemini reads the reading, the history and the ideal range and writes a note; if it fails, a rule-based advisor writes it.',
    docs: 'API documentation', code: 'Source code', by: 'Grown by',
  },
}

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
const HISTORY_HOURS = 24

let lang = 'es'
try { lang = localStorage.getItem('plantia-lang') || '' } catch { /* sin almacenamiento */ }
if (lang !== 'es' && lang !== 'en') lang = navigator.language.toLowerCase().startsWith('es') ? 'es' : 'en'

let data = null
const $ = (sel, root = document) => root.querySelector(sel)

function relative(iso) {
  const minutes = Math.round((Date.now() - new Date(iso)) / 60000)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  if (minutes < 60) return rtf.format(-minutes, 'minute')
  const hours = Math.round(minutes / 60)
  return hours < 48 ? rtf.format(-hours, 'hour') : rtf.format(-Math.round(hours / 24), 'day')
}

const num = (value, digits = 0) =>
  new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)

function applyStaticText() {
  const t = TEXT[lang]
  document.documentElement.lang = lang
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    if (typeof t[el.dataset.i18n] === 'string') el.textContent = t[el.dataset.i18n]
  })
  document.querySelectorAll('[data-lang]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)))
}

// Trazo: humedad en escala 0–100 % (izquierda) y temperatura en 0–40 °C (derecha).
function drawTrace(svg, readings, th) {
  const W = 600, H = 240, L = 36, R = 36, T = 10, B = 26
  const iw = W - L - R, ih = H - T - B
  const now = Date.now(), start = now - HISTORY_HOURS * 3600e3
  const x = (iso) => L + ((new Date(iso) - start) / (now - start)) * iw
  const yH = (v) => T + ih - (v / 100) * ih
  const yT = (v) => T + ih - (v / 40) * ih
  const t = TEXT[lang]

  let grid = ''
  for (let i = 0; i <= 10; i++) {
    const y = T + (ih / 10) * i
    grid += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" class="${i % 5 ? '' : 'major'}" />`
  }
  for (let i = 0; i <= 8; i++) {
    const xx = L + (iw / 8) * i
    grid += `<line y1="${T}" y2="${T + ih}" x1="${xx}" x2="${xx}" class="${i % 4 ? '' : 'major'}" />`
  }

  const band = `<rect class="band" x="${L}" width="${iw}" y="${yH(th.humidity_max)}" height="${yH(th.humidity_min) - yH(th.humidity_max)}" />`
  const axis = `
    <text x="${L - 8}" y="${yH(100) + 4}" text-anchor="end">100%</text>
    <text x="${L - 8}" y="${yH(50) + 4}" text-anchor="end">50</text>
    <text x="${L - 8}" y="${yH(0) + 4}" text-anchor="end">0</text>
    <text x="${W - R + 8}" y="${yT(40) + 4}">40°</text>
    <text x="${W - R + 8}" y="${yT(20) + 4}">20°</text>
    <text x="${W - R + 8}" y="${yT(0) + 4}">0°</text>
    <text x="${L}" y="${H - 6}">${t.hoursAgo(24)}</text>
    <text x="${L + iw / 2}" y="${H - 6}" text-anchor="middle">${t.hoursAgo(12)}</text>
    <text x="${W - R}" y="${H - 6}" text-anchor="end">${t.now}</text>`

  let lines = ''
  if (readings.length >= 2) {
    const path = (y, key) => readings.map((r, i) => `${i ? 'L' : 'M'}${x(r.recorded_at).toFixed(1)},${y(r[key]).toFixed(1)}`).join(' ')
    const last = readings.at(-1)
    lines = `
      <path class="temp" d="${path(yT, 'temperature')}" />
      <path class="hum" d="${path(yH, 'humidity')}" />
      <circle class="dot-temp" r="3" cx="${x(last.recorded_at)}" cy="${yT(last.temperature)}" />
      <circle class="dot-hum" r="3.5" cx="${x(last.recorded_at)}" cy="${yH(last.humidity)}" />`
  } else {
    lines = `<text class="empty" x="${L + iw / 2}" y="${T + ih / 2}" text-anchor="middle">${t.waiting}</text>`
  }

  svg.innerHTML = `<g class="grid">${grid}</g>${band}${lines}${axis}`
  svg.setAttribute('aria-label', `${t.humidity} / ${t.temperature}: ${readings.length}`)
}

function composePlate({ plant, readings, advice }, index) {
  const t = TEXT[lang]
  const el = $('#plate').content.firstElementChild.cloneNode(true)
  const last = plant.last_reading
  const th = plant.thresholds
  const status = advice?.status ?? 'none'

  el.querySelectorAll('[data-i18n]').forEach((n) => { n.textContent = t[n.dataset.i18n] })
  $('.plate__number', el).textContent = t.plate(ROMAN[index] ?? index + 1)
  $('.plate__species', el).textContent = plant.species
  $('.plate__name', el).textContent = `“${plant.name}”`

  $('.plate__stamp', el).dataset.status = status
  $('.plate__stamp', el).textContent = t.stamp[status]

  $('.v-humidity', el).textContent = last ? `${num(last.humidity)} %` : '—'
  $('.v-temperature', el).textContent = last ? `${num(last.temperature, 1)} °C` : '—'
  $('.v-hrange', el).textContent = `${num(th.humidity_min)}–${num(th.humidity_max)} %`
  $('.v-trange', el).textContent = `${num(th.temperature_min)}–${num(th.temperature_max)} °C`
  $('.v-last', el).textContent = last ? relative(last.recorded_at) : '—'
  $('.v-state', el).textContent = t.stamp[status]

  drawTrace($('.trace__svg', el), readings, th)

  $('.note__text', el).textContent = advice ? advice[`tip_${lang}`] : t.noNote
  $('.note__sign', el).textContent = advice
    ? `— ${t.signedBy[advice.source]}, ${new Date(advice.generated_at).toLocaleString(lang, { dateStyle: 'medium', timeStyle: 'short' })}`
    : ''
  return el
}

function render() {
  if (!data) return
  $('#plates').replaceChildren(...data.map(composePlate))
  const latest = data.map((d) => d.plant.last_reading?.recorded_at).filter(Boolean).sort().at(-1)
  $('#updated').textContent = latest ? TEXT[lang].updated(relative(latest)) : '—'
}

async function load() {
  try {
    const res = await fetch('/api/plants')
    if (!res.ok) throw new Error(res.status)
    const plants = await res.json()
    data = await Promise.all(plants.map((p) => fetch(`/api/plants/${p.id}`).then((r) => r.json())))
    render()
  } catch {
    if (!data) $('#plates').innerHTML = `<p class="placeholder">${TEXT[lang].error}</p>`
  }
}

document.querySelectorAll('[data-lang]').forEach((button) => {
  button.addEventListener('click', () => {
    lang = button.dataset.lang
    try { localStorage.setItem('plantia-lang', lang) } catch { /* sin almacenamiento */ }
    applyStaticText()
    render()
  })
})

applyStaticText()
load()
setInterval(load, REFRESH_MS)
