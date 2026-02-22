export function App() {
  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Last Strawberry</p>
          <h1>Greenfield Web Client</h1>
        </div>
        <div className="chip">React + Vite</div>
      </header>

      <section className="grid">
        <article className="panel panel-large">
          <h2>Spielansicht (MVP)</h2>
          <p>
            Hier entsteht der Turn-Loop: Narrativ, Eingabe, Verlauf, Charaktersheet und Inventar.
          </p>
          <div className="placeholder">
            <p>Narrativ / Journal / Turn Input</p>
          </div>
        </article>

        <article className="panel">
          <h2>Charaktersheet</h2>
          <ul>
            <li>Attribute</li>
            <li>Ressourcen</li>
            <li>Status</li>
            <li>Ort</li>
          </ul>
        </article>

        <article className="panel">
          <h2>Inventar</h2>
          <ul>
            <li>Inspect</li>
            <li>Use</li>
            <li>Equip / Consume</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
