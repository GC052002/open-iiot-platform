/**
 * App raíz del editor HMI.
 *
 * F3.0: conexión al backend por WS/REST (barra de conexión + tabla en vivo).
 * F3.1: editor de canvas — paleta arrastrable (izquierda), lienzo editable
 * (centro) e inspector de propiedades del nodo seleccionado (derecha).
 */

import { ConnectionBar } from "./components/ConnectionBar";
import { LoginBar } from "./components/LoginBar";
import { TagTable } from "./components/TagTable";
import { FlowCanvas } from "./components/FlowCanvas";
import { Palette } from "./components/Palette";
import { Inspector } from "./components/Inspector";
import { useProjectStore } from "./store/projectStore";
import "./App.css";

function EditorToolbar() {
  const name = useProjectStore((s) => s.meta.name);
  const setMeta = useProjectStore((s) => s.setMeta);
  const nodeCount = useProjectStore((s) => s.nodes.length);
  const edgeCount = useProjectStore((s) => s.edges.length);
  return (
    <div className="editor-toolbar">
      <label>
        Diseño
        <input value={name} size={18} onChange={(e) => setMeta({ name: e.target.value })} />
      </label>
      <span className="conn-note">
        {nodeCount} nodos · {edgeCount} conexiones
      </span>
    </div>
  );
}

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
          <div className="side-tags">
            <div className="side-title">Tags en vivo</div>
            <TagTable />
          </div>
        </aside>
        <main className="col-center">
          <EditorToolbar />
          <FlowCanvas />
        </main>
        <aside className="col-right">
          <Inspector />
        </aside>
      </div>
    </div>
  );
}
