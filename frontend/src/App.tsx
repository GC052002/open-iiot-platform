/**
 * App raíz del editor HMI.
 *
 * F3.0: conexión al backend por WS/REST (barra de conexión + tabla en vivo).
 * F3.1: editor de canvas — paleta (izq), lienzo editable (centro), inspector (der).
 * F3.2: widgets con data-binding en vivo por tag_id.
 * F3.3: editor de Tags del proyecto + import/export + enviar el diseño al backend.
 */

import { ConnectionBar } from "./components/ConnectionBar";
import { LoginBar } from "./components/LoginBar";
import { TagTable } from "./components/TagTable";
import { TagsPanel } from "./components/TagsPanel";
import { FlowCanvas } from "./components/FlowCanvas";
import { Palette } from "./components/Palette";
import { Inspector } from "./components/Inspector";
import { ProjectToolbar } from "./components/ProjectToolbar";
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
        <aside className="col-left">
          <Palette />
          <details className="side-section" open>
            <summary className="side-title">Tags del proyecto</summary>
            <TagsPanel />
          </details>
          <details className="side-section">
            <summary className="side-title">Tags en vivo</summary>
            <TagTable />
          </details>
        </aside>
        <main className="col-center">
          <ProjectToolbar />
          <FlowCanvas />
        </main>
        <aside className="col-right">
          <Inspector />
        </aside>
      </div>
    </div>
  );
}
