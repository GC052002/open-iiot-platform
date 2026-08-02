/**
 * App raíz del editor HMI (F3.0).
 *
 * Layout: cabecera (login opcional + barra de conexión) y cuerpo dividido en el
 * panel de tags en vivo (izquierda) y el canvas React Flow (derecha). En F3.1+ el
 * canvas gana paleta e inspector; aquí es el esqueleto que prueba la conexión
 * end-to-end contra el backend por WS/REST.
 */

import { ConnectionBar } from "./components/ConnectionBar";
import { LoginBar } from "./components/LoginBar";
import { TagTable } from "./components/TagTable";
import { FlowCanvas } from "./components/FlowCanvas";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>⚙️ IIoT Platform — Editor HMI</h1>
        <span className="spacer" />
        <LoginBar />
      </header>
      <ConnectionBar />
      <div className="app-body">
        <aside className="app-side">
          <TagTable />
        </aside>
        <main className="app-canvas">
          <FlowCanvas />
        </main>
      </div>
    </div>
  );
}
