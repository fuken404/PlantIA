// Panel de PlantIA: lee la API y dibuja una tarjeta por planta.
const REFRESH_MS = 60_000

const TEXT = {
  es: {
    title: 'Mis plantas, en tiempo real',
    lead: 'Un sensor mide la humedad del suelo y la temperatura; la API las guarda en Firestore y Gemini sugiere qué hacer.',
    loading: 'Cargando lecturas…',
    error: 'No se pudieron cargar las lecturas. Intenta de nuevo en un momento.',
    api: 'API', humidity: 'Humedad del suelo', temperature: 'Temperatura', last24: 'últimas 24 h',
    ideal: (a, b, u) => `Ideal: ${a}–${b}${u}`,
    noData: 'Sin lecturas todavía', noAdvice: 'El consejo aparecerá con la primera lectura.',
    status: { healthy: 'Saludable', attention: 'Requiere atención', critical: 'Crítico', none: 'Sin datos' },
    by: { gemini: 'Consejo de Gemini', rules: 'Consejo por reglas' },
    updated: 'actualizado',
    howTitle: 'Cómo funciona',
    step1: 'Sensor', step1d: 'ESP32 o simulador cada 30 min', step2d: 'valida y guarda la lectura',
    step3d: 'historial por planta', step4d: 'consejo de cuidado (con respaldo por reglas)',
    footer: 'Hecho por', lang: 'EN', langLabel: 'Switch to English',
  },
  en: {
    title: 'My plants, in real time',
    lead: 'A sensor measures soil moisture and temperature; the API stores them in Firestore and Gemini suggests what to do.',
    loading: 'Loading readings…',
    error: 'Could not load the readings. Please try again shortly.',
    api: 'API', humidity: 'Soil moisture', temperature: 'Temperature', last24: 'last 24 h',
    ideal: (a, b, u) => `Ideal: ${a}–${b}${u}`,
    noData: 'No readings yet', noAdvice: 'Advice will appear with the first reading.',
    status: { healthy: 'Healthy', attention: 'Needs attention', critical: 'Critical', none: 'No data' },
    by: { gemini: 'Advice by Gemini', rules: 'Rule-based advice' },
    updated: 'updated',
    howTitle: 'How it works',
    step1: 'Sensor', step1d: 'ESP32 or simulator every 30 min', step2d: 'validates and stores the reading',
    step3d: 'per-plant history', step4d: 'care advice (with rule-based fallback)',
    footer: 'Built by', lang: 'ES', langLabel: 'Cambiar a español',
  },
}

let lang = localStorage.getItem('plantia-lang') || (navigator.language.startsWith('es') ? 'es' : 'en')
let lastData = null

const $ = (sel, root = document) => root.querySelector(sel)

function applyStaticText() {
  const t = TEXT[lang]
  document.documentElement.lang = lang
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const value = t[el.dataset.i18n]
    if (typeof value === 'string') el.textContent = value
  })
  $('#lang').textContent = t.lang
  $('#lang').setAttribute('aria-label', t.langLabel)
}

function relativeTime(iso) {
  const minutes = Math.round((Date.now() - new Date(iso)) / 60000)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  if (Math.abs(minutes) < 60) return rtf.format(-minutes, 'minute')
  const hours = Math.round(minutes / 60)
  return Math.abs(hours) < 48 ? rtf.format(-hours, 'hour') : rtf.format(-Math.round(hours / 24), 'day')
}

function setRange(metric, value, min, max, scaleMin, scaleMax, unit) {
  const pct = (v) => `${Math.min(100, Math.max(0, ((v - scaleMin) / (scaleMax - scaleMin)) * 100))}%`
  $('.range__ideal', metric).style.left = pct(min)
  $('.range__ideal', metric).style.width = `calc(${pct(max)} - ${pct(min)})`
  $('.range__mark', metric).style.display = value == null ? 'none' : ''
  if (value != null) $('.range__mark', metric).style.left = pct(value)
  $('.metric__ideal', metric).textContent = TEXT[lang].ideal(min, max, unit)
}

function linePath(values, min, max) {
  if (values.length < 2) return ''
  const step = 300 / (values.length - 1)
  return values
    .map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(76 - ((v - min) / (max - min || 1)) * 72).toFixed(1)}`)
    .join(' ')
}

function renderChart(svg, readings) {
  const hum = readings.map((r) => r.humidity)
  const temp = readings.map((r) => r.temperature)
  svg.innerHTML = readings.length < 2 ? '' : `
    <path class="line line--hum" d="${linePath(hum, 0, 100)}" />
    <path class="line line--temp" d="${linePath(temp, Math.min(...temp) - 2, Math.max(...temp) + 2)}" />`
  svg.setAttribute('aria-label', `${TEXT[lang].last24}: ${readings.length}`)
}

function renderCard({ plant, readings, advice }) {
  const t = TEXT[lang]
  const card = $('#plant-card').content.firstElementChild.cloneNode(true)
  const last = plant.last_reading
  const th = plant.thresholds

  $('.card__name', card).textContent = plant.name
  $('.card__species', card).textContent = plant.species
  const status = advice?.status ?? 'none'
  $('.badge', card).dataset.status = status
  $('.badge', card).textContent = t.status[status]

  const hum = $('[data-kind="humidity"]', card)
  const temp = $('[data-kind="temperature"]', card)
  $('.metric__value', hum).textContent = last ? `${Math.round(last.humidity)}%` : '—'
  $('.metric__value', temp).textContent = last ? `${last.temperature.toFixed(1)}°C` : '—'
  setRange(hum, last?.humidity, th.humidity_min, th.humidity_max, 0, 100, '%')
  setRange(temp, last?.temperature, th.temperature_min, th.temperature_max, 0, 40, '°C')

  renderChart($('.chart__svg', card), readings)
  card.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t[el.dataset.i18n] })

  $('.advice__tip', card).textContent = advice ? advice[`tip_${lang}`] : (last ? '' : t.noData)
  $('.advice__meta', card).textContent = advice
    ? `${t.by[advice.source]} · ${t.updated} ${relativeTime(last.recorded_at)}`
    : t.noAdvice
  return card
}

function render() {
  const box = $('#plants')
  if (!lastData) return
  box.replaceChildren(...lastData.map(renderCard))
}

async function load() {
  try {
    const plants = await fetch('/api/plants').then((r) => { if (!r.ok) throw r; return r.json() })
    lastData = await Promise.all(plants.map((p) => fetch(`/api/plants/${p.id}`).then((r) => r.json())))
    render()
  } catch {
    if (!lastData) $('#plants').innerHTML = `<p class="muted">${TEXT[lang].error}</p>`
  }
}

$('#lang').addEventListener('click', () => {
  lang = lang === 'es' ? 'en' : 'es'
  try { localStorage.setItem('plantia-lang', lang) } catch { /* sin almacenamiento */ }
  applyStaticText()
  render()
})

applyStaticText()
load()
setInterval(load, REFRESH_MS)
