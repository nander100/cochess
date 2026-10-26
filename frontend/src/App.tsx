export default function App() {
  return (
    <main>
      <h1>CoChess</h1>
      <p>Engine isolation: {globalThis.crossOriginIsolated ? 'enabled' : 'disabled'}</p>
    </main>
  )
}
