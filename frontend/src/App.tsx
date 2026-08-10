/**
 * App raíz.
 *
 * F3: editor HMI (paleta / lienzo / inspector) con tabla en vivo.
 * F4.2: **dos modos** decididos por rol (Rev D1 §8.2.4):
 *   - *Authoring* (admin/engineer): editor completo + gestión de usuarios/proyectos.
 *   - *Runtime* (client/operator/viewer): visor HMI solo-lectura (`views/Viewer`).
 * El modo se puede forzar por hash (`#/edit` vs `#/view`) para previsualizar el visor.
 * La seguridad real es del backend; aquí solo se decide qué se pinta.
 */

import { useEffect, useState } from "react";
import { ConnectionBar } from "./components/ConnectionBar";
import { LoginBar } from "./components/LoginBar";
import { TagTable } from "./components/TagTable";
import { TagsPanel } from "./components/TagsPanel";
import { FlowCanvas } from "./components/FlowCanvas";
import { Palette } from "./components/Palette";
import { Inspector } from "./components/Inspector";
import { ProjectToolbar } from "./components/ProjectToolbar";
import { ProjectsPanel } from "./components/ProjectsPanel";
import { UsersPanel } from "./components/UsersPanel";
import { ViewerRoute } from "./views/ViewerRoute";
import { useSessionStore } from "./store/sessionStore";
import "./App.css";

function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export default function App() {
  const role = useSessionStore((s) => s.role);
  const hash = useHashRoute();

  const canEdit = role === null || role === "admin" || role === "engineer";
  const viewerMode = hash === "#/view" || (hash !== "#/edit" && !canEdit);

  return (
    <div className="app">
      <header className="app-header">
        <h1>⚙️ IIoT Platform — {viewerMode ? "Visor HMI" : "Editor HMI"}</h1>
        <span className="spacer" />
        {canEdit && (
          <a className="mode-link" href={viewerMode ? "#/edit" : "#/view"}>
            {viewerMode ? "Ir al editor" : "Ver como cliente"}
          </a>
        )}
        <LoginBar />
      </header>
      {viewerMode ? <ViewerRoute /> : <EditorLayout isAdmin={role === "admin"} />}
    </div>
  );
}

function EditorLayout({ isAdmin }: { isAdmin: boolean }) {
  return (
    <>
      <ConnectionBar />
      <div className="app-body">
        <aside className="col-left">
          <Palette />
          <details className="side-section" open>
            <summary className="side-title">Proyectos</summary>
            <ProjectsPanel />
          </details>
          {isAdmin && (
            <details className="side-section">
              <summary className="side-title">Usuarios</summary>
              <UsersPanel />
            </details>
          )}
          <details className="side-section">
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
    </>
  );
}
